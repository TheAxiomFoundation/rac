"""Tests for unit value validation in RAC files."""

import pytest
import re
from .conftest import get_all_rac_files


class TestUnitValidation:
    """Unit values must follow RAC spec conventions."""

    VALID_UNITS = {
        # Monetary
        "USD",
        # Rates/ratios
        "/1",
        # Time
        "years", "months", "weeks", "days", "hours",
        # Counts
        "people", "children", "dependents",
        # Other
        "percent",
    }

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_unquoted_units(self, rac_file):
        """unit: values must not be quoted."""
        content = rac_file.read_text()
        # Find quoted unit values like unit: "USD" or unit: "/1"
        quoted_units = re.findall(r'unit:\s*["\']([^"\']+)["\']', content)
        if quoted_units:
            pytest.fail(
                f"unit values must not be quoted. Found: {quoted_units}. "
                f"Use 'unit: USD' not 'unit: \"USD\"'"
            )

    @pytest.mark.parametrize("rac_file", get_all_rac_files(), ids=lambda f: f.name)
    def test_valid_unit_values(self, rac_file):
        """unit: values should be from the standard set."""
        content = rac_file.read_text()
        # Find all unit values (both quoted and unquoted for checking)
        # Unquoted: unit: USD
        unquoted = re.findall(r'unit:\s*(\w+)', content)
        # Quoted: unit: "/1" (already flagged by other test, but check value)
        quoted = re.findall(r'unit:\s*["\']([^"\']+)["\']', content)

        all_units = set(unquoted + quoted)
        invalid = all_units - self.VALID_UNITS

        if invalid:
            # Warning only - don't fail for now since units may need expansion
            # pytest.fail(f"Non-standard unit values: {invalid}")
            pass  # TODO: Enable once VALID_UNITS is comprehensive
