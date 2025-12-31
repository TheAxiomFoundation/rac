"""Reward function for policy encoding validation.

This module provides the reward signal for RL-based policy encoding agents.
It compares encoded parameters against multiple oracles (PolicyEngine, TAXSIM, IRS)
and returns a scalar reward indicating accuracy.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml


@dataclass
class RewardResult:
    """Result from reward function evaluation."""

    reward: float  # 0-1 scalar reward
    accuracy: float  # Percentage of test cases passed
    oracle_results: dict[str, list[float]]  # Results by oracle
    mean_error: float  # Mean absolute error on incorrect cases
    max_error: float  # Maximum absolute error
    n_cases: int  # Total test cases
    n_passed: int  # Number of cases passing all oracles
    n_failed: int  # Number of cases failing any oracle
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "reward": self.reward,
            "accuracy": self.accuracy,
            "mean_error": self.mean_error,
            "max_error": self.max_error,
            "n_cases": self.n_cases,
            "n_passed": self.n_passed,
            "n_failed": self.n_failed,
            "oracle_results": self.oracle_results,
            "diagnostics": self.diagnostics,
        }


@dataclass
class OracleComparison:
    """Comparison of a single test case against oracles."""

    test_case_id: str
    expected: float
    actual: float
    oracle_values: dict[str, float]  # Oracle name -> calculated value
    match: bool
    relative_error: float
    absolute_error: float
    consensus: bool  # Do all oracles agree?


class Oracle(ABC):
    """Base class for validation oracles."""

    name: str
    priority: int  # Lower = higher priority (1=ground truth, 2=reference, 3=supplementary)

    @abstractmethod
    def calculate(
        self, inputs: dict[str, Any], variable: str, year: int
    ) -> Optional[float]:
        """Calculate the variable value for given inputs.

        Args:
            inputs: Test case inputs (income, filing_status, children, etc.)
            variable: Variable to calculate (e.g., "eitc", "ctc")
            year: Tax year

        Returns:
            Calculated value or None if oracle doesn't support this case
        """
        pass

    @abstractmethod
    def supports(self, variable: str, year: int) -> bool:
        """Check if this oracle supports the variable/year combination."""
        pass


class PolicyEngineOracle(Oracle):
    """Validates against PolicyEngine-US."""

    name = "PolicyEngine"
    priority = 2  # Reference oracle

    def __init__(self):
        """Initialize PolicyEngine oracle."""
        from cosilico_validators.validators.policyengine import (
            PolicyEngineValidator,
        )

        self._validator = PolicyEngineValidator()

    def supports(self, variable: str, year: int) -> bool:
        """Check if PolicyEngine supports this variable."""
        return self._validator.supports_variable(variable)

    def calculate(
        self, inputs: dict[str, Any], variable: str, year: int
    ) -> Optional[float]:
        """Calculate using PolicyEngine."""
        from cosilico_validators.validators.base import TestCase

        test_case = TestCase(
            name=f"pe_test_{variable}",
            inputs=inputs,
            expected={variable: 0},  # Not used for oracle calculation
        )

        result = self._validator.validate(test_case, variable, year)

        if result.success:
            return result.calculated_value
        return None


class TaxsimOracle(Oracle):
    """Validates against TAXSIM (for supported years 1960-2023)."""

    name = "TAXSIM"
    priority = 2  # Reference oracle

    def __init__(self, taxsim_path: Optional[str] = None):
        """Initialize TAXSIM oracle.

        Args:
            taxsim_path: Path to TAXSIM executable (auto-detected if None)
        """
        try:
            from cosilico_validators.validators.taxsim import TaxsimValidator

            self._validator = TaxsimValidator(taxsim_path=taxsim_path)
            self._available = True
        except (ImportError, FileNotFoundError) as e:
            print(f"Warning: TAXSIM not available: {e}")
            self._validator = None
            self._available = False

    def supports(self, variable: str, year: int) -> bool:
        """Check if TAXSIM supports this variable/year."""
        if not self._available:
            return False
        # TAXSIM-35 supports years 1960-2023
        if year < 1960 or year > 2023:
            return False
        return self._validator.supports_variable(variable)

    def calculate(
        self, inputs: dict[str, Any], variable: str, year: int
    ) -> Optional[float]:
        """Calculate using TAXSIM."""
        if not self._available:
            return None

        from cosilico_validators.validators.base import TestCase

        test_case = TestCase(
            name=f"taxsim_test_{variable}",
            inputs=inputs,
            expected={variable: 0},  # Not used for oracle calculation
        )

        result = self._validator.validate(test_case, variable, year)

        if result.success:
            return result.calculated_value
        return None


class IRSTableOracle(Oracle):
    """Validates against IRS official tables and examples.

    This oracle uses test cases from official IRS publications.
    """

    name = "IRS"
    priority = 1  # Ground truth

    def __init__(self, test_cases_path: Optional[str] = None):
        """Initialize IRS table oracle.

        Args:
            test_cases_path: Path to IRS test cases YAML file
        """
        self.test_cases_by_variable: dict[str, list[dict]] = {}

        if test_cases_path:
            with open(test_cases_path) as f:
                data = yaml.safe_load(f)
                for var_name, cases in data.items():
                    self.test_cases_by_variable[var_name] = cases

    def supports(self, variable: str, year: int) -> bool:
        """Check if we have IRS test cases for this variable."""
        return variable.lower() in self.test_cases_by_variable

    def calculate(
        self, inputs: dict[str, Any], variable: str, year: int
    ) -> Optional[float]:
        """Look up expected value from IRS test cases.

        Note: This doesn't "calculate" - it returns the ground truth value
        from official IRS examples that match the inputs.
        """
        if variable.lower() not in self.test_cases_by_variable:
            return None

        # Find matching test case
        for case in self.test_cases_by_variable[variable.lower()]:
            if self._matches_inputs(case.get("inputs", {}), inputs):
                return case.get("expected", {}).get(variable, None)

        return None

    def _matches_inputs(self, case_inputs: dict, test_inputs: dict) -> bool:
        """Check if test inputs match a case's inputs."""
        # For now, require exact match on all keys in case_inputs
        for key, expected_val in case_inputs.items():
            if test_inputs.get(key) != expected_val:
                return False
        return True


