"""Tests for Adjusted Gross Income (AGI) variable.

Per 26 USC Section 62, AGI = Gross Income - Above-the-line deductions.
This simplified implementation sums income sources without deductions.
"""

import json
import subprocess

import pytest
import numpy as np

from src.rac.dsl_parser import parse_dsl, parse_file
from src.rac.js_generator import generate_js

try:
    from src.rac.py_generator import generate_python
except ImportError:
    generate_python = None


class TestAGIParsing:
    """Test that AGI DSL file parses correctly.

    NOTE: Statute files live in cosilico-us, NOT cosilico-engine.
    These tests skip if the file isn't found.
    """

    @pytest.fixture
    def agi_path(self):
        """Get path to AGI file in cosilico-us."""
        from pathlib import Path
        # Statute files are in cosilico-us, not cosilico-engine
        candidates = [
            Path.home() / "CosilicoAI" / "cosilico-us" / "26/62/a/adjusted_gross_income.rac",
            Path(__file__).parents[2] / "cosilico-us" / "26/62/a/adjusted_gross_income.rac",
        ]
        for path in candidates:
            if path.exists():
                return path
        pytest.skip("AGI file not found in cosilico-us - statute files live there, not in cosilico-engine")

    def test_agi_file_parses(self, agi_path):
        """AGI cosilico file parses without errors."""
        module = parse_file(str(agi_path))

        assert module is not None
        assert len(module.variables) == 1
        assert module.variables[0].name == "adjusted_gross_income"

    def test_agi_variable_metadata(self, agi_path):
        """AGI variable has correct metadata."""
        module = parse_file(str(agi_path))
        var = module.variables[0]

        assert var.entity == "TaxUnit"
        assert var.period == "Year"
        assert var.dtype == "Money"
        assert var.label == "Adjusted Gross Income"
        assert "26 USC 62" in var.reference

    def test_agi_has_formula(self, agi_path):
        """AGI variable has a formula defined."""
        module = parse_file(str(agi_path))
        var = module.variables[0]

        assert var.formula is not None
        assert var.formula.return_expr is not None

    def test_agi_references(self, agi_path):
        """AGI module has correct references."""
        module = parse_file(str(agi_path))

        assert module.references is not None
        aliases = [r.alias for r in module.references.references]

        # Check expected income sources are referenced
        assert "wages" in aliases
        assert "interest_income" in aliases
        assert "dividend_income" in aliases
        assert "capital_gains" in aliases
        assert "self_employment_income" in aliases


class TestAGICodeGeneration:
    """Test code generation for AGI."""

    @pytest.fixture
    def agi_dsl(self) -> str:
        """Simplified AGI DSL for testing code generation."""
        return """
variable adjusted_gross_income:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let employee_income = wages + salaries + tips
    let investment_income = interest_income + dividend_income + capital_gains
    return employee_income + self_employment_income + investment_income + other_income

"""

    def test_js_generation(self, agi_dsl: str):
        """AGI generates valid JavaScript."""
        module = parse_dsl(agi_dsl)
        js = generate_js(module)

        assert "function adjusted_gross_income" in js
        assert "inputs.wages" in js
        assert "inputs.salaries" in js
        assert "inputs.tips" in js
        assert "inputs.interest_income" in js

    @pytest.mark.skipif(generate_python is None, reason="Python generator not implemented")
    def test_python_generation(self, agi_dsl: str):
        """AGI generates valid Python."""
        module = parse_dsl(agi_dsl)
        py = generate_python(module)

        assert "def adjusted_gross_income" in py
        assert "wages" in py
        assert "salaries" in py


