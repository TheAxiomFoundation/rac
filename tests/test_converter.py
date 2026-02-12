"""Tests for v2-to-engine converter.

Tests the bridge from existing v2 .rac format (dsl_parser) to engine IR.
"""

from datetime import date

import pytest

from rac.dsl_parser import parse_dsl
from rac.engine import compile as engine_compile
from rac.engine.converter import convert_v2_to_engine_module


class TestConvertScalars:
    """Test converting v2 parameters to engine scalars."""

    def test_convert_simple_parameter(self):
        """A v2 parameter with values becomes engine scalar variables."""
        v2_source = """
parameter tax_rate:
  description: "Basic tax rate"
  unit: rate
  values:
    2024-01-01: 0.20
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")

        assert len(engine_module.variables) == 1
        var = engine_module.variables[0]
        assert var.path == "test/tax_rate"
        assert len(var.values) == 1
        assert var.values[0].expr.value == 0.20

    def test_convert_parameter_with_multiple_dates(self):
        """A parameter with multiple date values creates multiple temporal entries."""
        v2_source = """
parameter threshold:
  values:
    2023-01-01: 10000
    2024-01-01: 12000
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")

        var = engine_module.variables[0]
        assert len(var.values) == 2
        assert var.values[0].start == date(2023, 1, 1)
        assert var.values[0].expr.value == 10000
        assert var.values[1].start == date(2024, 1, 1)
        assert var.values[1].expr.value == 12000


class TestConvertInputs:
    """Test converting v2 inputs to engine entity fields."""

    def test_convert_input_to_entity(self):
        """A v2 input creates an engine entity declaration with fields."""
        v2_source = """
input earned_income:
  entity: Person
  period: Year
  dtype: Money
  default: 0
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")

        assert len(engine_module.entities) == 1
        entity = engine_module.entities[0]
        assert entity.name == "person"  # lowercased
        assert ("earned_income", "float") in entity.fields


class TestConvertVariables:
    """Test converting v2 variables with formulas to engine variables."""

    def test_convert_simple_arithmetic(self):
        """A v2 variable with arithmetic formula converts correctly."""
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
  formula: |
    return income * rate
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")

        # Should have: 1 parameter var + 1 formula var
        var_names = [v.path for v in engine_module.variables]
        assert "test/rate" in var_names
        assert "test/tax" in var_names

        # The formula variable should have entity set
        tax_var = next(v for v in engine_module.variables if v.path == "test/tax")
        assert tax_var.entity == "person"

    @pytest.mark.xfail(reason="v2 parser doesn't support multi-line if/else in formulas yet")
    def test_convert_if_expression(self):
        """A v2 if/else converts to engine Cond.

        Currently fails because the v2 parser doesn't handle multi-line
        if/return/else/return in formula blocks. Will work after Phase 3/4.
        """
        v2_source = """
parameter threshold:
  values:
    2024-01-01: 50000

input income:
  entity: Person
  period: Year
  dtype: Money
  default: 0

variable tax:
  entity: Person
  period: Year
  dtype: Money
  formula: |
    if income > threshold:
      return income * 0.3
    else:
      return income * 0.1
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")

        tax_var = next(v for v in engine_module.variables if v.path == "test/tax")
        # The formula should be a Cond
        assert tax_var.values[0].expr.type == "cond"

    def test_convert_builtin_functions(self):
        """Builtin functions like max, min convert correctly."""
        v2_source = """
input income:
  entity: Person
  period: Year
  dtype: Money
  default: 0

variable capped:
  entity: Person
  period: Year
  dtype: Money
  formula: |
    return max(0, income - 10000)
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")

        var = next(v for v in engine_module.variables if v.path == "test/capped")
        assert var.values[0].expr.type == "call"


class TestConvertAndExecute:
    """End-to-end: convert v2 → engine IR → execute."""

    def test_execute_converted_scalar(self):
        """Convert a v2 parameter, compile, and execute."""
        from rac.engine import execute as engine_execute

        v2_source = """
parameter rate:
  values:
    2024-01-01: 0.25
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="gov")

        ir = engine_compile([engine_module], as_of=date(2024, 6, 1))
        result = engine_execute(ir, {})
        assert result.scalars["gov/rate"] == 0.25

    def test_execute_converted_formula(self):
        """Convert v2 formula, compile, and execute with entity data."""
        from rac.engine import execute as engine_execute

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
  formula: |
    return income * rate
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")

        ir = engine_compile([engine_module], as_of=date(2024, 6, 1))
        data = {"person": [{"id": 1, "income": 1000}, {"id": 2, "income": 5000}]}
        result = engine_execute(ir, data)

        assert result.entities["person"]["test/tax"] == [100.0, 500.0]

    def test_execute_converted_with_max(self):
        """Convert v2 formula with max(), compile, and execute."""
        from rac.engine import execute as engine_execute

        v2_source = """
parameter exemption:
  values:
    2024-01-01: 500

input income:
  entity: Person
  period: Year
  dtype: Money
  default: 0

variable taxable:
  entity: Person
  period: Year
  dtype: Money
  formula: max(0, income - exemption)
"""
        v2_module = parse_dsl(v2_source)
        engine_module = convert_v2_to_engine_module(v2_module, module_path="test")

        ir = engine_compile([engine_module], as_of=date(2024, 6, 1))
        data = {"person": [{"id": 1, "income": 300}, {"id": 2, "income": 700}]}
        result = engine_execute(ir, data)

        assert result.entities["person"]["test/taxable"] == [0, 200]