class EncodingRewardFunction:
    """Reward function for policy encoding validation.

    Compares encoded parameters against multiple oracles and returns
    a reward signal (0-1) based on accuracy across test cases.
    """

    def __init__(
        self,
        oracles: list[Oracle],
        tolerance_absolute: float = 1.0,  # $1 absolute tolerance
        tolerance_relative: float = 0.01,  # 1% relative tolerance
        partial_credit: bool = True,  # Give partial credit for close answers
    ):
        """Initialize reward function.

        Args:
            oracles: List of validation oracles
            tolerance_absolute: Absolute error tolerance (e.g., $1)
            tolerance_relative: Relative error tolerance (e.g., 0.01 = 1%)
            partial_credit: Whether to give partial credit for near-correct answers
        """
        self.oracles = sorted(oracles, key=lambda o: o.priority)
        self.tolerance_absolute = tolerance_absolute
        self.tolerance_relative = tolerance_relative
        self.partial_credit = partial_credit

    def evaluate(
        self,
        encoded_params: dict[str, Any],
        variable: str,
        test_cases: list[dict[str, Any]],
        year: int = 2024,
    ) -> RewardResult:
        """Evaluate encoded parameters against oracles.

        Args:
            encoded_params: Encoded parameters (typically from YAML)
            variable: Variable being tested (e.g., "eitc", "ctc")
            test_cases: List of test cases with "inputs" and "expected" keys
            year: Tax year

        Returns:
            RewardResult with scalar reward and diagnostics
        """
        if not test_cases:
            return RewardResult(
                reward=0.0,
                accuracy=0.0,
                oracle_results={},
                mean_error=0.0,
                max_error=0.0,
                n_cases=0,
                n_passed=0,
                n_failed=0,
            )

        comparisons: list[OracleComparison] = []
        oracle_results: dict[str, list[float]] = {
            oracle.name: [] for oracle in self.oracles
        }

        # Evaluate each test case
        for i, test_case in enumerate(test_cases):
            inputs = test_case.get("inputs", {})
            expected = test_case.get("expected", {}).get(variable, 0)

            # Get oracle consensus
            oracle_values = {}
            for oracle in self.oracles:
                if oracle.supports(variable, year):
                    value = oracle.calculate(inputs, variable, year)
                    if value is not None:
                        oracle_values[oracle.name] = value
                        oracle_results[oracle.name].append(value)

            # Use highest-priority oracle as ground truth
            if not oracle_values:
                # No oracle available - use expected value from test case
                actual = expected
                consensus = True
            else:
                # Use highest priority oracle (lowest priority number)
                actual = next(iter(oracle_values.values()))
                # Check consensus (all oracles within tolerance of each other)
                consensus = self._check_consensus(list(oracle_values.values()))

            # Calculate match
            match = self._is_match(expected, actual)
            rel_error = self._relative_error(expected, actual)
            abs_error = abs(expected - actual)

            comparisons.append(
                OracleComparison(
                    test_case_id=f"test_{i}",
                    expected=expected,
                    actual=actual,
                    oracle_values=oracle_values,
                    match=match,
                    relative_error=rel_error,
                    absolute_error=abs_error,
                    consensus=consensus,
                )
            )

        # Compute aggregate metrics
        n_cases = len(comparisons)
        n_passed = sum(1 for c in comparisons if c.match)
        n_failed = n_cases - n_passed
        accuracy = n_passed / n_cases if n_cases > 0 else 0.0

        # Error metrics (only for failed cases)
        failed = [c for c in comparisons if not c.match]
        mean_error = sum(c.absolute_error for c in failed) / len(failed) if failed else 0.0
        max_error = max((c.absolute_error for c in failed), default=0.0)

        # Compute reward
        if self.partial_credit:
            reward = self._compute_partial_credit_reward(comparisons)
        else:
            reward = accuracy

        return RewardResult(
            reward=reward,
            accuracy=accuracy,
            oracle_results=oracle_results,
            mean_error=mean_error,
            max_error=max_error,
            n_cases=n_cases,
            n_passed=n_passed,
            n_failed=n_failed,
            diagnostics={
                "comparisons": [
                    {
                        "test_id": c.test_case_id,
                        "expected": c.expected,
                        "actual": c.actual,
                        "match": c.match,
                        "error": c.absolute_error,
                        "oracles": c.oracle_values,
                        "consensus": c.consensus,
                    }
                    for c in comparisons
                ],
                "failed_cases": [
                    {
                        "test_id": c.test_case_id,
                        "expected": c.expected,
                        "actual": c.actual,
                        "error": c.absolute_error,
                        "rel_error_pct": c.relative_error * 100,
                    }
                    for c in comparisons
                    if not c.match
                ],
            },
        )

    def _is_match(self, expected: float, actual: float) -> bool:
        """Check if actual matches expected within tolerance."""
        if expected == 0:
            return abs(actual) <= self.tolerance_absolute

        abs_error = abs(actual - expected)
        rel_error = abs_error / abs(expected)

        return (
            abs_error <= self.tolerance_absolute
            or rel_error <= self.tolerance_relative
        )

    def _relative_error(self, expected: float, actual: float) -> float:
        """Calculate relative error."""
        if expected == 0:
            return 0.0 if actual == 0 else float("inf")
        return abs(actual - expected) / abs(expected)

    def _check_consensus(self, values: list[float]) -> bool:
        """Check if all oracle values agree within tolerance."""
        if len(values) <= 1:
            return True

        # Check pairwise agreement
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                if not self._is_match(values[i], values[j]):
                    return False

        return True

    def _compute_partial_credit_reward(
        self, comparisons: list[OracleComparison]
    ) -> float:
        """Compute reward with partial credit for near-correct answers.

        Reward schedule (per the design doc):
        - <0.1% error: 1.0
        - <1% error: 0.95
        - <5% error: 0.8
        - <10% error: 0.6
        - <25% error: 0.3
        - >=25% error: 0.0
        """
        if not comparisons:
            return 0.0

        total_credit = 0.0

        for comp in comparisons:
            if comp.expected == 0:
                # For zero expected, exact match only
                credit = 1.0 if comp.actual == 0 else max(0.0, 1.0 - abs(comp.actual) / 100)
            else:
                rel_error = comp.relative_error

                if rel_error < 0.001:  # <0.1%
                    credit = 1.0
                elif rel_error < 0.01:  # <1%
                    credit = 0.95
                elif rel_error < 0.05:  # <5%
                    credit = 0.8
                elif rel_error < 0.10:  # <10%
                    credit = 0.6
                elif rel_error < 0.25:  # <25%
                    credit = 0.3
                else:
                    credit = 0.0

            total_credit += credit

        return total_credit / len(comparisons)


