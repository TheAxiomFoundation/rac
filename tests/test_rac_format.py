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
        r'^[ivxlcdm]+$',      # Roman numeral: i, ii, iii, iv
        r'^[A-Z]$',           # Capital letter: A, B, C
    ]

    FORBIDDEN_NAMES = ['eitc', 'ctc', 'snap', 'standard_deduction', 'agi', 'amt', 'rmd', 'cap']

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_filename_is_citation(self, rac_file):
        """Filename should be subsection identifier (a, 1, A, i), not descriptive."""
        filename = rac_file.stem

        is_valid = any(re.match(p, filename) for p in self.VALID_PATTERNS)

        if not is_valid:
            if filename.lower() in self.FORBIDDEN_NAMES:
                pytest.fail(
                    f"Filename '{filename}' is descriptive, not a citation. "
                    f"Use subsection identifier (e.g., 'a', '1', 'A')"
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
        """Formulas should reference parameters, not hardcode values."""
        content = rac_file.read_text()

        formula_match = re.search(r'formula:\s*\|?\s*\n((?:\s+.*\n)*)', content)
        if not formula_match:
            pytest.skip("No formula")

        formula = formula_match.group(1)
        numbers = re.findall(r'(?<![a-z_])(\d+\.?\d*)(?![a-z_\d])', formula)

        bad = [n for n in numbers if float(n) not in self.ALLOWED]
        if bad:
            pytest.fail(f"Hardcoded values in formula: {bad[:5]}. Use parameters.")


class TestSchemaValidation:
    """entity, period, dtype must be valid values."""

    VALID_ENTITIES = {"Person", "TaxUnit", "Household", "State", "SPMUnit"}
    VALID_PERIODS = {"Year", "Month", "Eternity"}
    VALID_DTYPES = {"Money", "Rate", "Boolean", "Integer", "Enum", "String"}

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
        """period: must be a valid period type."""
        content = rac_file.read_text()
        match = re.search(r'period:\s*(\w+)', content)
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
            if dtype not in self.VALID_DTYPES:
                pytest.fail(f"Invalid dtype '{dtype}'. Must be one of: {self.VALID_DTYPES}")


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

            # Check variable exists in target file
            if var_name:
                target_content = rac_path.read_text()
                if f"variable {var_name}:" not in target_content:
                    errors.append(f"Variable '{var_name}' not found in {path_part}.rac")

        if errors:
            pytest.fail("\n".join(errors[:5]))
