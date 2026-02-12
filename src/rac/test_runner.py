"""Test runner for .rac.test files.

Parses YAML test specifications and runs them against compiled .rac modules.

Test file format (.rac.test):
    Each top-level key is a variable name being tested. Its value is a list
    of test cases, each with:
        - name: human-readable description
        - period: YYYY-MM (resolved to first day of month)
        - inputs: dict of variable_name -> value
        - expect: expected output value

Example:
    my_variable:
      - name: "Basic case"
        period: 2024-01
        inputs:
          input_a: 100
          input_b: 0.5
        expect: 50

CLI usage:
    python -m rac.test_runner path/to/file.rac
    python -m rac.test_runner path/to/file.rac.test
    python -m rac.test_runner path/to/directory/
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from . import ast as rac_ast
from .compiler import IR, Compiler
from .executor import Context, evaluate
from .schema import Data


@dataclass
class TestCase:
    """A single test case from a .rac.test file."""

    __test__ = False  # Prevent pytest collection

    name: str
    variable: str
    period: date
    inputs: dict[str, object]
    expected: object


@dataclass
class TestResult:
    """Result of running a single test case."""

    __test__ = False  # Prevent pytest collection

    test: TestCase
    passed: bool
    actual: object = None
    error: str | None = None


@dataclass
class TestResults:
    """Aggregate results of running a test suite."""

    __test__ = False  # Prevent pytest collection

    results: list[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> list[TestResult]:
        return [r for r in self.results if not r.passed]


def _parse_period(period_str: str) -> date:
    """Parse a period string like '2024-01' into a date.

    Supports:
        '2024-01'     -> date(2024, 1, 1)
        '2024-01-15'  -> date(2024, 1, 15)
    """
    parts = period_str.split("-")
    if len(parts) == 2:
        return date(int(parts[0]), int(parts[1]), 1)
    return date.fromisoformat(period_str)


def load_tests(path: Path) -> list[TestCase]:
    """Parse a .rac.test file into a list of TestCase objects.

    Args:
        path: Path to a .rac.test file (YAML format).

    Returns:
        List of TestCase objects.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"Test file not found: {path}")

    content = path.read_text()
    data = yaml.safe_load(content)

    if data is None:
        return []

    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping at top level in {path}, got {type(data).__name__}")

    test_cases: list[TestCase] = []

    for variable_name, cases in data.items():
        if not isinstance(cases, list):
            raise ValueError(
                f"Expected list of test cases for variable '{variable_name}' "
                f"in {path}, got {type(cases).__name__}"
            )

        for i, case in enumerate(cases):
            if not isinstance(case, dict):
                raise ValueError(
                    f"Test case {i} for '{variable_name}' in {path} "
                    f"must be a mapping"
                )

            name = case.get("name", f"{variable_name} test {i}")
            period_str = case.get("period")
            if period_str is None:
                raise ValueError(
                    f"Test case '{name}' for '{variable_name}' in {path} "
                    f"is missing 'period'"
                )

            inputs = case.get("inputs", {})
            if not isinstance(inputs, dict):
                raise ValueError(
                    f"Test case '{name}' for '{variable_name}' in {path}: "
                    f"'inputs' must be a mapping"
                )

            if "expect" not in case:
                raise ValueError(
                    f"Test case '{name}' for '{variable_name}' in {path} "
                    f"is missing 'expect'"
                )

            test_cases.append(
                TestCase(
                    name=name,
                    variable=variable_name,
                    period=_parse_period(str(period_str)),
                    inputs=inputs,
                    expected=case["expect"],
                )
            )

    return test_cases


def _values_equal(actual: object, expected: object, tolerance: float = 0.01) -> bool:
    """Compare two values with optional floating-point tolerance.

    Args:
        actual: The computed value.
        expected: The expected value.
        tolerance: Absolute tolerance for numeric comparisons.

    Returns:
        True if values are considered equal.
    """
    # Strict bool comparison: bools must match bools exactly
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(actual) is type(expected) and actual == expected

    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if math.isnan(float(expected)) and math.isnan(float(actual)):
            return True
        return abs(float(actual) - float(expected)) <= tolerance

    return actual == expected


