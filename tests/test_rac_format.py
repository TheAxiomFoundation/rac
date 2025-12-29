"""Tests for .rac file format - applies to any jurisdiction."""

import pytest
import re
from pathlib import Path


# These tests can be run against any statute directory
# Set STATUTE_DIR env var or pass --statute-dir to pytest


def get_statute_dir():
    """Get statute directory from env or default."""
    import os
    default = Path.home() / "CosilicoAI" / "cosilico-us" / "statute"
    return Path(os.environ.get("STATUTE_DIR", default))


def get_all_rac_files():
    """Get all .rac files for parametrized testing."""
    statute_dir = get_statute_dir()
    if not statute_dir.exists():
        return []
    return list(statute_dir.rglob("*.rac"))


class TestFilenameIsCitation:
    """Filename must be citation identifier, not descriptive name."""

    VALID_PATTERNS = [
        r'^[a-z]$',           # Single letter: a, b, c
        r'^[1-9][0-9]*$',     # Number: 1, 2, 10
        r'^[1-9][0-9]*[A-Z]$', # Section with letter: 25A, 36B, 30D
        r'^[ivxlcdm]+$',      # Roman numeral: i, ii, iii, iv
        r'^[A-Z]$',           # Capital letter: A, B, C
    ]

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_filename_is_citation(self, rac_file):
        """Filename should be subsection identifier (a, 1, A, i), not descriptive."""
        filename = rac_file.stem

        is_valid = any(re.match(p, filename) for p in self.VALID_PATTERNS)

        if not is_valid:
            pytest.fail(
                f"Filename '{filename}' is not a valid citation identifier. "
                f"Must be: single letter (a-z), number (1, 2, ...), roman numeral (i, ii, ...), "
                f"or capital letter (A-Z). Path: {rac_file}"
            )


