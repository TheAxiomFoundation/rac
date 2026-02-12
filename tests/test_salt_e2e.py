"""End-to-end SALT deduction cap tests using override resolver.

Validates that:
1. Override resolver loads SALT cap parameters correctly
2. SALT deduction calculations correctly apply the $10,000 cap
3. Integration with cosilico-us statute files works

Reference:
- 26 USC Section 164(b)(6) - SALT Deduction Limitation
- Tax Cuts and Jobs Act of 2017 (P.L. 115-97)
"""

import math
from datetime import date
from pathlib import Path

import pytest

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


def calculate_salt_deduction(
    state_income_tax: float,
    real_property_tax: float,
    personal_property_tax: float = 0,
    sales_tax: float = 0,
    elects_sales_tax: bool = False,
    foreign_real_property_tax: float = 0,
    filing_status: str = "SINGLE",
    resolver=None,
    tax_year: int = 2024,
) -> dict:
    """Calculate SALT deduction using resolved parameters.

    Returns dict with:
    - salt_before_cap: Total SALT before applying cap
    - salt_cap_amount: Applicable cap for filing status
    - salt_deduction: Final deduction after cap
    - salt_cap_reduction: Amount disallowed by cap

    Formula per 26 USC Section 164(b)(6):
    1. Sum state/local income (or sales), real property, and personal property taxes
    2. Apply $10,000 cap ($5,000 for MFS)
    3. Add foreign real property tax (exempt from cap)
    """
    # Load cap parameters
    cap_data = resolver.load_base_value("statute/26/164/b/6/cap")

    # Get applicable cap based on filing status
    fs = filing_status.upper()
    if fs == "MARRIED_SEPARATE":
        salt_cap = get_value_for_year(
            cap_data["salt_cap_married_separate"]["values"], tax_year
        )
    else:
        salt_cap = get_value_for_year(cap_data["salt_cap"]["values"], tax_year)

    # Choose income tax or sales tax based on election
    income_or_sales = sales_tax if elects_sales_tax else state_income_tax

    # Calculate total SALT before cap
    salt_before_cap = real_property_tax + personal_property_tax + income_or_sales

    # Apply cap to domestic SALT
    if math.isinf(salt_cap):
        capped_salt = salt_before_cap
    else:
        capped_salt = min(salt_before_cap, salt_cap)

    # Foreign real property tax is exempt from cap
    salt_deduction = capped_salt + foreign_real_property_tax

    # Calculate amount disallowed by cap
    if math.isinf(salt_cap):
        cap_reduction = 0
    else:
        cap_reduction = max(0, salt_before_cap - salt_cap)

    return {
        "salt_before_cap": salt_before_cap,
        "salt_cap_amount": salt_cap,
        "salt_deduction": salt_deduction,
        "salt_cap_reduction": cap_reduction,
    }


class TestSALTCapParameterLoading:
    """Test that SALT cap parameters load correctly from statute files."""

    def test_salt_cap_2024(self, resolver):
        """Verify SALT cap is $10,000 for 2024."""
        data = resolver.load_base_value("statute/26/164/b/6/cap")
        assert data is not None
        value = get_value_for_year(data["salt_cap"]["values"], 2024)
        assert value == 10000

    def test_salt_cap_mfs_2024(self, resolver):
        """Verify MFS SALT cap is $5,000 for 2024."""
        data = resolver.load_base_value("statute/26/164/b/6/cap")
        value = get_value_for_year(data["salt_cap_married_separate"]["values"], 2024)
        assert value == 5000

    def test_salt_cap_pre_tcja(self, resolver):
        """Verify no cap before 2018 (TCJA)."""
        data = resolver.load_base_value("statute/26/164/b/6/cap")
        value = get_value_for_year(data["salt_cap"]["values"], 2017)
        assert math.isinf(value)

    def test_salt_cap_post_tcja(self, resolver):
        """Verify cap expires after 2025."""
        data = resolver.load_base_value("statute/26/164/b/6/cap")
        value = get_value_for_year(data["salt_cap"]["values"], 2026)
        assert math.isinf(value)


