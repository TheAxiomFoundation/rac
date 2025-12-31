"""End-to-end Alternative Minimum Tax calculation tests using override resolver.

Validates that:
1. Override resolver loads AMT parameters correctly
2. AMT calculations match IRS published values
3. Integration with cosilico-us statute files works

Reference:
- 26 USC Section 55 - Alternative Minimum Tax
- Rev. Proc. 2023-34, Section 3.03-3.04 - AMT inflation adjustments for 2024
"""

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


def calculate_amt(
    amti: float,
    regular_tax: float,
    filing_status: str,
    resolver,
    tax_year: int = 2024,
) -> dict:
    """Calculate Alternative Minimum Tax using resolved parameters.

    Returns dict with:
    - exemption: AMT exemption after phaseout
    - taxable_excess: AMTI - exemption
    - tentative_minimum_tax: Tax at 26%/28% rates
    - amt: Final AMT (excess of TMT over regular tax)

    Formula per 26 USC Section 55:
    1. Get exemption for filing status (Section 55(d)(1))
    2. Apply phaseout at 25% over threshold (Section 55(d)(2))
    3. Calculate taxable excess = AMTI - exemption
    4. Apply 26% rate up to bracket, 28% above (Section 55(b)(1))
    5. AMT = max(0, TMT - regular_tax) (Section 55(a))
    """
    # Load exemption amounts
    exemption_data = resolver.load_base_value("statute/26/55/d/1")
    phaseout_data = resolver.load_base_value("statute/26/55/d/2")
    rate_data = resolver.load_base_value("statute/26/55/b/1")
    bracket_data = resolver.load_base_value("statute/26/55/b/3")

    # Get values based on filing status
    fs = filing_status.upper()
    if fs == "JOINT":
        exemption_base = get_value_for_year(
            exemption_data["exemption_joint"]["values"], tax_year
        )
        phaseout_threshold = get_value_for_year(
            phaseout_data["phaseout_threshold_joint"]["values"], tax_year
        )
        bracket_threshold = get_value_for_year(
            bracket_data["amt_bracket_joint"]["values"], tax_year
        )
    elif fs == "MARRIED_SEPARATE":
        exemption_base = get_value_for_year(
            exemption_data["exemption_married_separate"]["values"], tax_year
        )
        phaseout_threshold = get_value_for_year(
            phaseout_data["phaseout_threshold_married_separate"]["values"], tax_year
        )
        bracket_threshold = get_value_for_year(
            bracket_data["amt_bracket_married_separate"]["values"], tax_year
        )
    else:  # SINGLE or HEAD_OF_HOUSEHOLD
        exemption_base = get_value_for_year(
            exemption_data["exemption_single"]["values"], tax_year
        )
        phaseout_threshold = get_value_for_year(
            phaseout_data["phaseout_threshold_single"]["values"], tax_year
        )
        bracket_threshold = get_value_for_year(
            bracket_data["amt_bracket_single"]["values"], tax_year
        )

    phaseout_rate = get_value_for_year(
        phaseout_data["phaseout_rate"]["values"], tax_year
    )
    rate_low = get_value_for_year(rate_data["amt_rate_low"]["values"], tax_year)
    rate_high = get_value_for_year(rate_data["amt_rate_high"]["values"], tax_year)

    # Step 1-2: Calculate exemption with phaseout
    excess_over_threshold = max(0, amti - phaseout_threshold)
    phaseout_amount = excess_over_threshold * phaseout_rate
    exemption = max(0, exemption_base - phaseout_amount)

    # Step 3: Calculate taxable excess
    taxable_excess = max(0, amti - exemption)

    # Step 4: Calculate tentative minimum tax (two-bracket)
    amount_at_26_pct = min(taxable_excess, bracket_threshold)
    amount_at_28_pct = max(0, taxable_excess - bracket_threshold)
    tmt = (amount_at_26_pct * rate_low) + (amount_at_28_pct * rate_high)

    # Step 5: AMT is excess of TMT over regular tax
    amt = max(0, tmt - regular_tax)

    return {
        "exemption_base": exemption_base,
        "phaseout_threshold": phaseout_threshold,
        "phaseout_amount": phaseout_amount,
        "exemption": exemption,
        "taxable_excess": taxable_excess,
        "tentative_minimum_tax": tmt,
        "amt": amt,
    }


