"""End-to-end Child Tax Credit calculation tests using override resolver.

Validates that:
1. Override resolver loads IRS guidance correctly
2. CTC calculations match IRS published tables
3. Integration with cosilico-us statute files works

Reference:
- 26 USC Section 24 - Child Tax Credit
- Rev. Proc. 2023-34, Section 3.10 - CTC inflation adjustments for 2024
"""

import math
from datetime import date
import pytest
from pathlib import Path

from rac.parameters.override_resolver import create_resolver


# Path to cosilico-us (absolute path for reliability)
COSILICO_US_ROOT = Path("/Users/maxghenis/CosilicoAI/cosilico-us")


@pytest.fixture
def resolver():
    """Create resolver pointing to cosilico-us."""
    if not COSILICO_US_ROOT.exists():
        pytest.skip("cosilico-us not found")
    return create_resolver(str(COSILICO_US_ROOT))


def get_value_for_year(values_dict: dict, tax_year: int):
    """Get the applicable value from a date-keyed dict for a tax year.

    Finds the most recent date that is <= the end of the tax year.
    """
    target_date = date(tax_year, 12, 31)
    applicable_value = None
    applicable_date = None

    for d, value in values_dict.items():
        if d <= target_date:
            if applicable_date is None or d > applicable_date:
                applicable_date = d
                applicable_value = value

    return applicable_value


def calculate_ctc(
    agi: float,
    num_qualifying_children: int,
    filing_status: str,
    earned_income: float,
    tax_liability: float,
    resolver,
    tax_year: int = 2024,
) -> dict:
    """Calculate Child Tax Credit using resolved parameters.

    Returns dict with:
    - child_tax_credit: Total CTC (nonrefundable portion applied to tax liability)
    - additional_child_tax_credit: Refundable portion (ACTC)

    Formula per 26 USC Section 24:
    1. Base credit = credit_per_child x num_qualifying_children (Section 24(a), 24(h)(2))
    2. Phaseout = $50 per $1,000 (or fraction) over threshold (Section 24(b))
    3. CTC = base credit - phaseout (limited to tax liability for nonrefundable)
    4. ACTC = min(15% x (earned_income - $2,500), refundable_max x children) (Section 24(d), 24(h)(5))
    """
    # Get parameters from resolver
    # Credit amount per child (Section 24(h)(2): $2,000 for 2018-2025)
    credit_data = resolver.load_base_value("statute/26/24/h/2")
    credit_per_child = get_value_for_year(
        credit_data["credit_amount"]["values"], tax_year
    )

    # Phaseout thresholds (Section 24(b)(1))
    thresholds = resolver.load_base_value("statute/26/24/b/1")
    if filing_status.upper() == "JOINT":
        phaseout_threshold = get_value_for_year(
            thresholds["phaseout_threshold_joint"]["values"], tax_year
        )
    else:
        phaseout_threshold = get_value_for_year(
            thresholds["phaseout_threshold_single"]["values"], tax_year
        )

    # Phaseout rate (Section 24(b)(2): $50 per $1,000)
    phaseout_rate_data = resolver.load_base_value("statute/26/24/b/2")
    phaseout_per_1000 = get_value_for_year(
        phaseout_rate_data["phaseout_rate"]["values"], tax_year
    )

    # ACTC parameters (Section 24(d)(1)(B))
    actc_params = resolver.load_base_value("statute/26/24/d/1/B")
    earned_income_threshold = get_value_for_year(
        actc_params["earned_income_threshold"]["values"], tax_year
    )
    refundable_rate = get_value_for_year(
        actc_params["refundable_rate"]["values"], tax_year
    )

    # Refundable maximum per child (Section 24(h)(5), indexed - get from IRS guidance)
    refundable_max = resolver.resolve(
        "statute/26/24/h/5/refundable_maximum",
        fragment="refundable_maximum",
        tax_year=tax_year,
    )

    # Step 1: Calculate base credit
    base_credit = credit_per_child * num_qualifying_children

    # Step 2: Calculate phaseout
    # Section 24(b)(2): "$50 for each $1,000 (or fraction thereof)"
    if agi > phaseout_threshold:
        excess = agi - phaseout_threshold
        # Round up to nearest $1,000
        thousands_over = math.ceil(excess / 1000)
        phaseout = phaseout_per_1000 * thousands_over
    else:
        phaseout = 0

    # Step 3: Credit after phaseout
    credit_after_phaseout = max(0, base_credit - phaseout)

    # Step 4: Split into nonrefundable (CTC) and refundable (ACTC)
    # CTC is limited to tax liability
    ctc = min(credit_after_phaseout, tax_liability)

    # ACTC = portion of remaining credit that can be refunded
    remaining_credit = credit_after_phaseout - ctc

    # Section 24(d)(1)(B)(i): 15% of earned income over $2,500
    actc_from_earned = refundable_rate * max(0, earned_income - earned_income_threshold)

    # Section 24(h)(5): capped at refundable_max per child
    refundable_cap = refundable_max * num_qualifying_children

    # ACTC = min(remaining credit, earned income formula, refundable cap)
    actc = min(remaining_credit, actc_from_earned, refundable_cap)

    return {
        "child_tax_credit": ctc,
        "additional_child_tax_credit": actc,
        "total_credit": ctc + actc,
        "base_credit": base_credit,
        "phaseout": phaseout,
    }


