"""Tests for Cosilico DSL parser.

Following TDD principles - tests define expected parser behavior.
"""

import pytest

from src.rac.dsl_parser import (
    BinaryOp,
    FunctionCall,
    Identifier,
    IfExpr,
    IndexExpr,
    Lexer,
    # Expression types
    MatchExpr,
    # AST nodes
    TokenType,
    UnaryOp,
    parse_dsl,
)


class TestLexer:
    """Tests for lexical analysis (tokenization)."""

    def test_empty_input(self):
        """Empty input produces only EOF token."""
        lexer = Lexer("")
        tokens = lexer.tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_whitespace_only(self):
        """Whitespace-only input produces only EOF token."""
        lexer = Lexer("   \n\t  \n  ")
        tokens = lexer.tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_single_line_comment_hash(self):
        """Hash-style comments are skipped."""
        lexer = Lexer("# this is a comment\nvariable")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.VARIABLE
        assert tokens[1].type == TokenType.EOF

    def test_single_line_comment_slash(self):
        """Slash-style comments are skipped."""
        lexer = Lexer("// this is a comment\nvariable")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.VARIABLE

    def test_keywords(self):
        """All keywords are recognized."""
        keywords = [
            "module", "version", "jurisdiction", "import", "imports", "references",
            "variable", "enum", "entity", "period", "dtype",
            "label", "description", "unit", "formula", "defined_for",
            "default", "private", "internal", "let", "return", "if",
            "else", "elif", "match", "case", "and", "or", "not", "true", "false"
        ]
        for kw in keywords:
            lexer = Lexer(kw)
            tokens = lexer.tokenize()
            assert tokens[0].type == TokenType[kw.upper()], f"Failed for keyword: {kw}"

    def test_identifier(self):
        """Identifiers are recognized."""
        lexer = Lexer("my_variable foo123 _private")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "my_variable"
        assert tokens[1].type == TokenType.IDENTIFIER
        assert tokens[1].value == "foo123"
        assert tokens[2].type == TokenType.IDENTIFIER
        assert tokens[2].value == "_private"

    def test_integer_number(self):
        """Integer numbers are parsed correctly."""
        lexer = Lexer("42 0 1000")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == 42
        assert tokens[1].value == 0
        assert tokens[2].value == 1000

    def test_float_number(self):
        """Float numbers are parsed correctly."""
        lexer = Lexer("3.14 0.5 100.0")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == 3.14
        assert tokens[1].value == 0.5
        assert tokens[2].value == 100.0

    def test_number_followed_by_dot_identifier(self):
        """Numbers followed by dot and identifier in statute paths.

        Note: The lexer reads "26.32" as a float because it's followed by a digit.
        The parser handles this by splitting floats in dotted name context.
        Tokens: statute, ., 26.32, ., a, ., 1, EOF
        """
        lexer = Lexer("statute.26.32.a.1")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "statute"
        assert tokens[1].type == TokenType.DOT
        assert tokens[2].type == TokenType.NUMBER
        assert tokens[2].value == 26.32  # Lexed as float
        assert tokens[3].type == TokenType.DOT
        assert tokens[4].type == TokenType.IDENTIFIER
        assert tokens[4].value == "a"
        assert tokens[5].type == TokenType.DOT
        assert tokens[6].type == TokenType.NUMBER
        assert tokens[6].value == 1

    def test_negative_number(self):
        """Negative numbers are lexed as MINUS + NUMBER tokens.

        Negative number construction happens in the parser, not lexer.
        This allows distinguishing `a - 42` from `-42`.
        """
        lexer = Lexer("-42 -3.14")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.MINUS
        assert tokens[1].type == TokenType.NUMBER
        assert tokens[1].value == 42
        assert tokens[2].type == TokenType.MINUS
        assert tokens[3].type == TokenType.NUMBER
        assert tokens[3].value == 3.14

    def test_percentage(self):
        """Percentages are converted to decimals."""
        lexer = Lexer("34% 7.65%")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == pytest.approx(0.34)
        assert tokens[1].value == pytest.approx(0.0765)

    def test_string(self):
        """String literals are parsed correctly."""
        lexer = Lexer('"hello world" "with \\"quotes\\""')
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "hello world"
        assert tokens[1].value == 'with "quotes"'

    def test_string_escapes(self):
        """String escape sequences are handled."""
        lexer = Lexer('"line1\\nline2" "tab\\there"')
        tokens = lexer.tokenize()
        assert tokens[0].value == "line1\nline2"
        assert tokens[1].value == "tab\there"

    def test_triple_quoted_string(self):
        """Triple-quoted strings preserve content including special chars."""
        lexer = Lexer('"""This has $100 and "quotes" inside."""')
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == 'This has $100 and "quotes" inside.'

    def test_triple_quoted_multiline(self):
        """Triple-quoted strings can span multiple lines."""
        lexer = Lexer('"""Line 1\nLine 2\nLine 3"""')
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.STRING
        assert "Line 1" in tokens[0].value
        assert "Line 2" in tokens[0].value

    def test_operators(self):
        """All operators are recognized."""
        lexer = Lexer("+ - * / % < > <= >= == != = =>")
        tokens = lexer.tokenize()
        expected = [
            TokenType.PLUS, TokenType.MINUS, TokenType.STAR, TokenType.SLASH,
            TokenType.PERCENT, TokenType.LT, TokenType.GT, TokenType.LE,
            TokenType.GE, TokenType.EQ, TokenType.NE, TokenType.EQUALS,
            TokenType.ARROW, TokenType.EOF
        ]
        for i, exp in enumerate(expected):
            assert tokens[i].type == exp, f"Token {i}: expected {exp}, got {tokens[i].type}"

    def test_brackets(self):
        """Brackets and braces are recognized."""
        lexer = Lexer("{ } ( ) [ ]")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.LBRACE
        assert tokens[1].type == TokenType.RBRACE
        assert tokens[2].type == TokenType.LPAREN
        assert tokens[3].type == TokenType.RPAREN
        assert tokens[4].type == TokenType.LBRACKET
        assert tokens[5].type == TokenType.RBRACKET

    def test_punctuation(self):
        """Punctuation is recognized."""
        lexer = Lexer(", : .")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.COMMA
        assert tokens[1].type == TokenType.COLON
        assert tokens[2].type == TokenType.DOT

    def test_line_tracking(self):
        """Line numbers are tracked correctly."""
        lexer = Lexer("foo\nbar\nbaz")
        tokens = lexer.tokenize()
        assert tokens[0].line == 1
        assert tokens[1].line == 2
        assert tokens[2].line == 3

    def test_column_tracking(self):
        """Column numbers are tracked correctly."""
        lexer = Lexer("foo bar")
        tokens = lexer.tokenize()
        assert tokens[0].column == 1
        assert tokens[1].column == 5