class TestAMTParameterLoading:
    """Test that AMT parameters load correctly from statute files."""

    def test_exemption_2024_joint(self, resolver):
        """Verify joint exemption is $133,300 for 2024."""
        data = resolver.load_base_value("statute/26/55/d/1")
        assert data is not None
        value = get_value_for_year(data["exemption_joint"]["values"], 2024)
        assert value == 133300

    def test_exemption_2024_single(self, resolver):
        """Verify single exemption is $85,700 for 2024."""
        data = resolver.load_base_value("statute/26/55/d/1")
        value = get_value_for_year(data["exemption_single"]["values"], 2024)
        assert value == 85700

    def test_exemption_2024_mfs(self, resolver):
        """Verify MFS exemption is $66,650 for 2024."""
        data = resolver.load_base_value("statute/26/55/d/1")
        value = get_value_for_year(data["exemption_married_separate"]["values"], 2024)
        assert value == 66650

    def test_phaseout_threshold_2024_joint(self, resolver):
        """Verify joint phaseout threshold is $1,218,700 for 2024."""
        data = resolver.load_base_value("statute/26/55/d/2")
        value = get_value_for_year(data["phaseout_threshold_joint"]["values"], 2024)
        assert value == 1218700

    def test_phaseout_threshold_2024_single(self, resolver):
        """Verify single phaseout threshold is $609,350 for 2024."""
        data = resolver.load_base_value("statute/26/55/d/2")
        value = get_value_for_year(data["phaseout_threshold_single"]["values"], 2024)
        assert value == 609350

    def test_phaseout_rate(self, resolver):
        """Verify phaseout rate is 25%."""
        data = resolver.load_base_value("statute/26/55/d/2")
        value = get_value_for_year(data["phaseout_rate"]["values"], 2024)
        assert value == 0.25

    def test_rates(self, resolver):
        """Verify AMT rates are 26% and 28%."""
        data = resolver.load_base_value("statute/26/55/b/1")
        assert get_value_for_year(data["amt_rate_low"]["values"], 2024) == 0.26
        assert get_value_for_year(data["amt_rate_high"]["values"], 2024) == 0.28

    def test_bracket_2024(self, resolver):
        """Verify 2024 bracket thresholds."""
        data = resolver.load_base_value("statute/26/55/b/3")
        assert get_value_for_year(data["amt_bracket_joint"]["values"], 2024) == 232600
        assert get_value_for_year(data["amt_bracket_single"]["values"], 2024) == 116300