class TestCTCParameterLoading:
    """Test that CTC parameters load correctly from statute files."""

    def test_credit_amount_2024(self, resolver):
        """Verify credit amount is $2,000 for 2024 (TCJA period)."""
        credit_data = resolver.load_base_value("statute/26/24/h/2")
        assert credit_data is not None
        values = credit_data["credit_amount"]["values"]
        # 2024 falls in TCJA period (2018-2025)
        assert values[date(2018, 1, 1)] == 2000

    def test_phaseout_thresholds(self, resolver):
        """Verify phaseout thresholds: $400k joint, $200k single."""
        thresholds = resolver.load_base_value("statute/26/24/b/1")
        assert thresholds["phaseout_threshold_joint"]["values"][date(2018, 1, 1)] == 400000
        assert thresholds["phaseout_threshold_single"]["values"][date(2018, 1, 1)] == 200000

    def test_phaseout_rate(self, resolver):
        """Verify phaseout rate is $50 per $1,000."""
        rate_data = resolver.load_base_value("statute/26/24/b/2")
        assert rate_data["phaseout_rate"]["values"][date(1998, 1, 1)] == 50

    def test_refundable_maximum_2024(self, resolver):
        """Verify refundable max is $1,700 for 2024 (from IRS guidance)."""
        refundable_max = resolver.resolve(
            "statute/26/24/h/5/refundable_maximum",
            fragment="refundable_maximum",
            tax_year=2024,
        )
        assert refundable_max == 1700

    def test_actc_parameters(self, resolver):
        """Verify ACTC parameters: $2,500 threshold, 15% rate."""
        params = resolver.load_base_value("statute/26/24/d/1/B")
        assert params["earned_income_threshold"]["values"][date(2018, 1, 1)] == 2500
        assert params["refundable_rate"]["values"][date(2018, 1, 1)] == 0.15


class TestCTCBasicCalculation:
    """Test basic CTC calculations without phaseout."""

    def test_single_child_below_phaseout(self, resolver):
        """Single filer, 1 child, $50k AGI -> $2,000 CTC."""
        result = calculate_ctc(
            agi=50000,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=50000,
            tax_liability=5000,
            resolver=resolver,
        )
        assert result["child_tax_credit"] == 2000
        assert result["additional_child_tax_credit"] == 0

    def test_two_children_below_phaseout(self, resolver):
        """Single filer, 2 children, $75k AGI -> $4,000 CTC."""
        result = calculate_ctc(
            agi=75000,
            num_qualifying_children=2,
            filing_status="SINGLE",
            earned_income=75000,
            tax_liability=8000,
            resolver=resolver,
        )
        assert result["child_tax_credit"] == 4000
        assert result["additional_child_tax_credit"] == 0

    def test_joint_three_children(self, resolver):
        """Joint filers, 3 children, $150k AGI -> $6,000 CTC."""
        result = calculate_ctc(
            agi=150000,
            num_qualifying_children=3,
            filing_status="JOINT",
            earned_income=150000,
            tax_liability=15000,
            resolver=resolver,
        )
        assert result["child_tax_credit"] == 6000
        assert result["additional_child_tax_credit"] == 0

    def test_no_children(self, resolver):
        """No qualifying children -> $0 credit."""
        result = calculate_ctc(
            agi=50000,
            num_qualifying_children=0,
            filing_status="SINGLE",
            earned_income=50000,
            tax_liability=5000,
            resolver=resolver,
        )
        assert result["child_tax_credit"] == 0
        assert result["additional_child_tax_credit"] == 0


