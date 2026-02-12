"""End-to-end tax bracket calculation tests using override resolver.

Validates that:
1. Override resolver loads 2024 IRS tax bracket thresholds correctly
2. Income tax calculations match IRS published tables
3. Integration with cosilico-us statute files works
"""

from pathlib import Path

import pytest

from src.rac.parameters.override_resolver import create_resolver

# Path to cosilico-us (absolute path for reliability)
COSILICO_US_ROOT = Path("/Users/maxghenis/CosilicoAI/cosilico-us")


@pytest.fixture
def resolver():
    """Create resolver pointing to cosilico-us."""
    if not COSILICO_US_ROOT.exists():
        pytest.skip("cosilico-us not found")
    return create_resolver(str(COSILICO_US_ROOT))


def calculate_income_tax(
    taxable_income: float,
    filing_status: str,
    resolver,
    tax_year: int = 2024,
) -> float:
    """Calculate federal income tax using resolved bracket thresholds.

    This implements the formula from 26 USC Section 1:
    Tax is calculated by applying marginal rates to income in each bracket.

    Args:
        taxable_income: Taxable income after deductions
        filing_status: One of 'single', 'married_filing_jointly',
                      'head_of_household', 'married_filing_separately'
        resolver: Override resolver for parameter lookup
        tax_year: Tax year for bracket lookup

    Returns:
        Total federal income tax
    """
    # Tax rates are fixed in statute (not indexed)
    rates = [0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37]

    # Get thresholds for this filing status (these are indexed)
    thresholds = []
    for rate in rates:
        threshold = resolver.resolve(
            "statute/26/1",
            fragment=filing_status,
            tax_year=tax_year,
            rate=rate,
        )
        thresholds.append(threshold)

    # Calculate tax by applying marginal rates
    total_tax = 0.0
    remaining_income = taxable_income

    for i, rate in enumerate(rates):
        bracket_floor = thresholds[i]
        # Bracket ceiling is next threshold (or infinity for top bracket)
        if i + 1 < len(thresholds):
            bracket_ceiling = thresholds[i + 1]
        else:
            bracket_ceiling = float('inf')

        # Income taxable at this rate
        if remaining_income > bracket_floor:
            if remaining_income <= bracket_ceiling:
                taxable_at_rate = remaining_income - bracket_floor
                total_tax += taxable_at_rate * rate
                break
            else:
                taxable_at_rate = bracket_ceiling - bracket_floor
                total_tax += taxable_at_rate * rate

    return round(total_tax, 2)