class TestAMTBelowPhaseout:
    """Test AMT calculations for taxpayers below phaseout threshold."""

    def test_single_no_amt(self, resolver):
        """Single filer, AMTI $100k, regular tax exceeds TMT -> no AMT."""
        # AMTI $100k, exemption $85,700 = taxable excess $14,300
        # TMT = $14,300 * 0.26 = $3,718
        # Regular tax $15,000 > TMT -> AMT = $0
        result = calculate_amt(
            amti=100000,
            regular_tax=15000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["exemption"] == 85700
        assert result["taxable_excess"] == 14300
        assert result["tentative_minimum_tax"] == pytest.approx(3718, rel=0.01)
        assert result["amt"] == 0

    def test_joint_no_amt(self, resolver):
        """Joint filer, AMTI $200k, regular tax exceeds TMT -> no AMT."""
        # AMTI $200k, exemption $133,300 = taxable excess $66,700
        # TMT = $66,700 * 0.26 = $17,342
        # Regular tax $25,000 > TMT -> AMT = $0
        result = calculate_amt(
            amti=200000,
            regular_tax=25000,
            filing_status="JOINT",
            resolver=resolver,
        )
        assert result["exemption"] == 133300
        assert result["taxable_excess"] == 66700
        assert result["tentative_minimum_tax"] == pytest.approx(17342, rel=0.01)
        assert result["amt"] == 0

    def test_single_with_amt(self, resolver):
        """Single filer where TMT exceeds regular tax -> has AMT."""
        # AMTI $150k, exemption $85,700 = taxable excess $64,300
        # TMT = $64,300 * 0.26 = $16,718
        # Regular tax $10,000 < TMT -> AMT = $6,718
        result = calculate_amt(
            amti=150000,
            regular_tax=10000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["exemption"] == 85700
        assert result["taxable_excess"] == 64300
        assert result["tentative_minimum_tax"] == pytest.approx(16718, rel=0.01)
        assert result["amt"] == pytest.approx(6718, rel=0.01)

    def test_amti_below_exemption(self, resolver):
        """AMTI below exemption amount -> no AMT."""
        # AMTI $50k < exemption $85,700 = taxable excess $0
        result = calculate_amt(
            amti=50000,
            regular_tax=5000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["exemption"] == 85700
        assert result["taxable_excess"] == 0
        assert result["tentative_minimum_tax"] == 0
        assert result["amt"] == 0


class TestAMTPhaseout:
    """Test AMT exemption phaseout calculations."""

    def test_single_partial_phaseout(self, resolver):
        """Single filer with partial exemption phaseout."""
        # AMTI $700k, threshold $609,350
        # Excess = $90,650
        # Phaseout = $90,650 * 0.25 = $22,662.50
        # Exemption = $85,700 - $22,662.50 = $63,037.50
        result = calculate_amt(
            amti=700000,
            regular_tax=100000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["phaseout_amount"] == pytest.approx(22662.5, rel=0.01)
        assert result["exemption"] == pytest.approx(63037.5, rel=0.01)

    def test_single_full_phaseout(self, resolver):
        """Single filer with exemption fully phased out."""
        # AMTI $1M, threshold $609,350
        # Excess = $390,650
        # Phaseout = $390,650 * 0.25 = $97,662.50
        # Exemption = $85,700 - $97,662.50 = $0 (floored)
        result = calculate_amt(
            amti=1000000,
            regular_tax=200000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["exemption"] == 0
        assert result["taxable_excess"] == 1000000

    def test_joint_partial_phaseout(self, resolver):
        """Joint filer with partial exemption phaseout."""
        # AMTI $1.4M, threshold $1,218,700
        # Excess = $181,300
        # Phaseout = $181,300 * 0.25 = $45,325
        # Exemption = $133,300 - $45,325 = $87,975
        result = calculate_amt(
            amti=1400000,
            regular_tax=300000,
            filing_status="JOINT",
            resolver=resolver,
        )
        assert result["phaseout_amount"] == pytest.approx(45325, rel=0.01)
        assert result["exemption"] == pytest.approx(87975, rel=0.01)

    def test_joint_exactly_at_threshold(self, resolver):
        """Joint filer exactly at phaseout threshold -> no phaseout."""
        result = calculate_amt(
            amti=1218700,
            regular_tax=250000,
            filing_status="JOINT",
            resolver=resolver,
        )
        assert result["phaseout_amount"] == 0
        assert result["exemption"] == 133300


class TestAMTTwoBracket:
    """Test AMT two-bracket rate structure (26%/28%)."""

    def test_single_within_26_bracket(self, resolver):
        """Taxable excess within 26% bracket only."""
        # Single bracket threshold: $116,300
        # AMTI $150k, exemption $85,700 = taxable excess $64,300
        # All at 26%: $64,300 * 0.26 = $16,718
        result = calculate_amt(
            amti=150000,
            regular_tax=10000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["taxable_excess"] == 64300
        assert result["tentative_minimum_tax"] == pytest.approx(16718, rel=0.01)

    def test_single_into_28_bracket(self, resolver):
        """Taxable excess spans both brackets."""
        # Single bracket threshold: $116,300
        # AMTI $250k, exemption $85,700 = taxable excess $164,300
        # At 26%: $116,300 * 0.26 = $30,238
        # At 28%: ($164,300 - $116,300) * 0.28 = $13,440
        # Total TMT = $43,678
        result = calculate_amt(
            amti=250000,
            regular_tax=30000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["taxable_excess"] == 164300
        expected_tmt = 116300 * 0.26 + 48000 * 0.28
        assert result["tentative_minimum_tax"] == pytest.approx(expected_tmt, rel=0.01)

    def test_joint_into_28_bracket(self, resolver):
        """Joint filer with income spanning both brackets."""
        # Joint bracket threshold: $232,600
        # AMTI $400k, exemption $133,300 = taxable excess $266,700
        # At 26%: $232,600 * 0.26 = $60,476
        # At 28%: ($266,700 - $232,600) * 0.28 = $9,548
        # Total TMT = $70,024
        result = calculate_amt(
            amti=400000,
            regular_tax=50000,
            filing_status="JOINT",
            resolver=resolver,
        )
        assert result["taxable_excess"] == 266700
        expected_tmt = 232600 * 0.26 + 34100 * 0.28
        assert result["tentative_minimum_tax"] == pytest.approx(expected_tmt, rel=0.01)
        assert result["amt"] == pytest.approx(expected_tmt - 50000, rel=0.01)


class TestAMTMarriedFilingSeparately:
    """Test AMT for married filing separately status."""

    def test_mfs_exemption(self, resolver):
        """Verify MFS uses correct exemption amount."""
        result = calculate_amt(
            amti=100000,
            regular_tax=15000,
            filing_status="MARRIED_SEPARATE",
            resolver=resolver,
        )
        assert result["exemption"] == 66650

    def test_mfs_with_amt(self, resolver):
        """MFS filer where TMT exceeds regular tax."""
        # AMTI $150k, exemption $66,650 = taxable excess $83,350
        # TMT = $83,350 * 0.26 = $21,671
        result = calculate_amt(
            amti=150000,
            regular_tax=15000,
            filing_status="MARRIED_SEPARATE",
            resolver=resolver,
        )
        assert result["taxable_excess"] == 83350
        assert result["tentative_minimum_tax"] == pytest.approx(21671, rel=0.01)
        assert result["amt"] == pytest.approx(6671, rel=0.01)


class TestAMTEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_amti(self, resolver):
        """Zero AMTI -> no AMT."""
        result = calculate_amt(
            amti=0,
            regular_tax=0,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["amt"] == 0

    def test_high_income_full_phaseout(self, resolver):
        """Very high income with full exemption phaseout."""
        # AMTI $5M, single
        # Exemption fully phased out
        # All $5M taxed at AMT rates
        result = calculate_amt(
            amti=5000000,
            regular_tax=1500000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["exemption"] == 0
        # TMT = $116,300 * 0.26 + ($5M - $116,300) * 0.28
        expected_tmt = 116300 * 0.26 + (5000000 - 116300) * 0.28
        assert result["tentative_minimum_tax"] == pytest.approx(expected_tmt, rel=0.01)

    def test_tmt_equals_regular_tax(self, resolver):
        """TMT exactly equals regular tax -> no AMT."""
        # AMTI $150k, exemption $85,700 = taxable excess $64,300
        # TMT = $16,718
        # Set regular tax = TMT
        result = calculate_amt(
            amti=150000,
            regular_tax=16718,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["amt"] == pytest.approx(0, abs=1)

    def test_exactly_at_bracket_threshold(self, resolver):
        """Taxable excess exactly at bracket threshold."""
        # Single: bracket threshold $116,300
        # Need taxable excess = $116,300
        # AMTI = $116,300 + $85,700 = $202,000
        result = calculate_amt(
            amti=202000,
            regular_tax=30000,
            filing_status="SINGLE",
            resolver=resolver,
        )
        assert result["taxable_excess"] == 116300
        # All at 26%
        expected_tmt = 116300 * 0.26
        assert result["tentative_minimum_tax"] == pytest.approx(expected_tmt, rel=0.01)
