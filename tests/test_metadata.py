"""Tests for metadata field support in variable declarations.

Covers: parsing, field storage, compiler pass-through, ordering, and error cases.
"""

from datetime import date

import pytest

from rac import compile, parse
from rac.parser import ParseError


class TestMetadataParsing:
    """Test that metadata fields are correctly parsed from .rac source."""

    def test_source_metadata(self):
        module = parse("""
            variable gov/irs/earned_income_credit:
                source: "26 USC 32"
                from 2024-01-01: 1000
        """)
        var = module.variables[0]
        assert var.source == "26 USC 32"

    def test_label_metadata(self):
        module = parse("""
            variable gov/irs/standard_deduction:
                label: "Standard Deduction"
                from 2024-01-01: 14600
        """)
        var = module.variables[0]
        assert var.label == "Standard Deduction"

    def test_description_metadata(self):
        module = parse("""
            variable gov/irs/standard_deduction:
                description: "Amount subtracted from AGI for filers who do not itemize"
                from 2024-01-01: 14600
        """)
        var = module.variables[0]
        assert var.description == "Amount subtracted from AGI for filers who do not itemize"

    def test_unit_metadata(self):
        module = parse("""
            variable gov/irs/tax_rate:
                unit: "percent"
                from 2024-01-01: 0.22
        """)
        var = module.variables[0]
        assert var.unit == "percent"

    def test_all_metadata_fields(self):
        module = parse("""
            variable gov/irs/earned_income_credit:
                source: "26 USC 32"
                label: "Earned Income Tax Credit"
                description: "Refundable credit for low-to-moderate income workers"
                unit: "USD"
                from 2024-01-01: max(0, income * 0.34)
        """)
        var = module.variables[0]
        assert var.source == "26 USC 32"
        assert var.label == "Earned Income Tax Credit"
        assert var.description == "Refundable credit for low-to-moderate income workers"
        assert var.unit == "USD"

    def test_metadata_with_entity(self):
        module = parse("""
            variable person/earned_income_credit:
                source: "26 USC 32"
                entity: person
                from 2024-01-01: max(0, income * 0.34)
        """)
        var = module.variables[0]
        assert var.source == "26 USC 32"
        assert var.entity == "person"

    def test_entity_before_metadata(self):
        module = parse("""
            variable person/earned_income_credit:
                entity: person
                source: "26 USC 32"
                from 2024-01-01: max(0, income * 0.34)
        """)
        var = module.variables[0]
        assert var.entity == "person"
        assert var.source == "26 USC 32"

    def test_metadata_with_entity_and_temporal(self):
        module = parse("""
            variable person/earned_income_credit:
                source: "26 USC 32"
                label: "Earned Income Tax Credit"
                unit: "USD"
                entity: person
                from 2024-01-01: max(0, income * 0.34)
                from 2025-01-01: max(0, income * 0.36)
        """)
        var = module.variables[0]
        assert var.source == "26 USC 32"
        assert var.label == "Earned Income Tax Credit"
        assert var.unit == "USD"
        assert var.entity == "person"
        assert len(var.values) == 2

    def test_metadata_order_does_not_matter(self):
        """Metadata fields can appear in any order relative to each other."""
        module = parse("""
            variable gov/irs/rate:
                unit: "percent"
                description: "Federal tax rate"
                label: "Tax Rate"
                source: "26 USC 1"
                from 2024-01-01: 0.22
        """)
        var = module.variables[0]
        assert var.unit == "percent"
        assert var.description == "Federal tax rate"
        assert var.label == "Tax Rate"
        assert var.source == "26 USC 1"

    def test_no_metadata_still_works(self):
        """Variables without metadata should parse exactly as before."""
        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.20
        """)
        var = module.variables[0]
        assert var.source is None
        assert var.label is None
        assert var.description is None
        assert var.unit is None

    def test_metadata_defaults_to_none(self):
        """Omitted metadata fields default to None."""
        module = parse("""
            variable gov/rate:
                source: "26 USC 1"
                from 2024-01-01: 0.20
        """)
        var = module.variables[0]
        assert var.source == "26 USC 1"
        assert var.label is None
        assert var.description is None
        assert var.unit is None


class TestMetadataErrors:
    """Test error handling for malformed metadata."""

    def test_metadata_requires_string_value(self):
        with pytest.raises(ParseError, match="requires a string value"):
            parse("""
                variable gov/rate:
                    source: 42
                    from 2024-01-01: 0.20
            """)

    def test_metadata_requires_string_not_ident(self):
        with pytest.raises(ParseError, match="requires a string value"):
            parse("""
                variable gov/rate:
                    source: some_ident
                    from 2024-01-01: 0.20
            """)


class TestMetadataCompilerPassthrough:
    """Test that metadata survives parse -> compile -> IR."""

    def test_metadata_in_resolved_var(self):
        module = parse("""
            variable gov/irs/rate:
                source: "26 USC 1"
                label: "Federal Rate"
                description: "Basic tax rate"
                unit: "percent"
                from 2024-01-01: 0.22
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        resolved = ir.variables["gov/irs/rate"]
        assert resolved.source == "26 USC 1"
        assert resolved.label == "Federal Rate"
        assert resolved.description == "Basic tax rate"
        assert resolved.unit == "percent"

    def test_metadata_none_when_absent_in_ir(self):
        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.20
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        resolved = ir.variables["gov/rate"]
        assert resolved.source is None
        assert resolved.label is None
        assert resolved.description is None
        assert resolved.unit is None

    def test_partial_metadata_in_ir(self):
        module = parse("""
            variable gov/rate:
                source: "26 USC 1"
                unit: "percent"
                from 2024-01-01: 0.22
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        resolved = ir.variables["gov/rate"]
        assert resolved.source == "26 USC 1"
        assert resolved.unit == "percent"
        assert resolved.label is None
        assert resolved.description is None

    def test_metadata_with_entity_in_ir(self):
        module = parse("""
            entity person:
                income: float

            variable person/tax:
                source: "26 USC 1"
                label: "Income Tax"
                entity: person
                from 2024-01-01: income * 0.22
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        resolved = ir.variables["person/tax"]
        assert resolved.source == "26 USC 1"
        assert resolved.label == "Income Tax"
        assert resolved.entity == "person"
