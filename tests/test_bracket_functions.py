"""Tests for bracket calculation functions: cut and marginal_agg.

These functions handle common tax/benefit patterns:
- cut: Step function lookup (which bracket are you in?)
- marginal_agg: Marginal rate aggregation (sum of amount * rate per bracket)
"""

import pytest
import numpy as np
from src.rac.brackets import cut, marginal_agg


class TestCut:
    """Test cut() - step function lookup."""

    def test_simple_lookup(self):
        """Basic step function: value based on which bracket."""
        schedule = {
            "thresholds": [10000, 20000, 30000],
            "amounts": [100, 75, 50, 0],
        }
        # Below first threshold
        assert cut(5000, schedule) == 100
        # Between first and second
        assert cut(15000, schedule) == 75
        # Between second and third
        assert cut(25000, schedule) == 50
        # Above all thresholds
        assert cut(40000, schedule) == 0

    def test_at_threshold_boundary(self):
        """Values exactly at thresholds."""
        schedule = {
            "thresholds": [10000, 20000],
            "amounts": [100, 50, 0],
        }
        # At threshold goes to next bracket
        assert cut(10000, schedule) == 50
        assert cut(20000, schedule) == 0

    def test_amount_by_key(self):
        """Amounts vary by categorical key (e.g., household size)."""
        schedule = {
            "thresholds": [100, 130],  # FPL percentages
            "amounts": {
                1: [291, 200, 0],
                2: [535, 400, 0],
                3: [766, 600, 0],
            },
        }
        # Household size 1, below 100% FPL
        assert cut(80, schedule, amount_by=1) == 291
        # Household size 2, between 100-130% FPL
        assert cut(115, schedule, amount_by=2) == 400
        # Household size 3, above 130% FPL
        assert cut(150, schedule, amount_by=3) == 0

    def test_threshold_by_key(self):
        """Thresholds vary by categorical key (e.g., state)."""
        schedule = {
            "thresholds": {
                "CA": [50000, 100000],
                "TX": [40000, 80000],
            },
            "amounts": [1000, 500, 0],
        }
        # CA thresholds
        assert cut(60000, schedule, threshold_by="CA") == 500
        # TX thresholds - same income falls in different bracket
        assert cut(60000, schedule, threshold_by="TX") == 500
        assert cut(45000, schedule, threshold_by="TX") == 500
        assert cut(35000, schedule, threshold_by="TX") == 1000

    def test_both_keys(self):
        """Both thresholds and amounts vary."""
        schedule = {
            "thresholds": {
                "urban": [100, 130],
                "rural": [130, 185],
            },
            "amounts": {
                1: [300, 200, 0],
                2: [550, 400, 0],
            },
        }
        # Urban area, household size 1, 115% FPL
        assert cut(115, schedule, threshold_by="urban", amount_by=1) == 200
        # Rural area, household size 2, 115% FPL (still in first bracket for rural)
        assert cut(115, schedule, threshold_by="rural", amount_by=2) == 550

    def test_vectorized(self):
        """Works with numpy arrays."""
        schedule = {
            "thresholds": [10000, 20000],
            "amounts": [100, 50, 0],
        }
        incomes = np.array([5000, 15000, 25000])
        result = cut(incomes, schedule)
        np.testing.assert_array_equal(result, [100, 50, 0])

    def test_vectorized_with_key_array(self):
        """Keys can also be arrays for vectorized lookup."""
        schedule = {
            "thresholds": [100, 200],
            "amounts": {
                1: [300, 200, 0],
                2: [500, 350, 0],
            },
        }
        incomes = np.array([50, 150, 250])
        hh_sizes = np.array([1, 2, 1])
        result = cut(incomes, schedule, amount_by=hh_sizes)
        np.testing.assert_array_equal(result, [300, 350, 0])


