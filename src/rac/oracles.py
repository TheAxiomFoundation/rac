"""Oracle implementations for validating generated code."""

from typing import Any, Protocol


class Oracle(Protocol):
    """Protocol for oracle implementations."""

    def evaluate(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Given inputs, return computed values."""
        ...


class PolicyEngineOracle:
    """Oracle using PolicyEngine-US for validation.

    Accepts Cosilico-style input variable names and maps them to
    PolicyEngine variables. Returns a comprehensive set of tax
    variables for validation.
    """

    # Map Cosilico input names to PolicyEngine variable names
    INPUT_MAPPING = {
        # Employment income
        "wages": "employment_income",
        "salaries": "employment_income",  # Combined with wages
        "tips": "employment_income",  # Combined with wages
        "employment_income": "employment_income",
        "earned_income": "employment_income",
        # Self-employment
        "self_employment_income": "self_employment_income",
        # Investment income
        "interest_income": "taxable_interest_income",
        "dividend_income": "qualified_dividend_income",
        "capital_gains": "long_term_capital_gains",
        "short_term_capital_gains": "short_term_capital_gains",
        "long_term_capital_gains": "long_term_capital_gains",
        # Other income
        "other_income": "miscellaneous_income",
        "unemployment_in_agi": "unemployment_compensation",
        "social_security_benefits": "social_security",
        "pension_income": "pension_income",
        # Demographics
        "age": "age",
        "n_children": None,  # Special handling
        "filing_status": None,  # Special handling
    }

    # Variables to calculate and return
    OUTPUT_VARIABLES = [
        # Core tax variables
        "adjusted_gross_income",
        "taxable_income",
        "income_tax_before_credits",
        "income_tax",
        # Credits
        "eitc",
        "ctc",
        "child_and_dependent_care_credit",
        "savers_credit",
        "american_opportunity_credit",
        "lifetime_learning_credit",
        # Deductions
        "standard_deduction",
        "itemized_taxable_income_deductions",
        "salt_deduction",
        # Payroll taxes
        "employee_social_security_tax",
        "employee_medicare_tax",
        "self_employment_tax",
        # Other
        "earned_income",
        "net_investment_income_tax",
    ]

    def __init__(self, year: int = 2024, output_variables: list[str] | None = None):
        self.year = year
        self._simulation_class = None
        self.output_variables = output_variables or self.OUTPUT_VARIABLES

    @property
    def Simulation(self):
        """Lazy import of PolicyEngine."""
        if self._simulation_class is None:
            from policyengine_us import Simulation
            self._simulation_class = Simulation
        return self._simulation_class

    def evaluate(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Evaluate inputs using PolicyEngine.

        Args:
            inputs: Dictionary with Cosilico-style variable names like:
                - wages: float
                - self_employment_income: float
                - interest_income: float
                - dividend_income: float
                - capital_gains: float
                - filing_status: str ("SINGLE", "JOINT", etc.)
                - n_children: int
                - age: int (optional)

        Returns:
            Dictionary with computed values including:
                - adjusted_gross_income
                - taxable_income
                - income_tax
                - eitc
                - ctc
                - etc.
        """
        situation = self._build_situation(inputs)
        sim = self.Simulation(situation=situation)

        results = {}
        for var in self.output_variables:
            try:
                value = sim.calculate(var, self.year)
                # Convert numpy to Python types
                if hasattr(value, "item"):
                    value = value.item()
                elif hasattr(value, "__iter__") and not isinstance(value, str):
                    value = float(value[0]) if len(value) > 0 else 0.0
                results[var] = float(value)
            except Exception as e:
                results[var] = 0.0
                results[f"{var}_error"] = str(e)

        return results

    def _build_situation(self, inputs: dict[str, Any]) -> dict:
        """Convert Cosilico inputs to PolicyEngine situation format."""
        # Extract demographics
        filing_status = inputs.get("filing_status", "SINGLE")
        n_children = int(inputs.get("n_children", 0))
        age = int(inputs.get("age", 30))

        # Aggregate income by PolicyEngine variable
        pe_income = {}
        for cosilico_var, pe_var in self.INPUT_MAPPING.items():
            if pe_var is None:
                continue  # Skip special handling vars
            value = inputs.get(cosilico_var, 0)
            if value:
                if pe_var in pe_income:
                    pe_income[pe_var] += float(value)
                else:
                    pe_income[pe_var] = float(value)

        # Build primary adult
        people = {
            "adult": {
                "age": {self.year: age},
            }
        }

        # Add income variables to adult
        for pe_var, value in pe_income.items():
            if value > 0:
                people["adult"][pe_var] = {self.year: value}

        # Add spouse for joint filing
        if filing_status == "JOINT":
            people["spouse"] = {
                "age": {self.year: age - 2},  # Slightly younger spouse
            }

        # Add children
        children_ids = []
        for i in range(n_children):
            child_id = f"child_{i}"
            children_ids.append(child_id)
            people[child_id] = {
                "age": {self.year: 5 + i * 2},  # Varying ages
                "is_tax_unit_dependent": {self.year: True},
            }

        # Build tax unit
        tax_unit_members = ["adult"]
        if filing_status == "JOINT":
            tax_unit_members.append("spouse")
        tax_unit_members.extend(children_ids)

        # Map filing status to PolicyEngine format
        pe_filing_status = {
            "SINGLE": "SINGLE",
            "JOINT": "JOINT",
            "MARRIED_FILING_JOINTLY": "JOINT",
            "MFJ": "JOINT",
            "MARRIED_FILING_SEPARATELY": "SEPARATE",
            "MFS": "SEPARATE",
            "HEAD_OF_HOUSEHOLD": "HEAD_OF_HOUSEHOLD",
            "HOH": "HEAD_OF_HOUSEHOLD",
            "WIDOW": "SURVIVING_SPOUSE",
            "SURVIVING_SPOUSE": "SURVIVING_SPOUSE",
        }.get(filing_status, "SINGLE")

        situation = {
            "people": people,
            "tax_units": {
                "tax_unit": {
                    "members": tax_unit_members,
                    "filing_status": {self.year: pe_filing_status},
                }
            },
            "families": {"family": {"members": tax_unit_members}},
            "spm_units": {"spm_unit": {"members": tax_unit_members}},
            "households": {
                "household": {
                    "members": tax_unit_members,
                    "state_code": {self.year: "TX"},  # No state tax
                }
            },
        }

        return situation


class MockOracle:
    """Mock oracle for testing without PolicyEngine."""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None):
        self.responses = responses or {}

    def evaluate(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Return mock responses based on inputs."""
        # Create a key from inputs
        key = str(sorted(inputs.items()))
        if key in self.responses:
            return self.responses[key]

        # Simple approximations for testing
        wages = inputs.get("wages", 0) + inputs.get("salaries", 0) + inputs.get("tips", 0)
        se_income = inputs.get("self_employment_income", 0)
        interest = inputs.get("interest_income", 0)
        dividends = inputs.get("dividend_income", 0)
        cap_gains = inputs.get("capital_gains", 0)
        other = inputs.get("other_income", 0)

        # Simple AGI
        agi = wages + se_income + interest + dividends + cap_gains + other

        # Simple standard deduction
        filing_status = inputs.get("filing_status", "SINGLE")
        std_deduction = 14600 if filing_status == "SINGLE" else 29200

        # Simple taxable income
        taxable = max(0, agi - std_deduction)

        return {
            "adjusted_gross_income": agi,
            "taxable_income": taxable,
            "standard_deduction": std_deduction,
            "income_tax": 0,  # Simplified
            "eitc": 0,
            "ctc": 0,
            "earned_income": wages + se_income,
        }
