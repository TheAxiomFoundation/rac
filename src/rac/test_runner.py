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
from .executor import Context, ExecutionError, evaluate
from .module_loader import load_modules_with_imports
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
    tables: dict[str, list[dict[str, object]]] = field(default_factory=dict)


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


SYNTHETIC_PERIOD = date(1970, 1, 1)


def _parse_period(period_str: str) -> date:
    """Parse a period string like '2024-01' into a date.

    Supports:
        '2024'        -> date(2024, 1, 1)
        '2024-01'     -> date(2024, 1, 1)
        '2024-01-15'  -> date(2024, 1, 15)
    """
    parts = period_str.split("-")
    if len(parts) == 1 and len(parts[0]) == 4:
        return date(int(parts[0]), 1, 1)
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

    test_cases: list[TestCase] = []
    if isinstance(data, dict):
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
                        tables=_parse_tables(case.get("tables", {}), path, name),
                        expected=case["expect"],
                    )
                )
        return test_cases

    if isinstance(data, list):
        for i, case in enumerate(data):
            if not isinstance(case, dict):
                raise ValueError(
                    f"Test case {i} in {path} must be a mapping"
                )

            period_str = case.get("period")
            if period_str is None:
                raise ValueError(
                    f"Test case {i} in {path} is missing 'period'"
                )

            inputs = case.get("input", case.get("inputs", {}))
            if not isinstance(inputs, dict):
                raise ValueError(
                    f"Test case {i} in {path}: 'input'/'inputs' must be a mapping"
                )

            outputs = case.get("output")
            if not isinstance(outputs, dict) or not outputs:
                raise ValueError(
                    f"Test case {i} in {path} is missing non-empty 'output' mapping"
                )

            case_name = case.get("name", f"test {i}")
            parsed_period = _parse_period(str(period_str))
            parsed_tables = _parse_tables(case.get("tables", {}), path, case_name)
            for variable_name, expected in outputs.items():
                test_cases.append(
                    TestCase(
                        name=f"{case_name}::{variable_name}",
                        variable=str(variable_name),
                        period=parsed_period,
                        inputs=inputs,
                        tables=parsed_tables,
                        expected=expected,
                    )
                )
        return test_cases

    raise ValueError(
        f"Expected YAML mapping or list at top level in {path}, got {type(data).__name__}"
    )


def _parse_default(value: str) -> object:
    """Convert a default value string to an appropriate Python type."""
    low = value.lower()
    if low in ("false", "False"):
        return False
    if low in ("true", "True"):
        return True
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _parse_tables(
    raw_tables: object,
    path: Path,
    case_name: str,
) -> dict[str, list[dict[str, object]]]:
    """Validate and normalize entity-table test inputs."""
    if raw_tables in ({}, None):
        return {}
    if not isinstance(raw_tables, dict):
        raise ValueError(
            f"Test case '{case_name}' in {path}: 'tables' must be a mapping"
        )

    parsed: dict[str, list[dict[str, object]]] = {}
    for entity_name, rows in raw_tables.items():
        if not isinstance(rows, list):
            raise ValueError(
                f"Test case '{case_name}' in {path}: table '{entity_name}' "
                "must be a list of rows"
            )
        normalized_rows: list[dict[str, object]] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(
                    f"Test case '{case_name}' in {path}: row {idx} in table "
                    f"'{entity_name}' must be a mapping"
                )
            normalized_rows.append(dict(row))
        parsed[str(entity_name)] = normalized_rows
    return parsed


def _normalize_tables_for_entities(
    tables: dict[str, list[dict[str, object]]],
    entity_names: set[str],
) -> dict[str, list[dict[str, object]]]:
    """Map case-insensitive/plural table keys to known entity names."""
    if not tables:
        return {}

    normalized: dict[str, list[dict[str, object]]] = {}
    for raw_name, rows in tables.items():
        canonical = raw_name
        raw_lower = raw_name.lower()
        for entity_name in entity_names:
            entity_lower = entity_name.lower()
            if raw_lower == entity_lower or raw_lower == f"{entity_lower}s":
                canonical = entity_name
                break
        normalized[canonical] = rows
    return normalized