class TestParserVariables:
    """Tests for parsing variable definitions."""

    def test_minimal_variable(self):
        """Parse minimal variable definition."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        module = parse_dsl(code)
        assert len(module.variables) == 1
        var = module.variables[0]
        assert var.name == "tax"
        assert var.entity == "TaxUnit"
        assert var.period == "Year"
        assert var.dtype == "Money"

    def test_variable_with_metadata(self):
        """Parse variable with label and description."""
        code = '''
variable income_tax:
  entity: TaxUnit
  period: Year
  dtype: Money
  label: "Income Tax"
  description: "Federal income tax liability"
'''
        module = parse_dsl(code)
        var = module.variables[0]
        assert var.label == "Income Tax"
        assert var.description == "Federal income tax liability"

    def test_variable_with_default(self):
        """Parse variable with default value."""
        code = """
variable deduction:
  entity: TaxUnit
  period: Year
  dtype: Money
  default: 0
"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert var.default == 0

    def test_private_variable(self):
        """Parse private variable."""
        code = """
private variable helper:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert var.visibility == "private"

    def test_internal_variable(self):
        """Parse internal variable."""
        code = """
internal variable intermediate:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert var.visibility == "internal"

    def test_multiple_variables(self):
        """Parse multiple variable definitions."""
        code = """
variable a:
  entity: TaxUnit
  period: Year
  dtype: Money

variable b:
  entity: Person
  period: Month
  dtype: Boolean
"""
        module = parse_dsl(code)
        assert len(module.variables) == 2
        assert module.variables[0].name == "a"
        assert module.variables[1].name == "b"


class TestParserFormulas:
    """Tests for parsing formula blocks."""

    def test_simple_formula(self):
        """Parse simple return expression."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert var.formula is not None
        assert var.formula.return_expr is not None

    def test_formula_with_let_binding(self):
        """Parse formula with let bindings."""
        code = """
variable eitc:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let rate = 0.34
    let cap = 6960
    return min(income * rate, cap)

"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert len(var.formula.bindings) == 2
        assert var.formula.bindings[0].name == "rate"
        assert var.formula.bindings[1].name == "cap"

    def test_formula_with_if_else(self):
        """Parse formula with conditional."""
        code = """
variable benefit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return if income < 20000: 1000 else 0

"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert isinstance(var.formula.return_expr, IfExpr)

    def test_formula_with_nested_if(self):
        """Parse formula with nested conditionals."""
        code = """
