"""Tests for JavaScript code generator.

TDD: Write tests first, then implement generator to pass them.
"""

import pytest

from src.rac.dsl_parser import parse_dsl

# Import will fail until we implement the generator
try:
    from src.rac.js_generator import generate_js, JSGenerator
except ImportError:
    generate_js = None
    JSGenerator = None


pytestmark = pytest.mark.skipif(
    generate_js is None,
    reason="js_generator not yet implemented"
)


class TestJSGeneratorBasic:
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
        js = generate_js(parse_dsl(code))
        assert "42" in js
        assert "function" in js or "=>" in js

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
        js = generate_js(parse_dsl(code))
        assert "true" in js

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
        js = generate_js(parse_dsl(code))
        assert "false" in js

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
        js = generate_js(parse_dsl(code))
        assert "*" in js
        assert "0.25" in js


class TestJSGeneratorOperators:
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
        js = generate_js(parse_dsl(code))
        assert "+" in js

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
        js = generate_js(parse_dsl(code))
        assert "-" in js

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
        js = generate_js(parse_dsl(code))
        assert "*" in js

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
        js = generate_js(parse_dsl(code))
        assert "/" in js

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
        js = generate_js(parse_dsl(code))
        assert "<" in js
        assert ">" in js
        assert "<=" in js
        assert ">=" in js
        assert "===" in js or "==" in js
        assert "!==" in js or "!=" in js

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
        js = generate_js(parse_dsl(code))
        assert "&&" in js

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
        js = generate_js(parse_dsl(code))
        assert "||" in js

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
        js = generate_js(parse_dsl(code))
        assert "!" in js


class TestJSGeneratorConditionals:
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
        js = generate_js(parse_dsl(code))
        # Should generate ternary operator
        assert "?" in js
        assert ":" in js

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
        js = generate_js(parse_dsl(code))
        # Should have two ternary operators
        assert js.count("?") >= 2


class TestJSGeneratorFunctions:
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
        js = generate_js(parse_dsl(code))
        assert "Math.min" in js

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
        js = generate_js(parse_dsl(code))
        assert "Math.max" in js

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
        js = generate_js(parse_dsl(code))
        assert "Math.min" in js
        assert "Math.max" in js


class TestJSGeneratorLetBindings:
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
        js = generate_js(parse_dsl(code))
        assert "const rate" in js or "let rate" in js
        assert "0.25" in js

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
        js = generate_js(parse_dsl(code))
        assert "rate" in js
        assert "cap" in js
        assert "0.34" in js
        assert "6960" in js


class TestJSGeneratorMatch:
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
        js = generate_js(parse_dsl(code))
        # Match should become chained ternaries or switch
        assert "14600" in js
        assert "29200" in js


class TestJSGeneratorModule:
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
        js = generate_js(parse_dsl(code))
        # Should export a function
        assert "export" in js or "function" in js

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
        js = generate_js(parse_dsl(code))
        assert "gross_income" in js
        assert "tax" in js

    def test_variable_dependencies(self):
        """Variables can reference other variables."""
        code = """
variable a:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return input_value * 2


variable b:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return a + 100

"""
        js = generate_js(parse_dsl(code))
        # b should reference a
        assert "a" in js


class TestJSGeneratorExecution:
    """Tests that verify generated JS actually executes correctly."""

    def test_execute_simple(self):
        """Execute generated JS and verify result."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        js = generate_js(parse_dsl(code))

        # Use a JS runtime to verify (optional - requires Node.js)
        # For now, just verify it generates valid-looking code
        assert "income" in js
        assert "0.25" in js


class TestJSGeneratorTypedArrays:
    """Tests for TypedArray vectorized code generation."""

    @pytest.mark.skip(reason="Vectorized output not yet implemented")
    def test_vectorized_option(self):
        """Generator can produce vectorized TypedArray code."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        gen = JSGenerator(vectorized=True)
        js = gen.generate(parse_dsl(code))
        # Should use Float64Array for Money type
        assert "Float64Array" in js or "TypedArray" in js or "Array" in js


class TestJSGeneratorEITC:
    """Integration test with real EITC example."""

    def test_eitc_formula(self):
        """Generate JS for EITC earned_income_credit."""
        code = """
references:
  is_eligible: statute/26/32/c/1/A/is_eligible_individual
  initial_credit: statute/26/32/a/2/A/initial_credit_amount
  reduction: statute/26/32/a/2/B/credit_reduction_amount

variable earned_income_credit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    if not is_eligible: 0 else max(0, initial_credit - reduction)

"""
        js = generate_js(parse_dsl(code))
        assert "is_eligible" in js
        assert "initial_credit" in js
        assert "reduction" in js
        assert "Math.max" in js
