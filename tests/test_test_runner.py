"""Tests for the .rac.test runner."""

from datetime import date

import pytest

from rac.test_runner import (
    TestCase,
    TestResult,
    TestResults,
    _parse_period,
    _values_equal,
    find_test_pairs,
    load_tests,
    main,
    run_test_suite,
    run_tests,
)

# ---------------------------------------------------------------------------
# Fixtures: .rac source and .rac.test content
# ---------------------------------------------------------------------------

SIMPLE_RAC = """\
variable gov/rate:
    from 2024-01-01: 0.20

variable gov/threshold:
    from 2024-01-01: 10000

variable gov/tax:
    from 2024-01-01: max(0, income - gov/threshold) * gov/rate
"""

SIMPLE_TEST = """\
gov/rate:
  - name: "Rate is 0.20 in 2024"
    period: 2024-01
    inputs: {}
    expect: 0.20

gov/threshold:
  - name: "Threshold is 10000 in 2024"
    period: 2024-01
    inputs: {}
    expect: 10000

gov/tax:
  - name: "Income below threshold"
    period: 2024-01
    inputs:
      income: 5000
    expect: 0
  - name: "Income above threshold"
    period: 2024-01
    inputs:
      income: 30000
    expect: 4000
  - name: "Income at threshold"
    period: 2024-01
    inputs:
      income: 10000
    expect: 0
"""

TEMPORAL_RAC = """\
variable gov/rate:
    from 2023-01-01: 0.15
    from 2024-01-01: 0.20
    from 2025-01-01: 0.25
"""

TEMPORAL_TEST = """\
gov/rate:
  - name: "2023 rate"
    period: 2023-06
    inputs: {}
    expect: 0.15
  - name: "2024 rate"
    period: 2024-06
    inputs: {}
    expect: 0.20
  - name: "2025 rate"
    period: 2025-06
    inputs: {}
    expect: 0.25
"""

CONDITIONAL_RAC = """\
variable gov/credit:
    from 2024-01-01:
        if eligible: amount * rate
        else: 0
"""

CONDITIONAL_TEST = """\
gov/credit:
  - name: "Eligible gets credit"
    period: 2024-01
    inputs:
      eligible: true
      amount: 5000
      rate: 0.34
    expect: 1700
  - name: "Ineligible gets zero"
    period: 2024-01
    inputs:
      eligible: false
      amount: 5000
      rate: 0.34
    expect: 0
"""

BOOLEAN_RAC = """\
variable gov/is_eligible:
    from 2024-01-01:
        if age >= threshold_age and income <= income_limit: true
        else: false
"""

BOOLEAN_TEST = """\
gov/is_eligible:
  - name: "Meets both criteria"
    period: 2024-01
    inputs:
      age: 30
      threshold_age: 25
      income: 20000
      income_limit: 50000
    expect: true
  - name: "Too young"
    period: 2024-01
    inputs:
      age: 20
      threshold_age: 25
      income: 20000
      income_limit: 50000
    expect: false
  - name: "Income too high"
    period: 2024-01
    inputs:
      age: 30
      threshold_age: 25
      income: 60000
      income_limit: 50000
    expect: false
"""

