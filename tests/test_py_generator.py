"""Tests for Python code generator.

TDD: Write tests first, then implement generator to pass them.
The Python generator produces vectorized (NumPy-compatible) code that returns
the same values as the JS generator for equivalent inputs.
"""

import pytest
import numpy as np

from src.rac.dsl_parser import parse_dsl

# Import will fail until we implement the generator
try:
    from src.rac.py_generator import generate_python, PyGenerator
except ImportError:
    generate_python = None
    PyGenerator = None


pytestmark = pytest.mark.skipif(
    generate_python is None,
    reason="py_generator not yet implemented"
)


def _execute_python(py_code: str, inputs: dict, params: dict = None) -> np.ndarray:
    """Execute generated Python code and return result."""
    if params is None:
        params = {}

    # Create namespace with numpy
    namespace = {"np": np, "inputs": inputs, "params": params}

    # Execute the generated code
    exec(py_code, namespace)

    # Find the function (last defined function)
    func_name = None
    for line in py_code.split("\n"):
        if line.startswith("def "):
            func_name = line.split("(")[0].replace("def ", "")

    if func_name is None:
        raise RuntimeError("No function found in generated code")

    return namespace[func_name](inputs, params)


class TestPyGeneratorBasic:
    """Basic code generation tests."""

    def test_literal_number(self):
        """Generate code for numeric literal."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return 42

"""
        py = generate_python(parse_dsl(code))
        assert "42" in py
        assert "def " in py

    def test_literal_boolean_true(self):
        """Generate code for boolean true."""
        code = """
variable flag:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return true

"""
        py = generate_python(parse_dsl(code))
        assert "True" in py  # Python uses True, not true

    def test_literal_boolean_false(self):
        """Generate code for boolean false."""
        code = """
variable flag:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return false

"""
        py = generate_python(parse_dsl(code))
        assert "False" in py  # Python uses False, not false

    def test_simple_arithmetic(self):
        """Generate code for arithmetic operations."""
        code = """
variable result:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        py = generate_python(parse_dsl(code))
        assert "*" in py
        assert "0.25" in py


class TestPyGeneratorOperators:
    """Tests for operator code generation."""

    def test_addition(self):
        """Generate code for addition."""
        code = """
variable sum:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return a + b

"""
        py = generate_python(parse_dsl(code))
        assert "+" in py

    def test_subtraction(self):
        """Generate code for subtraction."""
        code = """
variable diff:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return a - b

"""
        py = generate_python(parse_dsl(code))
        assert "-" in py

    def test_multiplication(self):
        """Generate code for multiplication."""
        code = """
variable product:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return a * b

"""
        py = generate_python(parse_dsl(code))
        assert "*" in py

    def test_division(self):
        """Generate code for division."""
        code = """
variable quotient:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return a / b

"""
        py = generate_python(parse_dsl(code))
        assert "/" in py

    def test_comparison_operators(self):
        """Generate code for comparison operators."""
        code = """
variable cmp:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return a < b and c > d and e <= f and g >= h and i == j and k != l

"""
        py = generate_python(parse_dsl(code))
        assert "<" in py
        assert ">" in py
        assert "<=" in py
        assert ">=" in py
        assert "==" in py
        assert "!=" in py

    def test_logical_and(self):
        """Generate code for logical AND."""
        code = """
variable both:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return a and b

"""
        py = generate_python(parse_dsl(code))
        # Python uses & for vectorized and
        assert "&" in py or "and" in py

    def test_logical_or(self):
        """Generate code for logical OR."""
        code = """
variable either:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return a or b

"""
        py = generate_python(parse_dsl(code))
        # Python uses | for vectorized or
        assert "|" in py or "or" in py

    def test_logical_not(self):
        """Generate code for logical NOT."""
        code = """
variable negated:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return not a

"""
        py = generate_python(parse_dsl(code))
        # Python uses ~ for vectorized not
        assert "~" in py or "not" in py


class TestPyGeneratorConditionals:
    """Tests for conditional code generation."""

    def test_if_then_else(self):
        """Generate code for if/then/else."""
        code = """
variable benefit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return if income < 20000: 1000 else 0

"""
        py = generate_python(parse_dsl(code))
        # Should generate np.where for vectorized conditionals
        assert "np.where" in py or "where" in py

    def test_nested_if(self):
        """Generate code for nested conditionals."""
        code = """
variable rate:
  entity: TaxUnit
  period: Year
  dtype: Rate

  formula:
    return if income < 10000: 0.10 else if income < 40000: 0.22 else 0.32