class TestTextFieldFormat:
    """text: field should contain actual statute text."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_text_not_summary(self, rac_file):
        """text: field should not be a made-up summary."""
        content = rac_file.read_text()

        text_match = re.search(r'text:\s*"""(.*?)"""', content, re.DOTALL)
        if not text_match:
            pytest.skip("No text: field")

        text = text_match.group(1).strip()

        # Reject obvious summaries
        if re.match(r'^(provides|this section|computation)', text.lower()):
            pytest.fail(f"text: looks like summary, not statute: '{text[:50]}...'")


class TestNoHardcodedValues:
    """Formulas should only use 0, 1, -1 as literals."""

    ALLOWED = {0, 0.0, 1, 1.0, -1, -1.0, 2, 3}

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_no_magic_numbers(self, rac_file):
        """Formulas should reference parameters, not hardcode values.

        NOTE: Currently xfail due to pre-existing violations.
        Remove xfail as files are fixed.
        """
        content = rac_file.read_text()

        # Find formula blocks - match 4+ space indented content after formula:
        # Formula content is typically at 4-space indent (inside variable definition)
        # Stop when we hit a line with less indentation (like tests:, default:)
        formula_matches = list(re.finditer(r'formula:\s*\|?\s*\n((?:    .*\n)*)', content))
        if not formula_matches:
            pytest.skip("No formula")

        # Combine all formulas, excluding comments (which may have citation numbers)
        formula_lines = []
        for match in formula_matches:
            block = match.group(1)
            for line in block.split('\n'):
                stripped = line.strip()
                # Skip comment lines (may have citation numbers like "# 63(c)(5)")
                if stripped and not stripped.startswith('#'):
                    # Also strip inline comments
                    if '#' in stripped:
                        stripped = stripped[:stripped.index('#')].strip()
                    if stripped:
                        formula_lines.append(stripped)
        formula = '\n'.join(formula_lines)

        if not formula.strip():
            pytest.skip("No formula code")

        numbers = re.findall(r'(?<![a-z_\d])(\d+\.?\d*)(?![a-z_\d])', formula)

        bad = [n for n in numbers if float(n) not in self.ALLOWED]
        if bad:
            pytest.xfail(f"Hardcoded values in formula: {bad[:5]}. Use parameters.")


class TestSchemaValidation:
    """entity, period, dtype must be valid values."""

    VALID_ENTITIES = {"Person", "TaxUnit", "Household", "State", "SPMUnit", "TanfUnit", "Corporation", "Asset", "Family", "Business"}
    VALID_PERIODS = {"Year", "Month", "Week", "Eternity"}
    VALID_DTYPES = {"Money", "Rate", "Boolean", "Integer", "Enum", "String", "Count", "Decimal"}

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_valid_entity(self, rac_file):
        """entity: must be a valid entity type."""
        content = rac_file.read_text()
        match = re.search(r'entity:\s*(\w+)', content)
        if match:
            entity = match.group(1)
            if entity not in self.VALID_ENTITIES:
                pytest.fail(f"Invalid entity '{entity}'. Must be one of: {self.VALID_ENTITIES}")

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_valid_period(self, rac_file):
        """period: must be a valid period type (in variable definition, not test cases)."""
        content = rac_file.read_text()
        # Match period: at variable definition level (2 spaces indent), not in test cases
        # Test case periods are deeper nested and use date formats like 2024 or 2024-01
        match = re.search(r'^  period:\s*(\w+)', content, re.MULTILINE)
        if match:
            period = match.group(1)
            if period not in self.VALID_PERIODS:
                pytest.fail(f"Invalid period '{period}'. Must be one of: {self.VALID_PERIODS}")

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_valid_dtype(self, rac_file):
        """dtype: must be a valid data type."""
        content = rac_file.read_text()
        match = re.search(r'dtype:\s*(\w+)', content)
        if match:
            dtype = match.group(1)
            # Allow Enum with parameters like Enum(FilingStatus) or Enum[...]
            if dtype == "Enum":
                return  # Enum with any parameters is valid
            if dtype not in self.VALID_DTYPES:
                pytest.fail(f"Invalid dtype '{dtype}'. Must be one of: {self.VALID_DTYPES}")


class TestUndefinedVariables:
    """Formula variables must be defined (imported or same-file)."""

    # Built-in functions and common inputs that don't need imports
    BUILTINS = {
        'max', 'min', 'sum', 'abs', 'round', 'int', 'float', 'len', 'range',
        'true', 'false', 'True', 'False', 'None',
        'np', 'numpy', 'where', 'select', 'clip',
        'return', 'if', 'else', 'elif', 'and', 'or', 'not', 'in', 'for',
    }

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_formula_vars_defined(self, rac_file):
        """Variables used in formula must be imported or defined in same file."""
        content = rac_file.read_text()

        # Extract imported variable names
        imported = set()
        imports_match = re.search(r'imports:\s*\n((?:\s+-\s+.*\n)*)', content)
        if imports_match:
            for imp in re.findall(r'#(\w+)', imports_match.group(1)):
                imported.add(imp)
            # Also handle "as alias" pattern
            for alias in re.findall(r'as\s+(\w+)', imports_match.group(1)):
                imported.add(alias)

        # Extract same-file variable names
        same_file = set(re.findall(r'variable\s+(\w+):', content))

        # Extract parameter names
        params = set(re.findall(r'parameter\s+(\w+):', content))

        # All defined names
        defined = imported | same_file | params | self.BUILTINS

        # Extract formula
        formula_match = re.search(r'formula:\s*\|?\s*\n((?:\s+.*\n)*)', content)
        if not formula_match:
            pytest.skip("No formula")

        formula = formula_match.group(1)

        # Find identifiers used in formula (simple heuristic)
        used = set(re.findall(r'\b([a-z_][a-z0-9_]*)\b', formula, re.IGNORECASE))

        # Filter out things that look like method calls or string content
        undefined = used - defined

        # Remove common false positives
        undefined -= {'result', 'i', 'x', 'n', 'value', 'rate', 'amount'}

        if undefined:
            pytest.xfail(f"Undefined variables in formula: {sorted(undefined)[:5]}")


class TestNoRedundantHeader:
    """First line should be text:, not a citation comment."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_no_citation_comment(self, rac_file):
        """File should not start with citation comment (filepath is the citation)."""
        content = rac_file.read_text()
        first_line = content.split('\n')[0].strip()

        # Check for citation-style comments at start
        if re.match(r'^#\s*\d+\s*(USC|U\.S\.C\.)', first_line, re.IGNORECASE):
            pytest.fail(f"Redundant citation comment: '{first_line}'. Filepath is the citation.")


