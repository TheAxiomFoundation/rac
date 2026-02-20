"""Tests for .rac migration script.

TDD: these tests define what migrated output should look like,
and verify the new parser can parse it.
"""

import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from migrate_rac import migrate_rac

from rac import parse


class TestBasicMigration:
    """Test basic declaration migration."""

    def test_simple_temporal_value(self):
        old = "threshold:\n  from 2024-01-01: 14600\n"
        result = migrate_rac(old)
        assert "threshold:" in result
        assert "from 2024-01-01: 14600" in result
        # Must parse
        parse(result)

    def test_multiple_temporal_values(self):
        old = (
            "rate:\n"
            "  from 2018-01-01: 0.10\n"
            "  from 2024-01-01: 0.12\n"
        )
        result = migrate_rac(old)
        assert "rate:" in result
        assert "from 2018-01-01: 0.10" in result
        assert "from 2024-01-01: 0.12" in result
        parse(result)

    def test_with_entity(self):
        old = (
            "credit:\n"
            "  entity: TaxUnit\n"
            "  from 2024-01-01: 1000\n"
        )
        result = migrate_rac(old)
        assert "credit:" in result
        assert "entity: taxunit" in result
        assert "from 2024-01-01: 1000" in result
        parse(result)

    def test_expression_temporal(self):
        old = (
            "net_income:\n"
            "  from 2024-01-01: gross_income - deductions\n"
        )
        result = migrate_rac(old)
        assert "net_income:" in result
        assert "from 2024-01-01: gross_income - deductions" in result
        parse(result)


class TestMetadataStripping:
    """Test that metadata fields are stripped."""

    def test_strips_description(self):
        old = (
            "rate:\n"
            '  description: "Some description"\n'
            "  from 2024-01-01: 0.10\n"
        )
        result = migrate_rac(old)
        assert "description" not in result
        assert "from 2024-01-01: 0.10" in result
        parse(result)

    def test_strips_all_metadata(self):
        old = (
            "credit:\n"
            "  entity: TaxUnit\n"
            "  period: Year\n"
            "  dtype: Money\n"
            "  unit: USD\n"
            '  label: "Tax Credit"\n'
            '  source: "26 USC 24"\n'
            "  indexed_by: cpi_adjustment\n"
            "  default: 0\n"
            "  from 2024-01-01: 1000\n"
        )
        result = migrate_rac(old)
        assert "period" not in result
        assert "dtype" not in result
        assert "unit: USD" not in result  # unit metadata stripped
        assert "label" not in result
        assert "source" not in result
        assert "indexed_by" not in result
        assert "default" not in result
        assert "entity: taxunit" in result
        assert "from 2024-01-01: 1000" in result
        parse(result)

    def test_strips_imports(self):
        old = (
            "credit:\n"
            "  imports:\n"
            "    - 26/24/a#ctc_maximum\n"
            "    - 26/24/b#ctc_after_phaseout\n"
            "  from 2024-01-01: ctc_maximum - ctc_after_phaseout\n"
        )
        result = migrate_rac(old)
        assert "imports" not in result
        # ctc_maximum should only appear in formula, not metadata
        lines_before_formula = result.split("from ")[0]
        assert "ctc_maximum" not in lines_before_formula
        parse(result)

    def test_strips_tests(self):
        old = (
            "credit:\n"
            "  from 2024-01-01: income * 0.1\n"
            "  tests:\n"
            "    - inputs: {income: 50000}\n"
            "      expect: 5000\n"
        )
        result = migrate_rac(old)
        assert "tests" not in result
        assert "inputs" not in result
        parse(result)


class TestStatuteText:
    """Test triple-quoted statute text conversion."""

    def test_multiline_statute_text(self):
        old = (
            '"""\n'
            "(a) In general\n"
            "The credit shall be...\n"
            '"""\n'
            "\n"
            "credit:\n"
            "  from 2024-01-01: 100\n"
        )
        result = migrate_rac(old)
        assert '"""' not in result
        assert "# (a) In general" in result
        assert "# The credit shall be..." in result
        parse(result)

    def test_single_line_statute_text(self):
        old = '"""This is a short statute."""\n\nrate:\n  from 2024-01-01: 0.1\n'
        result = migrate_rac(old)
        assert '"""' not in result
        assert "# This is a short statute." in result
        parse(result)


