"""Tests for unified RAC syntax.

The new unified syntax eliminates keyword prefixes (parameter, variable)
in favor of a single `name:` pattern, uses `from YYYY-MM-DD:` for temporal
entries, and moves docstrings to top-level triple-quoted strings.

These tests define the expected parser behavior (TDD - written before implementation).
"""

import pytest

from src.rac.dsl_parser import (
    FormulaBlock,
    Lexer,
    TokenType,
    parse_dsl,
)


class TestTopLevelDocstring:
    """Tests for top-level triple-quoted docstrings."""

    def test_docstring_parsed(self):
        """Top-level triple-quoted string sets module.docstring."""
        code = '''
"""
(a) In general. - There shall be imposed a tax...
"""

variable tax:
    entity: TaxUnit
    period: Year
    dtype: Money
'''
        module = parse_dsl(code)
        assert module.docstring is not None
        assert "In general" in module.docstring

    def test_docstring_preserves_content(self):
        """Docstring preserves multiline content."""
        code = '''
"""
(a) In general. - First paragraph.

(b) Exceptions. - Second paragraph.
"""

variable tax:
    entity: TaxUnit
    period: Year
    dtype: Money
'''
        module = parse_dsl(code)
        assert "(a) In general" in module.docstring
        assert "(b) Exceptions" in module.docstring

    def test_no_docstring(self):
        """Module without docstring has None."""
        code = """
variable tax:
    entity: TaxUnit
    period: Year
    dtype: Money
"""
        module = parse_dsl(code)
        assert module.docstring is None

    def test_docstring_with_special_chars(self):
        """Docstring handles special characters like dollar signs."""
        code = '''
"""
The tax rate is 3.8% of the lesser of $250,000 or net investment income.
"""

variable tax:
    entity: TaxUnit
    period: Year
    dtype: Money
'''
        module = parse_dsl(code)
        assert "$250,000" in module.docstring


class TestUnifiedParameterDefinition:
    """Tests for unified `name:` definitions parsed as parameters."""

    def test_simple_parameter(self):
        """A name: with unit and from entries is a parameter."""
        code = """
niit_rate:
    unit: /1
    from 2013-01-01: 0.038
"""
        module = parse_dsl(code)
        assert len(module.parameters) == 1
        param = module.parameters[0]
        assert param.name == "niit_rate"
        assert param.unit == "/1"
        assert "2013-01-01" in param.values
        assert param.values["2013-01-01"] == pytest.approx(0.038)

    def test_parameter_multiple_from_entries(self):
        """Parameter with multiple temporal values."""
        code = """
standard_deduction:
    unit: USD
    from 2023-01-01: 13850
    from 2024-01-01: 14600
"""
        module = parse_dsl(code)
        assert len(module.parameters) == 1
        param = module.parameters[0]
        assert param.values["2023-01-01"] == 13850
        assert param.values["2024-01-01"] == 14600

    def test_parameter_with_description(self):
        """Parameter with metadata fields."""
        code = '''
threshold_joint:
    description: "Threshold for joint filers"
    unit: USD
    from 2013-01-01: 250000
'''
        module = parse_dsl(code)
        param = module.parameters[0]
        assert param.description == "Threshold for joint filers"

    def test_multiple_parameters(self):
        """Multiple parameters parsed in sequence."""
        code = """
rate_a:
    unit: /1
    from 2024-01-01: 0.10

rate_b:
    unit: /1
    from 2024-01-01: 0.22
"""
        module = parse_dsl(code)
        assert len(module.parameters) == 2
        assert module.parameters[0].name == "rate_a"
        assert module.parameters[1].name == "rate_b"


class TestUnifiedVariableDefinition:
    """Tests for unified `name:` definitions parsed as variables."""

    def test_simple_variable(self):
        """A name: with entity/period/dtype is a variable."""
        code = """
net_investment_income_tax:
    entity: TaxUnit
    period: Year
    dtype: Money
    formula:
        return income * 0.038
"""
        module = parse_dsl(code)
        assert len(module.variables) == 1
        var = module.variables[0]
        assert var.name == "net_investment_income_tax"
        assert var.entity == "TaxUnit"
        assert var.period == "Year"
        assert var.dtype == "Money"
        assert var.formula is not None

    def test_variable_with_imports(self):
        """Variable with imports field."""
        code = """
net_investment_income_tax:
    imports:
        - 26/1411/c#net_investment_income
    entity: TaxUnit
    period: Year
    dtype: Money
    formula:
        return net_investment_income * 0.038
"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert len(var.imports) == 1

    def test_variable_with_from_formula(self):
        """Variable using `from` entry with formula code block."""
        code = """