def _build_ir_for_test(test: TestCase) -> IR:
    """Build a minimal IR that wires input variables to the tested variable.

    For each test case, we create:
    - One variable per input (scalar, resolving to a literal)
    - The formula is left to the caller to supply

    This is a helper for run_test when we don't have a .rac source file.
    """
    raise NotImplementedError("Direct IR building not yet supported")


def run_tests(
    rac_path: Path,
    test_path: Path,
    tolerance: float = 0.01,
) -> TestResults:
    """Parse a .rac file and its .rac.test file, compile, and run all tests.

    The .rac file is parsed and compiled. For each test case, the inputs are
    injected as scalar variables (overriding any existing definitions), the
    module is compiled for the test's period date, and the target variable
    is evaluated.

    Args:
        rac_path: Path to the .rac source file.
        test_path: Path to the .rac.test file.
        tolerance: Absolute tolerance for numeric comparisons (default 0.01).

    Returns:
        TestResults with pass/fail for each test case.
    """
    from .parser import parse as rac_parse

    if not rac_path.exists():
        raise FileNotFoundError(f"RAC file not found: {rac_path}")

    source = rac_path.read_text()
    module = rac_parse(source, str(rac_path))
    test_cases = load_tests(test_path)

    results = TestResults()

    for test in test_cases:
        result = _run_single_test(module, test, tolerance)
        results.results.append(result)

    return results


def _collect_deps(path: str, ir: IR, collected: set[str]) -> None:
    """Recursively collect all dependencies of a variable."""
    if path in collected:
        return
    collected.add(path)
    if path in ir.variables:
        for dep in ir.variables[path].deps:
            _collect_deps(dep, ir, collected)