class TestFormulaConversion:
    """Test multi-line formula to expression conversion."""

    def test_simple_return(self):
        old = (
            "credit:\n"
            "  from 2024-01-01:\n"
            "    return income * 0.1\n"
        )
        result = migrate_rac(old)
        assert "from 2024-01-01: income * 0.1" in result
        parse(result)

    def test_assignment_then_return(self):
        old = (
            "adjusted:\n"
            "  from 2024-01-01:\n"
            "    result = base * (1 + cola)\n"
            "    return result\n"
        )
        result = migrate_rac(old)
        assert "from 2024-01-01: base * (1 + cola)" in result
        parse(result)

    def test_conditional_return(self):
        old = (
            "credit:\n"
            "  from 2024-01-01:\n"
            "    return max(0, income - threshold)\n"
        )
        result = migrate_rac(old)
        assert "from 2024-01-01: max(0, income - threshold)" in result
        parse(result)

    def test_if_else_formula(self):
        """Multi-line if/else should be handled."""
        old = (
            "credit:\n"
            "  from 2013-01-01:\n"
            "    if not is_eligible:\n"
            "      return 0\n"
            "    return amount\n"
        )
        result = migrate_rac(old)
        # This is a complex case - the script should produce something
        assert "credit:" in result
        assert "from 2013-01-01:" in result


class TestEnumStripping:
    """Test enum block removal."""

    def test_strips_enum(self):
        old = (
            "enum FilingStatus:\n"
            "  values:\n"
            "    - SINGLE\n"
            "    - JOINT\n"
            "\n"
            "rate:\n"
            "  from 2024-01-01: 0.1\n"
        )
        result = migrate_rac(old)
        assert "enum" not in result
        assert "FilingStatus" not in result
        assert "rate:" in result
        parse(result)


class TestComments:
    """Test comment preservation."""

    def test_preserves_comments(self):
        old = (
            "# This is a comment\n"
            "rate:\n"
            "  from 2024-01-01: 0.1\n"
        )
        result = migrate_rac(old)
        assert "# This is a comment" in result
        parse(result)

    def test_preserves_header_comment(self):
        old = (
            "# 26 USC 32 - Earned Income Credit\n"
            "\n"
            "rate:\n"
            "  from 2024-01-01: 0.1\n"
        )
        result = migrate_rac(old)
        assert "# 26 USC 32 - Earned Income Credit" in result
        parse(result)


class TestMultipleDeclarations:
    """Test files with multiple declarations."""

    def test_two_declarations(self):
        old = (
            "rate:\n"
            "  from 2024-01-01: 0.10\n"
            "\n"
            "threshold:\n"
            "  from 2024-01-01: 50000\n"
        )
        result = migrate_rac(old)
        assert "rate:" in result
        assert "threshold:" in result
        m = parse(result)
        assert len(m.variables) == 2

    def test_declaration_with_no_temporals(self):
        """Declaration with only metadata and no temporal values gets a placeholder."""
        old = (
            "input_var:\n"
            "  entity: TaxUnit\n"
            "  period: Year\n"
            "  dtype: Money\n"
            '  label: "Some Input"\n'
            "  default: 0\n"
        )
        result = migrate_rac(old)
        assert "input_var:" in result
        # Should have a placeholder temporal value
        assert "from 2024-01-01:" in result
        parse(result)


class TestRealWorldFiles:
    """Test against patterns found in actual rac-us files."""

    def test_bracket_thresholds(self):
        """Tax bracket threshold pattern from 26 USC 1(j)(2)(A)."""
        old = (
            "joint_bracket_2_threshold:\n"
            '  description: "Second bracket threshold for MFJ"\n'
            "  indexed_by: cpi_adjustment\n"
            "  from 2018-01-01: 19050\n"
        )
        result = migrate_rac(old)
        assert "joint_bracket_2_threshold:" in result
        assert "from 2018-01-01: 19050" in result
        assert "description" not in result
        assert "indexed_by" not in result
        parse(result)

    def test_inflation_formula(self):
        """Inflation adjustment pattern from 26 USC 32(j)."""
        old = (
            "eitc_adjusted_amount:\n"
            "  entity: TaxUnit\n"
            "  period: Year\n"
            "  dtype: Money\n"
            "  from 1996-01-01:\n"
            "    # Apply inflation adjustment\n"
            "    adjusted = base_amount * (1 + cola)\n"
            "    return adjusted\n"
        )
        result = migrate_rac(old)
        assert "eitc_adjusted_amount:" in result
        assert "entity: taxunit" in result
        assert "from 1996-01-01: base_amount * (1 + cola)" in result
        parse(result)

    def test_full_file_with_statute_text(self):
        """Full file pattern with statute text, comments, and declarations."""
        old = (
            "# 26 USC 32(j) - Inflation adjustments\n"
            "\n"
            '"""\n'
            "(j) Inflation adjustments\n"
            "(1) In general\n"
            "Each dollar amount shall be increased...\n"
            '"""\n'
            "\n"
            "base_year:\n"
            '  description: "Base year for adjustments"\n'
            "  from 2016-01-01: 2015\n"
            "\n"
            "rounding:\n"
            "  unit: USD\n"
            "  from 1996-01-01: 10\n"
        )
        result = migrate_rac(old)
        assert "# 26 USC 32(j)" in result
        assert "# (j) Inflation adjustments" in result
        assert "base_year:" in result
        assert "rounding:" in result
        assert "from 2016-01-01: 2015" in result
        assert "from 1996-01-01: 10" in result
        m = parse(result)
        assert len(m.variables) == 2