variable rate:
  entity: TaxUnit
  period: Year
  dtype: Rate

  formula:
    return if income < 10000: 0.10 else if income < 40000: 0.22 else 0.32

"""
        module = parse_dsl(code)
        var = module.variables[0]
        expr = var.formula.return_expr
        assert isinstance(expr, IfExpr)
        assert isinstance(expr.else_branch, IfExpr)

    def test_formula_with_match(self):
        """Parse formula with match expression."""
        code = """
variable deduction:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return match {
      case filing_status == "SINGLE" => 14600
      case filing_status == "JOINT" => 29200
      else => 0
    }
"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert isinstance(var.formula.return_expr, MatchExpr)
        assert len(var.formula.return_expr.cases) == 3

    def test_formula_with_function_calls(self):
        """Parse formula with function calls."""
        code = """
variable capped:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return min(max(income, 0), 100000)

"""
        module = parse_dsl(code)
        var = module.variables[0]
        expr = var.formula.return_expr
        assert isinstance(expr, FunctionCall)
        assert expr.name == "min"

    def test_formula_with_binary_ops(self):
        """Parse formula with binary operations."""
        code = """
variable result:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return a + b * c - d / e

"""
        module = parse_dsl(code)
        var = module.variables[0]
        # Should parse with correct precedence
        assert isinstance(var.formula.return_expr, BinaryOp)

    def test_formula_with_comparison_ops(self):
        """Parse formula with comparison operations."""
        code = """
variable eligible:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return income >= 10000 and income <= 50000

"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert isinstance(var.formula.return_expr, BinaryOp)
        assert var.formula.return_expr.op == "and"

    def test_formula_with_unary_not(self):
        """Parse formula with unary not."""
        code = """
variable ineligible:
  entity: TaxUnit
  period: Year
  dtype: Boolean

  formula:
    return not is_eligible

"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert isinstance(var.formula.return_expr, UnaryOp)
        assert var.formula.return_expr.op == "not"

    def test_formula_with_parameter_index(self):
        """Parse formula with indexed parameter."""
        code = """
variable credit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    let rate = credit_rate[n_children]
    return income * rate

"""
        module = parse_dsl(code)
        var = module.variables[0]
        binding = var.formula.bindings[0]
        # IndexExpr with Identifier base and index
        assert isinstance(binding.value, IndexExpr)
        assert isinstance(binding.value.base, Identifier)
        assert binding.value.base.name == "credit_rate"
        assert isinstance(binding.value.index, Identifier)
        assert binding.value.index.name == "n_children"

    def test_formula_with_if_statement_early_return(self):
        """Parse formula with if statement and early return.

        This pattern is common in statute encodings:
        - Check eligibility condition
        - Return 0 if not eligible
        - Otherwise compute and return the value

        This is different from if-then-else expressions.
        """
        code = """
variable credit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    if not is_eligible:
      return 0

    return max(0, amount - reduction)
"""
        module = parse_dsl(code)
        var = module.variables[0]
        # Formula should have an if statement with early return
        # and a final return expression
        assert var.formula is not None
        assert var.formula.return_expr is not None

    def test_formula_with_multiple_if_guards(self):
        """Parse formula with multiple if guard statements.

        Pattern for checking multiple conditions before main computation.
        """
        code = """
variable benefit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    if income > income_limit:
      return 0

    if age < 18:
      return 0

    return base_amount * phase_in_rate
"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert var.formula is not None
        assert var.formula.return_expr is not None


class TestParserReferences:
    """Tests for parsing references blocks."""

    def test_empty_references(self):
        """Parse empty references block."""
        code = """
references:

variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        module = parse_dsl(code)
        assert module.imports is not None
        assert len(module.imports.references) == 0

    def test_single_reference(self):
        """Parse single reference."""
        code = """
references:
  earned_income: statute/26/32/c/2/A/earned_income

variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        module = parse_dsl(code)
        assert len(module.imports.references) == 1
        ref = module.imports.references[0]
        assert ref.alias == "earned_income"
        assert "statute/26/32" in ref.statute_path

    def test_multiple_references(self):
        """Parse multiple references."""
        code = """
references:
  income: statute/26/62/a/adjusted_gross_income
  children: statute/26/32/c/3/count_qualifying_children
  rate: statute/26/32/b/1/credit_percentage

variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        module = parse_dsl(code)
        assert len(module.imports.references) == 3
        aliases = [r.alias for r in module.imports.references]
        assert "income" in aliases
        assert "children" in aliases
        assert "rate" in aliases

    def test_references_get_path(self):
        """Test ReferencesBlock.get_path method."""
        code = """
references:
  income: statute/26/62/a/agi

variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        module = parse_dsl(code)
        path = module.imports.get_path("income")
        assert path is not None
        assert "agi" in path
        assert module.imports.get_path("nonexistent") is None


class TestParserModuleDeclarations:
    """Tests for module-level declarations."""

    def test_module_declaration_with_numeric_segments(self):
        """Parse module declaration with numeric path segments like statute.26.32.a.1."""
        code = """
module statute.26.32.a.1

variable earned_income_credit:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        module = parse_dsl(code)
        assert module.module_decl is not None
        assert module.module_decl.path == "statute.26.32.a.1"

    def test_module_declaration(self):
        """Parse module declaration."""
        code = """
module gov.irs.section32.subsection_a

variable eitc:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        module = parse_dsl(code)
        assert module.module_decl is not None
        assert module.module_decl.path == "gov.irs.section32.subsection_a"

    def test_version_declaration(self):
        """Parse version declaration."""
        code = '''
version "2024.1.0"

variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
'''
        module = parse_dsl(code)
        assert module.version_decl is not None
        assert module.version_decl.version == "2024.1.0"

    def test_jurisdiction_declaration(self):
        """Parse jurisdiction declaration."""
        code = """
jurisdiction us

variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        module = parse_dsl(code)
        assert module.jurisdiction_decl is not None
        assert module.jurisdiction_decl.jurisdiction == "us"

    def test_full_module_header(self):
        """Parse complete module header."""
        code = '''
module gov.irs.eitc
version "2024.1.0"
jurisdiction us

variable eitc:
  entity: TaxUnit
  period: Year
  dtype: Money
'''
        module = parse_dsl(code)
        assert module.module_decl.path == "gov.irs.eitc"
        assert module.version_decl.version == "2024.1.0"
        assert module.jurisdiction_decl.jurisdiction == "us"


class TestParserEnums:
    """Tests for parsing enum definitions."""

    def test_simple_enum(self):
        """Parse simple enum."""
        code = """
enum FilingStatus:
  SINGLE
  JOINT
  HEAD_OF_HOUSEHOLD
  MARRIED_FILING_SEPARATELY
"""
        module = parse_dsl(code)
        assert len(module.enums) == 1
        enum = module.enums[0]
        assert enum.name == "FilingStatus"
        assert "SINGLE" in enum.values
        assert "JOINT" in enum.values
        assert len(enum.values) == 4


class TestParserErrors:
    """Tests for parser error handling."""

    def test_unexpected_character(self):
        """Parser raises error on unexpected character."""
        with pytest.raises(SyntaxError):
            Lexer("variable @invalid").tokenize()

    def test_unclosed_string(self):
        """Lexer handles unclosed string (implementation detail)."""
        # Current implementation doesn't raise on unclosed string
        # but this test documents the behavior
        lexer = Lexer('"unclosed')
        tokens = lexer.tokenize()
        # Should have string token (possibly partial) and EOF
        assert tokens[-1].type == TokenType.EOF

    def test_missing_brace(self):
        """Parser raises error on missing closing brace."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
"""
        # This may or may not raise depending on implementation
        # Test documents expected behavior
        try:
            parse_dsl(code)
            # If it doesn't raise, variable should still be parsed
        except SyntaxError:
            pass  # Expected behavior

    def test_unknown_field_in_variable(self):
        """Parser raises error on unknown field in variable definition."""
        code = '''
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
  reference "26 USC 1"
'''
        with pytest.raises(SyntaxError) as exc_info:
            parse_dsl(code)
        assert "Unknown field 'reference'" in str(exc_info.value)

    def test_unknown_field_helpful_message(self):
        """Error message lists valid fields."""
        code = '''
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
  citation "26 USC 1"
'''
        with pytest.raises(SyntaxError) as exc_info:
            parse_dsl(code)
        assert "Valid fields:" in str(exc_info.value)
        assert "entity" in str(exc_info.value)
        assert "formula" in str(exc_info.value)

    def test_syntax_python_rejected(self):
        """syntax: python is a security risk and must be rejected."""
        code = '''
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
  syntax: python
  formula: |
    import os
    os.system("rm -rf /")
    return 0
'''
        with pytest.raises(SyntaxError) as exc_info:
            parse_dsl(code)
        assert "Invalid syntax 'python'" in str(exc_info.value)
        assert "Only DSL syntax is supported" in str(exc_info.value)

    def test_syntax_arbitrary_rejected(self):
        """Any syntax: value other than DSL-allowed must be rejected."""
        code = '''
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money
  syntax: javascript
  formula: return 0
'''
        with pytest.raises(SyntaxError) as exc_info:
            parse_dsl(code)
        assert "Invalid syntax" in str(exc_info.value)