class TestCTCPhaseout:
    """Test CTC phaseout calculations per Section 24(b)."""

    def test_single_phaseout_begins(self, resolver):
        """Single, AGI $210k -> phaseout $500, CTC = $1,500."""
        # $210k - $200k = $10k over threshold
        # $50 x 10 = $500 phaseout
        # $2,000 - $500 = $1,500
        result = calculate_ctc(
            agi=210000,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=210000,
            tax_liability=40000,
            resolver=resolver,
        )
        assert result["phaseout"] == 500
        assert result["child_tax_credit"] == 1500

    def test_single_fully_phased_out(self, resolver):
        """Single, AGI $240k -> fully phased out."""
        # $240k - $200k = $40k over threshold
        # $50 x 40 = $2,000 phaseout
        # $2,000 - $2,000 = $0
        result = calculate_ctc(
            agi=240000,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=240000,
            tax_liability=50000,
            resolver=resolver,
        )
        assert result["child_tax_credit"] == 0
        assert result["total_credit"] == 0

    def test_joint_phaseout_threshold(self, resolver):
        """Joint, AGI $420k -> phaseout $1,000, CTC = $1,000."""
        # $420k - $400k = $20k over threshold
        # $50 x 20 = $1,000 phaseout
        # $2,000 - $1,000 = $1,000
        result = calculate_ctc(
            agi=420000,
            num_qualifying_children=1,
            filing_status="JOINT",
            earned_income=420000,
            tax_liability=80000,
            resolver=resolver,
        )
        assert result["phaseout"] == 1000
        assert result["child_tax_credit"] == 1000

    def test_joint_two_children_partial_phaseout(self, resolver):
        """Joint, 2 children, AGI $430k -> phaseout $1,500, CTC = $2,500."""
        # $430k - $400k = $30k over threshold
        # $50 x 30 = $1,500 phaseout
        # $4,000 - $1,500 = $2,500
        result = calculate_ctc(
            agi=430000,
            num_qualifying_children=2,
            filing_status="JOINT",
            earned_income=430000,
            tax_liability=90000,
            resolver=resolver,
        )
        assert result["base_credit"] == 4000
        assert result["phaseout"] == 1500
        assert result["child_tax_credit"] == 2500

    def test_phaseout_rounds_up(self, resolver):
        """Verify phaseout rounds up to nearest $1,000."""
        # AGI $201,001 -> $1,001 over threshold
        # Rounds up to 2 x $50 = $100 phaseout
        result = calculate_ctc(
            agi=201001,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=201001,
            tax_liability=40000,
            resolver=resolver,
        )
        assert result["phaseout"] == 100  # Rounds up: $1,001 / $1,000 = 2 (ceiling) x $50


