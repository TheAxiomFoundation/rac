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

        # Try triple-quote format first
        text_match = re.search(r'text:\s*"""(.*?)"""', content, re.DOTALL)
        if not text_match:
            # Try YAML block scalar format (text: |)
            text_match = re.search(r'text:\s*\|\s*\n((?:  .*\n)*)', content)
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

        # Accept both formats: text: """ or text: |
        has_text = bool(re.search(r'text:\s*("""|[\|>])', content))

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


class TestParameterValuesInText:
    """Parameter values must appear in the statute text field.

    This catches:
    - Hallucinated values
    - Copy-paste errors from other statutes
    - Rev Proc values when encoding statute-only
    """

    ALWAYS_ALLOWED = {0, 0.0, 1, 1.0}  # Common defaults

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_param_values_in_text(self, rac_file):
        """Every parameter value must appear somewhere in text: field."""
        content = rac_file.read_text()

        # Extract text field
        text_match = re.search(r'text:\s*"""(.*?)"""', content, re.DOTALL)
        if not text_match:
            text_match = re.search(r'text:\s*\|\s*\n((?:  .*\n)*)', content)
        if not text_match:
            pytest.skip("No text: field")

        text = text_match.group(1)

        # Extract parameter values
        # Pattern: parameter name:\n  values:\n    date: value
        param_pattern = r'parameter\s+(\w+):\s*\n\s*values:\s*\n((?:\s+[\d-]+:\s*[\d.]+\n?)+)'

        missing = []
        for match in re.finditer(param_pattern, content):
            param_name = match.group(1)
            values_block = match.group(2)

            # Extract values (skip date keys)
            for val_match in re.finditer(r'[\d-]+:\s*([\d.]+)', values_block):
                value = float(val_match.group(1))

                if value in self.ALWAYS_ALLOWED:
                    continue

                if not self._value_in_text(value, text):
                    missing.append(f"{param_name}: {value}")

        if missing:
            pytest.fail(f"Parameter values not found in text: {missing[:5]}")

    def _value_in_text(self, value: float, text: str) -> bool:
        """Check if value appears in text in any common format."""
        text_lower = text.lower()

        # Check exact value (as int if whole number)
        if value == int(value):
            int_val = int(value)
            if re.search(rf'\b{int_val}\b', text):
                return True
            # With commas (100,000)
            if f"{int_val:,}" in text:
                return True

        # Check decimal
        if str(value) in text:
            return True

        # Check as percentage (0.075 -> 7.5%, 7.5 percent)
        if 0 < value < 1:
            pct = value * 100
            patterns = [
                rf'{pct}\s*%',
                rf'{pct}\s*percent',
                str(pct),
            ]
            if pct == int(pct):
                patterns.extend([rf'{int(pct)}\s*%', rf'{int(pct)}\s*percent'])
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return True

        # Check with dollar sign
        if value == int(value):
            int_val = int(value)
            if f"${int_val}" in text or f"${int_val:,}" in text:
                return True

        return False
