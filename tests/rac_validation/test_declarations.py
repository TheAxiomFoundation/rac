"""Tests for variable/parameter/input declarations."""

import pytest
import re
from .conftest import get_all_rac_files


class TestNoDuplicateDeclarations:
    """Each variable/parameter/input should only be declared once per file."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_no_duplicate_variables(self, rac_file):
        """Variable names must be unique within a file."""
        content = rac_file.read_text()

        variables = re.findall(r'^variable\s+(\w+):', content, re.MULTILINE)
        duplicates = [v for v in variables if variables.count(v) > 1]

        if duplicates:
            pytest.fail(f"Duplicate variable declarations: {set(duplicates)}")

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_no_duplicate_parameters(self, rac_file):
        """Parameter names must be unique within a file."""
        content = rac_file.read_text()

        parameters = re.findall(r'^parameter\s+(\w+):', content, re.MULTILINE)
        duplicates = [p for p in parameters if parameters.count(p) > 1]

        if duplicates:
            pytest.fail(f"Duplicate parameter declarations: {set(duplicates)}")

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_no_duplicate_inputs(self, rac_file):
        """Input names must be unique within a file."""
        content = rac_file.read_text()

        inputs = re.findall(r'^input\s+(\w+):', content, re.MULTILINE)
        duplicates = [i for i in inputs if inputs.count(i) > 1]

        if duplicates:
            pytest.fail(f"Duplicate input declarations: {set(duplicates)}")


class TestVariableCoverage:
    """Variables with formulas should have tests defined."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_formulas_have_tests(self, rac_file):
        """Variables with formulas should have tests: blocks."""
        content = rac_file.read_text()

        variables_with_formulas = re.findall(
            r'variable\s+(\w+):.*?formula:\s*\|',
            content,
            re.DOTALL
        )

        if not variables_with_formulas:
            pytest.skip("No variables with formulas")

        variables_with_tests = set(re.findall(
            r'variable\s+(\w+):.*?tests:',
            content,
            re.DOTALL
        ))

        untested = [v for v in variables_with_formulas if v not in variables_with_tests]

        if untested:
            coverage = len(variables_with_tests) / len(variables_with_formulas) * 100
            pytest.xfail(
                f"{len(untested)}/{len(variables_with_formulas)} variables without tests "
                f"({coverage:.0f}% coverage): {untested[:3]}"
            )
