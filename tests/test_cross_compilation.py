"""Tests for cross-compilation consistency.

VALIDATION STRATEGY:
1. Validate Python output against PolicyEngine ONCE per variable
2. Ensure all compilation targets (JS, Python, WASM) produce IDENTICAL results

This test file focuses on #2 - ensuring compilation target consistency.
For PolicyEngine validation, see tests/test_pe_validation.py (manual/CI).
"""

import json
import subprocess
from typing import Any

import numpy as np
import pytest

from src.rac.dsl_parser import parse_dsl
from src.rac.js_generator import generate_js

# Import Python executor (may not exist yet)
try:
    from src.rac.py_generator import generate_python
except ImportError:
    generate_python = None


class TestCrossCompilationConsistency:
    """Ensure all compilation targets produce identical results."""

    @pytest.fixture
    def simple_dsl(self) -> str:
        """Simple arithmetic DSL for testing."""
        return """
variable simple_tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""

    @pytest.fixture
    def conditional_dsl(self) -> str:
        """DSL with conditionals."""
        return """
variable capped_credit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return if income < 50000: income * 0.10 else 5000

"""

    @pytest.fixture
    def complex_dsl(self) -> str:
        """DSL with multiple features."""
        return """
variable complex_calc:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let base = income * 0.20
    let cap = 10000
    return min(base, cap)

"""

    def _execute_js(self, js_code: str, inputs: dict[str, Any]) -> float:
        """Execute JavaScript code and return result."""
        # Wrap JS in executable form
        wrapper = f"""
const inputs = {json.dumps(inputs)};
const params = {{}};

{js_code}