FAILING_TEST = """\
gov/rate:
  - name: "Deliberately wrong expectation"
    period: 2024-01
    inputs: {}
    expect: 999
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_pair(tmp_path):
    """Create a simple .rac / .rac.test pair."""
    rac_file = tmp_path / "tax.rac"
    test_file = tmp_path / "tax.rac.test"
    rac_file.write_text(SIMPLE_RAC)
    test_file.write_text(SIMPLE_TEST)
    return rac_file, test_file


@pytest.fixture
def temporal_pair(tmp_path):
    """Create a temporal .rac / .rac.test pair."""
    rac_file = tmp_path / "rate.rac"
    test_file = tmp_path / "rate.rac.test"
    rac_file.write_text(TEMPORAL_RAC)
    test_file.write_text(TEMPORAL_TEST)
    return rac_file, test_file


@pytest.fixture
def conditional_pair(tmp_path):
    """Create a conditional .rac / .rac.test pair."""
    rac_file = tmp_path / "credit.rac"
    test_file = tmp_path / "credit.rac.test"
    rac_file.write_text(CONDITIONAL_RAC)
    test_file.write_text(CONDITIONAL_TEST)
    return rac_file, test_file


@pytest.fixture
def boolean_pair(tmp_path):
    """Create a boolean .rac / .rac.test pair."""
    rac_file = tmp_path / "eligible.rac"
    test_file = tmp_path / "eligible.rac.test"
    rac_file.write_text(BOOLEAN_RAC)
    test_file.write_text(BOOLEAN_TEST)
    return rac_file, test_file


# ---------------------------------------------------------------------------
# Tests: _parse_period
# ---------------------------------------------------------------------------


class TestParsePeriod:
    def test_year_month(self):
        assert _parse_period("2024-01") == date(2024, 1, 1)

    def test_year_month_december(self):
        assert _parse_period("2024-12") == date(2024, 12, 1)

    def test_full_date(self):
        assert _parse_period("2024-06-15") == date(2024, 6, 15)


# ---------------------------------------------------------------------------
# Tests: _values_equal
# ---------------------------------------------------------------------------


class TestValuesEqual:
    def test_exact_int(self):
        assert _values_equal(100, 100)

    def test_exact_float(self):
        assert _values_equal(0.20, 0.20)

    def test_within_tolerance(self):
        assert _values_equal(99.995, 100.0, tolerance=0.01)

    def test_outside_tolerance(self):
        assert not _values_equal(99.0, 100.0, tolerance=0.01)

    def test_zero_tolerance(self):
        assert _values_equal(100.0, 100.0, tolerance=0.0)
        assert not _values_equal(100.001, 100.0, tolerance=0.0)

    def test_bool_true(self):
        assert _values_equal(True, True)

    def test_bool_false(self):
        assert _values_equal(False, False)

    def test_bool_not_equal(self):
        assert not _values_equal(True, False)

    def test_bool_vs_int(self):
        # bool True should not match int 1 when expected is bool
        assert not _values_equal(1, True)

    def test_string_equal(self):
        assert _values_equal("hello", "hello")

    def test_string_not_equal(self):
        assert not _values_equal("hello", "world")

    def test_custom_tolerance(self):
        assert _values_equal(100.0, 100.5, tolerance=1.0)
        assert not _values_equal(100.0, 102.0, tolerance=1.0)


# ---------------------------------------------------------------------------
# Tests: load_tests
# ---------------------------------------------------------------------------


class TestLoadTests:
    def test_load_simple(self, tmp_path):
        test_file = tmp_path / "test.rac.test"
        test_file.write_text(SIMPLE_TEST)
        cases = load_tests(test_file)
        assert len(cases) == 5

    def test_load_names(self, tmp_path):
        test_file = tmp_path / "test.rac.test"
        test_file.write_text(SIMPLE_TEST)
        cases = load_tests(test_file)
        names = [c.name for c in cases]
        assert "Rate is 0.20 in 2024" in names
        assert "Income below threshold" in names
        assert "Income above threshold" in names

    def test_load_variables(self, tmp_path):
        test_file = tmp_path / "test.rac.test"
        test_file.write_text(SIMPLE_TEST)
        cases = load_tests(test_file)
        variables = {c.variable for c in cases}
        assert variables == {"gov/rate", "gov/threshold", "gov/tax"}

    def test_load_inputs(self, tmp_path):
        test_file = tmp_path / "test.rac.test"
        test_file.write_text(SIMPLE_TEST)
        cases = load_tests(test_file)
        # Find the "Income above threshold" test
        case = [c for c in cases if c.name == "Income above threshold"][0]
        assert case.inputs == {"income": 30000}
        assert case.expected == 4000

    def test_load_period(self, tmp_path):
        test_file = tmp_path / "test.rac.test"
        test_file.write_text(SIMPLE_TEST)
        cases = load_tests(test_file)
        for c in cases:
            assert c.period == date(2024, 1, 1)

    def test_load_empty_file(self, tmp_path):
        test_file = tmp_path / "empty.rac.test"
        test_file.write_text("")
        cases = load_tests(test_file)
        assert cases == []

    def test_load_nonexistent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_tests(tmp_path / "nonexistent.rac.test")

    def test_load_invalid_yaml(self, tmp_path):
        test_file = tmp_path / "bad.rac.test"
        test_file.write_text("not a list\n  - broken yaml: [")
        # yaml.safe_load may parse this as a string or raise
        # Our code should handle it either way
        with pytest.raises((ValueError, Exception)):
            load_tests(test_file)

    def test_load_missing_period(self, tmp_path):
        test_file = tmp_path / "no_period.rac.test"
        test_file.write_text(
            "my_var:\n"
            "  - name: test\n"
            "    inputs: {}\n"
            "    expect: 0\n"
        )
        with pytest.raises(ValueError, match="missing 'period'"):
            load_tests(test_file)

    def test_load_missing_expect(self, tmp_path):
        test_file = tmp_path / "no_expect.rac.test"
        test_file.write_text(
            "my_var:\n"
            "  - name: test\n"
            "    period: 2024-01\n"
            "    inputs: {}\n"
        )
        with pytest.raises(ValueError, match="missing 'expect'"):
            load_tests(test_file)

    def test_load_boolean_expected(self, tmp_path):
        test_file = tmp_path / "bool.rac.test"
        test_file.write_text(BOOLEAN_TEST)
        cases = load_tests(test_file)
        assert cases[0].expected is True
        assert cases[1].expected is False

    def test_load_with_rac_us_format(self, tmp_path):
        """Test loading the actual rac-us format (top-level key = variable name)."""
        test_file = tmp_path / "eitc.rac.test"
        test_file.write_text(
            "eitc_credit:\n"
            "  - name: \"Low income\"\n"
            "    period: 2024-01\n"
            "    inputs:\n"
            "      earned_income: 5000\n"
            "      credit_percentage: 0.34\n"
            "    expect: 1700\n"
        )
        cases = load_tests(test_file)
        assert len(cases) == 1
        assert cases[0].variable == "eitc_credit"
        assert cases[0].inputs["earned_income"] == 5000


# ---------------------------------------------------------------------------
# Tests: run_tests
# ---------------------------------------------------------------------------


class TestRunTests:
    def test_simple_pass(self, simple_pair):
        rac_file, test_file = simple_pair
        results = run_tests(rac_file, test_file)
        assert results.total == 5
        assert results.all_passed
        assert results.passed == 5
        assert results.failed == 0

    def test_temporal_pass(self, temporal_pair):
        rac_file, test_file = temporal_pair
        results = run_tests(rac_file, test_file)
        assert results.total == 3
        assert results.all_passed

    def test_conditional_pass(self, conditional_pair):
        rac_file, test_file = conditional_pair
        results = run_tests(rac_file, test_file)
        assert results.total == 2
        assert results.all_passed

    def test_boolean_pass(self, boolean_pair):
        rac_file, test_file = boolean_pair
        results = run_tests(rac_file, test_file)
        assert results.total == 3
        assert results.all_passed

    def test_detect_failure(self, tmp_path):
        rac_file = tmp_path / "rate.rac"
        test_file = tmp_path / "rate.rac.test"
        rac_file.write_text(
            "variable gov/rate:\n"
            "    from 2024-01-01: 0.20\n"
        )
        test_file.write_text(FAILING_TEST)
        results = run_tests(rac_file, test_file)
        assert results.total == 1
        assert results.failed == 1
        assert not results.all_passed
        assert results.failures[0].test.name == "Deliberately wrong expectation"
        assert "Expected 999" in results.failures[0].error

    def test_missing_rac_file(self, tmp_path):
        test_file = tmp_path / "missing.rac.test"
        test_file.write_text(SIMPLE_TEST)
        with pytest.raises(FileNotFoundError):
            run_tests(tmp_path / "missing.rac", test_file)

    def test_missing_test_file(self, tmp_path):
        rac_file = tmp_path / "test.rac"
        rac_file.write_text(SIMPLE_RAC)
        with pytest.raises(FileNotFoundError):
            run_tests(rac_file, tmp_path / "nonexistent.rac.test")

    def test_variable_not_in_ir(self, tmp_path):
        rac_file = tmp_path / "minimal.rac"
        test_file = tmp_path / "minimal.rac.test"
        rac_file.write_text(
            "variable gov/rate:\n"
            "    from 2024-01-01: 0.20\n"
        )
        test_file.write_text(
            "nonexistent_var:\n"
            "  - name: test\n"
            "    period: 2024-01\n"
            "    inputs: {}\n"
            "    expect: 0\n"
        )
        results = run_tests(rac_file, test_file)
        assert results.failed == 1
        assert "not found" in results.failures[0].error


# ---------------------------------------------------------------------------
# Tests: tolerance
# ---------------------------------------------------------------------------


class TestTolerance:
    def test_default_tolerance(self, tmp_path):
        rac_file = tmp_path / "tol.rac"
        test_file = tmp_path / "tol.rac.test"
        rac_file.write_text(
            "variable gov/val:\n"
            "    from 2024-01-01: 100.005\n"
        )
        test_file.write_text(
            "gov/val:\n"
            "  - name: within tolerance\n"
            "    period: 2024-01\n"
            "    inputs: {}\n"
            "    expect: 100.0\n"
        )
        results = run_tests(rac_file, test_file, tolerance=0.01)
        assert results.all_passed

    def test_strict_tolerance(self, tmp_path):
        rac_file = tmp_path / "tol.rac"
        test_file = tmp_path / "tol.rac.test"
        rac_file.write_text(
            "variable gov/val:\n"
            "    from 2024-01-01: 100.005\n"
        )
        test_file.write_text(
            "gov/val:\n"
            "  - name: outside strict tolerance\n"
            "    period: 2024-01\n"
            "    inputs: {}\n"
            "    expect: 100.0\n"
        )
        results = run_tests(rac_file, test_file, tolerance=0.001)
        assert results.failed == 1

    def test_large_tolerance(self, tmp_path):
        rac_file = tmp_path / "tol.rac"
        test_file = tmp_path / "tol.rac.test"
        rac_file.write_text(
            "variable gov/val:\n"
            "    from 2024-01-01: 105\n"
        )
        test_file.write_text(
            "gov/val:\n"
            "  - name: within large tolerance\n"
            "    period: 2024-01\n"
            "    inputs: {}\n"
            "    expect: 100\n"
        )
        results = run_tests(rac_file, test_file, tolerance=10.0)
        assert results.all_passed


# ---------------------------------------------------------------------------
# Tests: find_test_pairs
# ---------------------------------------------------------------------------


class TestFindTestPairs:
    def test_find_from_rac_file(self, simple_pair):
        rac_file, test_file = simple_pair
        pairs = find_test_pairs(rac_file)
        assert len(pairs) == 1
        assert pairs[0] == (rac_file, test_file)

    def test_find_from_test_file(self, simple_pair):
        rac_file, test_file = simple_pair
        pairs = find_test_pairs(test_file)
        assert len(pairs) == 1
        assert pairs[0] == (rac_file, test_file)

    def test_find_from_directory(self, tmp_path):
        # Create multiple pairs
        for name in ["a", "b", "c"]:
            (tmp_path / f"{name}.rac").write_text(SIMPLE_RAC)
            (tmp_path / f"{name}.rac.test").write_text(SIMPLE_TEST)
        # Also a .rac without a test
        (tmp_path / "no_test.rac").write_text(SIMPLE_RAC)

        pairs = find_test_pairs(tmp_path)
        assert len(pairs) == 3
        rac_names = {p[0].name for p in pairs}
        assert rac_names == {"a.rac", "b.rac", "c.rac"}

    def test_no_test_file(self, tmp_path):
        rac_file = tmp_path / "lonely.rac"
        rac_file.write_text(SIMPLE_RAC)
        pairs = find_test_pairs(rac_file)
        assert pairs == []

    def test_nested_directory(self, tmp_path):
        subdir = tmp_path / "statute" / "26" / "32"
        subdir.mkdir(parents=True)
        (subdir / "a.rac").write_text(SIMPLE_RAC)
        (subdir / "a.rac.test").write_text(SIMPLE_TEST)

        pairs = find_test_pairs(tmp_path)
        assert len(pairs) == 1


# ---------------------------------------------------------------------------
# Tests: run_test_suite
# ---------------------------------------------------------------------------


class TestRunTestSuite:
    def test_suite_single_file(self, simple_pair):
        rac_file, _ = simple_pair
        results = run_test_suite(rac_file)
        assert results.total == 5
        assert results.all_passed

    def test_suite_directory(self, tmp_path):
        # Create two pairs
        (tmp_path / "a.rac").write_text(SIMPLE_RAC)
        (tmp_path / "a.rac.test").write_text(SIMPLE_TEST)
        (tmp_path / "b.rac").write_text(TEMPORAL_RAC)
        (tmp_path / "b.rac.test").write_text(TEMPORAL_TEST)

        results = run_test_suite(tmp_path)
        assert results.total == 8  # 5 + 3
        assert results.all_passed

    def test_suite_empty_directory(self, tmp_path):
        results = run_test_suite(tmp_path)
        assert results.total == 0

    def test_suite_verbose(self, simple_pair, capsys):
        rac_file, _ = simple_pair
        results = run_test_suite(rac_file, verbose=True)
        captured = capsys.readouterr()
        assert "PASS" in captured.out
        assert results.all_passed

    def test_suite_missing_rac_verbose(self, tmp_path, capsys):
        test_file = tmp_path / "orphan.rac.test"
        test_file.write_text(
            "gov/rate:\n"
            "  - name: test\n"
            "    period: 2024-01\n"
            "    inputs: {}\n"
            "    expect: 0.20\n"
        )
        results = run_test_suite(test_file, verbose=True)
        assert results.failed == 1
        captured = capsys.readouterr()
        assert "FAIL" in captured.out


# ---------------------------------------------------------------------------
# Tests: TestResults dataclass
# ---------------------------------------------------------------------------


class TestTestResults:
    def test_empty_results(self):
        r = TestResults()
        assert r.total == 0
        assert r.passed == 0
        assert r.failed == 0
        assert r.all_passed  # vacuously true

    def test_mixed_results(self):
        tc1 = TestCase("t1", "var", date(2024, 1, 1), {}, 0)
        tc2 = TestCase("t2", "var", date(2024, 1, 1), {}, 0)
        r = TestResults(results=[
            TestResult(test=tc1, passed=True, actual=0),
            TestResult(test=tc2, passed=False, actual=1, error="wrong"),
        ])
        assert r.total == 2
        assert r.passed == 1
        assert r.failed == 1
        assert not r.all_passed
        assert len(r.failures) == 1


# ---------------------------------------------------------------------------
# Tests: CLI (main)
# ---------------------------------------------------------------------------


class TestCLI:
    def test_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_no_args(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2

    def test_nonexistent_path(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["/nonexistent/path"])
        assert exc_info.value.code == 1

    def test_run_passing(self, simple_pair, capsys):
        rac_file, _ = simple_pair
        with pytest.raises(SystemExit) as exc_info:
            main([str(rac_file)])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "All tests passed" in captured.out

    def test_run_failing(self, tmp_path, capsys):
        rac_file = tmp_path / "rate.rac"
        test_file = tmp_path / "rate.rac.test"
        rac_file.write_text(
            "variable gov/rate:\n"
            "    from 2024-01-01: 0.20\n"
        )
        test_file.write_text(FAILING_TEST)
        with pytest.raises(SystemExit) as exc_info:
            main([str(rac_file)])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Failures" in captured.out

    def test_verbose_flag(self, simple_pair, capsys):
        rac_file, _ = simple_pair
        with pytest.raises(SystemExit) as exc_info:
            main(["-v", str(rac_file)])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "PASS" in captured.out

    def test_tolerance_flag(self, tmp_path, capsys):
        rac_file = tmp_path / "tol.rac"
        test_file = tmp_path / "tol.rac.test"
        rac_file.write_text(
            "variable gov/val:\n"
            "    from 2024-01-01: 105\n"
        )
        test_file.write_text(
            "gov/val:\n"
            "  - name: test\n"
            "    period: 2024-01\n"
            "    inputs: {}\n"
            "    expect: 100\n"
        )
        with pytest.raises(SystemExit) as exc_info:
            main(["--tolerance", "10", str(rac_file)])
        assert exc_info.value.code == 0

    def test_empty_directory(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main([str(tmp_path)])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No tests found" in captured.out

    def test_unknown_option(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--bogus"])
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Tests: import from rac package
# ---------------------------------------------------------------------------


class TestImports:
    def test_imports_from_package(self):
        import rac

        assert hasattr(rac, "load_tests")
        assert hasattr(rac, "run_tests")
        assert hasattr(rac, "TestCase")
        assert hasattr(rac, "TestResult")
        assert hasattr(rac, "TestResults")
        assert callable(rac.load_tests)
        assert callable(rac.run_tests)