class TestAGICalculation:
    """Test AGI calculation produces correct results."""

    @pytest.fixture
    def agi_dsl(self) -> str:
        """Simplified AGI DSL for testing calculations."""
        return """
variable adjusted_gross_income:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let employee_income = wages + salaries + tips
    let investment_income = interest_income + dividend_income + capital_gains
    return employee_income + self_employment_income + investment_income + other_income

"""

    def _execute_js(self, js_code: str, inputs: dict) -> float:
        """Execute JavaScript code and return result."""
        wrapper = f"""
const inputs = {json.dumps(inputs)};
const params = {{}};

{js_code}

console.log(adjusted_gross_income(inputs, params));
"""
        result = subprocess.run(
            ["node", "-e", wrapper],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(f"JS execution failed: {result.stderr}")
        return float(result.stdout.strip())

    def test_agi_wages_only(self, agi_dsl: str):
        """AGI with only wage income."""
        module = parse_dsl(agi_dsl)
        js = generate_js(module)

        inputs = {
            "wages": 50000,
            "salaries": 0,
            "tips": 0,
            "interest_income": 0,
            "dividend_income": 0,
            "capital_gains": 0,
            "self_employment_income": 0,
            "other_income": 0,
        }
        result = self._execute_js(js, inputs)
        assert result == pytest.approx(50000.0)

    def test_agi_all_income_types(self, agi_dsl: str):
        """AGI with all income types."""
        module = parse_dsl(agi_dsl)
        js = generate_js(module)

        inputs = {
            "wages": 60000,
            "salaries": 20000,
            "tips": 5000,
            "interest_income": 1500,
            "dividend_income": 2000,
            "capital_gains": 5000,
            "self_employment_income": 15000,
            "other_income": 500,
        }
        result = self._execute_js(js, inputs)

        # Expected: 60000 + 20000 + 5000 + 1500 + 2000 + 5000 + 15000 + 500 = 109000
        expected = 60000 + 20000 + 5000 + 1500 + 2000 + 5000 + 15000 + 500
        assert result == pytest.approx(expected)

    def test_agi_investment_income_only(self, agi_dsl: str):
        """AGI with only investment income (no wages)."""
        module = parse_dsl(agi_dsl)
        js = generate_js(module)

        inputs = {
            "wages": 0,
            "salaries": 0,
            "tips": 0,
            "interest_income": 10000,
            "dividend_income": 5000,
            "capital_gains": 20000,
            "self_employment_income": 0,
            "other_income": 0,
        }
        result = self._execute_js(js, inputs)
        assert result == pytest.approx(35000.0)

    def test_agi_zero_income(self, agi_dsl: str):
        """AGI with zero income."""
        module = parse_dsl(agi_dsl)
        js = generate_js(module)

        inputs = {
            "wages": 0,
            "salaries": 0,
            "tips": 0,
            "interest_income": 0,
            "dividend_income": 0,
            "capital_gains": 0,
            "self_employment_income": 0,
            "other_income": 0,
        }
        result = self._execute_js(js, inputs)
        assert result == pytest.approx(0.0)

    def test_agi_self_employment_income(self, agi_dsl: str):
        """AGI with self-employment income."""
        module = parse_dsl(agi_dsl)
        js = generate_js(module)

        inputs = {
            "wages": 30000,
            "salaries": 0,
            "tips": 0,
            "interest_income": 0,
            "dividend_income": 0,
            "capital_gains": 0,
            "self_employment_income": 40000,
            "other_income": 0,
        }
        result = self._execute_js(js, inputs)
        assert result == pytest.approx(70000.0)


@pytest.mark.skipif(generate_python is None, reason="Python generator not implemented")
class TestAGIPythonExecution:
    """Test AGI calculation in Python (vectorized)."""

    @pytest.fixture
    def agi_dsl(self) -> str:
        """Simplified AGI DSL for testing calculations."""
        return """
variable adjusted_gross_income:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let employee_income = wages + salaries + tips
    let investment_income = interest_income + dividend_income + capital_gains
    return employee_income + self_employment_income + investment_income + other_income

"""

    def _execute_python(self, py_code: str, inputs: dict) -> np.ndarray:
        """Execute Python code and return result."""
        namespace = {"np": np, "inputs": inputs, "params": {}}
        exec(py_code, namespace)
        return namespace["adjusted_gross_income"](inputs, {})

    def test_agi_vectorized(self, agi_dsl: str):
        """AGI calculation works with numpy arrays."""
        module = parse_dsl(agi_dsl)
        py = generate_python(module)

        inputs = {
            "wages": np.array([50000, 60000, 0, 30000]),
            "salaries": np.array([0, 20000, 0, 0]),
            "tips": np.array([0, 5000, 0, 0]),
            "interest_income": np.array([0, 1500, 10000, 0]),
            "dividend_income": np.array([0, 2000, 5000, 0]),
            "capital_gains": np.array([0, 5000, 20000, 0]),
            "self_employment_income": np.array([0, 15000, 0, 40000]),
            "other_income": np.array([0, 500, 0, 0]),
        }

        result = self._execute_python(py, inputs)

        expected = np.array([50000, 109000, 35000, 70000])
        np.testing.assert_array_almost_equal(result, expected)


class TestAGICrossCompilation:
    """Test AGI consistency across compilation targets."""

    @pytest.fixture
    def agi_dsl(self) -> str:
        """Simplified AGI DSL for testing."""
        return """
variable adjusted_gross_income:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let employee_income = wages + salaries + tips
    let investment_income = interest_income + dividend_income + capital_gains
    return employee_income + self_employment_income + investment_income + other_income

"""

    def _execute_js(self, js_code: str, inputs: dict) -> float:
        """Execute JavaScript code and return result."""
        wrapper = f"""
const inputs = {json.dumps(inputs)};
const params = {{}};

{js_code}

console.log(adjusted_gross_income(inputs, params));
"""
        result = subprocess.run(
            ["node", "-e", wrapper],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(f"JS execution failed: {result.stderr}")
        return float(result.stdout.strip())

    def _execute_python(self, py_code: str, inputs: dict) -> float:
        """Execute Python code and return result."""
        np_inputs = {k: np.array([v]) for k, v in inputs.items()}
        namespace = {"np": np, "inputs": np_inputs, "params": {}}
        exec(py_code, namespace)
        result = namespace["adjusted_gross_income"](np_inputs, {})
        return float(result[0])

    @pytest.mark.skipif(generate_python is None, reason="Python generator not implemented")
    def test_js_python_consistency(self, agi_dsl: str):
        """JS and Python produce identical AGI results."""
        module = parse_dsl(agi_dsl)
        js = generate_js(module)
        py = generate_python(module)

        test_cases = [
            {
                "wages": 50000,
                "salaries": 0,
                "tips": 0,
                "interest_income": 0,
                "dividend_income": 0,
                "capital_gains": 0,
                "self_employment_income": 0,
                "other_income": 0,
            },
            {
                "wages": 60000,
                "salaries": 20000,
                "tips": 5000,
                "interest_income": 1500,
                "dividend_income": 2000,
                "capital_gains": 5000,
                "self_employment_income": 15000,
                "other_income": 500,
            },
            {
                "wages": 0,
                "salaries": 0,
                "tips": 0,
                "interest_income": 0,
                "dividend_income": 0,
                "capital_gains": 0,
                "self_employment_income": 0,
                "other_income": 0,
            },
        ]

        for inputs in test_cases:
            js_result = self._execute_js(js, inputs)
            py_result = self._execute_python(py, inputs)
            assert js_result == pytest.approx(py_result, rel=1e-9), \
                f"JS={js_result} != Python={py_result} for inputs {inputs}"