class StructuralRewardFunction:
    """Reward function for structural/syntactic correctness.

    This provides a fast "shaping" signal before semantic correctness.
    """

    def __init__(self):
        """Initialize structural reward function."""
        pass

    def evaluate(self, code: str, metadata: dict[str, Any]) -> float:
        """Evaluate structural correctness of generated code.

        Args:
            code: Generated Cosilico DSL code
            metadata: Metadata from parsing/compilation

        Returns:
            Structural reward score (0-1)
        """
        score = 0.0

        # Parses without errors (0.3)
        if metadata.get("parses", False):
            score += 0.3

        # Uses correct DSL primitives (0.2)
        if metadata.get("uses_valid_primitives", False):
            score += 0.2

        # Has required metadata (citations, periods) (0.2)
        if metadata.get("has_required_metadata", False):
            score += 0.2

        # Follows naming conventions (0.1)
        if metadata.get("follows_naming_conventions", False):
            score += 0.1

        # References declared dependencies (0.2)
        if metadata.get("references_valid_dependencies", False):
            score += 0.2

        return score


class CombinedRewardFunction:
    """Combined reward function balancing structure and semantics.

    Early training: higher alpha (more structural shaping)
    Late training: lower alpha (focus on correctness)
    """

    def __init__(
        self,
        structural_fn: StructuralRewardFunction,
        semantic_fn: EncodingRewardFunction,
        alpha: float = 0.3,
    ):
        """Initialize combined reward function.

        Args:
            structural_fn: Structural reward function
            semantic_fn: Semantic reward function
            alpha: Weight for structural vs semantic (0 = pure semantic, 1 = pure structural)
        """
        self.structural_fn = structural_fn
        self.semantic_fn = semantic_fn
        self.alpha = alpha

    def evaluate(
        self,
        code: str,
        structural_metadata: dict[str, Any],
        encoded_params: dict[str, Any],
        variable: str,
        test_cases: list[dict[str, Any]],
        year: int = 2024,
    ) -> tuple[float, RewardResult]:
        """Evaluate combined reward.

        Args:
            code: Generated code
            structural_metadata: Metadata from parsing
            encoded_params: Encoded parameters
            variable: Variable being tested
            test_cases: Test cases
            year: Tax year

        Returns:
            Tuple of (combined_reward, semantic_result)
        """
        structural_reward = self.structural_fn.evaluate(code, structural_metadata)
        semantic_result = self.semantic_fn.evaluate(
            encoded_params, variable, test_cases, year
        )

        combined_reward = (
            self.alpha * structural_reward + (1 - self.alpha) * semantic_result.reward
        )

        return combined_reward, semantic_result

    def set_alpha(self, alpha: float):
        """Update alpha for curriculum learning.

        Alpha schedule:
        - Initial: 0.5 (learn DSL structure)
        - Middle: 0.3 (balance structure and correctness)
        - Late: 0.1 (focus on calculation accuracy)
        - Final: 0.0 (pure correctness)
        """
        self.alpha = max(0.0, min(1.0, alpha))