"""
        py = generate_python(parse_dsl(code))
        # Should have nested np.where calls
        assert py.count("np.where") >= 2 or py.count("where") >= 2


class TestPyGeneratorFunctions:
    """Tests for built-in function code generation."""

    def test_min_function(self):
        """Generate code for min()."""
        code = """
variable capped:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return min(income, 100000)

"""
        py = generate_python(parse_dsl(code))
        assert "np.minimum" in py

    def test_max_function(self):
        """Generate code for max()."""
        code = """
variable floor:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return max(income, 0)

"""
        py = generate_python(parse_dsl(code))
        assert "np.maximum" in py

    def test_nested_functions(self):
        """Generate code for nested function calls."""
        code = """
variable clamped:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return min(max(income, 0), 100000)

"""
        py = generate_python(parse_dsl(code))
        assert "np.minimum" in py
        assert "np.maximum" in py


class TestPyGeneratorLetBindings:
    """Tests for let binding code generation."""

    def test_single_let(self):
        """Generate code for single let binding."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let rate = 0.25
    return income * rate

"""
        py = generate_python(parse_dsl(code))
        assert "rate" in py
        assert "0.25" in py

    def test_multiple_lets(self):
        """Generate code for multiple let bindings."""
        code = """
variable eitc:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let rate = 0.34
    let cap = 6960
    return min(income * rate, cap)

"""
        py = generate_python(parse_dsl(code))
        assert "rate" in py
        assert "cap" in py
        assert "0.34" in py
        assert "6960" in py


class TestPyGeneratorMatch:
    """Tests for match expression code generation."""

    def test_match_expression(self):
        """Generate code for match expression."""
        code = """
variable deduction:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return match {
      case filing_status == "SINGLE" => 14600
      case filing_status == "JOINT" => 29200
      else => 0
    }
"""
        py = generate_python(parse_dsl(code))
        # Match should become chained np.where
        assert "14600" in py
        assert "29200" in py
        assert "np.where" in py


class TestPyGeneratorModule:
    """Tests for complete module generation."""

    def test_generates_function(self):
        """Generated code should be a callable function."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        py = generate_python(parse_dsl(code))
        # Should define a function
        assert "def tax(" in py

    def test_multiple_variables(self):
        """Generate code for multiple variables."""
        code = """
variable gross_income:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return wages + interest


variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return gross_income * 0.25

"""
        py = generate_python(parse_dsl(code))
        assert "def gross_income(" in py
        assert "def tax(" in py


class TestPyGeneratorExecution:
    """Tests that verify generated Python actually executes correctly."""

    def test_execute_simple_scalar(self):
        """Execute generated Python with scalar inputs."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        py = generate_python(parse_dsl(code))

        # Execute with scalar value
        inputs = {"income": np.array([40000.0])}
        result = _execute_python(py, inputs)

        assert result[0] == pytest.approx(10000.0)

    def test_execute_simple_vectorized(self):
        """Execute generated Python with array inputs."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        py = generate_python(parse_dsl(code))

        # Execute with array values
        inputs = {"income": np.array([0.0, 100.0, 40000.0, 100000.0])}
        result = _execute_python(py, inputs)

        expected = np.array([0.0, 25.0, 10000.0, 25000.0])
        np.testing.assert_array_almost_equal(result, expected)

    def test_execute_conditional(self):
        """Execute generated Python with conditionals."""
        code = """
variable capped_credit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return if income < 50000: income * 0.10 else 5000

"""
        py = generate_python(parse_dsl(code))

        inputs = {"income": np.array([0.0, 30000.0, 50000.0, 100000.0])}
        result = _execute_python(py, inputs)

        expected = np.array([0.0, 3000.0, 5000.0, 5000.0])
        np.testing.assert_array_almost_equal(result, expected)

    def test_execute_min_max(self):
        """Execute generated Python with min/max functions."""
        code = """
variable complex_calc:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let base = income * 0.20
    let cap = 10000
    return min(base, cap)

"""
        py = generate_python(parse_dsl(code))

        inputs = {"income": np.array([0.0, 10000.0, 50000.0, 100000.0])}
        result = _execute_python(py, inputs)

        expected = np.array([0.0, 2000.0, 10000.0, 10000.0])
        np.testing.assert_array_almost_equal(result, expected)

    def test_execute_boolean_ops(self):
        """Execute generated Python with boolean operations."""
        code = """
variable is_eligible:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return income > 1000 and income < 50000

"""
        py = generate_python(parse_dsl(code))

        inputs = {"income": np.array([500.0, 5000.0, 25000.0, 100000.0])}
        result = _execute_python(py, inputs)

        expected = np.array([False, True, True, False])
        np.testing.assert_array_equal(result, expected)