class TestSALTBelowCap:
    """Test SALT calculations when total is below the cap."""

    def test_single_below_cap(self, resolver):
        """Single filer with SALT below $10,000 cap."""
        result = calculate_salt_deduction(
            state_income_tax=3000,
            real_property_tax=5000,
            personal_property_tax=500,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 8500
        assert result["salt_cap_amount"] == 10000
        assert result["salt_deduction"] == 8500
        assert result["salt_cap_reduction"] == 0

    def test_joint_below_cap(self, resolver):
        """Joint filer with SALT below $10,000 cap."""
        result = calculate_salt_deduction(
            state_income_tax=4000,
            real_property_tax=4000,
            personal_property_tax=1000,
            filing_status="JOINT",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 9000
        assert result["salt_deduction"] == 9000
        assert result["salt_cap_reduction"] == 0

    def test_mfs_below_cap(self, resolver):
        """MFS filer with SALT below $5,000 cap."""
        result = calculate_salt_deduction(
            state_income_tax=2000,
            real_property_tax=2000,
            filing_status="MARRIED_SEPARATE",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 4000
        assert result["salt_cap_amount"] == 5000
        assert result["salt_deduction"] == 4000
        assert result["salt_cap_reduction"] == 0


class TestSALTAboveCap:
    """Test SALT calculations when total exceeds the cap."""

    def test_single_above_cap(self, resolver):
        """Single filer with SALT above $10,000 cap."""
        result = calculate_salt_deduction(
            state_income_tax=8000,
            real_property_tax=15000,
            personal_property_tax=2000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 25000
        assert result["salt_cap_amount"] == 10000
        assert result["salt_deduction"] == 10000
        assert result["salt_cap_reduction"] == 15000

    def test_joint_high_tax_state(self, resolver):
        """Joint filer in high-tax state exceeding cap."""
        result = calculate_salt_deduction(
            state_income_tax=20000,  # High state income tax
            real_property_tax=25000,  # High property tax
            filing_status="JOINT",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 45000
        assert result["salt_deduction"] == 10000
        assert result["salt_cap_reduction"] == 35000

    def test_mfs_above_cap(self, resolver):
        """MFS filer with SALT above $5,000 cap."""
        result = calculate_salt_deduction(
            state_income_tax=5000,
            real_property_tax=5000,
            filing_status="MARRIED_SEPARATE",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 10000
        assert result["salt_cap_amount"] == 5000
        assert result["salt_deduction"] == 5000
        assert result["salt_cap_reduction"] == 5000

    def test_exactly_at_cap(self, resolver):
        """SALT exactly at $10,000 cap."""
        result = calculate_salt_deduction(
            state_income_tax=5000,
            real_property_tax=5000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 10000
        assert result["salt_deduction"] == 10000
        assert result["salt_cap_reduction"] == 0


class TestSALTSalesTaxElection:
    """Test sales tax election instead of income tax."""

    def test_elects_sales_tax(self, resolver):
        """Taxpayer elects sales tax over income tax."""
        result = calculate_salt_deduction(
            state_income_tax=2000,
            sales_tax=4000,
            real_property_tax=5000,
            elects_sales_tax=True,
            filing_status="SINGLE",
            resolver=resolver,
        )
        # Should use sales tax ($4k) not income tax ($2k)
        assert result["salt_before_cap"] == 9000  # 4000 + 5000
        assert result["salt_deduction"] == 9000

    def test_does_not_elect_sales_tax(self, resolver):
        """Taxpayer uses income tax (default)."""
        result = calculate_salt_deduction(
            state_income_tax=2000,
            sales_tax=4000,
            real_property_tax=5000,
            elects_sales_tax=False,
            filing_status="SINGLE",
            resolver=resolver,
        )
        # Should use income tax ($2k) not sales tax ($4k)
        assert result["salt_before_cap"] == 7000  # 2000 + 5000
        assert result["salt_deduction"] == 7000


class TestSALTForeignRealProperty:
    """Test foreign real property tax exemption from cap."""

    def test_foreign_property_exempt_from_cap(self, resolver):
        """Foreign real property tax not subject to $10,000 cap."""
        result = calculate_salt_deduction(
            state_income_tax=5000,
            real_property_tax=8000,
            foreign_real_property_tax=3000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        # Domestic SALT = $13,000, capped at $10,000
        # Foreign = $3,000 added on top (exempt from cap)
        assert result["salt_before_cap"] == 13000
        assert result["salt_deduction"] == 13000  # $10,000 capped + $3,000 foreign
        assert result["salt_cap_reduction"] == 3000  # Only domestic reduction

    def test_below_cap_with_foreign(self, resolver):
        """Foreign property tax added to below-cap domestic SALT."""
        result = calculate_salt_deduction(
            state_income_tax=3000,
            real_property_tax=4000,
            foreign_real_property_tax=5000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        # Domestic = $7,000 (below cap)
        # Total = $7,000 + $5,000 foreign = $12,000
        assert result["salt_before_cap"] == 7000
        assert result["salt_deduction"] == 12000
        assert result["salt_cap_reduction"] == 0


class TestSALTHistoricalPeriods:
    """Test SALT cap in different tax years."""

    def test_pre_tcja_no_cap(self, resolver):
        """No cap applied before TCJA (2017 and earlier)."""
        result = calculate_salt_deduction(
            state_income_tax=50000,
            real_property_tax=50000,
            filing_status="SINGLE",
            resolver=resolver,
            tax_year=2017,
        )
        assert result["salt_before_cap"] == 100000
        assert math.isinf(result["salt_cap_amount"])
        assert result["salt_deduction"] == 100000
        assert result["salt_cap_reduction"] == 0

    def test_tcja_period_has_cap(self, resolver):
        """Cap applies during TCJA period (2018-2025)."""
        for year in [2018, 2020, 2024, 2025]:
            result = calculate_salt_deduction(
                state_income_tax=15000,
                real_property_tax=15000,
                filing_status="SINGLE",
                resolver=resolver,
                tax_year=year,
            )
            assert result["salt_cap_amount"] == 10000
            assert result["salt_deduction"] == 10000
            assert result["salt_cap_reduction"] == 20000

    def test_post_tcja_no_cap(self, resolver):
        """Cap expires after 2025 (TCJA sunset)."""
        result = calculate_salt_deduction(
            state_income_tax=50000,
            real_property_tax=50000,
            filing_status="SINGLE",
            resolver=resolver,
            tax_year=2026,
        )
        assert math.isinf(result["salt_cap_amount"])
        assert result["salt_deduction"] == 100000
        assert result["salt_cap_reduction"] == 0


class TestSALTFilingStatus:
    """Test SALT cap varies by filing status."""

    def test_all_filing_statuses_same_cap(self, resolver):
        """All non-MFS filing statuses use $10,000 cap."""
        for status in ["SINGLE", "JOINT", "HEAD_OF_HOUSEHOLD"]:
            result = calculate_salt_deduction(
                state_income_tax=15000,
                real_property_tax=5000,
                filing_status=status,
                resolver=resolver,
            )
            assert result["salt_cap_amount"] == 10000
            assert result["salt_deduction"] == 10000

    def test_mfs_lower_cap(self, resolver):
        """MFS has $5,000 cap (half of standard)."""
        result = calculate_salt_deduction(
            state_income_tax=15000,
            real_property_tax=5000,
            filing_status="MARRIED_SEPARATE",
            resolver=resolver,
        )
        assert result["salt_cap_amount"] == 5000
        assert result["salt_deduction"] == 5000
        assert result["salt_cap_reduction"] == 15000


class TestSALTEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_salt(self, resolver):
        """Zero SALT -> zero deduction."""
        result = calculate_salt_deduction(
            state_income_tax=0,
            real_property_tax=0,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 0
        assert result["salt_deduction"] == 0
        assert result["salt_cap_reduction"] == 0

    def test_one_dollar_over_cap(self, resolver):
        """SALT $1 over cap -> $1 reduction."""
        result = calculate_salt_deduction(
            state_income_tax=5000,
            real_property_tax=5001,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 10001
        assert result["salt_deduction"] == 10000
        assert result["salt_cap_reduction"] == 1

    def test_very_high_salt(self, resolver):
        """Very high SALT in high-tax state."""
        result = calculate_salt_deduction(
            state_income_tax=100000,
            real_property_tax=50000,
            personal_property_tax=10000,
            filing_status="JOINT",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 160000
        assert result["salt_deduction"] == 10000
        assert result["salt_cap_reduction"] == 150000

    def test_only_property_tax(self, resolver):
        """Only property tax, no income tax."""
        result = calculate_salt_deduction(
            state_income_tax=0,
            real_property_tax=15000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 15000
        assert result["salt_deduction"] == 10000
        assert result["salt_cap_reduction"] == 5000

    def test_only_income_tax(self, resolver):
        """Only income tax, no property tax."""
        result = calculate_salt_deduction(
            state_income_tax=15000,
            real_property_tax=0,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["salt_before_cap"] == 15000
        assert result["salt_deduction"] == 10000
        assert result["salt_cap_reduction"] == 5000
