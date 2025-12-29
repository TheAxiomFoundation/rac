"""Tests for text content and hardcoded values."""

import pytest
import re
from .conftest import get_all_rac_files


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

        if re.match(r'^(provides|this section|computation)', text.lower()):
            pytest.fail(f"text: looks like summary, not statute: '{text[:50]}...'")


class TestTextFieldRequired:
    """Files should have a text: field with actual statute text."""

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_has_text_field(self, rac_file):
        """Files should include the statute text in a text: field."""
        content = rac_file.read_text()

        has_text = bool(re.search(r'text:\s*"""', content))

        if not has_text:
            pytest.xfail("Missing text: field with statute text")


class TestNoHardcodedValues:
    """Formulas should only use 0, 1, -1, 2, 3 as literals."""

    ALLOWED = {0, 0.0, 1, 1.0, -1, -1.0, 2, 3}

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_no_magic_numbers(self, rac_file):
        """Formulas should reference parameters, not hardcode values."""
        content = rac_file.read_text()

        formula_matches = list(re.finditer(r'formula:\s*\|?\s*\n((?:    .*\n)*)', content))
        if not formula_matches:
            pytest.skip("No formula")

        formula_lines = []
        for match in formula_matches:
            block = match.group(1)
            for line in block.split('\n'):
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
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
            pytest.fail(f"Hardcoded values in formula: {bad[:5]}. Use parameters.")
