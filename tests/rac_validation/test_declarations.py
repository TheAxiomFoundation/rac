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

        # Split content by variable declarations to analyze each variable block
        # This properly handles multiple variables in the same file
        variable_blocks = re.split(r'(?=^variable\s+\w+:)', content, flags=re.MULTILINE)

        variables_with_formulas = []
        variables_with_tests = set()

        for block in variable_blocks:
            # Check if this block starts with a variable declaration
            var_match = re.match(r'^variable\s+(\w+):', block)
            if not var_match:
                continue

            var_name = var_match.group(1)

            # Check if variable has formula: | (multiline formula)
            has_formula = bool(re.search(r'^\s+formula:\s*\|', block, re.MULTILINE))

            # Check if variable has tests: block
            has_tests = bool(re.search(r'^\s+tests:', block, re.MULTILINE))

            if has_formula:
                variables_with_formulas.append(var_name)
                if has_tests:
                    variables_with_tests.add(var_name)

        if not variables_with_formulas:
            pytest.skip("No variables with formulas")

        untested = [v for v in variables_with_formulas if v not in variables_with_tests]

        if untested:
            coverage = len(variables_with_tests) / len(variables_with_formulas) * 100
            pytest.xfail(
                f"{len(untested)}/{len(variables_with_formulas)} variables without tests "
                f"({coverage:.0f}% coverage): {untested[:3]}"
            )
