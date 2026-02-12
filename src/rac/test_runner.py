"""Test runner for embedded .rac tests.

Executes tests embedded in variable definitions and reports results.
Also supports companion .rac.test files for externalized test cases.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dsl_parser import Lexer, Module, Parser, TestCase, TokenType, VariableDef, parse_file


@dataclass
class TestResult:
    """Result of a single test execution."""

    variable_name: str
    test_name: str
    period: str
    passed: bool
    expected: Any
    actual: Any
    error: str | None = None


@dataclass
class TestReport:
    """Summary of test run."""

    results: list[TestResult]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)


def load_test_file(path: str | Path) -> dict[str, list[TestCase]]:
    """Load tests from a .rac.test companion file.

    Format:
        variable_name:
            - name: "Test name"
              period: 2024-01
              inputs:
                  var1: 100
              expect: 300

    Returns:
        Dict mapping variable names to lists of TestCase objects.
    """
    path = Path(path)
    source = path.read_text()

    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens, source)

    result: dict[str, list[TestCase]] = {}

    while not parser._is_at_end():
        # Each top-level entry is variable_name: followed by test list
        if parser._check(TokenType.IDENTIFIER):
            var_name = parser._advance().value
            parser._consume(TokenType.COLON, f"Expected ':' after variable name '{var_name}'")
            tests = parser._parse_tests()
            result[var_name] = tests
        else:
            parser._advance()

    return result


def evaluate_formula(var: VariableDef, inputs: dict[str, Any]) -> Any:
    """Evaluate a variable's formula with given inputs.

    This is a simple evaluator that handles basic expressions.
    For production use, this would compile to Python and execute.
    """
    # Handle Python syntax formulas (formula_source)
    if var.formula_source:
        return _evaluate_python_formula(var.formula_source, inputs)

    if not var.formula:
        return None

    # Build local scope from inputs
    scope = dict(inputs)

    # Execute bindings
    for binding in var.formula.bindings:
        value = _eval_expr(binding.value, scope)
        scope[binding.name] = value

    # Evaluate return expression
    if var.formula.return_expr:
        return _eval_expr(var.formula.return_expr, scope)

    return None


def _evaluate_python_formula(source: str, inputs: dict[str, Any]) -> Any:
    """Evaluate a Python-syntax formula directly.

    Args:
        source: Python source code for the formula
        inputs: Dict of input variable names to values

    Returns:
        The result of the formula evaluation
    """
    import textwrap

    # Common enum values used in tax formulas
    filing_status_enums = {
        "JOINT": "JOINT",
        "SINGLE": "SINGLE",
        "MARRIED_FILING_JOINTLY": "MARRIED_FILING_JOINTLY",
        "MARRIED_FILING_SEPARATELY": "MARRIED_FILING_SEPARATELY",
        "HEAD_OF_HOUSEHOLD": "HEAD_OF_HOUSEHOLD",
        "QUALIFYING_WIDOW": "QUALIFYING_WIDOW",
        "SURVIVING_SPOUSE": "SURVIVING_SPOUSE",
        "SEPARATE": "SEPARATE",
    }

    # Build execution namespace with builtins
    namespace = {"max": max, "min": min, "abs": abs, "sum": sum, "round": round}
    namespace.update(filing_status_enums)
    namespace.update(inputs)

    # Wrap the formula in a function to handle return statements
    # First dedent the source to handle any leading indentation
    dedented_source = textwrap.dedent(source)

    # Indent each line by 4 spaces for the function body
    indented_lines = []
    for line in dedented_source.split("\n"):
        if line.strip():  # Non-empty line
            indented_lines.append("    " + line)
        else:
            indented_lines.append("")  # Keep blank lines as-is

    wrapped_source = "def _formula_():\n" + "\n".join(indented_lines)

    # Execute the wrapped function definition
    exec(wrapped_source, namespace)

    # Call the function and return the result
    result = namespace["_formula_"]()
    return result


def _eval_expr(expr: Any, scope: dict[str, Any]) -> Any:
    """Evaluate an expression in a scope."""
    from .dsl_parser import BinaryOp, FunctionCall, Identifier, IfExpr, Literal, UnaryOp

    if isinstance(expr, Literal):
        return expr.value

    if isinstance(expr, Identifier):
        if expr.name in scope:
            return scope[expr.name]
        raise ValueError(f"Undefined variable: {expr.name}")

    if isinstance(expr, BinaryOp):
        left = _eval_expr(expr.left, scope)
        right = _eval_expr(expr.right, scope)

        ops = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: a / b if b != 0 else 0,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "and": lambda a, b: a and b,
            "or": lambda a, b: a or b,
        }

        if expr.op in ops:
            return ops[expr.op](left, right)
        raise ValueError(f"Unknown operator: {expr.op}")

    if isinstance(expr, UnaryOp):
        operand = _eval_expr(expr.operand, scope)
        if expr.op == "-":
            return -operand
        if expr.op == "not":
            return not operand
        raise ValueError(f"Unknown unary operator: {expr.op}")

    if isinstance(expr, FunctionCall):
        # Handle built-in functions
        args = [_eval_expr(a, scope) for a in expr.args]

        if expr.name == "max":
            return max(args) if args else 0
        if expr.name == "min":
            return min(args) if args else 0
        if expr.name == "abs":
            return abs(args[0]) if args else 0

        raise ValueError(f"Unknown function: {expr.name}")

    if isinstance(expr, IfExpr):
        cond = _eval_expr(expr.condition, scope)
        if cond:
            return _eval_expr(expr.then_branch, scope)
        return _eval_expr(expr.else_branch, scope)

    raise ValueError(f"Cannot evaluate expression type: {type(expr)}")


def get_parameter_value(param, period: str) -> Any:
    """Get parameter value for a given period.

    Finds the most recent value that is <= the test period.
    """
    if not param.values:
        return None

    # Sort dates and find applicable value
    sorted_dates = sorted(param.values.keys())
    applicable_value = None

    for date_str in sorted_dates:
        # Compare as strings (YYYY-MM-DD format sorts correctly)
        if date_str <= f"{period}-12-31":
            applicable_value = param.values[date_str]

    return applicable_value


def run_test(var: VariableDef, test: TestCase, parameters: list = None) -> TestResult:
    """Run a single test case."""
    try:
        # Merge parameters into inputs (test inputs override)
        inputs = {}
        if parameters:
            for param in parameters:
                value = get_parameter_value(param, test.period)
                if value is not None:
                    inputs[param.name] = value
        inputs.update(test.inputs)

        actual = evaluate_formula(var, inputs)

        # Compare with tolerance for floats
        if isinstance(test.expect, (int, float)) and isinstance(actual, (int, float)):
            passed = abs(actual - test.expect) < 0.01
        else:
            passed = actual == test.expect

        return TestResult(
            variable_name=var.name,
            test_name=test.name,
            period=test.period,
            passed=passed,
            expected=test.expect,
            actual=actual,
        )
    except Exception as e:
        return TestResult(
            variable_name=var.name,
            test_name=test.name,
            period=test.period,
            passed=False,
            expected=test.expect,
            actual=None,
            error=str(e),
        )


def run_tests_for_variable(var: VariableDef, parameters: list = None) -> list[TestResult]:
    """Run all tests for a variable."""
    return [run_test(var, test, parameters) for test in var.tests]


def run_tests_for_module(module: Module) -> TestReport:
    """Run all tests in a module."""
    results = []
    for var in module.variables:
        results.extend(run_tests_for_variable(var, module.parameters))
    return TestReport(results=results)


def merge_companion_tests(module: Module, rac_path: Path) -> None:
    """Merge tests from a companion .rac.test file into the module's variables."""
    test_file = rac_path.with_suffix(".rac.test")
    if not test_file.exists():
        return
    external_tests = load_test_file(test_file)
    for var in module.variables:
        if var.name in external_tests:
            var.tests.extend(external_tests[var.name])


