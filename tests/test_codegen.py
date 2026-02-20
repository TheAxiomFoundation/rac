"""Tests for JavaScript and Python code generators.

Tests the full pipeline: parse .rac source -> compile -> generate JS/Python.
"""

from datetime import date

# Shared RAC source used across tests
TAX_MODEL_SOURCE = """
    entity person:
        income: float

    gov/rate:
        from 2024-01-01: 0.20

    person/tax:
        entity: person
        from 2024-01-01: income * gov/rate
"""


# -- JavaScript Generator ---------------------------------------------------


class TestJavaScriptGenerator:
    def test_generate_js_basic(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/rate:
                from 2024-01-01: 0.25

            gov/base:
                from 2024-01-01: 1000

            gov/tax:
                from 2024-01-01: gov/base * gov/rate
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)

        assert "computeScalars" in js_code
        assert "gov_rate" in js_code
        assert "gov_base" in js_code
        assert "gov_tax" in js_code

    def test_generate_js_with_entity(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            entity person:
                age: int
                income: float
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)

        assert "class PersonInput" in js_code
        assert "this.age" in js_code
        assert "this.income" in js_code

    def test_generate_js_entity_computation(self):
        from rac import compile, generate_javascript, parse

        module = parse(TAX_MODEL_SOURCE)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)

        assert "computePerson" in js_code
        assert "input" in js_code
        assert "scalars" in js_code

    def test_generate_js_conditional(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/rate:
                from 2024-01-01: 0.10
            gov/result:
                from 2024-01-01:
                    if gov/rate > 0.05: 100
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert "?" in js_code
        assert ":" in js_code

    def test_generate_js_builtins(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/val:
                from 2024-01-01: clip(50, 0, 100)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert "Math.min" in js_code
        assert "Math.max" in js_code

    def test_generate_js_min_max(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/a:
                from 2024-01-01: min(10, 20)
            gov/b:
                from 2024-01-01: max(5, 15)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert "Math.min(10, 20)" in js_code
        assert "Math.max(5, 15)" in js_code

    def test_generate_js_abs_round(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/a:
                from 2024-01-01: abs(-5)
            gov/b:
                from 2024-01-01: round(3.7)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert "Math.abs" in js_code
        assert "Math.round" in js_code

    def test_generate_js_unary_neg(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/val:
                from 2024-01-01: -5
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert "gov_val" in js_code

    def test_generate_js_boolean_ops(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/a:
                from 2024-01-01: 1

            gov/b:
                from 2024-01-01: 2

            gov/result:
                from 2024-01-01:
                    if gov/a > 0 and gov/b > 0: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert "&&" in js_code

    def test_generate_js_equality_ops(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/val:
                from 2024-01-01: 10
            gov/result:
                from 2024-01-01:
                    if gov/val == 10: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert "===" in js_code

    def test_generate_js_not_operator(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/flag:
                from 2024-01-01: 1
            gov/result:
                from 2024-01-01:
                    if not gov/flag > 0: 0
                    else: 1
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert "!" in js_code

    def test_generate_js_string_literal(self):
        from rac import ast
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        result = gen._gen_expr(ast.Literal(value="hello"))
        assert result == '"hello"'

    def test_generate_js_bool_literal(self):
        from rac import ast
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        assert gen._gen_expr(ast.Literal(value=True)) == "true"
        assert gen._gen_expr(ast.Literal(value=False)) == "false"

    def test_generate_js_field_access(self):
        from rac import ast
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        expr = ast.FieldAccess(obj=ast.Var(path="person"), field="income")
        result = gen._gen_expr(expr)
        assert result == "person.income"

    def test_generate_js_match(self):
        from rac import ast
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        expr = ast.Match(
            subject=ast.Var(path="status"),
            cases=[
                (ast.Literal(value=1), ast.Literal(value=100)),
                (ast.Literal(value=2), ast.Literal(value=200)),
            ],
            default=ast.Literal(value=0),
        )
        result = gen._gen_expr(expr)
        assert "===" in result
        assert "100" in result
        assert "200" in result

    def test_generate_js_match_no_default(self):
        from rac import ast
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        expr = ast.Match(
            subject=ast.Var(path="status"),
            cases=[
                (ast.Literal(value=1), ast.Literal(value=100)),
            ],
            default=None,
        )
        result = gen._gen_expr(expr)
        assert "===" in result

    def test_generate_js_unknown_builtin(self):
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        result = gen._gen_builtin_call("unknown_func", ["1", "2"])
        assert "unknown" in result

    def test_generate_js_unknown_expr(self):
        """Unknown AST node type falls to default."""
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        # Pass a non-Expr object to trigger default branch
        result = gen._gen_expr("not_an_expr")
        assert result == "0"

    def test_generate_js_reserved_word_ident(self):
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        assert gen._js_ident("class") == "_class"
        assert gen._js_ident("return") == "_return"
        assert gen._js_ident("normal") == "normal"

    def test_generate_js_sum_len(self):
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        assert "reduce" in gen._gen_builtin_call("sum", ["arr"])
        assert "length" in gen._gen_builtin_call("len", ["arr"])

    def test_generate_js_or_operator(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/a:
                from 2024-01-01: 0

            gov/b:
                from 2024-01-01: 1

            gov/result:
                from 2024-01-01:
                    if gov/a > 0 or gov/b > 0: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert "||" in js_code

    def test_generate_js_ne_operator(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/val:
                from 2024-01-01: 10
            gov/result:
                from 2024-01-01:
                    if gov/val != 5: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert "!==" in js_code

    def test_generate_js_header(self):
        from rac import compile, generate_javascript, parse

        module = parse("""
            gov/x:
                from 2024-01-01: 1
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        js_code = generate_javascript(ir)
        assert js_code.startswith("// Auto-generated by RAC compiler")

    def test_generate_js_var_in_computed_lookup(self):
        """Cover javascript.py L128: Var path found in computed_lookup."""
        from rac import ast
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        result = gen._gen_expr(
            ast.Var(path="some/var"),
            entity_var="input",
            scalars_var="scalars",
            computed=[("some/var", "some_var_local")],
        )
        assert result == "some_var_local"

    def test_generate_js_unary_unknown_op(self):
        """Cover javascript.py L150: UnaryOp with unknown operator."""
        from rac import ast
        from rac.codegen.javascript import JavaScriptGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = JavaScriptGenerator(ir, "test")
        result = gen._gen_expr(ast.UnaryOp(op="+", operand=ast.Literal(value=5)))
        assert result == "5"


# -- Python Generator -------------------------------------------------------


class TestPythonGenerator:
    def test_generate_python_basic(self):
        from rac import compile, generate_python, parse

        module = parse("""
            gov/rate:
                from 2024-01-01: 0.25

            gov/base:
                from 2024-01-01: 1000

            gov/tax:
                from 2024-01-01: gov/base * gov/rate
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)

        assert "def compute_scalars" in py_code
        assert "gov_rate" in py_code
        assert "gov_base" in py_code
        assert "gov_tax" in py_code

    def test_generate_python_with_entity(self):
        from rac import compile, generate_python, parse

        module = parse("""
            entity person:
                age: int
                income: float
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)

        assert "@dataclass" in py_code
        assert "class PersonInput" in py_code
        assert "age: int" in py_code
        assert "income: float" in py_code

    def test_generate_python_entity_computation(self):
        from rac import compile, generate_python, parse

        module = parse(TAX_MODEL_SOURCE)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)

        assert "def compute_person" in py_code
        assert "input_data" in py_code
        assert "scalars" in py_code

    def test_generate_python_conditional(self):
        from rac import compile, generate_python, parse

        module = parse("""
            gov/rate:
                from 2024-01-01: 0.10
            gov/result:
                from 2024-01-01:
                    if gov/rate > 0.05: 100
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)
        assert "if" in py_code
        assert "else" in py_code

    def test_generate_python_builtins(self):
        from rac import compile, generate_python, parse

        module = parse("""
            gov/val:
                from 2024-01-01: clip(50, 0, 100)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)
        assert "min(" in py_code
        assert "max(" in py_code

    def test_generate_python_min_max(self):
        from rac import compile, generate_python, parse

        module = parse("""
            gov/a:
                from 2024-01-01: min(10, 20)
            gov/b:
                from 2024-01-01: max(5, 15)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)
        assert "min(10, 20)" in py_code
        assert "max(5, 15)" in py_code

    def test_generate_python_abs_round(self):
        from rac import compile, generate_python, parse

        module = parse("""
            gov/a:
                from 2024-01-01: abs(-5)
            gov/b:
                from 2024-01-01: round(3.7)
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)
        assert "abs(" in py_code
        assert "round(" in py_code

    def test_generate_python_boolean_ops(self):
        from rac import compile, generate_python, parse

        module = parse("""
            gov/a:
                from 2024-01-01: 1

            gov/b:
                from 2024-01-01: 2

            gov/result:
                from 2024-01-01:
                    if gov/a > 0 and gov/b > 0: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)
        assert " and " in py_code

    def test_generate_python_or_operator(self):
        from rac import compile, generate_python, parse

        module = parse("""
            gov/a:
                from 2024-01-01: 0

            gov/b:
                from 2024-01-01: 1

            gov/result:
                from 2024-01-01:
                    if gov/a > 0 or gov/b > 0: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)
        assert " or " in py_code

    def test_generate_python_not_operator(self):
        from rac import compile, generate_python, parse

        module = parse("""
            gov/flag:
                from 2024-01-01: 1
            gov/result:
                from 2024-01-01:
                    if not gov/flag > 0: 0
                    else: 1
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)
        assert "not " in py_code

    def test_generate_python_string_literal(self):
        from rac import ast
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        result = gen._gen_expr(ast.Literal(value="hello"))
        assert result == '"hello"'

    def test_generate_python_bool_literal(self):
        from rac import ast
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        assert gen._gen_expr(ast.Literal(value=True)) == "True"
        assert gen._gen_expr(ast.Literal(value=False)) == "False"

    def test_generate_python_field_access(self):
        from rac import ast
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        expr = ast.FieldAccess(obj=ast.Var(path="person"), field="income")
        result = gen._gen_expr(expr)
        assert result == "person.income"

    def test_generate_python_match(self):
        from rac import ast
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        expr = ast.Match(
            subject=ast.Var(path="status"),
            cases=[
                (ast.Literal(value=1), ast.Literal(value=100)),
                (ast.Literal(value=2), ast.Literal(value=200)),
            ],
            default=ast.Literal(value=0),
        )
        result = gen._gen_expr(expr)
        assert "==" in result
        assert "100" in result
        assert "200" in result

    def test_generate_python_match_no_default(self):
        from rac import ast
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        expr = ast.Match(
            subject=ast.Var(path="status"),
            cases=[
                (ast.Literal(value=1), ast.Literal(value=100)),
            ],
            default=None,
        )
        result = gen._gen_expr(expr)
        assert "==" in result

    def test_generate_python_unknown_builtin(self):
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        result = gen._gen_builtin_call("unknown_func", ["1", "2"])
        assert "unknown" in result

    def test_generate_python_unknown_expr(self):
        """Unknown AST node type falls to default."""
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        result = gen._gen_expr("not_an_expr")
        assert result == "0"

    def test_generate_python_reserved_word_ident(self):
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        assert gen._py_ident("class") == "_class"
        assert gen._py_ident("return") == "_return"
        assert gen._py_ident("normal") == "normal"

    def test_generate_python_sum_len(self):
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        assert gen._gen_builtin_call("sum", ["arr"]) == "sum(arr)"
        assert gen._gen_builtin_call("len", ["arr"]) == "len(arr)"

    def test_generate_python_field_types(self):
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        assert gen._field_type("int") == "int"
        assert gen._field_type("float") == "float"
        assert gen._field_type("str") == "str"
        assert gen._field_type("bool") == "bool"
        assert gen._field_type("date") == "str"
        assert gen._field_type("unknown") == "float"

    def test_generate_python_header(self):
        from rac import compile, generate_python, parse

        module = parse("""
            gov/x:
                from 2024-01-01: 1
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)
        assert py_code.startswith('"""Auto-generated by RAC compiler."""')

    def test_generate_python_exec_works(self):
        """Verify the generated Python is valid and can be exec'd."""
        from rac import compile, generate_python, parse

        module = parse("""
            gov/rate:
                from 2024-01-01: 0.25

            gov/base:
                from 2024-01-01: 1000

            gov/tax:
                from 2024-01-01: gov/base * gov/rate
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)

        # Verify valid Python by exec'ing it
        namespace = {}
        exec(py_code, namespace)

        # Verify the function exists and produces correct results
        result = namespace["compute_scalars"]()
        assert result["gov_rate"] == 0.25
        assert result["gov_base"] == 1000
        assert result["gov_tax"] == 250.0

    def test_generate_python_exec_with_entity(self):
        """Verify generated Python with entity computation is valid."""
        from rac import compile, generate_python, parse

        module = parse(TAX_MODEL_SOURCE)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)

        namespace = {}
        exec(py_code, namespace)

        scalars = namespace["compute_scalars"]()
        assert scalars["gov_rate"] == 0.20

        # Create an input object
        person_input_cls = namespace["PersonInput"]
        person = person_input_cls(income=50000.0)
        result = namespace["compute_person"](person, scalars)
        assert result["person_tax"] == 10000.0

    def test_generate_python_exec_conditional(self):
        """Verify conditional logic executes correctly."""
        from rac import compile, generate_python, parse

        module = parse("""
            gov/threshold:
                from 2024-01-01: 50000

            gov/high_rate:
                from 2024-01-01: 0.30

            gov/low_rate:
                from 2024-01-01: 0.10

            gov/rate:
                from 2024-01-01:
                    if gov/threshold > 40000: gov/high_rate
                    else: gov/low_rate
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)

        namespace = {}
        exec(py_code, namespace)
        result = namespace["compute_scalars"]()
        assert result["gov_rate"] == 0.30

    def test_generate_python_entity_no_fields(self):
        """Entity with no fields generates valid Python."""
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Entity, Schema

        schema = Schema()
        schema.add_entity(Entity(name="empty_thing"))
        ir = IR(schema_=schema, variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        code = gen.generate()
        assert "pass" in code

    def test_generate_python_ne_operator(self):
        from rac import compile, generate_python, parse

        module = parse("""
            gov/val:
                from 2024-01-01: 10
            gov/result:
                from 2024-01-01:
                    if gov/val != 5: 1
                    else: 0
        """)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)
        assert "!=" in py_code

    def test_generate_python_scalars_via_dict(self):
        """Verify scalars are accessed via dict in entity compute."""
        from rac import compile, generate_python, parse

        module = parse(TAX_MODEL_SOURCE)
        ir = compile([module], as_of=date(2024, 6, 1))
        py_code = generate_python(ir)
        assert 'scalars["gov_rate"]' in py_code

    def test_generate_python_var_in_computed_lookup(self):
        """Cover python.py L137: Var path found in computed_lookup."""
        from rac import ast
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        # Pass a computed list that contains the path being referenced
        result = gen._gen_expr(
            ast.Var(path="some/var"),
            entity_var="input_data",
            scalars_var="scalars",
            computed=[("some/var", "some_var_local")],
        )
        assert result == "some_var_local"

    def test_generate_python_unary_unknown_op(self):
        """Cover python.py L159: UnaryOp with unknown operator."""
        from rac import ast
        from rac.codegen.python import PythonGenerator
        from rac.compiler import IR
        from rac.schema import Schema

        ir = IR(schema_=Schema(), variables={}, order=[])
        gen = PythonGenerator(ir, "test")
        # UnaryOp with an operator that is neither "-" nor "not"
        result = gen._gen_expr(ast.UnaryOp(op="+", operand=ast.Literal(value=5)))
        assert result == "5"
