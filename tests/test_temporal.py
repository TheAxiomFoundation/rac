"""Tests for temporal value resolution in the v2-to-engine pipeline.

Verifies that parameters with multiple date-dependent values resolve
correctly for different as_of dates.
"""

from datetime import date

import pytest

from rac.dsl_parser import parse_dsl
from rac.engine import compile as engine_compile, execute as engine_execute
from rac.engine.converter import convert_v2_to_engine_module


class TestTemporalParameters:
    """Test temporal resolution of v2 parameters through the engine."""

    def test_parameter_resolves_to_correct_date(self):
        """Parameters resolve to the value effective on the as_of date."""
        v2_source = """
parameter threshold:
  values:
    2023-01-01: 10000
    2024-01-01: 12000
    2025-01-01: 14000
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="gov")

        # 2023 → 10000
        ir = engine_compile([engine_module], as_of=date(2023, 6, 1))
        result = engine_execute(ir, {})
        assert result.scalars["gov/threshold"] == 10000

        # 2024 → 12000
        ir = engine_compile([engine_module], as_of=date(2024, 6, 1))
        result = engine_execute(ir, {})
        assert result.scalars["gov/threshold"] == 12000

        # 2025 → 14000
        ir = engine_compile([engine_module], as_of=date(2025, 6, 1))
        result = engine_execute(ir, {})
        assert result.scalars["gov/threshold"] == 14000

    def test_formula_uses_temporally_resolved_parameter(self):
        """Formulas compute correctly using the date-resolved parameter values."""
        v2_source = """
parameter rate:
  values:
    2023-01-01: 0.10
    2024-01-01: 0.20

input income:
  entity: Person
  period: Year
  dtype: Money
  default: 0

variable tax:
  entity: Person
  period: Year
  dtype: Money
  formula: income * rate
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")
        data = {"person": [{"id": 1, "income": 1000}]}

        # 2023: rate=0.10 → tax=100
        ir = engine_compile([engine_module], as_of=date(2023, 6, 1))
        result = engine_execute(ir, data)
        assert result.entities["person"]["test/tax"] == [100.0]

        # 2024: rate=0.20 → tax=200
        ir = engine_compile([engine_module], as_of=date(2024, 6, 1))
        result = engine_execute(ir, data)
        assert result.entities["person"]["test/tax"] == [200.0]

    def test_no_value_before_earliest_date(self):
        """If as_of is before all parameter dates, the variable is not resolved."""
        v2_source = """
parameter rate:
  values:
    2024-01-01: 0.25
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")

        ir = engine_compile([engine_module], as_of=date(2020, 1, 1))
        # Variable should not be in IR (no applicable temporal value)
        assert "test/rate" not in ir.variables

    def test_multiple_parameters_different_timelines(self):
        """Multiple parameters with different temporal schedules resolve independently."""
        v2_source = """
parameter rate:
  values:
    2024-01-01: 0.10
    2025-01-01: 0.15

parameter exemption:
  values:
    2023-01-01: 5000
    2024-07-01: 6000

input income:
  entity: Person
  period: Year
  dtype: Money
  default: 0

variable tax:
  entity: Person
  period: Year
  dtype: Money
  formula: max(0, income - exemption) * rate
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")
        data = {"person": [{"id": 1, "income": 10000}]}

        # 2024-03: rate=0.10, exemption=5000 → (10000-5000)*0.10 = 500
        ir = engine_compile([engine_module], as_of=date(2024, 3, 1))
        result = engine_execute(ir, data)
        assert result.entities["person"]["test/tax"] == [500.0]

        # 2025-03: rate=0.15, exemption=6000 → (10000-6000)*0.15 = 600
        ir = engine_compile([engine_module], as_of=date(2025, 3, 1))
        result = engine_execute(ir, data)
        assert result.entities["person"]["test/tax"] == [600.0]