class TestTaxBracketResolution:
    """Test that bracket thresholds are resolved correctly from IRS guidance."""

    def test_resolver_loads_2024_single_thresholds(self, resolver):
        """Verify 2024 IRS single filer thresholds are loaded correctly."""
        # 10% bracket starts at $0
        t10 = resolver.resolve(
            "statute/26/1",
            fragment="single",
            tax_year=2024,
            rate=0.10,
        )
        assert t10 == 0, f"Expected 0, got {t10}"

        # 12% bracket starts at $11,600
        t12 = resolver.resolve(
            "statute/26/1",
            fragment="single",
            tax_year=2024,
            rate=0.12,
        )
        assert t12 == 11600, f"Expected 11600, got {t12}"

        # 22% bracket starts at $47,150
        t22 = resolver.resolve(
            "statute/26/1",
            fragment="single",
            tax_year=2024,
            rate=0.22,
        )
        assert t22 == 47150, f"Expected 47150, got {t22}"

        # 37% bracket starts at $609,350
        t37 = resolver.resolve(
            "statute/26/1",
            fragment="single",
            tax_year=2024,
            rate=0.37,
        )
        assert t37 == 609350, f"Expected 609350, got {t37}"

    def test_resolver_loads_2024_mfj_thresholds(self, resolver):
        """Verify 2024 IRS married filing jointly thresholds."""
        # 12% bracket starts at $23,200 for MFJ
        t12 = resolver.resolve(
            "statute/26/1",
            fragment="married_filing_jointly",
            tax_year=2024,
            rate=0.12,
        )
        assert t12 == 23200, f"Expected 23200, got {t12}"

        # 37% bracket starts at $731,200 for MFJ
        t37 = resolver.resolve(
            "statute/26/1",
            fragment="married_filing_jointly",
            tax_year=2024,
            rate=0.37,
        )
        assert t37 == 731200, f"Expected 731200, got {t37}"

    def test_resolver_loads_2024_hoh_thresholds(self, resolver):
        """Verify 2024 IRS head of household thresholds."""
        # 12% bracket starts at $16,550 for HoH
        t12 = resolver.resolve(
            "statute/26/1",
            fragment="head_of_household",
            tax_year=2024,
            rate=0.12,
        )
        assert t12 == 16550, f"Expected 16550, got {t12}"

    def test_resolver_loads_2024_mfs_thresholds(self, resolver):
        """Verify 2024 IRS married filing separately thresholds."""
        # MFS uses half of MFJ thresholds for most brackets
        t12 = resolver.resolve(
            "statute/26/1",
            fragment="married_filing_separately",
            tax_year=2024,
            rate=0.12,
        )
        assert t12 == 11600, f"Expected 11600, got {t12}"

        # 37% threshold is $365,600 (half of MFJ $731,200)
        t37 = resolver.resolve(
            "statute/26/1",
            fragment="married_filing_separately",
            tax_year=2024,
            rate=0.37,
        )
        assert t37 == 365600, f"Expected 365600, got {t37}"

    def test_base_values_for_2018(self, resolver):
        """Test that base TCJA 2018 values are used when no override exists."""
        # For 2018, should get base TCJA values (no IRS override for 2018)
        t12 = resolver.resolve(
            "statute/26/1",
            fragment="single",
            tax_year=2018,
            rate=0.12,
        )
        assert t12 == 9525, f"Expected 9525 (2018 base), got {t12}"


