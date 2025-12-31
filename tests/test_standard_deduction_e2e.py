"""End-to-end Standard Deduction calculation tests using override resolver.

Validates that:
1. Override resolver loads IRS guidance correctly for standard deduction
2. Standard deduction calculations match IRS published tables (Rev. Proc. 2023-34)
3. Integration with cosilico-us statute files works

Test values from: https://www.irs.gov/irb/2023-48_IRB#RP-2023-34
"""

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


def calculate_standard_deduction(
    filing_status: str,
    age: int,
    spouse_age: int | None,
    is_blind: bool,
    spouse_is_blind: bool,
    is_dependent: bool,
    earned_income: float,
    is_nonresident_alien: bool,
    spouse_itemizes: bool,
    resolver,
    tax_year: int = 2024,
) -> float:
    """Calculate standard deduction using resolved parameters.

    This implements the formula from 26 USC SS 63:
    1. Check ineligibility (SS 63(c)(6))
    2. Get basic amount by filing status (SS 63(c)(2))
    3. Apply dependent limitation if applicable (SS 63(c)(5))
    4. Add additional amounts for age/blindness (SS 63(f))
    """
    # SS 63(c)(6): Check ineligibility
    if is_nonresident_alien:
        return 0
    if filing_status == "MARRIED_SEPARATE" and spouse_itemizes:
        return 0

    # Determine if married for additional amount selection
    is_married = filing_status in ["JOINT", "MARRIED_SEPARATE"]

    # Get basic standard deduction by filing status (SS 63(c)(2))
    if filing_status == "JOINT":
        basic = resolver.resolve(
            "statute/26/63/c/2/basic_amounts",
            fragment="basic_joint",
            tax_year=tax_year,
        )
    elif filing_status == "HEAD_OF_HOUSEHOLD":
        basic = resolver.resolve(
            "statute/26/63/c/2/basic_amounts",
            fragment="basic_head_of_household",
            tax_year=tax_year,
        )
    else:  # SINGLE or MARRIED_SEPARATE
        basic = resolver.resolve(
            "statute/26/63/c/2/basic_amounts",
            fragment="basic_single",
            tax_year=tax_year,
        )

    # SS 63(c)(5): Dependent limitation
    if is_dependent:
        dependent_min = resolver.resolve(
            "statute/26/63/c/5/parameters",
            fragment="dependent_minimum",
            tax_year=tax_year,
        )
        dependent_addon = resolver.resolve(
            "statute/26/63/c/5/parameters",
            fragment="dependent_earned_addon",
            tax_year=tax_year,
        )
        # Greater of minimum or (earned income + addon), but not more than basic
        earned_plus = earned_income + dependent_addon
        basic = min(max(dependent_min, earned_plus), basic)

    # SS 63(f): Additional amounts for age and blindness
    additional = 0

    # Select amounts based on marital status
    if is_married:
        aged_amount = resolver.resolve(
            "statute/26/63/f/1/aged_amount",
            fragment="additional_aged_married",
            tax_year=tax_year,
        )
        blind_amount = resolver.resolve(
            "statute/26/63/f/2/blind_amount",
            fragment="additional_blind_married",
            tax_year=tax_year,
        )
    else:
        aged_amount = resolver.resolve(
            "statute/26/63/f/1/aged_amount",
            fragment="additional_aged_unmarried",
            tax_year=tax_year,
        )
        blind_amount = resolver.resolve(
            "statute/26/63/f/2/blind_amount",
            fragment="additional_blind_unmarried",
            tax_year=tax_year,
        )

    # Primary taxpayer
    if age >= 65:
        additional += aged_amount
    if is_blind:
        additional += blind_amount

    # Spouse (joint filers only)
    if filing_status == "JOINT" and spouse_age is not None:
        if spouse_age >= 65:
            additional += aged_amount
        if spouse_is_blind:
            additional += blind_amount

    return basic + additional