def run_tests_for_file(path: str | Path) -> TestReport:
    """Run all tests in a .rac file, including companion .rac.test file."""
    path = Path(path)
    module = parse_file(str(path))
    merge_companion_tests(module, path)
    return run_tests_for_module(module)


def run_tests_for_directory(path: str | Path, pattern: str = "**/*.rac") -> TestReport:
    """Run all tests in .rac files in a directory."""
    path = Path(path)
    results = []

    for rac_file in path.glob(pattern):
        try:
            report = run_tests_for_file(rac_file)
            results.extend(report.results)
        except Exception as e:
            # Record file-level error
            results.append(
                TestResult(
                    variable_name="<file>",
                    test_name=str(rac_file),
                    period="",
                    passed=False,
                    expected=None,
                    actual=None,
                    error=str(e),
                )
            )

    return TestReport(results=results)


def print_report(report: TestReport, verbose: bool = False) -> None:
    """Print test report to stdout."""
    print("=" * 70)
    print("TEST RESULTS")
    print("=" * 70)

    for result in report.results:
        status = "✓" if result.passed else "✗"
        print(f"{status} {result.variable_name}::{result.test_name}")

        if not result.passed or verbose:
            if result.error:
                print(f"    ERROR: {result.error}")
            else:
                print(f"    Expected: {result.expected}")
                print(f"    Actual:   {result.actual}")

    print()
    print("=" * 70)
    print(f"RESULTS: {report.passed}/{report.total} passed, {report.failed} failed")
    print("=" * 70)


def main():
    """CLI entry point."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m rac.test_runner <path>")
        print("  path: .rac file or directory containing .rac files")
        sys.exit(1)

    path = Path(sys.argv[1])
    verbose = "-v" in sys.argv or "--verbose" in sys.argv

    if path.is_file():
        report = run_tests_for_file(path)
    elif path.is_dir():
        report = run_tests_for_directory(path)
    else:
        print(f"Error: {path} not found")
        sys.exit(1)

    print_report(report, verbose=verbose)

    # Exit with error code if any tests failed
    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