class TestTaxCalculation:
    """Test income tax calculations against IRS tax tables."""

    def test_single_10_percent_only(self, resolver):
        """Test: Single filer, $10,000 income -> entirely in 10% bracket."""
        tax = calculate_income_tax(
            taxable_income=10000,
            filing_status="single",
            resolver=resolver,
        )
        # 10000 * 0.10 = 1000
        assert tax == 1000.00, f"Expected 1000.00, got {tax}"

    def test_single_two_brackets(self, resolver):
        """Test: Single filer, $20,000 income -> spans 10% and 12% brackets."""
        tax = calculate_income_tax(
            taxable_income=20000,
            filing_status="single",
            resolver=resolver,
        )
        # 10%: $11,600 * 0.10 = $1,160
        # 12%: ($20,000 - $11,600) * 0.12 = $8,400 * 0.12 = $1,008
        # Total: $1,160 + $1,008 = $2,168
        assert tax == 2168.00, f"Expected 2168.00, got {tax}"

    def test_single_50k_income(self, resolver):
        """Test: Single filer, $50,000 income -> spans first three brackets."""
        tax = calculate_income_tax(
            taxable_income=50000,
            filing_status="single",
            resolver=resolver,
        )
        # 10%: $11,600 * 0.10 = $1,160
        # 12%: ($47,150 - $11,600) * 0.12 = $35,550 * 0.12 = $4,266
        # 22%: ($50,000 - $47,150) * 0.22 = $2,850 * 0.22 = $627
        # Total: $1,160 + $4,266 + $627 = $6,053
        assert tax == 6053.00, f"Expected 6053.00, got {tax}"

    def test_single_100k_income(self, resolver):
        """Test: Single filer, $100,000 income."""
        tax = calculate_income_tax(
            taxable_income=100000,
            filing_status="single",
            resolver=resolver,
        )
        # 10%: $11,600 * 0.10 = $1,160
        # 12%: ($47,150 - $11,600) * 0.12 = $4,266
        # 22%: ($100,000 - $47,150) * 0.22 = $52,850 * 0.22 = $11,627
        # Total: $1,160 + $4,266 + $11,627 = $17,053
        assert tax == 17053.00, f"Expected 17053.00, got {tax}"

    def test_mfj_50k_income(self, resolver):
        """Test: Married filing jointly, $50,000 income."""
        tax = calculate_income_tax(
            taxable_income=50000,
            filing_status="married_filing_jointly",
            resolver=resolver,
        )
        # 10%: $23,200 * 0.10 = $2,320
        # 12%: ($50,000 - $23,200) * 0.12 = $26,800 * 0.12 = $3,216
        # Total: $2,320 + $3,216 = $5,536
        assert tax == 5536.00, f"Expected 5536.00, got {tax}"

    def test_mfj_vs_single_same_income(self, resolver):
        """Test: MFJ pays less tax than single filer at same income level."""
        income = 60000

        single_tax = calculate_income_tax(
            taxable_income=income,
            filing_status="single",
            resolver=resolver,
        )

        mfj_tax = calculate_income_tax(
            taxable_income=income,
            filing_status="married_filing_jointly",
            resolver=resolver,
        )

        # MFJ has wider brackets, so should pay less tax
        assert mfj_tax < single_tax, f"MFJ tax ({mfj_tax}) should be less than single ({single_tax})"

    def test_zero_income(self, resolver):
        """Test: $0 income -> $0 tax."""
        tax = calculate_income_tax(
            taxable_income=0,
            filing_status="single",
            resolver=resolver,
        )
        assert tax == 0.00

    def test_high_income_top_bracket(self, resolver):
        """Test: Income well into top bracket."""
        tax = calculate_income_tax(
            taxable_income=700000,
            filing_status="single",
            resolver=resolver,
        )
        # This person is in the 37% bracket (starts at $609,350)
        # Calculate incrementally:
        # 10%: $11,600 * 0.10 = $1,160
        # 12%: $35,550 * 0.12 = $4,266
        # 22%: $53,375 * 0.22 = $11,742.50
        # 24%: $91,425 * 0.24 = $21,942
        # 32%: $51,775 * 0.32 = $16,568
        # 35%: $365,625 * 0.35 = $127,968.75
        # 37%: $90,650 * 0.37 = $33,540.50
        # Total: $217,187.75
        expected = (
            11600 * 0.10 +  # 10%
            (47150 - 11600) * 0.12 +  # 12%
            (100525 - 47150) * 0.22 +  # 22%
            (191950 - 100525) * 0.24 +  # 24%
            (243725 - 191950) * 0.32 +  # 32%
            (609350 - 243725) * 0.35 +  # 35%
            (700000 - 609350) * 0.37  # 37%
        )
        assert abs(tax - expected) < 0.01, f"Expected ~{expected:.2f}, got {tax}"


class TestHeadOfHousehold:
    """Test head of household calculations."""

    def test_hoh_40k_income(self, resolver):
        """Test: Head of household, $40,000 income."""
        tax = calculate_income_tax(
            taxable_income=40000,
            filing_status="head_of_household",
            resolver=resolver,
        )
        # 10%: $16,550 * 0.10 = $1,655
        # 12%: ($40,000 - $16,550) * 0.12 = $23,450 * 0.12 = $2,814
        # Total: $1,655 + $2,814 = $4,469
        assert tax == 4469.00, f"Expected 4469.00, got {tax}"

    def test_hoh_vs_single_same_income(self, resolver):
        """Test: HoH pays less than single at same income."""
        income = 40000

        single_tax = calculate_income_tax(
            taxable_income=income,
            filing_status="single",
            resolver=resolver,
        )

        hoh_tax = calculate_income_tax(
            taxable_income=income,
            filing_status="head_of_household",
            resolver=resolver,
        )

        assert hoh_tax < single_tax


class TestMarriedFilingSeparately:
    """Test married filing separately calculations."""

    def test_mfs_50k_income(self, resolver):
        """Test: Married filing separately, $50,000 income."""
        tax = calculate_income_tax(
            taxable_income=50000,
            filing_status="married_filing_separately",
            resolver=resolver,
        )
        # Same brackets as single for lower incomes
        # 10%: $11,600 * 0.10 = $1,160
        # 12%: ($47,150 - $11,600) * 0.12 = $4,266
        # 22%: ($50,000 - $47,150) * 0.22 = $627
        # Total: $6,053
        assert tax == 6053.00, f"Expected 6053.00, got {tax}"