class TestStandardDeductionResolver:
    """Test that resolver loads 2024 IRS values correctly."""

    def test_basic_amounts_2024(self, resolver):
        """Verify basic standard deduction amounts for 2024."""
        # Joint: $29,200
        joint = resolver.resolve(
            "statute/26/63/c/2/basic_amounts",
            fragment="basic_joint",
            tax_year=2024,
        )
        assert joint == 29200

        # Head of household: $21,900
        hoh = resolver.resolve(
            "statute/26/63/c/2/basic_amounts",
            fragment="basic_head_of_household",
            tax_year=2024,
        )
        assert hoh == 21900

        # Single: $14,600
        single = resolver.resolve(
            "statute/26/63/c/2/basic_amounts",
            fragment="basic_single",
            tax_year=2024,
        )
        assert single == 14600

    def test_additional_amounts_2024(self, resolver):
        """Verify additional amounts for aged/blind in 2024."""
        # Aged unmarried: $1,950
        aged_unmarried = resolver.resolve(
            "statute/26/63/f/1/aged_amount",
            fragment="additional_aged_unmarried",
            tax_year=2024,
        )
        assert aged_unmarried == 1950

        # Aged married: $1,550
        aged_married = resolver.resolve(
            "statute/26/63/f/1/aged_amount",
            fragment="additional_aged_married",
            tax_year=2024,
        )
        assert aged_married == 1550

        # Blind amounts should equal aged amounts
        blind_unmarried = resolver.resolve(
            "statute/26/63/f/2/blind_amount",
            fragment="additional_blind_unmarried",
            tax_year=2024,
        )
        assert blind_unmarried == 1950

        blind_married = resolver.resolve(
            "statute/26/63/f/2/blind_amount",
            fragment="additional_blind_married",
            tax_year=2024,
        )
        assert blind_married == 1550

    def test_dependent_parameters_2024(self, resolver):
        """Verify dependent limitation parameters for 2024."""
        # Minimum: $1,300
        dep_min = resolver.resolve(
            "statute/26/63/c/5/parameters",
            fragment="dependent_minimum",
            tax_year=2024,
        )
        assert dep_min == 1300

        # Earned addon: $450
        dep_addon = resolver.resolve(
            "statute/26/63/c/5/parameters",
            fragment="dependent_earned_addon",
            tax_year=2024,
        )
        assert dep_addon == 450