def _synthetic_failure_result(
    test_path: Path,
    error: str,
    *,
    test_name: str | None = None,
) -> TestResult:
    """Create a synthetic failing result for suite-level failures."""
    name = test_name or test_path.name
    return TestResult(
        test=TestCase(
            name=name,
            variable="__suite__",
            period=SYNTHETIC_PERIOD,
            inputs={},
            tables={},
            expected=None,
        ),
        passed=False,
        error=error,
    )


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

    if isinstance(expected, list) and isinstance(actual, list):
        if len(actual) != len(expected):
            return False
        return all(
            _values_equal(a_item, e_item, tolerance)
            for a_item, e_item in zip(actual, expected, strict=False)
        )

    if isinstance(expected, dict) and isinstance(actual, dict):
        if set(actual.keys()) != set(expected.keys()):
            return False
        return all(
            _values_equal(actual[key], expected[key], tolerance)
            for key in expected
        )

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
    all_modules: list[rac_ast.Module] | None = None,
) -> TestResults:
    """Parse a .rac file and its .rac.test file, compile, and run all tests.

    Args:
        rac_path: Path to the .rac source file.
        test_path: Path to the .rac.test file.
        tolerance: Absolute tolerance for numeric comparisons (default 0.01).
        all_modules: Pre-parsed modules for cross-file resolution.

    Returns:
        TestResults with pass/fail for each test case.
    """
    if not rac_path.exists():
        raise FileNotFoundError(f"RAC file not found: {rac_path}")

    modules = load_modules_with_imports(rac_path)
    test_cases = load_tests(test_path)

    results = TestResults()

    for test in test_cases:
        result = _run_single_test(modules, all_modules or [], test, tolerance)
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
    modules: list[rac_ast.Module],
    all_modules: list[rac_ast.Module],
    test: TestCase,
    tolerance: float,
) -> TestResult:
    """Run a single test case against parsed modules.

    Strategy: compile primary modules for the test's period, then inject
    defaults from all modules and test inputs into execution context.
    """
    try:
        compiler = Compiler(modules)
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

        # Build execution context with test inputs pre-loaded
        entity_names = {var.entity for var in ir.variables.values() if var.entity is not None}
        ctx = Context(data=Data(tables=_normalize_tables_for_entities(test.tables, entity_names)))
        entity_results: dict[str, dict[str, list[object]]] = {}

        # Inject default values from all module variable declarations,
        # but NOT for variables that will be computed from the IR
        all_mods = all_modules if all_modules else modules
        for mod in all_mods:
            for var_decl in mod.variables:
                if (var_decl.default is not None
                        and var_decl.path not in test.inputs
                        and var_decl.path not in ir.variables):
                    ctx.computed[var_decl.path] = _parse_default(var_decl.default)

        # Inject all test inputs upfront (they may be bare names or paths)
        for input_name, input_val in test.inputs.items():
            ctx.computed[input_name] = input_val

        # Evaluate all variables in topological order
        # Skip non-target variables that fail (cross-file deps may be missing)
        for path in ir.order:
            if path in ctx.computed:
                continue
            var = ir.variables[path]
            try:
                if var.entity is None:
                    ctx.computed[path] = evaluate(var.expr, ctx)
                else:
                    entity_name = var.entity
                    rows = ctx.data.get_rows(entity_name)
                    if not rows:
                        ctx.current_row = None
                        ctx.current_entity = entity_name
                        ctx.computed[path] = evaluate(var.expr, ctx)
                        ctx.current_row = None
                        ctx.current_entity = None
                        continue
                    entity_bucket = entity_results.setdefault(entity_name, {})
                    outputs = entity_bucket.setdefault(path, [])

                    for i, row in enumerate(rows):
                        augmented = dict(row)
                        for prev_path, prev_vals in entity_bucket.items():
                            if len(prev_vals) > i:
                                augmented[prev_path] = prev_vals[i]
                        ctx.current_row = augmented
                        ctx.current_entity = entity_name
                        outputs.append(evaluate(var.expr, ctx))
                        ctx.current_row = None
                        ctx.current_entity = None
            except ExecutionError:
                if path == test.variable:
                    raise
                # Non-target variable failed — skip it

        target_var = ir.variables[test.variable]
        if target_var.entity is None:
            actual = ctx.computed.get(test.variable)
        else:
            actual = entity_results.get(target_var.entity, {}).get(
                test.variable, ctx.computed.get(test.variable)
            )
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

    # Pre-parse all .rac files in the directory for cross-file resolution
    all_modules: list[rac_ast.Module] = []
    if path.is_dir():
        seen_module_paths: set[str] = set()
        for rac_file in sorted(path.rglob("*.rac")):
            if ".rac.test" in rac_file.name:
                continue
            try:
                for mod in load_modules_with_imports(rac_file):
                    if mod.path not in seen_module_paths:
                        all_modules.append(mod)
                        seen_module_paths.add(mod.path)
            except Exception:
                pass  # Skip files that fail to parse

    for rac_path, test_path in pairs:
        if verbose:
            print(f"\n--- {test_path.name} ---")

        if not rac_path.exists():
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
                all_results.results.append(
                    _synthetic_failure_result(
                        test_path,
                        f"{type(exc).__name__}: {exc}",
                        test_name=f"{test_path.name}::load_tests",
                    )
                )
            continue

        try:
            results = run_tests(rac_path, test_path, tolerance, all_modules=all_modules or None)
        except Exception as exc:
            try:
                test_cases = load_tests(test_path)
            except Exception as load_exc:
                all_results.results.append(
                    _synthetic_failure_result(
                        test_path,
                        (
                            f"{type(exc).__name__}: {exc}; "
                            f"additionally failed to load tests: {type(load_exc).__name__}: {load_exc}"
                        ),
                        test_name=f"{test_path.name}::suite_error",
                    )
                )
                if verbose:
                    print(f"  ERROR: {exc}")
                continue

            for tc in test_cases:
                all_results.results.append(
                    TestResult(
                        test=tc,
                        passed=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
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
