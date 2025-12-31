"""Tests for parameter override resolution."""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.rac.parameters.override_resolver import OverrideResolver, create_resolver


@pytest.fixture
def rules_dir():
    """Create a temporary rules directory with test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rules = Path(tmpdir)

        # Create statute directory structure
        statute_dir = rules / "statute" / "26" / "32" / "b" / "2" / "A"
        statute_dir.mkdir(parents=True)

        # Base amounts YAML (statute values)
        base_amounts = {
            "reference": "26 USC § 32(b)(2)(A)",
            "inflation_adjustment": {
                "section": "§32(j)(1)",
                "base_year": 1995,
            },
            "earned_income_amount": {
                0: 4220,
                1: 6330,
                2: 8890,
                3: 8890,
            },
            "phaseout_amount": {
                0: 5280,
                1: 11610,
                2: 11610,
                3: 11610,
            },
        }
        with open(statute_dir / "base_amounts.yaml", "w") as f:
            yaml.dump(base_amounts, f)

        # Create IRS guidance directory
        irs_dir = rules / "irs" / "rev-proc-2023-34"
        irs_dir.mkdir(parents=True)

        # IRS guidance YAML (overrides)
        irs_guidance = {
            "source": {
                "document": "Rev. Proc. 2023-34",
                "effective_date": "2024-01-01",
            },
            "earned_income_amount": {
                "implements": "statute/26/32/j/1",
                "overrides": "statute/26/32/b/2/A/base_amounts#earned_income_amount",
                "indexed_by": "num_qualifying_children",
                "values": {
                    0: 8260,
                    1: 12390,
                    2: 17400,
                    3: 17400,
                },
            },
            "phaseout_amount": {
                "implements": "statute/26/32/j/1",
                "overrides": "statute/26/32/b/2/A/base_amounts#phaseout_amount",
                "indexed_by": "num_qualifying_children",
                "values": {
                    0: 9800,
                    1: 21560,
                    2: 21560,
                    3: 21560,
                },
            },
        }
        with open(irs_dir / "eitc-2024.yaml", "w") as f:
            yaml.dump(irs_guidance, f)

        yield rules


def test_load_irs_overrides(rules_dir):
    """Test that IRS overrides are loaded correctly."""
    resolver = create_resolver(str(rules_dir))

    # Check that overrides were indexed
    assert resolver.index.has_override(
        "statute/26/32/b/2/A/base_amounts#earned_income_amount",
        2024,
    )
    assert resolver.index.has_override(
        "statute/26/32/b/2/A/base_amounts#phaseout_amount",
        2024,
    )


def test_resolve_with_override(rules_dir):
    """Test resolving a parameter with an IRS override."""
    resolver = create_resolver(str(rules_dir))

    # Should get IRS 2024 value, not statute base
    value = resolver.resolve(
        "statute/26/32/b/2/A/base_amounts",
        fragment="earned_income_amount",
        tax_year=2024,
        num_qualifying_children=1,
    )
    assert value == 12390  # IRS 2024 value


def test_resolve_without_override(rules_dir):
    """Test resolving a parameter without an override (different year)."""
    resolver = create_resolver(str(rules_dir))

    # For 2020, no IRS override exists - should get base value
    value = resolver.resolve(
        "statute/26/32/b/2/A/base_amounts",
        fragment="earned_income_amount",
        tax_year=2020,
        num_qualifying_children=1,
    )
    assert value == 6330  # Base statute value


def test_resolve_indexed_parameter(rules_dir):
    """Test resolving indexed parameters for different child counts."""
    resolver = create_resolver(str(rules_dir))

    # Test all child counts
    expected = {0: 8260, 1: 12390, 2: 17400, 3: 17400}

    for n_children, expected_value in expected.items():
        value = resolver.resolve(
            "statute/26/32/b/2/A/base_amounts",
            fragment="earned_income_amount",
            tax_year=2024,
            num_qualifying_children=n_children,
        )
        assert value == expected_value, f"Failed for {n_children} children"


def test_resolve_phaseout_amount(rules_dir):
    """Test resolving phaseout amounts."""
    resolver = create_resolver(str(rules_dir))

    value = resolver.resolve(
        "statute/26/32/b/2/A/base_amounts",
        fragment="phaseout_amount",
        tax_year=2024,
        num_qualifying_children=0,
    )
    assert value == 9800  # IRS 2024 value for 0 children
