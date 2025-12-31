"""End-to-end EITC calculation tests using override resolver.

Validates that:
1. Override resolver loads IRS guidance correctly
2. EITC calculations match IRS published tables
3. Integration with cosilico-us statute files works
"""

import numpy as np
import pytest
from pathlib import Path

from src.rac.parameters.override_resolver import create_resolver


# Path to cosilico-us (absolute path for reliability)
COSILICO_US_ROOT = Path("/Users/maxghenis/CosilicoAI/cosilico-us")


@pytest.fixture
def resolver():
    """Create resolver pointing to cosilico-us."""
    if not COSILICO_US_ROOT.exists():
        pytest.skip("cosilico-us not found")
    return create_resolver(str(COSILICO_US_ROOT))


def calculate_eitc(
    earned_income: float,
    agi: float,
    num_children: int,
    filing_status: str,
    resolver,
    tax_year: int = 2024,
) -> float:
    """Calculate EITC using resolved parameters.

    This implements the formula from 26 USC §32(a):
    credit = min(phase_in_credit, max_credit) - phase_out_reduction

    Phase-in: credit_percentage × min(earned_income, earned_income_amount)
    Phase-out: phaseout_percentage × max(0, income - phaseout_threshold)
    """
    n = min(num_children, 3)  # Caps at 3+

    # Get credit percentage from statute (not inflation-adjusted)
    # These are fixed in the statute table
    credit_percentages = {0: 0.0765, 1: 0.34, 2: 0.40, 3: 0.45}
    phaseout_percentages = {0: 0.0765, 1: 0.1598, 2: 0.2106, 3: 0.2106}

    credit_pct = credit_percentages[n]
    phaseout_pct = phaseout_percentages[n]

    # Get inflation-adjusted amounts from resolver (IRS 2024 values)
    earned_income_amount = resolver.resolve(
        "statute/26/32/b/2/A/base_amounts",
        fragment="earned_income_amount",
        tax_year=tax_year,
        num_qualifying_children=n,
    )

    phaseout_amount = resolver.resolve(
        "statute/26/32/b/2/A/base_amounts",
        fragment="phaseout_amount",
        tax_year=tax_year,
        num_qualifying_children=n,
    )

    joint_adjustment = resolver.resolve(
        "statute/26/32/b/2/B/base_joint_return_adjustment",
        fragment="joint_return_adjustment",
        tax_year=tax_year,
    )

    # Adjust phaseout threshold for joint filers
    if filing_status == "JOINT":
        phaseout_threshold = phaseout_amount + joint_adjustment
    else:
        phaseout_threshold = phaseout_amount

    # Phase-in credit: credit_pct × min(earned_income, earned_income_amount)
    phase_in_credit = credit_pct * min(earned_income, earned_income_amount)

    # Max credit (plateau)
    max_credit = credit_pct * earned_income_amount

    # Phase-out uses greater of AGI or earned income
    income_for_phaseout = max(agi, earned_income)

    # Phase-out reduction
    if income_for_phaseout > phaseout_threshold:
        phase_out_reduction = phaseout_pct * (income_for_phaseout - phaseout_threshold)
    else:
        phase_out_reduction = 0

    # Final credit
    credit = max(0, min(phase_in_credit, max_credit) - phase_out_reduction)

    return round(credit, 2)