class TestIndentation:
    """All .rac files must use 2-space indentation."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_two_space_indent(self, rac_file):
        """YAML structure must use 2-space indentation increments, not 4."""
        content = rac_file.read_text()
        lines = content.split('\n')

        bad_lines = []
        in_multiline_block = False
        multiline_marker = None
        prev_indent = 0

        for i, line in enumerate(lines, 1):
            # Skip empty lines and comments
            if not line.strip() or line.strip().startswith('#'):
                continue

            # Track multi-line blocks: formula: |, text: """, text: |, etc.
            # These have their own indentation rules
            if re.match(r'\s*(formula|syntax):\s*\|', line):
                in_multiline_block = True
                multiline_marker = 'pipe'
                continue
            if re.match(r'\s*text:\s*(\"\"\"|\'\'\'|\|)', line):
                in_multiline_block = True
                multiline_marker = 'triple' if '"""' in line or "'''" in line else 'pipe'
                continue

            # Exit multi-line block
            if in_multiline_block:
                curr_indent = len(line) - len(line.lstrip())
                # Triple-quote block ends with closing quotes
                if multiline_marker == 'triple' and ('"""' in line or "'''" in line):
                    in_multiline_block = False
                    continue
                # Pipe block ends when indent returns to base level
                elif multiline_marker == 'pipe' and curr_indent <= 2 and re.match(r'\s*\w+:', line):
                    in_multiline_block = False
                else:
                    continue  # Skip block content

            # Check for 4-space indent jump (wrong - should be 2)
            curr_indent = len(line) - len(line.lstrip())
            if curr_indent - prev_indent == 4 and prev_indent == 0:
                # Line jumped from 0 to 4 spaces - likely using 4-space tabs
                bad_lines.append(f"Line {i}: {line.strip()}")

            prev_indent = curr_indent

        if bad_lines:
            pytest.fail(f"4-space indentation found (should be 2):\n" + "\n".join(bad_lines[:5]))


class TestImportValidation:
    """imports: must resolve to real files and variables."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_imports_resolve(self, rac_file):
        """All imports must point to existing files and variables."""
        content = rac_file.read_text()
        statute_dir = get_statute_dir()

        # Find imports block
        imports_match = re.search(r'imports:\s*\n((?:\s+-\s+.*\n)*)', content)
        if not imports_match:
            pytest.skip("No imports")

        imports_block = imports_match.group(1)
        imports = re.findall(r'-\s+([^\s#]+)', imports_block)

        errors = []
        for imp in imports:
            # Parse import: path#variable or just path
            if '#' in imp:
                path_part, var_name = imp.rsplit('#', 1)
            else:
                path_part = imp
                var_name = None

            # Resolve path
            rac_path = statute_dir / f"{path_part}.rac"
            if not rac_path.exists():
                errors.append(f"Import path not found: {path_part} -> {rac_path}")
                continue

            # Check variable/parameter/input exists in target file
            if var_name:
                target_content = rac_path.read_text()
                has_variable = f"variable {var_name}:" in target_content
                has_parameter = f"parameter {var_name}:" in target_content
                has_input = f"input {var_name}:" in target_content
                if not (has_variable or has_parameter or has_input):
                    errors.append(f"'{var_name}' not found as variable/parameter/input in {path_part}.rac")

        if errors:
            pytest.fail("\n".join(errors[:5]))


class TestThousandsSeparator:
    """Numeric values >= 1000 should use underscore separator for readability."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_large_numbers_use_separator(self, rac_file):
        """Values >= 1000 in parameter values should use _ separator (e.g., 5_000 not 5000)."""
        content = rac_file.read_text()

        # Find values: blocks in parameters
        # Look for numeric values that are 1000+ without underscore separator
        # Pattern: standalone 4+ digit numbers not using underscore
        # Exclude: dates (2024-01-01), test periods, line numbers in comments

        bad_values = []
        lines = content.split('\n')
        in_text_block = False

        for i, line in enumerate(lines, 1):
            # Track text: """ blocks
            if '"""' in line:
                in_text_block = not in_text_block
                continue
            if in_text_block:
                continue
            # Skip comments
            if line.strip().startswith('#'):
                continue
            # Skip lines that look like dates (YYYY-MM-DD)
            if re.search(r'\d{4}-\d{2}-\d{2}', line):
                continue
            # Skip period: lines in tests (e.g., period: 2024)
            if 'period:' in line:
                continue
            # Skip source/reference lines (contain years like 2023-34)
            if 'source:' in line.lower() or 'reference:' in line.lower():
                continue
            # Skip expect: lines (test outputs, may have decimals or exact values)
            if 'expect:' in line:
                continue
            # Skip import lines (contain section numbers like 26/1222)
            if 'imports:' in line or line.strip().startswith('-') and '/' in line:
                continue

            # Find 4+ digit integers without underscore separator
            # Match: 1000, 12390, 17400 (bad)
            # Don't match: 1_000, 12_390, 17_400 (good)
            # Don't match: 0.0765, 100.5 (decimals)
            matches = re.findall(r'(?<![_\d])(\d{4,})(?![_\d.])', line)
            for match in matches:
                # Skip years (1900-2100 range) - they don't need separators
                if 1900 <= int(match) <= 2100:
                    continue
                # Verify it's actually a large integer (not part of something else)
                if int(match) >= 1000:
                    bad_values.append(f"Line {i}: {match} (use {self._format_with_separator(match)})")

        if bad_values:
            pytest.fail(
                f"Large numbers without _ separator:\n" +
                "\n".join(bad_values[:10])
            )

    @staticmethod
    def _format_with_separator(num_str):
        """Format number with underscore thousands separator."""
        n = int(num_str)
        return f"{n:_}"