class TestStandardDeductionBasic:
    """Test basic standard deduction by filing status."""

    def test_single_filer(self, resolver):
        """Single filer, under 65, not blind."""
        result = calculate_standard_deduction(
            filing_status="SINGLE",
            age=35,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=False,
            earned_income=50000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 14600

    def test_married_filing_jointly(self, resolver):
        """MFJ, both under 65, neither blind."""
        result = calculate_standard_deduction(
            filing_status="JOINT",
            age=40,
            spouse_age=38,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=False,
            earned_income=100000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 29200

    def test_married_filing_separately(self, resolver):
        """MFS, under 65, not blind."""
        result = calculate_standard_deduction(
            filing_status="MARRIED_SEPARATE",
            age=45,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=False,
            earned_income=75000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 14600

    def test_head_of_household(self, resolver):
        """Head of household, under 65, not blind."""
        result = calculate_standard_deduction(
            filing_status="HEAD_OF_HOUSEHOLD",
            age=35,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=False,
            earned_income=60000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 21900


class TestStandardDeductionAdditional:
    """Test additional amounts for age and blindness (SS 63(f))."""

    def test_single_aged_65(self, resolver):
        """Single filer age 65+: $14,600 + $1,950 = $16,550"""
        result = calculate_standard_deduction(
            filing_status="SINGLE",
            age=65,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=False,
            earned_income=50000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 16550

    def test_single_aged_and_blind(self, resolver):
        """Single filer 65+ and blind: $14,600 + $1,950 + $1,950 = $18,500"""
        result = calculate_standard_deduction(
            filing_status="SINGLE",
            age=65,
            spouse_age=None,
            is_blind=True,
            spouse_is_blind=False,
            is_dependent=False,
            earned_income=50000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 18500

    def test_joint_both_aged(self, resolver):
        """MFJ both 65+: $29,200 + $1,550 + $1,550 = $32,300"""
        result = calculate_standard_deduction(
            filing_status="JOINT",
            age=67,
            spouse_age=66,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=False,
            earned_income=80000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 32300

    def test_joint_one_aged_one_blind(self, resolver):
        """MFJ one 65+, one blind: $29,200 + $1,550 + $1,550 = $32,300"""
        result = calculate_standard_deduction(
            filing_status="JOINT",
            age=67,
            spouse_age=55,
            is_blind=False,
            spouse_is_blind=True,
            is_dependent=False,
            earned_income=80000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 32300

    def test_joint_both_aged_and_blind(self, resolver):
        """MFJ both 65+ and both blind: $29,200 + 4 x $1,550 = $35,400"""
        result = calculate_standard_deduction(
            filing_status="JOINT",
            age=70,
            spouse_age=68,
            is_blind=True,
            spouse_is_blind=True,
            is_dependent=False,
            earned_income=60000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 35400

    def test_hoh_aged(self, resolver):
        """Head of household 65+: $21,900 + $1,950 = $23,850"""
        result = calculate_standard_deduction(
            filing_status="HEAD_OF_HOUSEHOLD",
            age=68,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=False,
            earned_income=50000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 23850


class TestStandardDeductionDependent:
    """Test dependent limitation (SS 63(c)(5))."""

    def test_dependent_no_earned_income(self, resolver):
        """Dependent with $0 earned income: min($1,300, $14,600) = $1,300"""
        result = calculate_standard_deduction(
            filing_status="SINGLE",
            age=16,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=True,
            earned_income=0,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 1300

    def test_dependent_low_earned_income(self, resolver):
        """Dependent with $500 earned: max($1,300, $500+$450) = $1,300"""
        result = calculate_standard_deduction(
            filing_status="SINGLE",
            age=17,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=True,
            earned_income=500,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 1300

    def test_dependent_moderate_earned_income(self, resolver):
        """Dependent with $3,000 earned: max($1,300, $3,000+$450) = $3,450"""
        result = calculate_standard_deduction(
            filing_status="SINGLE",
            age=19,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=True,
            earned_income=3000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 3450

    def test_dependent_high_earned_income(self, resolver):
        """Dependent with $20,000 earned: capped at basic = $14,600"""
        result = calculate_standard_deduction(
            filing_status="SINGLE",
            age=22,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=True,
            earned_income=20000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 14600

    def test_dependent_aged_and_blind(self, resolver):
        """Dependent 65+ and blind: dependent limitation + additionals"""
        # Basic for dependent: max($1,300, $2,000+$450) = $2,450
        # Additional: $1,950 (aged) + $1,950 (blind) = $3,900
        # Total: $2,450 + $3,900 = $6,350
        result = calculate_standard_deduction(
            filing_status="SINGLE",
            age=68,
            spouse_age=None,
            is_blind=True,
            spouse_is_blind=False,
            is_dependent=True,
            earned_income=2000,
            is_nonresident_alien=False,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 6350


class TestStandardDeductionIneligibility:
    """Test ineligibility rules (SS 63(c)(6))."""

    def test_mfs_spouse_itemizes(self, resolver):
        """MFS where spouse itemizes: $0"""
        result = calculate_standard_deduction(
            filing_status="MARRIED_SEPARATE",
            age=40,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=False,
            earned_income=50000,
            is_nonresident_alien=False,
            spouse_itemizes=True,
            resolver=resolver,
        )
        assert result == 0

    def test_nonresident_alien(self, resolver):
        """Nonresident alien: $0"""
        result = calculate_standard_deduction(
            filing_status="SINGLE",
            age=30,
            spouse_age=None,
            is_blind=False,
            spouse_is_blind=False,
            is_dependent=False,
            earned_income=50000,
            is_nonresident_alien=True,
            spouse_itemizes=False,
            resolver=resolver,
        )
        assert result == 0