class TestPyGeneratorMatchesJS:
    """Tests ensuring Python produces same results as JS generator."""

    def test_arithmetic_matches_js(self):
        """Python arithmetic matches JS results."""
        code = """
variable simple_tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        py = generate_python(parse_dsl(code))

        # Same test cases as JS
        test_cases = [
            (0, 0.0),
            (100, 25.0),
            (40000, 10000.0),
            (100000, 25000.0),
        ]

        for income_val, expected in test_cases:
            inputs = {"income": np.array([float(income_val)])}
            result = _execute_python(py, inputs)
            assert result[0] == pytest.approx(expected, rel=1e-6), \
                f"Python result {result[0]} != expected {expected} for income {income_val}"

    def test_conditional_matches_js(self):
        """Python conditionals match JS results."""
        code = """
variable capped_credit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return if income < 50000: income * 0.10 else 5000

"""
        py = generate_python(parse_dsl(code))

        test_cases = [
            (0, 0.0),
            (30000, 3000.0),
            (50000, 5000.0),
            (100000, 5000.0),
        ]

        for income_val, expected in test_cases:
            inputs = {"income": np.array([float(income_val)])}
            result = _execute_python(py, inputs)
            assert result[0] == pytest.approx(expected, rel=1e-6), \
                f"Python result {result[0]} != expected {expected} for income {income_val}"

    def test_functions_match_js(self):
        """Python functions match JS results."""
        code = """
variable complex_calc:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let base = income * 0.20
    let cap = 10000
    return min(base, cap)

"""
        py = generate_python(parse_dsl(code))

        test_cases = [
            (0, 0.0),
            (10000, 2000.0),
            (50000, 10000.0),
            (100000, 10000.0),
        ]

        for income_val, expected in test_cases:
            inputs = {"income": np.array([float(income_val)])}
            result = _execute_python(py, inputs)
            assert result[0] == pytest.approx(expected, rel=1e-6), \
                f"Python result {result[0]} != expected {expected} for income {income_val}"


class TestPyGeneratorRealWorld:
    """Real-world formula tests matching JS generator."""

    def test_eitc_phase_in_formula(self):
        """EITC phase-in calculation."""
        code = """
variable eitc_phase_in:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let rate = 0.34
    let earned_income_cap = 11750
    return min(earned_income, earned_income_cap) * rate

"""
        py = generate_python(parse_dsl(code))

        test_cases = [
            (0, 0.0),
            (5000, 1700.0),
            (11750, 3995.0),
            (20000, 3995.0),
        ]

        for earned, expected in test_cases:
            inputs = {"earned_income": np.array([float(earned)])}
            result = _execute_python(py, inputs)
            assert result[0] == pytest.approx(expected, rel=1e-6)

    def test_standard_deduction_formula(self):
        """Standard deduction with filing status."""
        code = """
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
        py = generate_python(parse_dsl(code))

        # Test with array of different filing statuses
        inputs = {"filing_status": np.array(["SINGLE", "JOINT", "HEAD_OF_HOUSEHOLD", "UNKNOWN"])}
        result = _execute_python(py, inputs)

        expected = np.array([14600.0, 29200.0, 21900.0, 14600.0])
        np.testing.assert_array_almost_equal(result, expected)


class TestPyGeneratorVectorization:
    """Tests specifically for vectorization behavior."""

    def test_broadcasts_scalars(self):
        """Scalar parameters broadcast to array inputs."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        py = generate_python(parse_dsl(code))

        # Large array
        inputs = {"income": np.linspace(0, 100000, 1000)}
        result = _execute_python(py, inputs)

        expected = inputs["income"] * 0.25
        np.testing.assert_array_almost_equal(result, expected)

    def test_element_wise_comparison(self):
        """Comparisons work element-wise."""
        code = """
variable threshold_check:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return income >= threshold

"""
        py = generate_python(parse_dsl(code))

        inputs = {
            "income": np.array([1000.0, 2000.0, 3000.0, 4000.0]),
            "threshold": np.array([1500.0, 1500.0, 2500.0, 5000.0]),
        }
        result = _execute_python(py, inputs)

        expected = np.array([False, True, True, False])
        np.testing.assert_array_equal(result, expected)