net_investment_income_tax:
    imports:
        - 26/1411/c#net_investment_income
    entity: TaxUnit
    period: Year
    dtype: Money
    from 2013-01-01:
        excess = max(0, magi - threshold)
        return niit_rate * min(net_investment_income, excess)
"""
        module = parse_dsl(code)
        var = module.variables[0]
        # Should have a temporal formula for 2013-01-01
        assert hasattr(var, "temporal_formulas")
        assert "2013-01-01" in var.temporal_formulas
        # The temporal formula should be raw source text for Python-style formulas
        # or a parsed FormulaBlock for DSL formulas

    def test_variable_multiple_from_formulas(self):
        """Variable with formulas for different time periods."""
        code = """
tax_rate:
    entity: TaxUnit
    period: Year
    dtype: Rate
    from 2020-01-01:
        return 0.10
    from 2024-01-01:
        return 0.12
"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert hasattr(var, "temporal_formulas")
        assert "2020-01-01" in var.temporal_formulas
        assert "2024-01-01" in var.temporal_formulas

    def test_variable_with_single_from_also_sets_formula(self):
        """When only one from entry exists, also set .formula for backward compat."""
        code = """
simple_tax:
    entity: TaxUnit
    period: Year
    dtype: Money
    from 2024-01-01:
        return income * 0.25
"""
        module = parse_dsl(code)
        var = module.variables[0]
        # Should also set formula for backward compat with executors
        assert var.formula is not None or var.formula_source is not None


class TestFromKeyword:
    """Tests for the `from` keyword in temporal entries."""

    def test_from_is_keyword(self):
        """'from' is recognized as a keyword token."""
        lexer = Lexer("from")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.FROM

    def test_from_with_date_and_scalar(self):
        """from YYYY-MM-DD: scalar_value for parameters."""
        code = """
rate:
    unit: /1
    from 2024-01-01: 0.038
"""
        module = parse_dsl(code)
        param = module.parameters[0]
        assert param.values["2024-01-01"] == pytest.approx(0.038)

    def test_from_with_date_and_code_block(self):
        """from YYYY-MM-DD: followed by indented code block for variables."""
        code = """
tax:
    entity: TaxUnit
    period: Year
    dtype: Money
    from 2024-01-01:
        return income * rate
"""
        module = parse_dsl(code)
        var = module.variables[0]
        assert hasattr(var, "temporal_formulas")
        assert "2024-01-01" in var.temporal_formulas

    def test_from_with_negative_value(self):
        """from with negative scalar value."""
        code = """
offset:
    unit: USD
    from 2024-01-01: -500
"""
        module = parse_dsl(code)
        param = module.parameters[0]
        assert param.values["2024-01-01"] == -500


class TestRacTestFiles:
    """Tests for .rac.test companion file loading."""

    def test_parse_test_file_format(self, tmp_path):
        """Parse a .rac.test file with test cases."""
        # Create a .rac file
        rac_file = tmp_path / "niit.rac"
        rac_file.write_text("""
niit_rate:
    unit: /1
    from 2013-01-01: 0.038

net_investment_income_tax:
    entity: TaxUnit
    period: Year
    dtype: Money
    formula:
        return niit_rate * net_investment_income
""")

        # Create companion .rac.test file
        test_file = tmp_path / "niit.rac.test"
        test_file.write_text("""
net_investment_income_tax:
    - name: "Basic NIIT"
      period: 2024-01
      inputs:
          net_investment_income: 50000
      expect: 1900

    - name: "Zero income"
      period: 2024-01
      inputs:
          net_investment_income: 0
      expect: 0
""")

        # Import here since it may not exist yet
        from src.rac.test_runner import load_test_file

        tests = load_test_file(test_file)
        assert "net_investment_income_tax" in tests
        assert len(tests["net_investment_income_tax"]) == 2
        assert tests["net_investment_income_tax"][0].name == "Basic NIIT"


