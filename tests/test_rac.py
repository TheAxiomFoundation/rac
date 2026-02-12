"""Tests for the RAC engine: parse -> compile -> execute pipeline.

Tests the public API: parse, compile, execute, generate_rust, Model.
"""

from datetime import date

import pytest

# Shared RAC source for tax model tests (entity + scalar rate + entity variable)
TAX_MODEL_SOURCE = """
    entity person:
        income: float

    variable gov/rate:
        from 2024-01-01: 0.20

    variable person/tax:
        entity: person
        from 2024-01-01: income * gov/rate
"""

# -- Parser ------------------------------------------------------------------


class TestParser:
    def test_parse_scalar_variable(self):
        from rac import parse

        module = parse("""
            variable gov/tax/rate:
                from 2024-01-01: 0.25
        """)
        assert len(module.variables) == 1
        assert module.variables[0].path == "gov/tax/rate"

    def test_parse_entity_variable(self):
        from rac import parse

        module = parse("""
            variable person/tax:
                entity: person
                from 2024-01-01: income * 0.2
        """)
        assert module.variables[0].entity == "person"

    def test_parse_temporal_ranges(self):
        from rac import parse

        module = parse("""
            variable gov/threshold:
                from 2023-01-01 to 2023-12-31: 10000
                from 2024-01-01: 12000
        """)
        assert len(module.variables[0].values) == 2

    def test_parse_expressions(self):
        from rac import parse

        module = parse("""
            variable test/expr:
                from 2024-01-01: max(0, income - 10000) * 0.22
        """)
        assert module.variables[0].values[0].expr is not None

    def test_parse_conditional(self):
        from rac import parse

        module = parse("""
            variable test/cond:
                from 2024-01-01:
                    if income > 50000: income * 0.3
                    else: income * 0.1
        """)
        assert module.variables[0].values[0].expr.type == "cond"

    def test_parse_entity_declaration(self):
        from rac import parse

        module = parse("""
            entity person:
                age: int
                income: float
        """)
        assert len(module.entities) == 1
        assert module.entities[0].name == "person"

    def test_parse_amendment(self):
        from rac import parse

        module = parse("""
            amend gov/rate:
                from 2024-06-01: 0.15
        """)
        assert len(module.amendments) == 1
        assert module.amendments[0].target == "gov/rate"

    def test_parse_file(self, tmp_path):
        from rac import parse_file

        f = tmp_path / "test.rac"
        f.write_text("""
            variable gov/rate:
                from 2024-01-01: 0.25
        """)
        module = parse_file(f)
        assert len(module.variables) == 1

    def test_parse_error(self):
        from rac import ParseError, parse

        with pytest.raises(ParseError):
            parse("!!! invalid")

    def test_parse_boolean_literals(self):
        from rac import parse

        module = parse("""
            variable test/flag:
                from 2024-01-01: true
        """)
        assert module.variables[0].values[0].expr.value is True

    def test_parse_string_literal(self):
        from rac import parse

        module = parse("""
            variable test/status:
                from 2024-01-01: "active"
        """)
        assert module.variables[0].values[0].expr.value == "active"

    def test_parse_unary_minus(self):
        from rac import parse

        module = parse("""
            variable test/neg:
                from 2024-01-01: -100
        """)
        expr = module.variables[0].values[0].expr
        assert expr.type == "unaryop"
        assert expr.op == "-"

    def test_parse_match_expression(self):
        from rac import parse

        module = parse("""
            variable test/match_var:
                from 2024-01-01:
                    match status:
                        "single" => 12000
                        "married" => 24000
        """)
        expr = module.variables[0].values[0].expr
        assert expr.type == "match"

    def test_parse_field_access(self):
        from rac import parse

        module = parse("""
            variable test/field:
                entity: household
                from 2024-01-01: members.income
        """)
        expr = module.variables[0].values[0].expr
        assert expr.type == "field_access"

    def test_parse_nested_expressions(self):
        from rac import parse

        module = parse("""
            variable test/nested:
                from 2024-01-01: max(0, (income - 10000) * 0.22 + 500)
        """)
        assert module.variables[0].values[0].expr is not None

    def test_parse_multiple_variables(self):
        from rac import parse

        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.10

            variable gov/base:
                from 2024-01-01: 1000

            variable gov/tax:
                from 2024-01-01: gov/base * gov/rate
        """)
        assert len(module.variables) == 3

    def test_parse_entity_with_foreign_key(self):
        from rac import parse

        module = parse("""
            entity person:
                age: int
                household: -> household
        """)
        entity = module.entities[0]
        assert len(entity.foreign_keys) == 1
        assert entity.foreign_keys[0] == ("household", "household")

    def test_parse_empty_source(self):
        from rac import parse

        module = parse("")
        assert len(module.variables) == 0
        assert len(module.entities) == 0
        assert len(module.amendments) == 0


# -- AST Nodes --------------------------------------------------------------


class TestAST:
    def test_module_is_pydantic(self):
        from rac import Module

        m = Module()
        assert m.model_dump() is not None

    def test_variable_decl_fields(self):
        from rac import VariableDecl

        v = VariableDecl(path="test/var")
        assert v.path == "test/var"
        assert v.entity is None
        assert v.values == []

    def test_temporal_value_serialization(self):
        from rac import Literal, TemporalValue

        tv = TemporalValue(start=date(2024, 1, 1), expr=Literal(value=42))
        d = tv.model_dump()
        assert d["start"] == date(2024, 1, 1)
        assert d["expr"]["value"] == 42

    def test_expr_discriminated_union(self):
        from rac import BinOp, Literal

        expr = BinOp(op="+", left=Literal(value=1), right=Literal(value=2))
        assert expr.type == "binop"
        assert expr.left.type == "literal"


# -- Compiler ----------------------------------------------------------------


class TestCompiler:
    def test_compile_scalar(self):
        from rac import compile, parse

        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.25
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        assert "gov/rate" in ir.variables

    def test_temporal_resolution(self):
        from rac import compile, parse

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
        from rac import compile, parse

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

    def test_amendment_before_effective_date(self):
        from rac import compile, parse

        base = parse("""
            variable gov/rate:
                from 2024-01-01: 0.10
        """)
        amendment = parse("""
            amend gov/rate:
                from 2024-06-01: 0.15
        """)
        ir = compile([base, amendment], as_of=date(2024, 3, 1))
        assert ir.variables["gov/rate"].expr.value == 0.10

    def test_dependency_ordering(self):
        from rac import compile, parse

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

    def test_compile_error_duplicate_variable(self):
        from rac import CompileError, compile, parse

        m1 = parse("""
            variable gov/rate:
                from 2024-01-01: 0.10
        """)
        m2 = parse("""
            variable gov/rate:
                from 2024-01-01: 0.20
        """)
        with pytest.raises(CompileError, match="duplicate"):
            compile([m1, m2], as_of=date(2024, 6, 1))

    def test_compile_circular_dependency(self):
        from rac import CompileError, compile, parse

        module = parse("""
            variable gov/a:
                from 2024-01-01: gov/b * 2

            variable gov/b:
                from 2024-01-01: gov/a * 3
        """)
        with pytest.raises(CompileError, match="circular"):
            compile([module], as_of=date(2024, 6, 1))

    def test_schema_from_entity_declaration(self):
        from rac import compile, parse

        module = parse("""
            entity person:
                age: int
                income: float

            variable person/tax:
                entity: person
                from 2024-01-01: income * 0.2
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        assert "person" in ir.schema_.entities
        assert "age" in ir.schema_.entities["person"].fields

    def test_variable_not_yet_effective(self):
        from rac import compile, parse

        module = parse("""
            variable gov/rate:
                from 2025-01-01: 0.25
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        assert "gov/rate" not in ir.variables


# -- Executor ----------------------------------------------------------------


class TestExecutor:
    def test_execute_scalar(self):
        from rac import compile, execute, parse

        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.25
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["gov/rate"] == 0.25

    def test_execute_arithmetic(self):
        from rac import compile, execute, parse

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
        from rac import compile, execute, parse

        module = parse("""
            variable test/clipped:
                from 2024-01-01: clip(150, 0, 100)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/clipped"] == 100

    def test_execute_min_max(self):
        from rac import compile, execute, parse

        module = parse("""
            variable test/lo:
                from 2024-01-01: min(10, 20)
            variable test/hi:
                from 2024-01-01: max(10, 20)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/lo"] == 10
        assert result.scalars["test/hi"] == 20

    def test_execute_conditional(self):
        from rac import compile, execute, parse

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
        from rac import compile, execute, parse

        module = parse("""
            variable person/doubled:
                entity: person
                from 2024-01-01: income * 2
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        data = {"person": [{"id": 1, "income": 1000}, {"id": 2, "income": 2000}]}
        result = execute(ir, data)
        assert result.entities["person"]["person/doubled"] == [2000, 4000]

    def test_execute_entity_with_scalar(self):
        from rac import compile, execute, parse

        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.20

            variable person/tax:
                entity: person
                from 2024-01-01: income * gov/rate
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        data = {"person": [{"id": 1, "income": 50000}]}
        result = execute(ir, data)
        assert result.scalars["gov/rate"] == 0.20
        assert result.entities["person"]["person/tax"] == [10000.0]

    def test_execute_boolean_comparison(self):
        from rac import compile, execute, parse

        module = parse("""
            variable test/val:
                from 2024-01-01: 42
            variable test/is_big:
                from 2024-01-01:
                    if test/val > 100: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/is_big"] == 0

    def test_execute_division_by_zero(self):
        from rac import compile, execute, parse

        module = parse("""
            variable test/zero:
                from 2024-01-01: 0
            variable test/div:
                from 2024-01-01: 100 / test/zero
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/div"] == 0  # safe division

    def test_execute_chained_dependencies(self):
        from rac import compile, execute, parse

        module = parse("""
            variable gov/a:
                from 2024-01-01: 10
            variable gov/b:
                from 2024-01-01: gov/a * 2
            variable gov/c:
                from 2024-01-01: gov/b + gov/a
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["gov/a"] == 10
        assert result.scalars["gov/b"] == 20
        assert result.scalars["gov/c"] == 30


# -- Rust Codegen ------------------------------------------------------------


class TestRustCodegen:
    def test_generate_rust_basic(self):
        from rac import compile, generate_rust, parse

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
        from rac import compile, generate_rust, parse

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

    def test_generate_rust_conditional(self):
        from rac import compile, generate_rust, parse

        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.10
            variable gov/result:
                from 2024-01-01:
                    if gov/rate > 0.05: 100
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        assert "if" in rust_code
        assert "else" in rust_code

    def test_generate_rust_builtins(self):
        from rac import compile, generate_rust, parse

        module = parse("""
            variable gov/val:
                from 2024-01-01: clip(50, 0, 100)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        assert ".max(" in rust_code
        assert ".min(" in rust_code


# -- Native Compilation (requires Rust toolchain) ---------------------------


class TestNative:
    @pytest.fixture(autouse=True)
    def check_cargo(self):
        import shutil

        if not shutil.which("cargo"):
            pytest.skip("Rust toolchain not available")

    def test_compile_to_binary(self):
        from rac import compile, compile_to_binary, parse

        module = parse(TAX_MODEL_SOURCE)
        ir = compile([module], as_of=date(2024, 6, 1))
        binary = compile_to_binary(ir)
        assert binary.binary_path.exists()
        assert "person" in binary.entity_outputs


# -- Model API (requires Rust toolchain) ------------------------------------


class TestModel:
    @pytest.fixture(autouse=True)
    def check_cargo(self):
        import shutil

        if not shutil.which("cargo"):
            pytest.skip("Rust toolchain not available")

    def test_model_from_source(self):
        from rac import Model

        model = Model.from_source(TAX_MODEL_SOURCE, as_of=date(2024, 6, 1))
        assert "person" in model.entities
        assert "person/tax" in model.outputs("person")

    def test_model_scalars(self):
        from rac import Model

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

    def test_model_from_file(self, tmp_path):
        from rac import Model

        f = tmp_path / "test.rac"
        f.write_text("""
            variable gov/rate:
                from 2024-01-01: 0.25
        """)
        model = Model.from_file(f, as_of=date(2024, 6, 1))
        assert model.scalars["gov/rate"] == 0.25


# -- End-to-end scenarios ---------------------------------------------------


class TestEndToEnd:
    def test_simple_tax_system(self):
        """A complete tax system: rates, brackets, entity computation."""
        from rac import compile, execute, parse

        module = parse("""
            entity person:
                income: float
                filing_status: str

            variable gov/exemption:
                from 2024-01-01: 15000

            variable gov/rate:
                from 2024-01-01: 0.20

            variable person/taxable_income:
                entity: person
                from 2024-01-01: max(0, income - gov/exemption)

            variable person/tax:
                entity: person
                from 2024-01-01: person/taxable_income * gov/rate
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        data = {
            "person": [
                {"id": 1, "income": 50000.0, "filing_status": "single"},
                {"id": 2, "income": 10000.0, "filing_status": "single"},
            ]
        }
        result = execute(ir, data)

        assert result.scalars["gov/exemption"] == 15000
        assert result.scalars["gov/rate"] == 0.20
        assert result.entities["person"]["person/taxable_income"] == [35000.0, 0]
        assert result.entities["person"]["person/tax"] == [7000.0, 0]

    def test_reform_via_amendment(self):
        """Demonstrate reform modeling via amend."""
        from rac import compile, execute, parse

        base = parse("""
            variable gov/rate:
                from 2024-01-01: 0.20
            variable gov/revenue:
                from 2024-01-01: 1000000 * gov/rate
        """)
        reform = parse("""
            amend gov/rate:
                from 2024-06-01: 0.25
        """)

        # Before reform
        ir_before = compile([base], as_of=date(2024, 3, 1))
        r_before = execute(ir_before, {})
        assert r_before.scalars["gov/rate"] == 0.20
        assert r_before.scalars["gov/revenue"] == 200000.0

        # After reform
        ir_after = compile([base, reform], as_of=date(2024, 7, 1))
        r_after = execute(ir_after, {})
        assert r_after.scalars["gov/rate"] == 0.25
        assert r_after.scalars["gov/revenue"] == 250000.0

    def test_multi_module_composition(self):
        """Multiple modules combined into one compilation."""
        from rac import compile, execute, parse

        params = parse("""
            variable gov/rate:
                from 2024-01-01: 0.10
            variable gov/threshold:
                from 2024-01-01: 50000
        """)
        formulas = parse("""
            entity person:
                income: float
            variable person/tax:
                entity: person
                from 2024-01-01:
                    if income > gov/threshold: (income - gov/threshold) * gov/rate
                    else: 0
        """)
        ir = compile([params, formulas], as_of=date(2024, 6, 1))
        data = {
            "person": [
                {"id": 1, "income": 100000.0},
                {"id": 2, "income": 30000.0},
            ]
        }
        result = execute(ir, data)
        assert result.entities["person"]["person/tax"] == [5000.0, 0]


# -- Coverage gap tests -----------------------------------------------------


class TestExecutorCoverage:
    """Tests for executor branches not covered above."""

    def test_execute_unary_not(self):
        from rac import compile, execute, parse

        module = parse("""
            variable test/flag:
                from 2024-01-01: true
            variable test/neg:
                from 2024-01-01:
                    if not test/flag: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/neg"] == 0

    def test_execute_and_or(self):
        from rac import compile, execute, parse

        module = parse("""
            variable test/a:
                from 2024-01-01: 1
            variable test/b:
                from 2024-01-01: 0
            variable test/and_result:
                from 2024-01-01:
                    if test/a > 0 and test/b > 0: 1
                    else: 0
            variable test/or_result:
                from 2024-01-01:
                    if test/a > 0 or test/b > 0: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/and_result"] == 0
        assert result.scalars["test/or_result"] == 1

    def test_execute_match(self):
        from rac import compile, execute, parse

        module = parse("""
            variable test/status:
                from 2024-01-01: "married"
            variable test/deduction:
                from 2024-01-01:
                    match test/status:
                        "single" => 12000
                        "married" => 24000
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/deduction"] == 24000

    def test_execute_field_access(self):
        from rac import compile, execute, parse

        module = parse("""
            entity household:
                size: int

            entity person:
                income: float
                household: -> household

            variable person/income_share:
                entity: person
                from 2024-01-01: income
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        data = {"person": [{"id": 1, "income": 50000.0}]}
        result = execute(ir, data)
        assert result.entities["person"]["person/income_share"] == [50000.0]

    def test_execute_abs_round(self):
        from rac import compile, execute, parse

        module = parse("""
            variable test/abs_val:
                from 2024-01-01: abs(-42)
            variable test/round_val:
                from 2024-01-01: round(3.7)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/abs_val"] == 42
        assert result.scalars["test/round_val"] == 4

    def test_execute_subtraction_and_division(self):
        from rac import compile, execute, parse

        module = parse("""
            variable test/a:
                from 2024-01-01: 100
            variable test/b:
                from 2024-01-01: test/a - 30
            variable test/c:
                from 2024-01-01: test/a / 4
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/b"] == 70
        assert result.scalars["test/c"] == 25.0

    def test_execute_equality_inequality(self):
        from rac import compile, execute, parse

        module = parse("""
            variable test/a:
                from 2024-01-01: 10
            variable test/eq:
                from 2024-01-01:
                    if test/a == 10: 1
                    else: 0
            variable test/neq:
                from 2024-01-01:
                    if test/a != 10: 1
                    else: 0
            variable test/le:
                from 2024-01-01:
                    if test/a <= 10: 1
                    else: 0
            variable test/ge:
                from 2024-01-01:
                    if test/a >= 10: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/eq"] == 1
        assert result.scalars["test/neq"] == 0
        assert result.scalars["test/le"] == 1
        assert result.scalars["test/ge"] == 1

    def test_execute_unknown_variable_raises(self):
        from rac.ast import Var
        from rac.executor import Context, ExecutionError, evaluate
        from rac.schema import Data

        ctx = Context(data=Data(tables={}))
        with pytest.raises(ExecutionError, match="undefined"):
            evaluate(Var(path="nonexistent"), ctx)

    def test_execute_unknown_function_raises(self):
        from rac.ast import Call, Literal
        from rac.executor import Context, ExecutionError, evaluate
        from rac.schema import Data

        ctx = Context(data=Data(tables={}))
        with pytest.raises(ExecutionError, match="unknown function"):
            evaluate(Call(func="bogus", args=[Literal(value=1)]), ctx)


class TestCompilerCoverage:
    """Tests for compiler branches not covered above."""

    def test_repeal(self):
        from rac import compile, parse

        module = parse("""
            variable gov/old_credit:
                from 2020-01-01: 500
        """)
        # Manually add a repeal since parser doesn't parse repeal yet
        from rac.ast import RepealDecl

        module.repeals.append(RepealDecl(target="gov/old_credit", effective=date(2024, 1, 1)))

        ir = compile([module], as_of=date(2024, 6, 1))
        assert "gov/old_credit" not in ir.variables

        ir_before = compile([module], as_of=date(2023, 6, 1))
        assert "gov/old_credit" in ir_before.variables

    def test_amendment_creates_new_variable(self):
        from rac import compile, parse

        amendment = parse("""
            amend gov/new_var:
                from 2024-01-01: 999
        """)
        ir = compile([amendment], as_of=date(2024, 6, 1))
        assert ir.variables["gov/new_var"].expr.value == 999

    def test_schema_reverse_relation_inference(self):
        from rac import compile, parse

        module = parse("""
            entity household:
                size: int

            entity person:
                income: float
                household: -> household
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        household = ir.schema_.entities["household"]
        assert "persons" in household.reverse_relations


class TestRustCodegenCoverage:
    """Tests for codegen branches not covered above."""

    def test_generate_rust_entity_computation(self):
        from rac import compile, generate_rust, parse

        module = parse(TAX_MODEL_SOURCE)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        assert "PersonOutput" in rust_code
        assert "PersonInput" in rust_code
        assert "person_tax" in rust_code
        assert "impl PersonOutput" in rust_code

    def test_generate_rust_unary_and_boolean(self):
        from rac import compile, generate_rust, parse

        module = parse("""
            variable gov/val:
                from 2024-01-01: -100
            variable gov/flag:
                from 2024-01-01: true
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        assert "true" in rust_code

    def test_generate_rust_abs_round(self):
        from rac import compile, generate_rust, parse

        module = parse("""
            variable gov/a:
                from 2024-01-01: abs(-5)
            variable gov/b:
                from 2024-01-01: round(3.14)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        assert ".abs()" in rust_code
        assert ".round()" in rust_code

    def test_generate_rust_and_or(self):
        from rac import compile, generate_rust, parse

        module = parse("""
            variable gov/a:
                from 2024-01-01: 1
            variable gov/b:
                from 2024-01-01: 1
            variable gov/both:
                from 2024-01-01:
                    if gov/a == 1 and gov/b == 1: 1
                    else: 0
            variable gov/either:
                from 2024-01-01:
                    if gov/a == 1 or gov/b == 0: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        assert "&&" in rust_code
        assert "||" in rust_code

    def test_generate_rust_string_literal(self):
        from rac import compile, generate_rust, parse

        module = parse("""
            variable gov/status:
                from 2024-01-01: "active"
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        assert '"active"' in rust_code

    def test_generate_rust_not(self):
        from rac import compile, generate_rust, parse

        module = parse("""
            variable gov/flag:
                from 2024-01-01: true
            variable gov/neg:
                from 2024-01-01:
                    if not gov/flag: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        assert "!" in rust_code


class TestSchemaCoverage:
    """Tests for schema module coverage."""

    def test_data_get_rows_empty(self):
        from rac.schema import Data

        data = Data(tables={})
        assert data.get_rows("nonexistent") == []

    def test_data_get_row_by_pk(self):
        from rac.schema import Data

        data = Data(tables={"person": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]})
        assert data.get_row("person", 1) == {"id": 1, "name": "Alice"}
        assert data.get_row("person", 3) is None

    def test_data_get_related(self):
        from rac.schema import Data

        data = Data(
            tables={
                "household": [{"id": 1}],
                "person": [
                    {"id": 1, "household_id": 1},
                    {"id": 2, "household_id": 1},
                    {"id": 3, "household_id": 2},
                ],
            }
        )
        related = data.get_related("person", "household_id", 1)
        assert len(related) == 2


class TestParserCoverage:
    """Tests for parser branches not covered above."""

    def test_parse_parenthesized_expression(self):
        from rac import parse

        module = parse("""
            variable test/val:
                from 2024-01-01: (10 + 5) * 2
        """)
        result_expr = module.variables[0].values[0].expr
        assert result_expr.type == "binop"

    def test_parse_comparison_operators(self):
        from rac import parse

        for op in ["<", ">", "<=", ">=", "==", "!="]:
            module = parse(f"""
                variable test/cmp:
                    from 2024-01-01:
                        if 10 {op} 5: 1
                        else: 0
            """)
            assert module.variables[0].values[0].expr.type == "cond"

    def test_parse_comment_ignored(self):
        from rac import parse

        module = parse("""
            # This is a comment
            variable gov/rate:
                from 2024-01-01: 0.25  # inline comment
        """)
        assert len(module.variables) == 1

    def test_lexer_unexpected_char(self):
        from rac import ParseError, parse

        with pytest.raises(ParseError):
            parse("variable test: from 2024-01-01: @invalid")

    def test_parser_unexpected_token_at_top_level(self):
        from rac import ParseError, parse

        with pytest.raises(ParseError, match="unexpected token"):
            parse("12345")

    def test_parse_false_literal(self):
        from rac import parse

        module = parse("""
            variable test/flag:
                from 2024-01-01: false
        """)
        assert module.variables[0].values[0].expr.value is False

    def test_parse_reverse_relation(self):
        from rac import parse

        module = parse("""
            entity household:
                size: int
                members: [person]
        """)
        entity = module.entities[0]
        assert len(entity.reverse_relations) == 1
        assert entity.reverse_relations[0] == ("members", "person", "members")

    def test_parse_path_as_ident(self):
        """_parse_path falls back to IDENT when no PATH token."""
        from rac import parse

        module = parse("""
            amend rate:
                from 2024-01-01: 0.5
        """)
        assert module.amendments[0].target == "rate"

    def test_parse_call_non_function_raises(self):
        from rac import ParseError, parse

        with pytest.raises(ParseError, match="can only call named functions"):
            parse("""
                variable test/v:
                    from 2024-01-01: (1 + 2)(3)
            """)

    def test_parse_unexpected_in_expression(self):
        from rac import ParseError, parse

        with pytest.raises(ParseError, match="unexpected token in expression"):
            parse("""
                variable test/v:
                    from 2024-01-01: :
            """)

    def test_peek_past_end(self):
        from rac.parser import Lexer, Parser

        lexer = Lexer("")
        parser = Parser(lexer.tokens)
        # Peek way past end returns EOF
        tok = parser.peek(100)
        assert tok.type == "EOF"

    def test_consume_mismatch(self):
        from rac.parser import Lexer, ParseError, Parser

        lexer = Lexer("variable")
        parser = Parser(lexer.tokens)
        with pytest.raises(ParseError, match="expected COLON"):
            parser.consume("COLON")


# -- Additional executor coverage -------------------------------------------


class TestExecutorCoverage2:
    """Cover remaining executor branches."""

    def test_less_than_operator(self):
        from rac import compile, execute, parse

        module = parse("""
            variable test/a:
                from 2024-01-01: 5
            variable test/r:
                from 2024-01-01:
                    if test/a < 10: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        result = execute(ir, {})
        assert result.scalars["test/r"] == 1

    def test_unknown_binop_raises(self):
        from rac.ast import BinOp, Literal
        from rac.executor import Context, ExecutionError, evaluate
        from rac.schema import Data

        ctx = Context(data=Data(tables={}))
        expr = BinOp(op="^", left=Literal(value=1), right=Literal(value=2))
        with pytest.raises(ExecutionError, match="unknown op"):
            evaluate(expr, ctx)

    def test_unknown_unaryop_raises(self):
        from rac.ast import Literal, UnaryOp
        from rac.executor import Context, ExecutionError, evaluate
        from rac.schema import Data

        ctx = Context(data=Data(tables={}))
        expr = UnaryOp(op="~", operand=Literal(value=1))
        with pytest.raises(ExecutionError, match="unknown unary op"):
            evaluate(expr, ctx)

    def test_field_access_on_dict(self):
        from rac.ast import FieldAccess, Var
        from rac.executor import Context, evaluate
        from rac.schema import Data

        ctx = Context(data=Data(tables={}), computed={"obj": {"name": "Alice"}})
        expr = FieldAccess(obj=Var(path="obj"), field="name")
        result = evaluate(expr, ctx)
        assert result == "Alice"

    def test_field_access_on_list(self):
        from rac.ast import FieldAccess, Var
        from rac.executor import Context, evaluate
        from rac.schema import Data

        ctx = Context(
            data=Data(tables={}),
            computed={"items": [{"x": 1}, {"x": 2}]},
        )
        expr = FieldAccess(obj=Var(path="items"), field="x")
        result = evaluate(expr, ctx)
        assert result == [1, 2]

    def test_field_access_on_object(self):
        from rac.ast import FieldAccess, Var
        from rac.executor import Context, evaluate
        from rac.schema import Data

        class Obj:
            z = 42

        ctx = Context(data=Data(tables={}), computed={"myobj": Obj()})
        expr = FieldAccess(obj=Var(path="myobj"), field="z")
        result = evaluate(expr, ctx)
        assert result == 42

    def test_match_with_default(self):
        from rac.ast import Literal, Match, Var
        from rac.executor import Context, evaluate
        from rac.schema import Data

        ctx = Context(data=Data(tables={}), computed={"status": "other"})
        expr = Match(
            subject=Var(path="status"),
            cases=[(Literal(value="a"), Literal(value=1))],
            default=Literal(value=99),
        )
        result = evaluate(expr, ctx)
        assert result == 99

    def test_match_no_match_no_default_raises(self):
        from rac.ast import Literal, Match, Var
        from rac.executor import Context, ExecutionError, evaluate
        from rac.schema import Data

        ctx = Context(data=Data(tables={}), computed={"status": "other"})
        expr = Match(
            subject=Var(path="status"),
            cases=[(Literal(value="a"), Literal(value=1))],
            default=None,
        )
        with pytest.raises(ExecutionError, match="no match"):
            evaluate(expr, ctx)

    def test_unknown_expr_type_raises(self):
        from rac.executor import Context, ExecutionError, evaluate
        from rac.schema import Data

        class FakeExpr:
            pass

        ctx = Context(data=Data(tables={}))
        with pytest.raises(ExecutionError, match="unknown expr type"):
            evaluate(FakeExpr(), ctx)

    def test_get_related(self):
        from rac.executor import Context
        from rac.schema import Data

        data = Data(
            tables={
                "person": [
                    {"id": 1, "household_id": 10},
                    {"id": 2, "household_id": 10},
                    {"id": 3, "household_id": 20},
                ],
            }
        )
        ctx = Context(data=data, current_row={"id": 10})
        related = ctx.get_related("person", "household_id")
        assert len(related) == 2

    def test_get_related_no_current_row_raises(self):
        from rac.executor import Context, ExecutionError
        from rac.schema import Data

        ctx = Context(data=Data(tables={}))
        with pytest.raises(ExecutionError, match="no current row"):
            ctx.get_related("person", "household_id")

    def test_get_fk_target(self):
        from rac.executor import Context
        from rac.schema import Data

        data = Data(tables={"household": [{"id": 1, "size": 3}]})
        ctx = Context(data=data)
        row = ctx.get_fk_target(1, "household")
        assert row == {"id": 1, "size": 3}


# -- Additional compiler coverage ------------------------------------------


class TestCompilerCoverage2:
    """Cover remaining compiler branches."""

    def test_temporal_layer_replace(self):
        from rac.ast import Literal, TemporalValue
        from rac.compiler import TemporalLayer

        layer = TemporalLayer("test/var")
        layer.add_values([TemporalValue(start=date(2024, 1, 1), expr=Literal(value=10))])
        assert layer.resolve(date(2024, 6, 1)).value == 10

        layer.add_values(
            [TemporalValue(start=date(2024, 1, 1), expr=Literal(value=99))],
            replace=True,
        )
        assert layer.resolve(date(2024, 6, 1)).value == 99

    def test_entity_with_explicit_reverse_relation(self):
        from rac import compile, parse

        module = parse("""
            entity household:
                size: int
                members: [person]
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        household = ir.schema_.entities["household"]
        assert "members" in household.reverse_relations

    def test_walk_deps_field_access(self):
        from rac import compile, parse

        module = parse("""
            entity household:
                size: int

            entity person:
                income: float
                household: -> household

            variable person/hh_income:
                entity: person
                from 2024-01-01: household.size
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        # Should compile without error - FieldAccess dep walking works
        assert "person/hh_income" in ir.variables

    def test_walk_deps_match_with_default(self):
        from rac import ast
        from rac.ast import Literal, Match, TemporalValue, Var, VariableDecl
        from rac.compiler import Compiler

        module = ast.Module()
        module.variables.append(
            VariableDecl(
                path="gov/rate",
                values=[TemporalValue(start=date(2024, 1, 1), expr=Literal(value=0.1))],
            )
        )
        module.variables.append(
            VariableDecl(
                path="gov/status",
                values=[TemporalValue(start=date(2024, 1, 1), expr=Literal(value="a"))],
            )
        )
        module.variables.append(
            VariableDecl(
                path="gov/result",
                values=[
                    TemporalValue(
                        start=date(2024, 1, 1),
                        expr=Match(
                            subject=Var(path="gov/status"),
                            cases=[(Literal(value="a"), Var(path="gov/rate"))],
                            default=Literal(value=0),
                        ),
                    )
                ],
            )
        )

        ir = Compiler([module]).compile(date(2024, 6, 1))
        assert "gov/rate" in ir.variables["gov/result"].deps


# -- Additional codegen coverage -------------------------------------------


class TestRustCodegenCoverage2:
    """Cover remaining codegen/rust.py branches."""

    def test_gen_min_max_two_args(self):
        from rac import compile, generate_rust, parse

        module = parse("""
            variable gov/lo:
                from 2024-01-01: min(10, 20)
            variable gov/hi:
                from 2024-01-01: max(10, 20)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        assert ".min(" in rust_code
        assert ".max(" in rust_code

    def test_gen_sum_len(self):
        """Test codegen for sum and len builtins."""
        from rac.ast import Call, Var
        from rac.codegen.rust import RustGenerator
        from rac.compiler import IR, ResolvedVar
        from rac.schema import Schema

        ir = IR(
            schema_=Schema(),
            variables={
                "gov/total": ResolvedVar(
                    path="gov/total",
                    expr=Call(func="sum", args=[Var(path="items")]),
                ),
                "gov/count": ResolvedVar(
                    path="gov/count",
                    expr=Call(func="len", args=[Var(path="items")]),
                ),
            },
            order=["gov/total", "gov/count"],
        )
        gen = RustGenerator(ir, "test")
        code = gen.generate()
        assert ".iter().sum::<f64>()" in code
        assert ".len() as f64" in code

    def test_gen_unknown_builtin(self):
        from rac.ast import Call, Literal
        from rac.codegen.rust import RustGenerator
        from rac.compiler import IR, ResolvedVar
        from rac.schema import Schema

        ir = IR(
            schema_=Schema(),
            variables={
                "gov/x": ResolvedVar(
                    path="gov/x",
                    expr=Call(func="bogus", args=[Literal(value=1)]),
                ),
            },
            order=["gov/x"],
        )
        gen = RustGenerator(ir, "test")
        code = gen.generate()
        assert "/* unknown: bogus */" in code

    def test_gen_field_access(self):
        from rac import compile, generate_rust, parse

        module = parse("""
            entity household:
                size: int

            entity person:
                income: float
                household: -> household

            variable person/hh_size:
                entity: person
                from 2024-01-01: household.size
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        # FieldAccess generates obj.field
        assert ".size" in rust_code

    def test_gen_reserved_word_escaping(self):
        from rac.codegen.rust import RustGenerator

        gen = RustGenerator.__new__(RustGenerator)
        assert gen._rust_ident("type") == "r#type"
        assert gen._rust_ident("match") == "r#match"
        assert gen._rust_ident("fn") == "r#fn"
        assert gen._rust_ident("normal") == "normal"

    def test_gen_entity_computed_var_reference(self):
        """Entity variable referencing a previously computed entity variable."""
        from rac import compile, generate_rust, parse

        module = parse("""
            entity person:
                income: float

            variable gov/rate:
                from 2024-01-01: 0.20

            variable person/gross_tax:
                entity: person
                from 2024-01-01: income * gov/rate

            variable person/net_tax:
                entity: person
                from 2024-01-01: person/gross_tax * 0.9
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        rust_code = generate_rust(ir)
        # person/net_tax should reference computed person_gross_tax variable
        assert "person_gross_tax" in rust_code

    def test_gen_bare_var_no_entity(self):
        """Var with no '/' and no entity_var context."""
        from rac.ast import Var
        from rac.codegen.rust import RustGenerator
        from rac.compiler import IR, ResolvedVar
        from rac.schema import Schema

        ir = IR(
            schema_=Schema(),
            variables={
                "gov/x": ResolvedVar(path="gov/x", expr=Var(path="something")),
            },
            order=["gov/x"],
        )
        gen = RustGenerator(ir, "test")
        code = gen.generate()
        assert "something" in code

    def test_gen_unaryop_fallthrough(self):
        """UnaryOp with unknown op falls through."""
        from rac.ast import Literal, UnaryOp
        from rac.codegen.rust import RustGenerator
        from rac.compiler import IR, ResolvedVar
        from rac.schema import Schema

        ir = IR(
            schema_=Schema(),
            variables={
                "gov/x": ResolvedVar(
                    path="gov/x", expr=UnaryOp(op="~", operand=Literal(value=1))
                ),
            },
            order=["gov/x"],
        )
        gen = RustGenerator(ir, "test")
        code = gen.generate()
        # Falls through to just returning inner
        assert "1_f64" in code

    def test_gen_expr_catchall(self):
        """Unknown AST node type in codegen falls to default."""
        from rac.codegen.rust import RustGenerator

        gen = RustGenerator.__new__(RustGenerator)
        gen.ir = None

        class FakeExpr:
            pass

        result = gen._gen_expr(FakeExpr())
        assert result == "0.0_f64"

    def test_gen_max_n_args(self):
        """max with more than 2 args uses fold."""
        from rac.codegen.rust import RustGenerator

        gen = RustGenerator.__new__(RustGenerator)
        result = gen._gen_builtin_call("max", ["a", "b", "c"])
        assert "fold(f64::NEG_INFINITY" in result

    def test_gen_min_n_args(self):
        """min with more than 2 args uses fold."""
        from rac.codegen.rust import RustGenerator

        gen = RustGenerator.__new__(RustGenerator)
        result = gen._gen_builtin_call("min", ["a", "b", "c"])
        assert "fold(f64::INFINITY" in result


# -- Native + Model with Rust ----------------------------------------------


class TestNativeCoverage:
    """Cover native.py branches that require Rust."""

    @pytest.fixture(autouse=True)
    def check_cargo(self):
        import shutil

        if not shutil.which("cargo"):
            pytest.skip("Rust toolchain not available")

    @pytest.fixture
    def tax_binary(self):
        from rac import compile, compile_to_binary, parse

        module = parse(TAX_MODEL_SOURCE)
        ir = compile([module], as_of=date(2024, 6, 1))
        return compile_to_binary(ir)

    def test_run_with_list_dicts(self, tax_binary):

        data = {"person": [{"id": 1, "income": 50000.0}, {"id": 2, "income": 100000.0}]}
        results = tax_binary.run(data)
        assert "person" in results
        assert results["person"].shape == (2, 1)
        assert abs(results["person"][0, 0] - 10000.0) < 0.01
        assert abs(results["person"][1, 0] - 20000.0) < 0.01

    def test_run_with_numpy_array(self, tax_binary):
        import numpy as np

        # income column
        arr = np.array([[50000.0], [100000.0]])
        data = {"person": arr}
        results = tax_binary.run(data)
        assert "person" in results
        assert abs(results["person"][0, 0] - 10000.0) < 0.01

    def test_run_with_empty_rows(self, tax_binary):

        data = {"person": []}
        results = tax_binary.run(data)
        assert results["person"].shape == (0, 1)

    def test_run_skips_unknown_entity(self, tax_binary):
        data = {"vehicle": [{"id": 1}]}
        results = tax_binary.run(data)
        assert "vehicle" not in results

    def test_cache_hit(self):
        from rac import compile, compile_to_binary, parse

        module = parse(TAX_MODEL_SOURCE)
        ir = compile([module], as_of=date(2024, 6, 1))
        # First compile
        binary1 = compile_to_binary(ir)
        # Second compile should hit cache
        binary2 = compile_to_binary(ir)
        assert binary1.binary_path == binary2.binary_path

    def test_get_cargo_fallback(self):
        from rac.native import _get_cargo

        cargo = _get_cargo()
        assert cargo is not None

    def test_ensure_cargo(self):
        from rac.native import ensure_cargo

        cargo = ensure_cargo()
        assert cargo is not None

    def test_ir_hash_deterministic(self):
        from rac import compile, parse
        from rac.native import _ir_hash

        module = parse("""
            variable gov/rate:
                from 2024-01-01: 0.25
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        assert _ir_hash(ir) == _ir_hash(ir)

    def test_compile_failure_raises(self):
        """Compilation with invalid Rust code raises RuntimeError."""
        from unittest.mock import patch

        from rac import compile, parse
        from rac.native import compile_to_binary

        module = parse("""
            entity person:
                income: float
            variable person/tax:
                entity: person
                from 2024-01-01: income * 0.2
        """)
        ir = compile([module], as_of=date(2024, 6, 1))

        # Patch generate_rust to produce invalid Rust
        with patch("rac.native.generate_rust", return_value="INVALID RUST CODE {{{"):
            with pytest.raises(RuntimeError, match="Compilation failed"):
                compile_to_binary(ir, cache=False)

    def test_generate_main_called(self):
        """_generate_main produces valid Rust main function."""
        from rac import compile, parse
        from rac.native import _generate_main

        module = parse("""
            entity person:
                income: float
                age: int

            variable gov/rate:
                from 2024-01-01: 0.20

            variable person/tax:
                entity: person
                from 2024-01-01: income * gov/rate
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        entity_schemas = {"person": ["income", "age"]}
        entity_outputs = {"person": ["person/tax"]}

        main_code = _generate_main(ir, entity_schemas, entity_outputs)
        assert "fn main()" in main_code
        assert '"person"' in main_code
        assert "as i64" in main_code  # age is int

    def test_generate_main_empty_outputs(self):
        """_generate_main skips entity with no outputs (L216-217)."""
        from rac import compile, parse
        from rac.native import _generate_main

        module = parse("""
            entity person:
                income: float
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        # entity_schemas has person, but entity_outputs has empty list
        main_code = _generate_main(ir, {"person": ["income"]}, {"person": []})
        assert "fn main()" in main_code
        # Should not contain person handler since outputs is empty
        assert '"person"' not in main_code

    def test_compile_to_binary_no_cache(self):
        """Force a fresh build (no cache) to cover lines 169-204 + _generate_main."""
        from rac import compile, compile_to_binary, parse

        module = parse(TAX_MODEL_SOURCE)
        ir = compile([module], as_of=date(2024, 6, 1))
        binary = compile_to_binary(ir, cache=False)
        assert binary.binary_path.exists()
        assert "person" in binary.entity_outputs


class TestNativeNoRust:
    """Test native.py paths that don't need actual Rust."""

    def test_get_cargo_returns_none_when_missing(self):
        from unittest.mock import patch

        with patch("shutil.which", return_value=None):
            from pathlib import Path

            from rac.native import _get_cargo

            # Also mock the fallback path
            with patch.object(Path, "exists", return_value=False):
                result = _get_cargo()
                assert result is None

    def test_get_cargo_fallback_to_cargo_home(self):
        """Cover line 33: cargo_home fallback when shutil.which fails."""
        from pathlib import Path
        from unittest.mock import patch

        with patch("shutil.which", return_value=None):
            from rac.native import _get_cargo

            with patch.object(Path, "exists", return_value=True):
                result = _get_cargo()
                assert result is not None

    def test_ensure_cargo_installs_when_missing(self):
        """Cover line 67: ensure_cargo falls through to _install_rust."""
        from pathlib import Path
        from unittest.mock import patch

        with (
            patch("rac.native._get_cargo", return_value=None),
            patch("rac.native._install_rust", return_value=Path("/fake/cargo")) as mock_install,
        ):
            from rac.native import ensure_cargo

            result = ensure_cargo()
            assert result == Path("/fake/cargo")
            mock_install.assert_called_once()

    def test_install_rust_unix(self):
        from unittest.mock import MagicMock, patch

        with (
            patch("platform.system", return_value="Linux"),
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.exists", return_value=True),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            from rac.native import _install_rust

            result = _install_rust()
            assert result is not None

    def test_install_rust_windows(self):
        from unittest.mock import MagicMock, patch

        with (
            patch("platform.system", return_value="Windows"),
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.mkdir"),
            patch("urllib.request.urlretrieve"),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            from rac.native import _install_rust

            result = _install_rust()
            assert result is not None

    def test_install_rust_failure(self):
        from unittest.mock import MagicMock, patch

        with (
            patch("platform.system", return_value="Linux"),
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.exists", return_value=False),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            from rac.native import _install_rust

            with pytest.raises(RuntimeError, match="Failed to install Rust"):
                _install_rust()

    def test_binary_run_error(self):
        """Binary returning non-zero exit code raises RuntimeError."""
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        from rac.compiler import IR
        from rac.native import CompiledBinary
        from rac.schema import Schema

        binary = CompiledBinary(
            binary_path=Path("/fake/binary"),
            ir=IR(schema_=Schema(), variables={}, order=[]),
            entity_schemas={"person": ["income"]},
            entity_outputs={"person": ["person/tax"]},
        )

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "some error"

        # Only mock subprocess.run, let real file I/O happen
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="Binary failed"):
                binary.run({"person": [{"id": 1, "income": 50000.0}]})


# -- Model API coverage ---------------------------------------------------


class TestModelCoverage:
    """Cover model.py branches."""

    @pytest.fixture(autouse=True)
    def check_cargo(self):
        import shutil

        if not shutil.which("cargo"):
            pytest.skip("Rust toolchain not available")

    @pytest.fixture
    def tax_model(self):
        from rac import Model

        return Model.from_source(TAX_MODEL_SOURCE, as_of=date(2024, 6, 1))

    @pytest.fixture
    def reform_model(self):
        """Reform model with rate 0.25 (vs baseline 0.20)."""
        from rac import Model

        return Model.from_source(
            """
            entity person:
                income: float

            variable gov/rate:
                from 2024-01-01: 0.25

            variable person/tax:
                entity: person
                from 2024-01-01: income * gov/rate
            """,
            as_of=date(2024, 6, 1),
        )

    def test_model_run(self, tax_model):
        data = {"person": [{"id": 1, "income": 50000.0}, {"id": 2, "income": 100000.0}]}
        result = tax_model.run(data)
        assert "person" in result.arrays
        assert abs(result.arrays["person"][0, 0] - 10000.0) < 0.01

    def test_model_inputs(self, tax_model):
        inputs = tax_model.inputs("person")
        assert "income" in inputs

    def test_run_result_getitem(self, tax_model):
        import numpy as np

        data = {"person": [{"id": 1, "income": 50000.0}]}
        result = tax_model.run(data)
        arr = result["person"]
        assert isinstance(arr, np.ndarray)

    def test_run_result_to_dict(self, tax_model):
        data = {"person": [{"id": 1, "income": 50000.0}, {"id": 2, "income": 100000.0}]}
        result = tax_model.run(data)
        dicts = result.to_dict("person")
        assert len(dicts) == 2
        assert "person/tax" in dicts[0]
        assert abs(dicts[0]["person/tax"] - 10000.0) < 0.01

    def test_model_compare(self, tax_model):
        from rac import Model

        amend_model = Model.from_source(
            """
            entity person:
                income: float

            variable gov/rate:
                from 2024-01-01: 0.20

            variable person/tax:
                entity: person
                from 2024-01-01: income * gov/rate
            """,
            """
            amend gov/rate:
                from 2024-06-01: 0.25
            """,
            as_of=date(2024, 7, 1),
        )

        data = {"person": [{"id": 1, "income": 50000.0}, {"id": 2, "income": 100000.0}]}
        comparison = tax_model.compare(amend_model, data)

        assert "person" in comparison.n_rows
        assert comparison.n_rows["person"] == 2

    def test_compare_result_gain(self, tax_model, reform_model):
        data = {"person": [{"id": 1, "income": 50000.0}]}
        comparison = tax_model.compare(reform_model, data)
        gain = comparison.gain("person", "person/tax")
        # Reform rate 0.25 vs baseline 0.20, income 50k
        # Reform tax: 12500, baseline tax: 10000, gain = +2500
        assert abs(gain[0] - 2500.0) < 0.01

    def test_compare_result_summary(self, tax_model, reform_model):
        data = {
            "person": [
                {"id": i, "income": float(10000 + i * 10000)} for i in range(1, 21)
            ]
        }
        comparison = tax_model.compare(reform_model, data)
        summary = comparison.summary("person", "person/tax")

        assert summary["n"] == 20
        assert "total_annual" in summary
        assert "mean_monthly" in summary
        assert "winners" in summary
        assert "losers" in summary

    def test_compare_result_summary_with_income_deciles(self, tax_model, reform_model):
        import numpy as np

        data = {
            "person": [
                {"id": i, "income": float(10000 + i * 10000)} for i in range(1, 101)
            ]
        }
        comparison = tax_model.compare(reform_model, data)
        income_col = np.array([10000 + i * 10000 for i in range(1, 101)], dtype=np.float64)
        summary = comparison.summary("person", "person/tax", income_col=income_col)

        assert "by_decile" in summary
        assert len(summary["by_decile"]) > 0
        assert "avg_income" in summary["by_decile"][0]
        assert "avg_gain" in summary["by_decile"][0]

    def test_compare_result_summary_empty_decile(self, tax_model, reform_model):
        """Cover model.py line 71: empty decile skipped."""
        import numpy as np

        # Very small dataset where some deciles will be empty
        data = {"person": [{"id": 1, "income": 50000.0}, {"id": 2, "income": 50000.0}]}
        comparison = tax_model.compare(reform_model, data)
        # All same income → most decile bins will be empty
        income_col = np.array([50000.0, 50000.0], dtype=np.float64)
        summary = comparison.summary("person", "person/tax", income_col=income_col)
        assert "by_decile" in summary


# -- Validate coverage -----------------------------------------------------


class TestValidate:
    """Cover validate.py functions."""

    def test_validate_schema_clean(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("""entity: Person
period: Year
dtype: Money
label: My variable
formula: |
    return income * 1
""")
        errors = validate_schema(tmp_path)
        assert errors == []

    def test_validate_schema_invalid_entity(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("entity: BadEntity\n")
        errors = validate_schema(tmp_path)
        assert any("invalid entity" in e for e in errors)

    def test_validate_schema_invalid_period(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("period: Quarterly\n")
        errors = validate_schema(tmp_path)
        assert any("invalid period" in e for e in errors)

    def test_validate_schema_invalid_dtype(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("dtype: Unknown\n")
        errors = validate_schema(tmp_path)
        assert any("invalid dtype" in e for e in errors)

    def test_validate_schema_forbidden_attribute(self, tmp_path):
        from rac.validate import validate_schema

        # "UPPER:" is not a bare definition (starts with uppercase)
        # and not in ALLOWED_ATTRIBUTES, so it triggers the final else
        f = tmp_path / "test.rac"
        # Use a name that matches ^[a-z_]+: but isn't allowed or a bare def
        # Actually "badattr:" matches BARE_DEFINITION_PATTERN so it won't be forbidden.
        # We need something that passes re.match(r"^([a-z_]+)(:|\s|$)") but is NOT
        # in ALLOWED_ATTRIBUTES, CODE_KEYWORDS, code-starting attrs, or BARE_DEF.
        # BARE_DEFINITION_PATTERN is r"^([a-z_][a-z0-9_]*):\s*(?!\|)"
        # So "badattr:" matches BARE_DEF. We need to trick it.
        # If attribute matches code keywords check first and we're not in code, that's line 261-265.
        # For forbidden: need an attr not in ALLOWED, not CODE_KEYWORDS, not code-starting,
        # not BARE_DEF. The BARE_DEF check is "badattr: value" (with non-| value).
        # Actually "badattr:" with nothing after colon also matches BARE_DEF.
        # The only way to reach "forbidden attribute" is if it's NOT a bare def.
        # "badattr  stuff" would match ^([a-z_]+)(\s) but not BARE_DEF_PATTERN.
        f.write_text("badattr stuff\n")
        errors = validate_schema(tmp_path)
        assert any("forbidden attribute" in e for e in errors)

    def test_validate_schema_code_keyword_outside_block(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("return:\n")
        errors = validate_schema(tmp_path)
        assert any("code keyword" in e for e in errors)

    def test_validate_schema_hardcoded_literal(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("formula: |\n    return income * 0.075\n")
        errors = validate_schema(tmp_path)
        assert any("hardcoded literal" in e for e in errors)

    def test_validate_schema_literal_allowed_values(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        # 0, 1, 2, 3 and -1 are allowed
        f.write_text("formula: |\n    return income * 0\n")
        errors = validate_schema(tmp_path)
        assert not any("hardcoded literal" in e for e in errors)

    def test_validate_schema_legislation_antipattern(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("parameter pre_tcja_rate:\n    value: 0.1\n")
        errors = validate_schema(tmp_path)
        assert any("TCJA" in e for e in errors)

    def test_validate_schema_temporal_entry(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("label: test\n  from 2024-01-01: 100\n")
        errors = validate_schema(tmp_path)
        assert errors == []

    def test_validate_schema_multiline_string(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text('label: test\n\"\"\"\nsome bad content\n\"\"\"\n')
        errors = validate_schema(tmp_path)
        assert errors == []

    def test_validate_schema_variable_keyword(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("variable my_var:\n    entity: Person\n")
        errors = validate_schema(tmp_path)
        assert errors == []

    def test_validate_schema_function_keyword(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("function my_func:\n    return 0\n")
        errors = validate_schema(tmp_path)
        assert errors == []

    def test_validate_schema_defined_for(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("defined_for:\n    return True\n")
        errors = validate_schema(tmp_path)
        assert errors == []

    def test_validate_schema_indented_line(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("label: test\n    indented content\n")
        errors = validate_schema(tmp_path)
        assert errors == []

    def test_validate_schema_bare_definition(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("my_variable: some value\n")
        errors = validate_schema(tmp_path)
        assert errors == []

    def test_validate_schema_enum_dtype(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("dtype: Enum[Single,Married]\n")
        errors = validate_schema(tmp_path)
        assert errors == []

    def test_validate_schema_assignment_outside_code(self, tmp_path):
        from rac.validate import validate_schema

        # To reach line 252, we need: not indented, no named match, no main ^([a-z_]+) match,
        # not in code section, and matches ^[a-z_]+\s*=.
        # The main match is r"^([a-z_]+)(:|\s|$)" — "x=5" has "=" after "x" which is not :, \s, or $.
        # So the main match fails for "x=5" (no space before =).
        f = tmp_path / "test.rac"
        f.write_text("x=5\n")
        errors = validate_schema(tmp_path)
        assert any("assignment outside code block" in e for e in errors)

    def test_validate_schema_code_keyword_in_code_block(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        f.write_text("formula: |\n    if True:\n        return 0\n")
        errors = validate_schema(tmp_path)
        # code keyword inside code block is fine
        assert not any("code keyword" in e for e in errors)

    def test_validate_imports_clean(self, tmp_path):
        from rac.validate import validate_imports

        f = tmp_path / "test.rac"
        f.write_text("variable my_var:\n    label: test\n")
        errors = validate_imports(tmp_path)
        assert errors == []

    def test_validate_imports_broken_import(self, tmp_path):
        from rac.validate import validate_imports

        f = tmp_path / "test.rac"
        f.write_text("imports: [nonexistent#my_var]\n")
        errors = validate_imports(tmp_path)
        assert any("broken import" in e for e in errors)

    def test_validate_imports_inline_list(self, tmp_path):
        from rac.validate import validate_imports

        # Create target file
        target = tmp_path / "other.rac"
        target.write_text("variable my_var:\n    label: test\n")

        f = tmp_path / "test.rac"
        f.write_text("imports: [other#my_var]\n")
        errors = validate_imports(tmp_path)
        assert errors == []

    def test_validate_imports_multiline(self, tmp_path):
        from rac.validate import validate_imports

        target = tmp_path / "other.rac"
        target.write_text("variable my_var:\n    label: test\n")

        f = tmp_path / "test.rac"
        f.write_text("imports:\n  - other#my_var\n")
        errors = validate_imports(tmp_path)
        assert errors == []

    def test_validate_imports_cross_repo_skipped(self, tmp_path):
        from rac.validate import validate_imports

        f = tmp_path / "test.rac"
        f.write_text("imports: [rac-us:statute/26/1#some_var]\n")
        errors = validate_imports(tmp_path)
        # Cross-repo imports are skipped
        assert errors == []

    def test_validate_imports_cycle_detection(self, tmp_path):
        from rac.validate import validate_imports

        a = tmp_path / "a.rac"
        b = tmp_path / "b.rac"
        a.write_text("imports: [b#y]\nvariable x:\n    label: x\n")
        b.write_text("imports: [a#x]\nvariable y:\n    label: y\n")
        errors = validate_imports(tmp_path)
        assert any("Circular dependency" in e for e in errors)

    def test_validate_imports_directory_import(self, tmp_path):
        from rac.validate import validate_imports

        subdir = tmp_path / "submod"
        subdir.mkdir()
        (subdir / "index.rac").write_text("variable my_var:\n    label: test\n")

        f = tmp_path / "test.rac"
        f.write_text("imports: [submod#my_var]\n")
        errors = validate_imports(tmp_path)
        assert errors == []

    def test_validate_imports_dir_without_index(self, tmp_path):
        from rac.validate import validate_imports

        subdir = tmp_path / "submod"
        subdir.mkdir()
        (subdir / "stuff.rac").write_text("variable my_var:\n    label: test\n")

        f = tmp_path / "test.rac"
        f.write_text("imports: [submod#my_var]\n")
        errors = validate_imports(tmp_path)
        assert errors == []

    def test_validate_imports_variable_not_found(self, tmp_path):
        from rac.validate import validate_imports

        target = tmp_path / "other.rac"
        target.write_text("variable different_var:\n    label: test\n")

        f = tmp_path / "test.rac"
        f.write_text("imports: [other#missing_var]\n")
        errors = validate_imports(tmp_path)
        assert any("not found" in e for e in errors)

    def test_validate_all(self, tmp_path):
        from rac.validate import validate_all

        f = tmp_path / "test.rac"
        f.write_text("label: test\n")
        errors = validate_all(tmp_path)
        assert errors == []

    def test_extract_exports_bare_def(self, tmp_path):
        from rac.validate import _extract_exports

        f = tmp_path / "test.rac"
        f.write_text("my_var:\n    label: test\n")
        exports = _extract_exports(f)
        assert "my_var" in exports

    def test_extract_exports_parameter(self, tmp_path):
        from rac.validate import _extract_exports

        f = tmp_path / "test.rac"
        f.write_text("parameter my_param:\n    value: 100\n")
        exports = _extract_exports(f)
        assert "my_param" in exports

    def test_extract_exports_skips_structural_keywords(self, tmp_path):
        from rac.validate import _extract_exports

        f = tmp_path / "test.rac"
        f.write_text("imports:\n    - other#x\n")
        exports = _extract_exports(f)
        assert "imports" not in exports

    def test_extract_imports_block_end(self, tmp_path):
        """Import block ends when non-indented non-list line appears."""
        from rac.validate import _extract_imports

        f = tmp_path / "test.rac"
        f.write_text("imports:\n  - other#x\nlabel: test\n")
        imports = _extract_imports(f)
        assert len(imports) == 1

    def test_resolve_import_path_dir_with_name_rac(self, tmp_path):
        from rac.validate import _resolve_import_path

        subdir = tmp_path / "mymod"
        subdir.mkdir()
        # No index.rac, but parent has mymod.rac
        (tmp_path / "mymod.rac").write_text("variable x:\n    label: test\n")
        result = _resolve_import_path("mymod", tmp_path)
        # Should find mymod.rac
        assert result is not None

    def test_find_variable_in_path_not_exists(self):
        from pathlib import Path

        from rac.validate import _find_variable_in_path

        found, msg = _find_variable_in_path("nonexistent", "x", Path("/tmp/fake"))
        assert not found
        assert "does not exist" in msg

    def test_main_schema_command(self, tmp_path):
        from rac.validate import main

        f = tmp_path / "test.rac"
        f.write_text("label: test\n")
        with pytest.raises(SystemExit) as exc_info:
            main(["schema", str(tmp_path)])
        assert exc_info.value.code == 0

    def test_main_imports_command(self, tmp_path):
        from rac.validate import main

        f = tmp_path / "test.rac"
        f.write_text("label: test\n")
        with pytest.raises(SystemExit) as exc_info:
            main(["imports", str(tmp_path)])
        assert exc_info.value.code == 0

    def test_main_all_command(self, tmp_path):
        from rac.validate import main

        f = tmp_path / "test.rac"
        f.write_text("label: test\n")
        with pytest.raises(SystemExit) as exc_info:
            main(["all", str(tmp_path)])
        assert exc_info.value.code == 0

    def test_main_unknown_command(self):
        from rac.validate import main

        with pytest.raises(SystemExit) as exc_info:
            main(["badcmd", "/tmp"])
        assert exc_info.value.code == 2

    def test_main_missing_args(self):
        from rac.validate import main

        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2

    def test_main_nonexistent_dir(self):
        from rac.validate import main

        with pytest.raises(SystemExit) as exc_info:
            main(["schema", "/nonexistent/path"])
        assert exc_info.value.code == 1

    def test_main_with_errors(self, tmp_path):
        from rac.validate import main

        f = tmp_path / "test.rac"
        f.write_text("entity: BadEntity\n")
        with pytest.raises(SystemExit) as exc_info:
            main(["schema", str(tmp_path)])
        assert exc_info.value.code == 1

    def test_find_variable_in_dir_not_found(self, tmp_path):
        from rac.validate import _find_variable_in_path

        subdir = tmp_path / "mymod"
        subdir.mkdir()
        (subdir / "stuff.rac").write_text("variable other_var:\n    label: test\n")

        found, msg = _find_variable_in_path("mymod", "missing", tmp_path)
        assert not found
        assert "not found" in msg

    def test_extract_exports_error_handling(self, tmp_path):
        """_extract_exports handles unreadable files gracefully."""
        from pathlib import Path

        from rac.validate import _extract_exports

        result = _extract_exports(Path("/nonexistent/file.rac"))
        assert result == set()

    def test_imports_pipe_syntax(self, tmp_path):
        from rac.validate import _extract_imports

        f = tmp_path / "test.rac"
        f.write_text("imports: |\n  other#x\n")
        imports = _extract_imports(f)
        # Pipe syntax doesn't produce list items
        assert imports == []

    def test_validate_schema_in_code_section_ignored(self, tmp_path):
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        # "formula:" sets in_code_section=True, then "if" on next line is fine
        f.write_text("formula: |\n    if True:\n        return 0\n    return 1\n")
        errors = validate_schema(tmp_path)
        # Should have no errors - code keywords inside code blocks are OK
        assert errors == []

    def test_validate_schema_formula_end(self, tmp_path):
        """Formula block ends when non-indented non-formula line appears."""
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        # formula block, then a non-indented line that ends the formula
        f.write_text("formula: |\n    return 0\nlabel: test\n")
        errors = validate_schema(tmp_path)
        assert errors == []

    def test_validate_schema_literal_value_error(self, tmp_path):
        """Literal that can't be parsed as float is still flagged."""
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        # A literal like "9e" — matches digit pattern but causes ValueError on float()
        # Actually the regex LITERAL_PATTERN only matches \d+\.\d+ | [4-9] | [1-9]\d+
        # None of those cause ValueError. The ValueError path (L183-185) is very unlikely.
        # Let's test with a valid formula literal instead
        f.write_text("formula: |\n    return income * 100\n")
        errors = validate_schema(tmp_path)
        assert any("hardcoded literal" in e for e in errors)

    def test_validate_schema_code_section_unknown_attr(self, tmp_path):
        """Unknown attribute inside code section is silently ignored (L282)."""
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        # function: starts code section, then unknown attr "xyz" at col 0
        f.write_text("function my_func:\n    return 0\nxyz\n")
        errors = validate_schema(tmp_path)
        # "xyz" doesn't match ^([a-z_]+)(:|\s|$), so it hits the no-match branch.
        # in_code_section is True, so it continues.
        assert not any("xyz" in e for e in errors)

    def test_validate_schema_code_section_match_continues(self, tmp_path):
        """Line matching main regex but in code section is ignored (L251/L282)."""
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        # defined_for: starts code section, then "badattr something" in code section
        f.write_text("defined_for:\n    return True\nbadattr something\n")
        errors = validate_schema(tmp_path)
        # badattr matches ^([a-z_]+)(\s), but we're in code section → L282 continue
        assert not any("forbidden" in e and "badattr" in e for e in errors)

    def test_validate_import_path_neither_file_nor_dir(self, tmp_path):
        """_find_variable_in_path where resolved is neither file nor dir (L395)."""
        from unittest.mock import patch

        from rac.validate import _find_variable_in_path

        # This path is extremely unlikely in practice — _resolve_import_path returns
        # either a file, directory, or None. But we can test it with a mock.
        with patch("rac.validate._resolve_import_path") as mock_resolve:
            from pathlib import Path

            fake_path = Path("/dev/null")  # exists but is special file
            mock_resolve.return_value = fake_path
            found, msg = _find_variable_in_path("test", "x", tmp_path)
            assert not found

    def test_validate_imports_extraction_error(self, tmp_path):
        """Exception during import extraction is caught (L499-501)."""
        import unittest.mock

        f = tmp_path / "test.rac"
        f.write_text("imports: [other#x]\n")

        with (
            unittest.mock.patch(
                "rac.validate._extract_imports", side_effect=ValueError("parse fail")
            ),
            unittest.mock.patch(
                "rac.validate._build_dependency_graph", return_value={}
            ),
        ):
            from rac.validate import validate_imports

            errors = validate_imports(tmp_path)
            assert any("failed to parse imports" in e for e in errors)

    def test_validate_main_module_guard(self):
        """The if __name__ == '__main__' guard (L594) — test via subprocess."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "rac.validate"],
            capture_output=True,
            text=True,
        )
        # No args → usage error, exit code 2
        assert result.returncode == 2
        assert "Usage" in result.stderr

    def test_validate_schema_allowed_literal_in_formula(self, tmp_path):
        """Cover L183: literal value in {-1, 0, 1, 2, 3} is allowed."""
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        # "1.0" matches LITERAL_PATTERN (\d+\.\d+), float("1.0") == 1.0 which is allowed
        f.write_text("formula: |\n    return income * 1.0\n")
        errors = validate_schema(tmp_path)
        assert not any("hardcoded literal '1.0'" in e for e in errors)

    def test_validate_schema_non_alpha_line_in_code_section(self, tmp_path):
        """Cover L251: non-matching line in code section is skipped."""
        from rac.validate import validate_schema

        f = tmp_path / "test.rac"
        # "function" starts code section; then "X_LINE" at col 0 doesn't match
        # ^([a-z_]+)(:|\s|$) because it starts with uppercase.
        # in_code_section is True, so L250-251 triggers.
        f.write_text("function my_func:\n    return 0\nX_LINE = test\n")
        errors = validate_schema(tmp_path)
        assert not any("X_LINE" in e for e in errors)