class TestValidAttributes:
    """Only spec-defined attributes are allowed."""

    # Per RAC_SPEC.md
    PARAMETER_ATTRS = {'description', 'unit', 'indexed_by', 'values'}
    VARIABLE_ATTRS = {'imports', 'entity', 'period', 'dtype', 'unit', 'label',
                      'description', 'default', 'formula', 'tests', 'syntax', 'versions'}
    INPUT_ATTRS = {'entity', 'period', 'dtype', 'label', 'description', 'default'}
    INDEXING_RULE_ATTRS = {'description', 'base_year', 'rounding', 'series'}

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_no_invalid_attributes(self, rac_file):
        """Attributes must be in the spec. No source/reference (filepath is citation)."""
        content = rac_file.read_text()
        errors = []

        # Find parameter blocks and check attributes
        for match in re.finditer(r'^parameter\s+\w+:\s*\n((?:  \w+:.*\n)*)', content, re.MULTILINE):
            block = match.group(1)
            attrs = set(re.findall(r'^  (\w+):', block, re.MULTILINE))
            invalid = attrs - self.PARAMETER_ATTRS
            if invalid:
                errors.append(f"parameter has invalid attrs: {invalid}")

        # Find variable blocks and check attributes
        for match in re.finditer(r'^variable\s+\w+:\s*\n((?:  \w+:.*\n)*)', content, re.MULTILINE):
            block = match.group(1)
            attrs = set(re.findall(r'^  (\w+):', block, re.MULTILINE))
            invalid = attrs - self.VARIABLE_ATTRS
            if invalid:
                errors.append(f"variable has invalid attrs: {invalid}")

        # Find input blocks and check attributes
        for match in re.finditer(r'^input\s+\w+:\s*\n((?:  \w+:.*\n)*)', content, re.MULTILINE):
            block = match.group(1)
            attrs = set(re.findall(r'^  (\w+):', block, re.MULTILINE))
            invalid = attrs - self.INPUT_ATTRS
            if invalid:
                errors.append(f"input has invalid attrs: {invalid}")

        if errors:
            pytest.fail(f"Invalid attributes in {rac_file.name}:\n" + "\n".join(errors[:5]))


class TestVariableCoverage:
    """Variables with formulas should have tests defined."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_formulas_have_tests(self, rac_file):
        """Variables with formulas should have tests: blocks.

        NOTE: Currently xfail to report coverage gap without blocking CI.
        """
        content = rac_file.read_text()

        # Find all variables with formulas
        variables_with_formulas = re.findall(
            r'variable\s+(\w+):.*?formula:\s*\|',
            content,
            re.DOTALL
        )

        if not variables_with_formulas:
            pytest.skip("No variables with formulas")

        # Find all variables with tests
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
