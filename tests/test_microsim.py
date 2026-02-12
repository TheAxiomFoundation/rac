"""Tests for RAC microsimulation runner."""

import numpy as np
import pytest

pd = pytest.importorskip("pandas")


class TestCPSLoading:
    """Tests for CPS data loading."""

    def test_load_cps_finds_data(self):
        """Can find and load CPS data from sibling repo."""
        from src.rac.microsim import load_cps

        # Try to load - may fail if data not present
        try:
            df = load_cps(year=2024)
            assert len(df) > 0
            assert "weight" in df.columns
            assert "wage_salary_income" in df.columns or "income" in df.columns
        except FileNotFoundError:
            pytest.skip("CPS data not found")

    def test_load_cps_has_required_columns(self):
        """CPS data has columns needed for tax calculations."""
        from src.rac.microsim import load_cps

        try:
            df = load_cps(year=2024)
            required = ["weight", "age"]
            for col in required:
                assert col in df.columns, f"Missing column: {col}"
        except FileNotFoundError:
            pytest.skip("CPS data not found")


class TestInputMapping:
    """Tests for CPS to Cosilico input mapping."""

    def test_map_creates_earned_income(self):
        """Mapping creates earned_income from wage components."""
        import pandas as pd

        from src.rac.microsim import map_cps_to_inputs

        df = pd.DataFrame({
            "wage_salary_income": [50000, 0, 25000],
            "self_employment_income": [0, 10000, 5000],
            "weight": [100, 100, 100],
            "age": [35, 40, 30],
            "household_id": [1, 2, 3],
        })

        inputs = map_cps_to_inputs(df)

        assert "earned_income" in inputs
        np.testing.assert_array_equal(inputs["earned_income"], [50000, 10000, 30000])

    def test_map_handles_missing_columns(self):
        """Mapping handles CPS files with missing optional columns."""
        import pandas as pd

        from src.rac.microsim import map_cps_to_inputs

        df = pd.DataFrame({
            "wage_salary_income": [50000],
            "weight": [100],
            "age": [35],
            "household_id": [1],
            # Missing: self_employment_income, etc.
        })

        inputs = map_cps_to_inputs(df)

        assert "earned_income" in inputs
        assert inputs["earned_income"][0] == 50000

    def test_map_filing_status(self):
        """Mapping infers filing status from marital status."""
        import pandas as pd

        from src.rac.microsim import map_cps_to_inputs

        df = pd.DataFrame({
            "marital_status": [1, 6, 4],  # Married, Never married, Divorced
            "weight": [100, 100, 100],
            "age": [35, 25, 40],
            "household_id": [1, 2, 3],
        })

        inputs = map_cps_to_inputs(df)

        assert inputs["filing_status"][0] == "JOINT"
        assert inputs["filing_status"][1] == "SINGLE"
        assert inputs["filing_status"][2] == "SINGLE"


    def test_derive_qualifying_children(self):
        """Qualifying children are derived from household structure per §152(c)."""
        import pandas as pd

        from src.rac.microsim import derive_qualifying_children

        # Household 1: Two adults (35, 32) with two children (8, 5)
        # Household 2: Single adult (28) with one child (3)
        # Household 3: Single adult (25) with no children
        df = pd.DataFrame({
            "household_id": [1, 1, 1, 1, 2, 2, 3],
            "age": [35, 32, 8, 5, 28, 3, 25],
        })

        children = derive_qualifying_children(df)

        # Oldest adult in HH1 (age 35) should have 2 children
        assert children[0] == 2  # Adult age 35

        # Other household members should have 0
        assert children[1] == 0  # Adult age 32 (spouse, not primary filer)
        assert children[2] == 0  # Child age 8
        assert children[3] == 0  # Child age 5

        # Adult in HH2 should have 1 child
        assert children[4] == 1  # Adult age 28

        # Child in HH2 should have 0
        assert children[5] == 0  # Child age 3

        # Adult in HH3 with no children should have 0
        assert children[6] == 0  # Adult age 25


class TestMicrosimExecution:
    """Tests for running microsimulation."""

    def test_run_microsim_returns_aggregates(self):
        """Microsim returns aggregate statistics."""
        from src.rac.microsim import run_microsim

        try:
            results = run_microsim(year=2024, sample_size=1000)

            assert "meta" in results
            assert "variables" in results
            assert results["meta"]["n_records"] == 1000
            assert "adjusted_gross_income" in results["variables"]
        except FileNotFoundError:
            pytest.skip("CPS data not found")

    def test_run_microsim_computes_totals(self):
        """Microsim computes weighted totals."""
        from src.rac.microsim import run_microsim

        try:
            results = run_microsim(year=2024, sample_size=1000)

            agi = results["variables"]["adjusted_gross_income"]
            assert agi["total"] > 0
            assert agi["mean"] > 0
            assert agi["nonzero_count"] > 0
        except FileNotFoundError:
            pytest.skip("CPS data not found")


class TestPerformance:
    """Performance benchmarks for microsimulation."""

    def test_full_cps_under_one_second(self):
        """Full CPS microsim completes in under 1 second."""
        from src.rac.microsim import run_microsim

        try:
            results = run_microsim(year=2024)

            # Should be well under 1 second (typically <0.01s)
            assert results["meta"]["elapsed_seconds"] < 1.0
            assert results["meta"]["n_records"] > 100000
        except FileNotFoundError:
            pytest.skip("CPS data not found")

    def test_throughput_exceeds_10m_per_second(self):
        """Microsim processes at least 10M records per second."""
        from src.rac.microsim import run_microsim

        try:
            results = run_microsim(year=2024)

            throughput = results["meta"]["records_per_second"]
            assert throughput > 10_000_000, f"Throughput {throughput:,.0f} < 10M/sec"
        except FileNotFoundError:
            pytest.skip("CPS data not found")