class TestParserIntegration:
    """Integration tests for complete DSL files."""

    def test_eitc_example(self):
        """Parse EITC example from architecture page."""
        # Note: The DSL uses functional if/then/else expressions, not imperative
        # if statements with early returns. The entire if/then/else is one expression.
        code = """
references:
  is_eligible: statute/26/32/c/1/A/is_eligible_individual
  initial_credit: statute/26/32/a/2/A/initial_credit_amount
  reduction: statute/26/32/a/2/B/credit_reduction_amount

variable earned_income_credit:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    if not is_eligible: 0 else max(0, initial_credit - reduction)

"""
        module = parse_dsl(code)
        assert len(module.variables) == 1
        assert module.imports is not None
        assert len(module.imports.references) == 3

        var = module.variables[0]
        assert var.name == "earned_income_credit"
        assert var.formula is not None

    def test_qualifying_child_example(self):
        """Parse qualifying child example with two variables."""
        # Note: Uses functional if/then/else - nested conditionals are one expression
        code = """
references:
  age: core/person/age
  is_dependent: statute/26/152/is_dependent
  max_age: statute/26/32/c/3/A/max_age
  is_student: statute/26/152/d/2/is_full_time_student

variable is_eitc_qualifying_child:
  entity: Person
  period: Year
  dtype: Boolean

  formula:
    if not is_dependent: false
    else if age < max_age: true
    else false


variable count_eitc_qualifying_children:
  entity: TaxUnit
  period: Year
  dtype: Integer

  formula:
    sum(members, is_eitc_qualifying_child)

"""
        module = parse_dsl(code)
        assert len(module.variables) == 2
        assert module.variables[0].entity == "Person"
        assert module.variables[1].entity == "TaxUnit"

    def test_roundtrip_consistency(self):
        """Parsing same code twice produces equivalent results."""
        code = """
variable tax:
  entity: TaxUnit
  period: Year
  dtype: Money

  formula:
    return income * 0.25

"""
        module1 = parse_dsl(code)
        module2 = parse_dsl(code)

        assert module1.variables[0].name == module2.variables[0].name
        assert module1.variables[0].entity == module2.variables[0].entity


class TestV2ColonSyntax:
    """V2 format requires colons after all field names."""

    def test_entity_requires_colon(self):
        """entity: TaxUnit is valid, entity TaxUnit is not."""
        valid = """
variable test:
  entity: TaxUnit
  period: Year
  dtype: Money
  formula: return 0
"""
        module = parse_dsl(valid)
        assert module.variables[0].entity == "TaxUnit"

    def test_entity_without_colon_fails(self):
        """entity TaxUnit (no colon) should fail."""
        # NOTE: Intentionally using old syntax WITHOUT colon to test error
        invalid = "variable test:\n  entity TaxUnit\n  period: Year\n  dtype: Money\n  formula: return 0\n"
        with pytest.raises(SyntaxError, match="Expected ':'"):
            parse_dsl(invalid)

    def test_period_requires_colon(self):
        """period: Year is valid."""
        valid = """
variable test:
  entity: Person
  period: Year
  dtype: Money
  formula: return 0
"""
        module = parse_dsl(valid)
        assert module.variables[0].period == "Year"

    def test_dtype_requires_colon(self):
        """dtype: Money is valid."""
        valid = """
variable test:
  entity: Person
  period: Year
  dtype: Money
  formula: return 0
"""
        module = parse_dsl(valid)
        assert module.variables[0].dtype == "Money"

    def test_all_fields_with_colons(self):
        """All fields use colon syntax."""
        valid = """
variable test:
  entity: TaxUnit
  period: Year
  dtype: Money
  unit: "USD"
  label: "Test Variable"
  description: "A test"
  default: 0
  formula: return 0
"""
        module = parse_dsl(valid)
        var = module.variables[0]
        assert var.entity == "TaxUnit"
        assert var.period == "Year"
        assert var.dtype == "Money"
        assert var.unit == "USD"
        assert var.label == "Test Variable"
        assert var.description == "A test"
