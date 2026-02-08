"""Tests for rac.engine — Nikhil's clean pipeline ported as subpackage.

Tests parser, compiler, executor, Rust codegen, and high-level Model API.
"""

from datetime import date

import pytest


class TestEngineParser:
    def test_parse_scalar_variable(self):
        from rac.engine import parse

        module = parse("""
            variable gov/tax/rate:
                from 2024-01-01: 0.25
        """)
        assert len(module.variables) == 1
        assert module.variables[0].path == "gov/tax/rate"

    def test_parse_entity_variable(self):
        from rac.engine import parse

        module = parse("""
            variable person/tax:
                entity: person
                from 2024-01-01: income * 0.2
        """)
        assert module.variables[0].entity == "person"

    def test_parse_temporal_ranges(self):
        from rac.engine import parse

        module = parse("""
            variable gov/threshold:
                from 2023-01-01 to 2023-12-31: 10000
                from 2024-01-01: 12000
        """)
        assert len(module.variables[0].values) == 2

    def test_parse_expressions(self):
        from rac.engine import parse

        module = parse("""
            variable test/expr:
                from 2024-01-01: max(0, income - 10000) * 0.22
        """)
        assert module.variables[0].values[0].expr is not None

    def test_parse_conditional(self):
        from rac.engine import parse

        module = parse("""
            variable test/cond:
                from 2024-01-01:
                    if income > 50000: income * 0.3
                    else: income * 0.1
        """)
        assert module.variables[0].values[0].expr.type == "cond"

    def test_parse_entity_declaration(self):
        from rac.engine import parse

        module = parse("""
            entity person:
                age: int
                income: float
        """)
        assert len(module.entities) == 1
        assert module.entities[0].name == "person"

    def test_parse_amendment(self):
        from rac.engine import parse

        module = parse("""
            amend gov/rate:
                from 2024-06-01: 0.15
        """)
        assert len(module.amendments) == 1
        assert module.amendments[0].target == "gov/rate"


class TestEngineCompiler:
    def test_compile_scalar(self):
        from rac.engine import compile, parse

        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.25
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        assert "gov/rate" in ir.variables

    def test_temporal_resolution(self):
        from rac.engine import compile, parse

        module = parse("""
            variable gov/val:
                from 2023-01-01 to 2023-12-31: 100
                from 2024-01-01: 200
        """)
        ir_2023 = compile([module], as_of=date(2023, 6, 1))
        ir_2024 = compile([module], as_of=date(2024, 6, 1))

        assert ir_2023.variables["gov/val"].expr.value == 100
        assert ir_2024.variables["gov/val"].expr.value == 200

    def test_amendment_override(self):
        from rac.engine import compile, parse

        base = parse("""
            variable gov/rate:
                from 2024-01-01: 0.10
        """)
        amendment = parse("""
            amend gov/rate:
                from 2024-06-01: 0.15
        """)
        ir = compile([base, amendment], as_of=date(2024, 7, 1))
        assert ir.variables["gov/rate"].expr.value == 0.15

    def test_dependency_ordering(self):
        from rac.engine import compile, parse

        module = parse("""
            variable gov/base:
                from 2024-01-01: 1000

            variable gov/rate:
                from 2024-01-01: 0.1

            variable gov/tax:
                from 2024-01-01: gov/base * gov/rate
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        assert ir.order.index("gov/tax") > ir.order.index("gov/base")
        assert ir.order.index("gov/tax") > ir.order.index("gov/rate")


class TestEngineExecutor:
    def test_execute_scalar(self):
        from rac.engine import compile, execute, parse

        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.25
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["gov/rate"] == 0.25

    def test_execute_arithmetic(self):
        from rac.engine import compile, execute, parse

        module = parse("""
            variable test/a:
                from 2024-01-01: 10

            variable test/b:
                from 2024-01-01: test/a * 2 + 5
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/b"] == 25

    def test_execute_builtin_functions(self):
        from rac.engine import compile, execute, parse

        module = parse("""
            variable test/clipped:
                from 2024-01-01: clip(150, 0, 100)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/clipped"] == 100

    def test_execute_conditional(self):
        from rac.engine import compile, execute, parse

        module = parse("""
            variable test/threshold:
                from 2024-01-01: 50

            variable test/result:
                from 2024-01-01:
                    if test/threshold > 40: 100
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/result"] == 100

    def test_execute_entity_variable(self):
        from rac.engine import compile, execute, parse

        module = parse("""
            variable person/doubled:
                entity: person
                from 2024-01-01: income * 2
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        data = {"person": [{"id": 1, "income": 1000}, {"id": 2, "income": 2000}]}
        result = execute(ir, data)
        assert result.entities["person"]["person/doubled"] == [2000, 4000]


class TestEngineRustCodegen:
    def test_generate_rust_basic(self):
        from rac.engine import compile, generate_rust, parse

        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.25

            variable gov/base:
                from 2024-01-01: 1000

            variable gov/tax:
                from 2024-01-01: gov/base * gov/rate
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)

        assert "pub struct Scalars" in rust_code
        assert "fn compute" in rust_code
        assert "gov_rate" in rust_code
        assert "gov_base" in rust_code

    def test_generate_rust_with_entity(self):
        from rac.engine import compile, generate_rust, parse

        module = parse("""
            entity person:
                age: int
                income: float
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)

        assert "pub struct PersonInput" in rust_code
        assert "pub age: i64" in rust_code
        assert "pub income: f64" in rust_code


class TestEngineModel:
    """Test the high-level Model API (requires Rust toolchain)."""

    @pytest.fixture(autouse=True)
    def check_cargo(self):
        """Skip tests if cargo is not available."""
        import shutil

        if not shutil.which("cargo"):
            pytest.skip("Rust toolchain not available")

    def test_model_from_source(self):
        from rac.engine import Model

        model = Model.from_source(
            """
            entity person:
                income: float

            variable gov/rate:
                from 2024-01-01: 0.20

            variable person/tax:
                entity: person
                from 2024-01-01: income * gov/rate
            """,
            as_of=date(2024, 6, 1),
        )
        assert "person" in model.entities
        assert "person/tax" in model.outputs("person")

    def test_model_scalars(self):
        from rac.engine import Model

        model = Model.from_source(
            """
            variable gov/rate:
                from 2024-01-01: 0.25
            variable gov/base:
                from 2024-01-01: 1000
            variable gov/tax:
                from 2024-01-01: gov/base * gov/rate
            """,
            as_of=date(2024, 6, 1),
        )
        scalars = model.scalars
        assert scalars["gov/rate"] == 0.25
        assert scalars["gov/base"] == 1000
        assert scalars["gov/tax"] == 250.0