class TestMixedDefinitions:
    """Tests for files with both parameters and variables."""

    def test_parameters_and_variables_together(self):
        """Parameters and variables coexist in unified syntax."""
        code = """
niit_rate:
    unit: /1
    from 2013-01-01: 0.038

threshold_joint:
    unit: USD
    from 2013-01-01: 250000

net_investment_income_tax:
    entity: TaxUnit
    period: Year
    dtype: Money
    formula:
        return niit_rate * min(net_investment_income, max(0, magi - threshold_joint))
"""
        module = parse_dsl(code)
        assert len(module.parameters) == 2
        assert len(module.variables) == 1
        assert module.parameters[0].name == "niit_rate"
        assert module.parameters[1].name == "threshold_joint"
        assert module.variables[0].name == "net_investment_income_tax"

    def test_full_niit_example(self):
        """Complete NIIT example in new syntax."""
        code = '''
"""
(a) In general. - In the case of an individual, there shall be imposed
(in addition to any other tax imposed by this subtitle) for each taxable year
a tax equal to 3.8 percent of the lesser of -
(A) net investment income for such taxable year, or
(B) the excess (if any) of -
(i) modified adjusted gross income for such taxable year, over
(ii) the threshold amount.
"""

niit_rate:
    unit: /1
    from 2013-01-01: 0.038

threshold_joint:
    unit: USD
    from 2013-01-01: 250000

net_investment_income_tax:
    imports:
        - 26/1411/c#net_investment_income
    entity: TaxUnit
    period: Year
    dtype: Money
    from 2013-01-01:
        excess = max(0, magi - threshold)
        return niit_rate * min(net_investment_income, excess)
'''
        module = parse_dsl(code)
        assert module.docstring is not None
        assert "In general" in module.docstring
        assert len(module.parameters) == 2
        assert len(module.variables) == 1

    def test_docstring_then_params_then_variable(self):
        """Docstring, parameters, then variable in order."""
        code = '''
"""
Section text here.
"""

rate:
    unit: /1
    from 2024-01-01: 0.10

tax:
    entity: TaxUnit
    period: Year
    dtype: Money
    formula:
        return income * rate
'''
        module = parse_dsl(code)
        assert module.docstring is not None
        assert len(module.parameters) == 1
        assert len(module.variables) == 1


class TestBackwardCompatibility:
    """Tests that old syntax still works alongside new syntax."""

    def test_old_parameter_keyword_still_works(self):
        """parameter name: still parses as ParameterDef."""
        code = """
parameter credit_rate:
    unit: /1
    values:
        2024-01-01: 0.34
"""
        module = parse_dsl(code)
        assert len(module.parameters) == 1
        assert module.parameters[0].name == "credit_rate"

    def test_old_variable_keyword_still_works(self):
        """variable name: still parses as VariableDef."""
        code = """
variable tax:
    entity: TaxUnit
    period: Year
    dtype: Money
    formula:
        return income * 0.25
"""
        module = parse_dsl(code)
        assert len(module.variables) == 1
        assert module.variables[0].name == "tax"

    def test_old_text_field_still_works(self):
        """Old text: | field is still accepted."""
        code = """
text: |
    (a) In general...

variable tax:
    entity: TaxUnit
    period: Year
    dtype: Money
"""
        module = parse_dsl(code)
        # text field should set docstring for backward compat
        assert module.docstring is not None
        assert "In general" in module.docstring

    def test_mixed_old_and_new_syntax(self):
        """Old keyword syntax and new unified syntax can coexist."""
        code = """
niit_rate:
    unit: /1
    from 2013-01-01: 0.038

variable net_investment_income_tax:
    entity: TaxUnit
    period: Year
    dtype: Money
    formula:
        return income * niit_rate
"""
        module = parse_dsl(code)
        assert len(module.parameters) == 1
        assert len(module.variables) == 1


class TestEdgeCases:
    """Edge cases and error handling for unified syntax."""

    def test_empty_file(self):
        """Empty file produces empty module."""
        module = parse_dsl("")
        assert len(module.variables) == 0
        assert len(module.parameters) == 0
        assert module.docstring is None

    def test_only_docstring(self):
        """File with only a docstring."""
        code = '''
"""
Just a docstring, no definitions.
"""
'''
        module = parse_dsl(code)
        assert module.docstring is not None
        assert len(module.variables) == 0
        assert len(module.parameters) == 0

    def test_parameter_with_integer_value(self):
        """Parameter with integer from value."""
        code = """
max_children:
    unit: /1
    from 2024-01-01: 3
"""
        module = parse_dsl(code)
        param = module.parameters[0]
        assert param.values["2024-01-01"] == 3

    def test_unified_definition_disambiguation(self):
        """Parser correctly distinguishes parameters from variables.

        Key heuristic: if a definition has entity/period/dtype fields,
        it's a variable. If it has only from/unit fields, it's a parameter.
        """
        code = """
rate:
    unit: /1
    from 2024-01-01: 0.10

tax:
    entity: TaxUnit
    period: Year
    dtype: Money
    formula:
        return income * rate
"""
        module = parse_dsl(code)
        # rate should be a parameter (no entity/period/dtype)
        assert len(module.parameters) == 1
        assert module.parameters[0].name == "rate"
        # tax should be a variable (has entity/period/dtype)
        assert len(module.variables) == 1
        assert module.variables[0].name == "tax"

    def test_from_not_confused_with_identifier(self):
        """'from' as a keyword doesn't interfere with identifiers containing 'from'."""
        code = """
income_from_wages:
    entity: TaxUnit
    period: Year
    dtype: Money
    formula:
        return wages
"""
        module = parse_dsl(code)
        assert len(module.variables) == 1
        assert module.variables[0].name == "income_from_wages"
