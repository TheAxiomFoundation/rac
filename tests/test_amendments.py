"""Tests for amendment/reform workflow.

Amendments use the engine's native format (amend keyword) which can be
applied on top of v2 modules converted to engine format.
"""

from datetime import date

from rac.dsl_parser import parse_dsl
from rac.engine import compile as engine_compile
from rac.engine import execute as engine_execute
from rac.engine import parse as engine_parse
from rac.engine.converter import convert_v2_to_engine_module


class TestAmendmentWorkflow:
    """Test amendment files applied on top of baseline v2 modules."""

    def test_amend_parameter_value(self):
        """An amendment overrides a parameter's value."""
        # Baseline in v2 format
        v2_source = """
parameter rate:
  values:
    2024-01-01: 0.10

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
        # Reform in engine format
        reform_source = """
amend test/rate:
    from 2024-01-01: 0.20
"""
        v2_module = parse_dsl(v2_source)
        baseline_module = convert_v2_to_engine_module(v2_module, module_path="test")
        reform_module = engine_parse(reform_source)

        # Compile with amendment applied
        ir = engine_compile([baseline_module, reform_module], as_of=date(2024, 6, 1))
        data = {"person": [{"id": 1, "income": 1000}]}
        result = engine_execute(ir, data)

        # With amendment: tax = 1000 * 0.20 = 200
        assert result.entities["person"]["test/tax"] == [200.0]

    def test_baseline_without_amendment(self):
        """Verify baseline is correct before applying amendment."""
        v2_source = """
parameter rate:
  values:
    2024-01-01: 0.10

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
        baseline_module = convert_v2_to_engine_module(v2_module, module_path="test")

        ir = engine_compile([baseline_module], as_of=date(2024, 6, 1))
        data = {"person": [{"id": 1, "income": 1000}]}
        result = engine_execute(ir, data)

        # Without amendment: tax = 1000 * 0.10 = 100
        assert result.entities["person"]["test/tax"] == [100.0]

    def test_amendment_with_effective_date(self):
        """An amendment that takes effect mid-year only applies after its date."""
        v2_source = """
parameter rate:
  values:
    2024-01-01: 0.10

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
        reform_source = """
amend test/rate:
    from 2024-07-01: 0.15
"""
        v2_module = parse_dsl(v2_source)
        baseline = convert_v2_to_engine_module(v2_module, module_path="test")
        reform = engine_parse(reform_source)

        # Before amendment effective date: still 0.10
        ir = engine_compile([baseline, reform], as_of=date(2024, 3, 1))
        data = {"person": [{"id": 1, "income": 1000}]}
        result = engine_execute(ir, data)
        assert result.entities["person"]["test/tax"] == [100.0]

        # After amendment effective date: 0.15
        ir = engine_compile([baseline, reform], as_of=date(2024, 8, 1))
        result = engine_execute(ir, data)
        assert result.entities["person"]["test/tax"] == [150.0]

    def test_multiple_amendments_stack(self):
        """Multiple amendments stack — later amendments override earlier ones."""
        v2_source = """
parameter rate:
  values:
    2024-01-01: 0.10
"""
        reform1 = engine_parse("""
amend test/rate:
    from 2024-01-01: 0.15
""")
        reform2 = engine_parse("""
amend test/rate:
    from 2024-01-01: 0.20
""")

        v2_module = parse_dsl(v2_source)
        baseline = convert_v2_to_engine_module(v2_module, module_path="test")

        ir = engine_compile([baseline, reform1, reform2], as_of=date(2024, 6, 1))
        result = engine_execute(ir, {})

        # Last amendment wins: 0.20
        assert result.scalars["test/rate"] == 0.20

    def test_reform_comparison(self):
        """Compare baseline vs reform results side by side."""
        v2_source = """
parameter exemption:
  values:
    2024-01-01: 5000

parameter rate:
  values:
    2024-01-01: 0.10

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
        reform_source = """
amend test/exemption:
    from 2024-01-01: 8000
amend test/rate:
    from 2024-01-01: 0.12
"""
        v2_module = parse_dsl(v2_source)
        baseline = convert_v2_to_engine_module(v2_module, module_path="test")
        reform = engine_parse(reform_source)

        data = {"person": [{"id": 1, "income": 10000}, {"id": 2, "income": 3000}]}

        # Baseline: (10000-5000)*0.10=500, max(0,3000-5000)*0.10=0
        ir_base = engine_compile([baseline], as_of=date(2024, 6, 1))
        result_base = engine_execute(ir_base, data)
        assert result_base.entities["person"]["test/tax"] == [500.0, 0]

        # Reform: (10000-8000)*0.12=240, max(0,3000-8000)*0.12=0
        ir_reform = engine_compile([baseline, reform], as_of=date(2024, 6, 1))
        result_reform = engine_execute(ir_reform, data)
        assert result_reform.entities["person"]["test/tax"] == [240.0, 0]