class TestAdditionalChildTaxCredit:
    """Test ACTC (refundable portion) calculations per Section 24(d)."""

    def test_low_income_actc(self, resolver):
        """Low income, no tax liability -> ACTC refundable."""
        # Earned income $15k, 1 child
        # ACTC = 15% x ($15,000 - $2,500) = 15% x $12,500 = $1,875
        # Capped at $1,700 (2024 refundable max)
        result = calculate_ctc(
            agi=15000,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=15000,
            tax_liability=0,
            resolver=resolver,
        )
        assert result["child_tax_credit"] == 0  # No tax liability
        assert result["additional_child_tax_credit"] == 1700  # Capped at max

    def test_very_low_income_partial_actc(self, resolver):
        """Very low income -> partial ACTC."""
        # Earned income $5k, 1 child
        # ACTC = 15% x ($5,000 - $2,500) = 15% x $2,500 = $375
        result = calculate_ctc(
            agi=5000,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=5000,
            tax_liability=0,
            resolver=resolver,
        )
        assert result["child_tax_credit"] == 0
        assert result["additional_child_tax_credit"] == 375

    def test_below_earned_income_threshold(self, resolver):
        """Earned income below $2,500 -> no ACTC."""
        result = calculate_ctc(
            agi=2000,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=2000,
            tax_liability=0,
            resolver=resolver,
        )
        assert result["child_tax_credit"] == 0
        assert result["additional_child_tax_credit"] == 0

    def test_multiple_children_actc(self, resolver):
        """Multiple children, ACTC limited by earned income formula."""
        # Earned income $25k, 3 children
        # ACTC from earned income = 15% x ($25,000 - $2,500) = 15% x $22,500 = $3,375
        # Refundable cap = $1,700 x 3 = $5,100
        # Base credit = $2,000 x 3 = $6,000
        # Credit limited by earned income formula = $3,375
        result = calculate_ctc(
            agi=25000,
            num_qualifying_children=3,
            filing_status="SINGLE",
            earned_income=25000,
            tax_liability=0,
            resolver=resolver,
        )
        assert result["child_tax_credit"] == 0
        assert result["additional_child_tax_credit"] == 3375

    def test_partial_tax_liability_splits_credit(self, resolver):
        """Partial tax liability splits credit between CTC and ACTC."""
        # 1 child, $15k earned income, $500 tax liability
        # Base credit = $2,000
        # CTC (nonrefundable) = min($2,000, $500) = $500
        # Remaining for ACTC = $2,000 - $500 = $1,500
        # ACTC from earned = 15% x ($15,000 - $2,500) = $1,875
        # ACTC = min($1,500, $1,875, $1,700) = $1,500 (remaining credit)
        result = calculate_ctc(
            agi=15000,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=15000,
            tax_liability=500,
            resolver=resolver,
        )
        assert result["child_tax_credit"] == 500
        assert result["additional_child_tax_credit"] == 1500


class TestCTCEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_exactly_at_single_threshold(self, resolver):
        """AGI exactly at $200k threshold -> no phaseout."""
        result = calculate_ctc(
            agi=200000,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=200000,
            tax_liability=40000,
            resolver=resolver,
        )
        assert result["phaseout"] == 0
        assert result["child_tax_credit"] == 2000

    def test_exactly_at_joint_threshold(self, resolver):
        """AGI exactly at $400k threshold -> no phaseout."""
        result = calculate_ctc(
            agi=400000,
            num_qualifying_children=2,
            filing_status="JOINT",
            earned_income=400000,
            tax_liability=80000,
            resolver=resolver,
        )
        assert result["phaseout"] == 0
        assert result["child_tax_credit"] == 4000

    def test_one_dollar_over_threshold(self, resolver):
        """AGI $1 over threshold -> $50 phaseout (rounds up)."""
        result = calculate_ctc(
            agi=200001,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=200001,
            tax_liability=40000,
            resolver=resolver,
        )
        assert result["phaseout"] == 50
        assert result["child_tax_credit"] == 1950

    def test_high_income_many_children(self, resolver):
        """High income with many children - partial phaseout."""
        # Joint $500k, 4 children
        # Base = $2,000 x 4 = $8,000
        # Phaseout = $50 x 100 = $5,000
        # CTC = $8,000 - $5,000 = $3,000
        result = calculate_ctc(
            agi=500000,
            num_qualifying_children=4,
            filing_status="JOINT",
            earned_income=500000,
            tax_liability=100000,
            resolver=resolver,
        )
        assert result["base_credit"] == 8000
        assert result["phaseout"] == 5000
        assert result["child_tax_credit"] == 3000

    def test_zero_earned_income_with_agi(self, resolver):
        """AGI from non-earned sources -> no ACTC."""
        # Has AGI but no earned income (e.g., investment income)
        result = calculate_ctc(
            agi=50000,
            num_qualifying_children=1,
            filing_status="SINGLE",
            earned_income=0,
            tax_liability=0,
            resolver=resolver,
        )
        # Base credit exists but can't be refunded
        assert result["base_credit"] == 2000
        assert result["child_tax_credit"] == 0
        assert result["additional_child_tax_credit"] == 0