class TestMarginalAgg:
    """Test marginal_agg() - marginal rate aggregation."""

    def test_simple_brackets(self):
        """Basic marginal tax calculation."""
        brackets = {
            "thresholds": [0, 10000, 40000, 80000],
            "rates": [0.10, 0.12, 0.22, 0.24],
        }
        # Income of 15000:
        # First 10000 at 10% = 1000
        # Next 5000 at 12% = 600
        # Total = 1600
        assert marginal_agg(15000, brackets) == pytest.approx(1600)

    def test_all_brackets(self):
        """Income spans all brackets."""
        brackets = {
            "thresholds": [0, 10000, 40000],
            "rates": [0.10, 0.20, 0.30],
        }
        # Income of 50000:
        # First 10000 at 10% = 1000
        # Next 30000 at 20% = 6000
        # Next 10000 at 30% = 3000
        # Total = 10000
        assert marginal_agg(50000, brackets) == pytest.approx(10000)

    def test_below_first_threshold(self):
        """Income below first threshold."""
        brackets = {
            "thresholds": [0, 10000],
            "rates": [0.10, 0.20],
        }
        assert marginal_agg(5000, brackets) == pytest.approx(500)

    def test_zero_income(self):
        """Zero income returns zero tax."""
        brackets = {
            "thresholds": [0, 10000],
            "rates": [0.10, 0.20],
        }
        assert marginal_agg(0, brackets) == 0

    def test_threshold_by_filing_status(self):
        """Thresholds vary by filing status."""
        brackets = {
            "thresholds": {
                "single": [0, 11600, 47150],
                "joint": [0, 23200, 94300],
            },
            "rates": [0.10, 0.12, 0.22],
        }
        # Single with 20000 income:
        # First 11600 at 10% = 1160
        # Next 8400 at 12% = 1008
        # Total = 2168
        assert marginal_agg(20000, brackets, threshold_by="single") == pytest.approx(2168)

        # Joint with 20000 income:
        # First 20000 at 10% = 2000 (still in first bracket)
        assert marginal_agg(20000, brackets, threshold_by="joint") == pytest.approx(2000)

    def test_real_federal_brackets_2024(self):
        """Test with actual 2024 federal tax brackets."""
        brackets = {
            "thresholds": {
                "single": [0, 11600, 47150, 100525, 191950, 243725, 609350],
                "joint": [0, 23200, 94300, 201050, 383900, 487450, 731200],
            },
            "rates": [0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37],
        }
        # Single filer with $50,000 income
        # 11600 * 0.10 = 1160
        # (47150 - 11600) * 0.12 = 4266
        # (50000 - 47150) * 0.22 = 627
        # Total = 6053
        expected = 11600 * 0.10 + (47150 - 11600) * 0.12 + (50000 - 47150) * 0.22
        assert marginal_agg(50000, brackets, threshold_by="single") == pytest.approx(expected)

    def test_vectorized(self):
        """Works with numpy arrays."""
        brackets = {
            "thresholds": [0, 10000, 40000],
            "rates": [0.10, 0.20, 0.30],
        }
        incomes = np.array([5000, 15000, 50000])
        result = marginal_agg(incomes, brackets)
        expected = np.array([500, 2000, 10000])
        np.testing.assert_array_almost_equal(result, expected)

    def test_vectorized_with_threshold_key(self):
        """Vectorized with varying filing status."""
        brackets = {
            "thresholds": {
                "single": [0, 10000],
                "joint": [0, 20000],
            },
            "rates": [0.10, 0.20],
        }
        incomes = np.array([15000, 15000])
        statuses = np.array(["single", "joint"])
        result = marginal_agg(incomes, brackets, threshold_by=statuses)
        # Single: 10000 * 0.10 + 5000 * 0.20 = 2000
        # Joint: 15000 * 0.10 = 1500
        np.testing.assert_array_almost_equal(result, [2000, 1500])

    def test_offset_basic(self):
        """Offset shifts where amount starts in brackets."""
        brackets = {
            "thresholds": [0, 10000, 40000],
            "rates": [0.10, 0.20, 0.30],
        }
        # Without offset: 15000 income
        # 10000 * 0.10 + 5000 * 0.20 = 2000
        assert marginal_agg(15000, brackets) == pytest.approx(2000)

        # With offset of 5000 (ordinary income already used 5000 of first bracket)
        # Preferential income of 15000 starts at position 5000
        # 5000 at 0.10 (fills rest of first bracket) + 10000 at 0.20 = 2500
        assert marginal_agg(15000, brackets, offset=5000) == pytest.approx(2500)

    def test_offset_skips_bracket(self):
        """Offset can skip entire brackets."""
        brackets = {
            "thresholds": [0, 10000, 40000],
            "rates": [0.10, 0.20, 0.30],
        }
        # Offset of 35000 uses all of first bracket and 25000 of second
        # Preferential income of 10000 starts at position 35000
        # 5000 at 0.20 (fills rest of second bracket) + 5000 at 0.30 = 2500
        assert marginal_agg(10000, brackets, offset=35000) == pytest.approx(2500)

    def test_offset_capital_gains_pattern(self):
        """Test the capital gains pattern: ordinary income fills brackets first."""
        brackets = {
            "thresholds": {
                "single": [0, 47025, 518900],
            },
            "rates": [0.00, 0.15, 0.20],
        }
        # Single filer with $50,000 ordinary income and $30,000 cap gains
        ordinary_income = 50000
        cap_gains = 30000

        # Ordinary income uses up the 0% bracket (0-47025) and 2975 of 15% bracket
        # Cap gains of 30000: all at 15% rate
        result = marginal_agg(cap_gains, brackets, threshold_by="single", offset=ordinary_income)
        expected = 30000 * 0.15  # All cap gains in 15% bracket
        assert result == pytest.approx(expected)

    def test_offset_all_in_zero_bracket(self):
        """When offset + amount stays in 0% bracket, tax is 0."""
        brackets = {
            "thresholds": [0, 47025, 518900],
            "rates": [0.00, 0.15, 0.20],
        }
        # $20,000 ordinary income, $10,000 cap gains
        # Total $30,000 stays in 0% bracket
        result = marginal_agg(10000, brackets, offset=20000)
        assert result == pytest.approx(0)

    def test_offset_vectorized(self):
        """Offset works with vectorized inputs."""
        brackets = {
            "thresholds": [0, 10000, 40000],
            "rates": [0.10, 0.20, 0.30],
        }
        amounts = np.array([15000, 15000, 15000])
        offsets = np.array([0, 5000, 35000])
        result = marginal_agg(amounts, brackets, offset=offsets)
        # offset=0: 10000*0.10 + 5000*0.20 = 2000
        # offset=5000: 5000*0.10 + 10000*0.20 = 2500
        # offset=35000: 5000*0.20 + 10000*0.30 = 4000
        np.testing.assert_array_almost_equal(result, [2000, 2500, 4000])