def _run_single_test(
    module: rac_ast.Module,
    test: TestCase,
    tolerance: float,
) -> TestResult:
    """Run a single test case against a parsed module.

    Strategy: compile the module for the test's period, then inject input
    values as pre-computed scalars in the execution context. Only evaluate
    variables in the dependency chain of the target variable.
    """
    try:
        # Compile for the test date
        compiler = Compiler([module])
        ir = compiler.compile(test.period)

        # Check that the target variable exists in the IR
        if test.variable not in ir.variables:
            return TestResult(
                test=test,
                passed=False,
                error=(
                    f"Variable '{test.variable}' not found in compiled IR. "
                    f"Available: {sorted(ir.variables.keys())}"
                ),
            )

        # Collect only the variables needed for the target
        needed: set[str] = set()
        _collect_deps(test.variable, ir, needed)

        # Build execution context with test inputs pre-loaded
        ctx = Context(data=Data(tables={}))

        # Inject all test inputs upfront (they may be bare names or paths)
        for input_name, input_val in test.inputs.items():
            ctx.computed[input_name] = input_val

        # Evaluate only needed variables in topological order
        for path in ir.order:
            if path not in needed:
                continue
            if path in ctx.computed:
                # Already injected as a test input
                continue
            if path == test.variable:
                # This is the variable under test -- evaluate it
                var = ir.variables[path]
                if var.entity is not None:
                    return TestResult(
                        test=test,
                        passed=False,
                        error=f"Entity-level variable testing not yet supported (entity={var.entity})",
                    )
                ctx.computed[path] = evaluate(var.expr, ctx)
            else:
                # Evaluate dependency
                var = ir.variables[path]
                if var.entity is None:
                    ctx.computed[path] = evaluate(var.expr, ctx)

        actual = ctx.computed.get(test.variable)
        passed = _values_equal(actual, test.expected, tolerance)

        return TestResult(
            test=test,
            passed=passed,
            actual=actual,
            error=None if passed else (
                f"Expected {test.expected}, got {actual}"
            ),
        )

    except Exception as exc:
        return TestResult(
            test=test,
            passed=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def find_test_pairs(path: Path) -> list[tuple[Path, Path]]:
    """Find all .rac / .rac.test file pairs under a directory or for a single file.

    Args:
        path: A .rac file, a .rac.test file, or a directory.

    Returns:
        List of (rac_path, test_path) tuples.
    """
    if path.is_file():
        if path.name.endswith(".rac.test"):
            rac_path = path.parent / path.name.removesuffix(".test")
            if rac_path.exists():
                return [(rac_path, path)]
            return [(rac_path, path)]  # Will error at runtime with clear message
        elif path.name.endswith(".rac"):
            test_path = path.parent / (path.name + ".test")
            if test_path.exists():
                return [(path, test_path)]
            return []  # No test file found
        else:
            return []

    # Directory: find all .rac.test files and pair them
    pairs: list[tuple[Path, Path]] = []
    for test_file in sorted(path.rglob("*.rac.test")):
        rac_file = test_file.parent / test_file.name.removesuffix(".test")
        pairs.append((rac_file, test_file))
    return pairs


def run_test_suite(
    path: Path,
    tolerance: float = 0.01,
    verbose: bool = False,
) -> TestResults:
    """Run all tests found at a path (file or directory).

    Args:
        path: A .rac file, .rac.test file, or directory.
        tolerance: Absolute tolerance for numeric comparisons.
        verbose: Print individual test results as they run.

    Returns:
        Aggregated TestResults.
    """
    pairs = find_test_pairs(path)
    all_results = TestResults()

    if not pairs:
        if verbose:
            print(f"No .rac.test files found at {path}")
        return all_results

    for rac_path, test_path in pairs:
        if verbose:
            print(f"\n--- {test_path.name} ---")

        if not rac_path.exists():
            # Still load tests to report them as errors
            try:
                test_cases = load_tests(test_path)
                for tc in test_cases:
                    result = TestResult(
                        test=tc,
                        passed=False,
                        error=f"RAC file not found: {rac_path}",
                    )
                    all_results.results.append(result)
                    if verbose:
                        print(f"  FAIL  {tc.name}: RAC file not found")
            except Exception as exc:
                if verbose:
                    print(f"  ERROR loading tests: {exc}")
            continue

        try:
            results = run_tests(rac_path, test_path, tolerance)
        except Exception as exc:
            if verbose:
                print(f"  ERROR: {exc}")
            continue

        for r in results.results:
            all_results.results.append(r)
            if verbose:
                status = "PASS" if r.passed else "FAIL"
                msg = f"  {status}  {r.test.name}"
                if not r.passed and r.error:
                    msg += f" -- {r.error}"
                print(msg)

    return all_results


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for ``python -m rac.test_runner``."""
    args = argv if argv is not None else sys.argv[1:]

    usage = (
        "Usage: python -m rac.test_runner [OPTIONS] <path>\n"
        "\n"
        "Run .rac.test files against their .rac counterparts.\n"
        "\n"
        "Arguments:\n"
        "  <path>          A .rac file, .rac.test file, or directory\n"
        "\n"
        "Options:\n"
        "  --tolerance N   Floating-point tolerance (default: 0.01)\n"
        "  --verbose, -v   Print individual test results\n"
        "  --help, -h      Show this message\n"
    )

    tolerance = 0.01
    verbose = False
    paths: list[str] = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--help", "-h"):
            print(usage)
            sys.exit(0)
        elif arg == "--tolerance":
            i += 1
            if i >= len(args):
                print("Error: --tolerance requires a value", file=sys.stderr)
                sys.exit(2)
            tolerance = float(args[i])
        elif arg in ("--verbose", "-v"):
            verbose = True
        elif arg.startswith("-"):
            print(f"Unknown option: {arg}", file=sys.stderr)
            print(usage, file=sys.stderr)
            sys.exit(2)
        else:
            paths.append(arg)
        i += 1

    if not paths:
        print("Error: no path provided", file=sys.stderr)
        print(usage, file=sys.stderr)
        sys.exit(2)

    all_results = TestResults()

    for p in paths:
        target = Path(p)
        if not target.exists():
            print(f"Error: {target} not found", file=sys.stderr)
            sys.exit(1)

        results = run_test_suite(target, tolerance=tolerance, verbose=verbose)
        all_results.results.extend(results.results)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Tests: {all_results.total}  Passed: {all_results.passed}  Failed: {all_results.failed}")

    if all_results.failures:
        print("\nFailures:")
        for r in all_results.failures:
            print(f"  [{r.test.variable}] {r.test.name}")
            if r.error:
                print(f"    {r.error}")
        sys.exit(1)
    elif all_results.total == 0:
        print("No tests found.")
        sys.exit(0)
    else:
        print("All tests passed.")
        sys.exit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
