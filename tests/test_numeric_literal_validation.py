"""Tests for numeric literal validation in DSL formulas.

Per DSL_SPEC.md: Only 0, 1, -1 are allowed as numeric literals in formulas.
All other values must come from parameters.
"""

from dataclasses import dataclass

import pytest

from src.rac.dsl_parser import (
    BinaryOp,
    FormulaBlock,
    FunctionCall,
    IfExpr,
    IndexExpr,
    LetBinding,
    Literal,
    MatchExpr,
    Module,
    UnaryOp,
    parse_dsl,
)

# === Validation Logic (inline for pytest) ===

ALLOWED_LITERALS: set[float] = {0, 0.0, 1, 1.0, -1, -1.0}


class NumericLiteralError(Exception):
    """Raised when a formula contains disallowed numeric literals."""

    def __init__(self, violations: list["LiteralViolation"]):
        self.violations = violations
        messages = []
        for v in violations:
            messages.append(
                f"Disallowed numeric literal {v.value} at line {v.line} in variable '{v.variable_name}'. "
                f"Values other than 0, 1, -1 must come from parameters."
            )
        super().__init__("\n".join(messages))


@dataclass
class LiteralViolation:
    """A single violation of the numeric literal rule."""

    value: float
    line: int
    variable_name: str


def validate_numeric_literals(ast: Module) -> None:
    """Validate that all numeric literals in formulas are 0, 1, or -1."""
    violations: list[LiteralViolation] = []

    for var in ast.variables:
        if var.formula:
            var_violations = _check_expression(var.formula, var.name)
            violations.extend(var_violations)

    if violations:
        raise NumericLiteralError(violations)


def _check_expression(expr, variable_name: str, line: int = 0) -> list[LiteralViolation]:
    """Recursively check an expression for disallowed literals."""
    violations = []

    if expr is None:
        return violations

    if isinstance(expr, FormulaBlock):
        for binding in expr.bindings:
            violations.extend(_check_expression(binding, variable_name, line))
        for guard in expr.guards:
            condition, return_value = guard
            violations.extend(_check_expression(condition, variable_name, line))
            violations.extend(_check_expression(return_value, variable_name, line))
        violations.extend(_check_expression(expr.return_expr, variable_name, line))
        return violations

    if isinstance(expr, LetBinding):
        violations.extend(_check_expression(expr.value, variable_name, line))
        return violations

    if isinstance(expr, Literal):
        if expr.dtype == "number":
            value = expr.value
            if value not in ALLOWED_LITERALS:
                if not (value == -1 or value == -1.0):
                    violations.append(
                        LiteralViolation(value=value, line=line, variable_name=variable_name)
                    )

    elif isinstance(expr, BinaryOp):
        violations.extend(_check_expression(expr.left, variable_name, line))
        violations.extend(_check_expression(expr.right, variable_name, line))

    elif isinstance(expr, UnaryOp):
        if expr.op == "-" and isinstance(expr.operand, Literal):
            if expr.operand.dtype == "number" and expr.operand.value == 1:
                return violations
        violations.extend(_check_expression(expr.operand, variable_name, line))

    elif isinstance(expr, IfExpr):
        violations.extend(_check_expression(expr.condition, variable_name, line))
        violations.extend(_check_expression(expr.then_branch, variable_name, line))
        if expr.else_branch:
            violations.extend(_check_expression(expr.else_branch, variable_name, line))

    elif isinstance(expr, FunctionCall):
        for arg in expr.args:
            violations.extend(_check_expression(arg, variable_name, line))

    elif isinstance(expr, IndexExpr):
        violations.extend(_check_expression(expr.obj, variable_name, line))
        violations.extend(_check_expression(expr.index, variable_name, line))

    elif isinstance(expr, MatchExpr):
        violations.extend(_check_expression(expr.subject, variable_name, line))
        for case in expr.cases:
            violations.extend(_check_expression(case.pattern, variable_name, line))
            violations.extend(_check_expression(case.value, variable_name, line))

    elif isinstance(expr, list):
        for item in expr:
            violations.extend(_check_expression(item, variable_name, line))

    return violations


# === Tests ===

class TestNumericLiteralValidation:
    """Test that formulas only contain allowed numeric literals (0, 1, -1)."""

    def test_allowed_zero(self):
        """Zero is allowed in formulas."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  return max(0, income - threshold)
"""
        ast = parse_dsl(source)
        validate_numeric_literals(ast)

    def test_allowed_one(self):
        """One is allowed in formulas."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  return income * (1 - rate)
"""
        ast = parse_dsl(source)
        validate_numeric_literals(ast)

    def test_allowed_negative_one(self):
        """Negative one is allowed in formulas."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  return income * -1
"""
        ast = parse_dsl(source)
        validate_numeric_literals(ast)

    def test_disallowed_integer(self):
        """Other integers are not allowed."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  return income * 12
"""
        ast = parse_dsl(source)
        with pytest.raises(NumericLiteralError) as exc_info:
            validate_numeric_literals(ast)
        assert "12" in str(exc_info.value)
        assert "must come from parameters" in str(exc_info.value).lower()

    def test_disallowed_float(self):
        """Floats are not allowed."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  return income * 0.34
"""
        ast = parse_dsl(source)
        with pytest.raises(NumericLiteralError) as exc_info:
            validate_numeric_literals(ast)
        assert "0.34" in str(exc_info.value)

    def test_disallowed_large_number(self):
        """Large numbers like thresholds are not allowed."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  if income > 200000:
    return 0
  else:
    return credit
"""
        ast = parse_dsl(source)
        with pytest.raises(NumericLiteralError) as exc_info:
            validate_numeric_literals(ast)
        assert "200000" in str(exc_info.value)

    def test_disallowed_in_nested_expression(self):
        """Disallowed numbers in nested expressions are caught."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  result = max(0, min(income, 50000))
  return result
"""
        ast = parse_dsl(source)
        with pytest.raises(NumericLiteralError) as exc_info:
            validate_numeric_literals(ast)
        assert "50000" in str(exc_info.value)

    def test_allowed_in_default(self):
        """Numbers in default values are allowed (they're metadata, not formula)."""
        source = """
entity: Person
period: Year
dtype: Money

default: 1000

formula:
  return income
"""
        ast = parse_dsl(source)
        validate_numeric_literals(ast)

    def test_multiple_violations_reported(self):
        """All violations in a formula are reported."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  rate = 0.34
  threshold = 50000
  return income * rate
"""
        ast = parse_dsl(source)
        with pytest.raises(NumericLiteralError) as exc_info:
            validate_numeric_literals(ast)
        error_msg = str(exc_info.value)
        assert "0.34" in error_msg
        assert "50000" in error_msg

    def test_error_includes_line_number(self):
        """Error message includes line number for debugging."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  return income * 27.4
"""
        ast = parse_dsl(source)
        with pytest.raises(NumericLiteralError) as exc_info:
            validate_numeric_literals(ast)
        assert "line" in str(exc_info.value).lower()

    def test_allowed_zero_point_zero(self):
        """0.0 is equivalent to 0 and should be allowed."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  return max(0.0, income)
"""
        ast = parse_dsl(source)
        validate_numeric_literals(ast)

    def test_allowed_one_point_zero(self):
        """1.0 is equivalent to 1 and should be allowed."""
        source = """
entity: Person
period: Year
dtype: Money

formula:
  return income * 1.0
"""
        ast = parse_dsl(source)
        validate_numeric_literals(ast)