class TestEITCCalculation:
    """Test EITC calculations against IRS tables."""

    def test_resolver_loads_2024_values(self, resolver):
        """Verify 2024 IRS values are loaded correctly."""
        # Check earned income amounts
        ei_0 = resolver.resolve(
            "statute/26/32/b/2/A/base_amounts",
            fragment="earned_income_amount",
            tax_year=2024,
            num_qualifying_children=0,
        )
        assert ei_0 == 8260, f"Expected 8260, got {ei_0}"

        ei_1 = resolver.resolve(
            "statute/26/32/b/2/A/base_amounts",
            fragment="earned_income_amount",
            tax_year=2024,
            num_qualifying_children=1,
        )
        assert ei_1 == 12390, f"Expected 12390, got {ei_1}"

        ei_2 = resolver.resolve(
            "statute/26/32/b/2/A/base_amounts",
            fragment="earned_income_amount",
            tax_year=2024,
            num_qualifying_children=2,
        )
        assert ei_2 == 17400, f"Expected 17400, got {ei_2}"

    def test_resolver_loads_phaseout_amounts(self, resolver):
        """Verify phaseout amounts are correct (from Rev. Proc. 2023-34)."""
        po_0 = resolver.resolve(
            "statute/26/32/b/2/A/base_amounts",
            fragment="phaseout_amount",
            tax_year=2024,
            num_qualifying_children=0,
        )
        assert po_0 == 10330  # Corrected value

        po_1 = resolver.resolve(
            "statute/26/32/b/2/A/base_amounts",
            fragment="phaseout_amount",
            tax_year=2024,
            num_qualifying_children=1,
        )
        assert po_1 == 22720  # Corrected value

    def test_resolver_loads_joint_adjustment(self, resolver):
        """Verify joint return adjustment is correct."""
        adj = resolver.resolve(
            "statute/26/32/b/2/B/base_joint_return_adjustment",
            fragment="joint_return_adjustment",
            tax_year=2024,
        )
        assert adj == 6920

    def test_eitc_1_child_20k(self, resolver):
        """Test: 1 child, $20,000 income → $4,213"""
        credit = calculate_eitc(
            earned_income=20000,
            agi=20000,
            num_children=1,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert credit == 4212.60, f"Expected 4212.60, got {credit}"

    def test_eitc_2_children_30k(self, resolver):
        """Test: 2 children, $30,000 income → $5,427 (verified against PolicyEngine)"""
        credit = calculate_eitc(
            earned_income=30000,
            agi=30000,
            num_children=2,
            filing_status="SINGLE",
            resolver=resolver,
        )
        # Phase-in: 0.40 × 17400 = 6960 (max credit)
        # Phase-out: 0.2106 × (30000 - 22720) = 0.2106 × 7280 = 1533.17
        # Credit: 6960 - 1533.17 = 5426.83
        assert abs(credit - 5426.83) < 1, f"Expected ~5426.83, got {credit}"

    def test_eitc_0_children_15k(self, resolver):
        """Test: 0 children, $15,000 income → ~$275 (verified against PolicyEngine)"""
        credit = calculate_eitc(
            earned_income=15000,
            agi=15000,
            num_children=0,
            filing_status="SINGLE",
            resolver=resolver,
        )
        # Phase-in: 0.0765 × 8260 = 631.89 (max credit)
        # Phase-out: 0.0765 × (15000 - 10330) = 0.0765 × 4670 = 357.26
        # Credit: 631.89 - 357.26 = 274.63
        assert abs(credit - 274.63) < 1, f"Expected ~274.63, got {credit}"

    def test_eitc_joint_filer_higher_threshold(self, resolver):
        """Test that joint filers get higher phaseout threshold."""
        # At $25,000, single filer with 1 child is in phaseout
        # Joint filer should still be below phaseout (21560 + 6920 = 28480)

        single_credit = calculate_eitc(
            earned_income=25000,
            agi=25000,
            num_children=1,
            filing_status="SINGLE",
            resolver=resolver,
        )

        joint_credit = calculate_eitc(
            earned_income=25000,
            agi=25000,
            num_children=1,
            filing_status="JOINT",
            resolver=resolver,
        )

        # Joint credit should be higher (less phaseout reduction)
        assert joint_credit > single_credit

    def test_eitc_zero_income(self, resolver):
        """Test: $0 income → $0 credit"""
        credit = calculate_eitc(
            earned_income=0,
            agi=0,
            num_children=2,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert credit == 0

    def test_eitc_high_income_phased_out(self, resolver):
        """Test: income above phaseout end → $0 credit"""
        credit = calculate_eitc(
            earned_income=60000,
            agi=60000,
            num_children=3,
            filing_status="SINGLE",
            resolver=resolver,
        )
        # Phaseout end for 3 children is around $59,899
        assert credit == 0