// Find the exported function
const funcMatch = {json.dumps(js_code)}.match(/function (\\w+)\\(inputs/);
const funcName = funcMatch ? funcMatch[1] : 'unknown';
console.log(JSON.stringify(eval(funcName + '(inputs, params)')));
"""
        result = subprocess.run(
            ["node", "-e", wrapper],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(f"JS execution failed: {result.stderr}")
        return float(json.loads(result.stdout.strip()))

    def _execute_python(self, py_code: str, inputs: dict[str, Any]) -> float:
        """Execute Python code and return result."""
        # Convert scalar inputs to numpy arrays
        np_inputs = {k: np.array([v]) for k, v in inputs.items()}
        params = {}

        # Create namespace with numpy
        namespace = {"np": np, "inputs": np_inputs, "params": params}

        # Execute the generated code
        exec(py_code, namespace)

        # Find the function (last defined function)
        func_name = None
        for line in py_code.split("\n"):
            if line.startswith("def "):
                func_name = line.split("(")[0].replace("def ", "")

        if func_name is None:
            raise RuntimeError("No function found in generated code")

        result = namespace[func_name](np_inputs, params)
        return float(result[0])

    def test_js_generates_valid_code(self, simple_dsl: str):
        """JavaScript generator produces valid JS."""
        module = parse_dsl(simple_dsl)
        js = generate_js(module)

        assert "function simple_tax" in js
        assert "inputs.income" in js
        assert "0.25" in js
        assert "export" in js

    def test_js_arithmetic_matches_expected(self, simple_dsl: str):
        """JS arithmetic produces expected results."""
        module = parse_dsl(simple_dsl)
        js = generate_js(module)

        # Test with known values
        test_cases = [
            ({"income": 0}, 0.0),
            ({"income": 100}, 25.0),
            ({"income": 40000}, 10000.0),
            ({"income": 100000}, 25000.0),
        ]

        for inputs, expected in test_cases:
            result = self._execute_js(js, inputs)
            assert result == pytest.approx(expected, rel=1e-6), \
                f"JS result {result} != expected {expected} for inputs {inputs}"

    def test_js_conditionals_match_expected(self, conditional_dsl: str):
        """JS conditionals produce expected results."""
        module = parse_dsl(conditional_dsl)
        js = generate_js(module)

        test_cases = [
            ({"income": 0}, 0.0),           # Below threshold: 0 * 0.10
            ({"income": 30000}, 3000.0),    # Below threshold: 30000 * 0.10
            ({"income": 50000}, 5000.0),    # At threshold (else branch)
            ({"income": 100000}, 5000.0),   # Above threshold: capped
        ]

        for inputs, expected in test_cases:
            result = self._execute_js(js, inputs)
            assert result == pytest.approx(expected, rel=1e-6), \
                f"JS result {result} != expected {expected} for inputs {inputs}"

    def test_js_functions_match_expected(self, complex_dsl: str):
        """JS built-in functions (min/max) produce expected results."""
        module = parse_dsl(complex_dsl)
        js = generate_js(module)

        test_cases = [
            ({"income": 0}, 0.0),           # base=0, min(0, 10000)=0
            ({"income": 10000}, 2000.0),    # base=2000, min(2000, 10000)=2000
            ({"income": 50000}, 10000.0),   # base=10000, min(10000, 10000)=10000
            ({"income": 100000}, 10000.0),  # base=20000, min(20000, 10000)=10000
        ]

        for inputs, expected in test_cases:
            result = self._execute_js(js, inputs)
            assert result == pytest.approx(expected, rel=1e-6), \
                f"JS result {result} != expected {expected} for inputs {inputs}"

    @pytest.mark.skipif(generate_python is None, reason="Python generator not implemented")
    def test_js_python_consistency(self, simple_dsl: str):
        """JS and Python produce identical results."""
        module = parse_dsl(simple_dsl)
        js = generate_js(module)
        py = generate_python(module)

        test_cases = [
            {"income": 0},
            {"income": 100},
            {"income": 40000},
            {"income": 100000},
            {"income": 12345.67},
        ]

        for inputs in test_cases:
            js_result = self._execute_js(js, inputs)
            py_result = self._execute_python(py, inputs)

            assert js_result == pytest.approx(py_result, rel=1e-9), \
                f"JS={js_result} != Python={py_result} for inputs {inputs}"


class TestEdgeCases:
    """Test edge cases for cross-compilation consistency."""

    def test_boolean_literals(self):
        """Boolean literals compile consistently."""
        dsl = """
variable is_eligible:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return true

"""
        module = parse_dsl(dsl)
        js = generate_js(module)
        assert "true" in js  # JS boolean, not Python True

    def test_zero_division_handling(self):
        """Division by zero is handled consistently."""
        dsl = """
variable ratio:
  entity: TaxUnit
  period: Year
  dtype: Rate

  formula:
    return if denominator == 0: 0 else numerator / denominator

"""
        module = parse_dsl(dsl)
        js = generate_js(module)

        # Should use ternary to avoid division by zero
        assert "?" in js
        assert ":" in js

    def test_negative_numbers(self):
        """Negative numbers handled correctly."""
        dsl = """
variable net:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income - expenses

"""
        module = parse_dsl(dsl)
        js = generate_js(module)

        # Test with various combinations
        wrapper = f"""
const inputs = {{"income": 100, "expenses": 150}};
const params = {{}};

{js}

console.log(net(inputs, params));
"""
        result = subprocess.run(
            ["node", "-e", wrapper],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert float(result.stdout.strip()) == -50.0

    def test_floating_point_precision(self):
        """Floating point precision is consistent."""
        dsl = """
variable precise_calc:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return value * 0.1 + value * 0.2

"""
        module = parse_dsl(dsl)
        js = generate_js(module)

        # Test with value that exposes FP issues
        wrapper = f"""
const inputs = {{"value": 0.3}};
const params = {{}};

{js}

console.log(precise_calc(inputs, params));
"""
        result = subprocess.run(
            ["node", "-e", wrapper],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # 0.3 * 0.1 + 0.3 * 0.2 = 0.03 + 0.06 = 0.09
        assert float(result.stdout.strip()) == pytest.approx(0.09, rel=1e-10)


class TestRealWorldFormulas:
    """Test real-world tax/benefit formulas for consistency."""

    def test_eitc_phase_in_formula(self):
        """EITC phase-in calculation is consistent."""
        dsl = """
variable eitc_phase_in:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let rate = 0.34
    let earned_income_cap = 11750
    return min(earned_income, earned_income_cap) * rate

"""
        module = parse_dsl(dsl)
        js = generate_js(module)

        test_cases = [
            ({"earned_income": 0}, 0.0),
            ({"earned_income": 5000}, 1700.0),       # 5000 * 0.34
            ({"earned_income": 11750}, 3995.0),     # 11750 * 0.34
            ({"earned_income": 20000}, 3995.0),     # Capped at 11750 * 0.34
        ]

        for inputs, expected in test_cases:
            wrapper = f"""
const inputs = {json.dumps(inputs)};
const params = {{}};

{js}

console.log(eitc_phase_in(inputs, params));
"""
            result = subprocess.run(
                ["node", "-e", wrapper],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert float(result.stdout.strip()) == pytest.approx(expected, rel=1e-6)

    def test_standard_deduction_formula(self):
        """Standard deduction with filing status is consistent."""
        dsl = """
variable standard_deduction:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return match {
      case filing_status == "SINGLE" => 14600
      case filing_status == "JOINT" => 29200
      case filing_status == "HEAD_OF_HOUSEHOLD" => 21900
      else => 14600
    }
"""
        module = parse_dsl(dsl)
        js = generate_js(module)

        test_cases = [
            ({"filing_status": "SINGLE"}, 14600.0),
            ({"filing_status": "JOINT"}, 29200.0),
            ({"filing_status": "HEAD_OF_HOUSEHOLD"}, 21900.0),
            ({"filing_status": "UNKNOWN"}, 14600.0),  # Default
        ]

        for inputs, expected in test_cases:
            wrapper = f"""
const inputs = {json.dumps(inputs)};
const params = {{}};

{js}

console.log(standard_deduction(inputs, params));
"""
            result = subprocess.run(
                ["node", "-e", wrapper],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert float(result.stdout.strip()) == expected
