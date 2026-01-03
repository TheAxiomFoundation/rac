"""Cosilico DSL Parser.

Parses .rac files according to the DSL specification in docs/DSL.md.
This is a recursive descent parser that produces an AST.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union


class TokenType(Enum):
    # Keywords
    MODULE = "module"
    VERSION = "version"
    JURISDICTION = "jurisdiction"
    IMPORT = "import"
    IMPORTS = "imports"  # Import block for variables and parameters
    REFERENCES = "references"  # Deprecated alias for imports (backwards compat)
    PARAMETERS = "parameters"  # Parameter block for policy values
    PARAMETER = "parameter"  # Single parameter declaration (RAC v2)
    INPUT = "input"  # Input declaration (RAC v2)
    VARIABLE = "variable"
    ENUM = "enum"
    ENTITY = "entity"
    PERIOD = "period"
    DTYPE = "dtype"
    LABEL = "label"
    DESCRIPTION = "description"
    UNIT = "unit"
    FORMULA = "formula"
    DEFINED_FOR = "defined_for"
    DEFAULT = "default"
    TESTS = "tests"
    PRIVATE = "private"
    INTERNAL = "internal"
    SYNTAX = "syntax"
    LET = "let"
    RETURN = "return"
    IF = "if"
    # THEN removed - using COLON for Python-style syntax
    ELSE = "else"
    ELIF = "elif"
    MATCH = "match"
    CASE = "case"
    AND = "and"
    OR = "or"
    NOT = "not"
    TRUE = "true"
    FALSE = "false"
    AS = "as"  # For import aliasing

    # Symbols
    LBRACE = "{"
    RBRACE = "}"
    LPAREN = "("
    RPAREN = ")"
    LBRACKET = "["
    RBRACKET = "]"
    COMMA = ","
    COLON = ":"
    DOT = "."
    EQUALS = "="
    ARROW = "=>"
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    PERCENT = "%"
    LT = "<"
    GT = ">"
    LE = "<="
    GE = ">="
    EQ = "=="
    NE = "!="
    QUESTION = "?"
    AMPERSAND = "&"  # Alternative for logical and
    PIPE = "|"  # Alternative for logical or
    HASH = "#"  # Fragment identifier in paths

    # Literals
    NUMBER = "NUMBER"
    STRING = "STRING"
    IDENTIFIER = "IDENTIFIER"

    # Special
    EOF = "EOF"
    NEWLINE = "NEWLINE"
    COMMENT = "COMMENT"


@dataclass
class Token:
    type: TokenType
    value: Any
    line: int
    column: int


@dataclass
class ModuleDecl:
    path: str


@dataclass
class VersionDecl:
    version: str


@dataclass
class JurisdictionDecl:
    jurisdiction: str


@dataclass
class ImportDecl:
    module_path: str
    names: list[str]  # ["*"] for wildcard
    alias: Optional[str] = None


@dataclass
class VariableImport:
    """A parsed variable import with optional package prefix.

    Import syntax: package:path#variable as alias
    Example: cosilico-us:statute/26/62/a#adjusted_gross_income as fed_agi

    For local imports (same package), package is None:
        statute/26/62/a#adjusted_gross_income
    """
    file_path: str  # File path within package (e.g., statute/26/62/a)
    variable_name: str  # Variable name within file (e.g., adjusted_gross_income)
    package: Optional[str] = None  # External package name (e.g., cosilico-us)
    alias: Optional[str] = None  # Optional alias for use in formula

    @property
    def effective_name(self) -> str:
        """Name to use in formula (alias or variable_name)."""
        return self.alias if self.alias else self.variable_name

    def full_path(self) -> str:
        """Full import path with package prefix if present."""
        prefix = f"{self.package}:" if self.package else ""
        return f"{prefix}{self.file_path}#{self.variable_name}"


@dataclass
class StatuteReference:
    """A reference mapping a local alias to a statute path.

    Example:
        imports:
          federal_agi: cosilico-us:statute/26/62/a#adjusted_gross_income
          filing_status: statute/26/1#filing_status
    """
    alias: str  # Local name used in formulas
    statute_path: str  # Full statute path (package:path#variable or path#variable)
    # Parsed components
    package: Optional[str] = None  # External package (e.g., cosilico-us)
    file_path: Optional[str] = None  # File path (e.g., statute/26/62/a)
    variable_name: Optional[str] = None  # Variable name (e.g., adjusted_gross_income)


@dataclass
class ReferencesBlock:
    """Block of statute-path references that alias variables for use in formulas."""
    references: list[StatuteReference] = field(default_factory=list)

    def get_path(self, alias: str) -> Optional[str]:
        """Get the statute path for a given alias."""
        for ref in self.references:
            if ref.alias == alias:
                return ref.statute_path
        return None

    def as_dict(self) -> dict[str, str]:
        """Return references as alias -> path dict."""
        return {ref.alias: ref.statute_path for ref in self.references}


@dataclass
class LetBinding:
    name: str
    value: "Expression"


@dataclass
class VariableRef:
    name: str
    period_offset: Optional[int] = None


@dataclass
class ParameterRef:
    path: str
    index: Optional[str] = None  # For indexed params like rate[n_children]


@dataclass
class BinaryOp:
    op: str
    left: "Expression"
    right: "Expression"


@dataclass
class UnaryOp:
    op: str
    operand: "Expression"


@dataclass
class FunctionCall:
    name: str
    args: list["Expression"]


@dataclass
class IfExpr:
    condition: "Expression"
    then_branch: "Expression"
    else_branch: "Expression"


@dataclass
class MatchCase:
    condition: Optional["Expression"]  # None for else
    value: "Expression"


@dataclass
class MatchExpr:
    match_value: Optional["Expression"]  # Value to match against (None for condition-only)
    cases: list[MatchCase]


@dataclass
class Literal:
    value: Any
    dtype: str  # "number", "string", "bool"


@dataclass
class Identifier:
    name: str


@dataclass
class IndexExpr:
    """Subscript/index expression: base[index]

    Used for parameter lookups like credit_percentage[num_qualifying_children]
    """
    base: "Expression"
    index: "Expression"


Expression = Union[
    'LetBinding', 'VariableRef', 'ParameterRef', 'BinaryOp', 'UnaryOp',
    'FunctionCall', 'IfExpr', 'MatchExpr', 'Literal', 'Identifier', 'IndexExpr'
]


@dataclass
class FormulaBlock:
    bindings: list[LetBinding]
    guards: list[tuple]  # List of (condition, return_value) tuples for if-guards
    return_expr: Expression


@dataclass
class VariableDef:
    name: str
    entity: str
    period: str
    dtype: str
    label: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    formula: Optional[FormulaBlock] = None
    formula_source: Optional[str] = None  # Raw formula text (for Python formulas)
    defined_for: Optional[Expression] = None
    default: Optional[Any] = None
    visibility: str = "public"  # "public", "private", "internal"
    imports: list[str] = field(default_factory=list)  # Per-variable imports
    tests: list["TestCase"] = field(default_factory=list)  # Embedded test cases
    syntax: Optional[str] = None  # "python" or None (DSL default)


@dataclass
class TestCase:
    """A test case embedded in a variable definition."""
    name: str
    period: str
    inputs: dict[str, Any]
    expect: Any  # Expected output value


@dataclass
class EnumDef:
    name: str
    values: list[str]


@dataclass
class ParameterDef:
    """A named parameter declaration (RAC v2 format).

    Example:
        parameter credit_rate:
          description: "Credit rate"
          unit: USD
          values:
            2024-01-01: 0.34
    """
    name: str
    description: Optional[str] = None
    unit: Optional[str] = None
    source: Optional[str] = None
    reference: Optional[str] = None
    values: dict[str, Any] = field(default_factory=dict)  # date -> value


@dataclass
class InputDef:
    """An input declaration (RAC v2 format).

    Example:
        input earned_income:
          entity: TaxUnit
          period: Year
          dtype: Money
          unit: USD
          label: "Earned Income"
          description: "Wages plus self-employment income"
          default: 0
    """
    name: str
    entity: str
    period: str
    dtype: str
    unit: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    default: Optional[Any] = None


@dataclass
class Module:
    module_decl: Optional[ModuleDecl] = None
    version_decl: Optional[VersionDecl] = None
    jurisdiction_decl: Optional[JurisdictionDecl] = None
    legacy_imports: list[ImportDecl] = field(default_factory=list)  # Old import syntax
    imports: Optional[ReferencesBlock] = None  # imports { } block for vars/params
    parameters: list[ParameterDef] = field(default_factory=list)  # RAC v2 parameters
    inputs: list[InputDef] = field(default_factory=list)  # RAC v2 inputs
    variables: list[VariableDef] = field(default_factory=list)
    enums: list[EnumDef] = field(default_factory=list)

    @property
    def references(self) -> Optional[ReferencesBlock]:
        """Alias for imports block - used by vectorized executor."""
        return self.imports


class Lexer:
    """Tokenizer for Cosilico DSL."""

    KEYWORDS = {
        "module", "version", "jurisdiction", "import", "imports", "references", "parameters", "parameter", "input", "variable", "enum",
        "entity", "period", "dtype", "label", "description",
        "unit", "formula", "defined_for", "default", "tests", "private", "internal", "syntax",
        "let", "return", "if", "elif", "else", "match", "case",
        "and", "or", "not", "true", "false", "as",
    }

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        while self.pos < len(self.source):
            self._skip_whitespace_and_comments()
            if self.pos >= len(self.source):
                break

            ch = self.source[self.pos]

            # String literals (double or single quotes)
            if ch == '"' or ch == "'":
                self._read_string()
            # Numbers
            elif ch.isdigit():
                self._read_number()
            # Identifiers and keywords (including § for statute section references)
            elif ch.isalpha() or ch == '_' or ch == '§':
                self._read_identifier()
            # Operators and symbols
            else:
                self._read_symbol()

        self.tokens.append(Token(TokenType.EOF, None, self.line, self.column))
        return self.tokens

    def _peek(self, offset: int = 0) -> str:
        pos = self.pos + offset
        if pos < len(self.source):
            return self.source[pos]
        return ""

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _skip_whitespace_and_comments(self):
        consumed_whitespace = False
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch in ' \t\r\n':
                consumed_whitespace = True
                self._advance()
            elif ch == '#':
                # # is a comment only if:
                # 1. At start of line (column == 1), OR
                # 2. After whitespace (we just consumed spaces/tabs/newlines)
                # Otherwise it's a token (fragment identifier in paths)
                if self.column == 1 or consumed_whitespace:
                    while self.pos < len(self.source) and self.source[self.pos] != '\n':
                        self._advance()
                    consumed_whitespace = False  # Reset after consuming comment
                else:
                    break  # Not a comment, let tokenizer handle it
            elif ch == '/' and self.pos + 1 < len(self.source) and self.source[self.pos + 1] == '/':
                # Skip to end of line (// style comment)
                while self.pos < len(self.source) and self.source[self.pos] != '\n':
                    self._advance()
            else:
                break

    def _read_string(self):
        start_line, start_col = self.line, self.column

        # Check for triple-quoted string
        if (self.pos + 2 < len(self.source) and
            self.source[self.pos:self.pos+3] == '"""'):
            self._advance()  # Skip first "
            self._advance()  # Skip second "
            self._advance()  # Skip third "

            value = ""
            while self.pos + 2 < len(self.source):
                if self.source[self.pos:self.pos+3] == '"""':
                    self._advance()  # Skip first "
                    self._advance()  # Skip second "
                    self._advance()  # Skip third "
                    break
                value += self._advance()

            self.tokens.append(Token(TokenType.STRING, value, start_line, start_col))
            return

        # Single-quoted string
        self._advance()  # Skip opening quote

        value = ""
        while self.pos < len(self.source) and self.source[self.pos] != '"':
            if self.source[self.pos] == '\\':
                self._advance()
                if self.pos < len(self.source):
                    escape_ch = self._advance()
                    if escape_ch == 'n':
                        value += '\n'
                    elif escape_ch == 't':
                        value += '\t'
                    else:
                        value += escape_ch
            else:
                value += self._advance()

        if self.pos < len(self.source):
            self._advance()  # Skip closing quote

        self.tokens.append(Token(TokenType.STRING, value, start_line, start_col))

    def _read_number(self):
        start_line, start_col = self.line, self.column
        value = ""

        if self.source[self.pos] == '-':
            value += self._advance()

        # Read digits (including underscores as separators like 5_000)
        while self.pos < len(self.source) and (self.source[self.pos].isdigit() or self.source[self.pos] == '_'):
            ch = self._advance()
            if ch != '_':  # Skip underscores but continue reading
                value += ch

        # Read decimal part only if dot is followed by a digit
        # This allows "26.32.a.1" to be lexed as "26" "." "32" "." "a" "." "1"
        # while still allowing "3.14" to be lexed as a single float
        if self.pos < len(self.source) and self.source[self.pos] == '.':
            # Peek ahead to see if there's a digit after the dot
            if self.pos + 1 < len(self.source) and self.source[self.pos + 1].isdigit():
                value += self._advance()  # Consume the dot
                # Read fractional digits (including underscores)
                while self.pos < len(self.source) and (self.source[self.pos].isdigit() or self.source[self.pos] == '_'):
                    ch = self._advance()
                    if ch != '_':
                        value += ch

        # Check for percentage
        if self.pos < len(self.source) and self.source[self.pos] == '%':
            self._advance()
            num_value = float(value) / 100
        else:
            num_value = float(value) if '.' in value else int(value)

        self.tokens.append(Token(TokenType.NUMBER, num_value, start_line, start_col))

    def _read_identifier(self):
        start_line, start_col = self.line, self.column
        value = ""

        # Allow alphanumeric, underscore, and § (section symbol) in identifiers
        while self.pos < len(self.source) and (
            self.source[self.pos].isalnum() or
            self.source[self.pos] == '_' or
            self.source[self.pos] == '§'
        ):
            value += self._advance()

        # Check if keyword
        if value in self.KEYWORDS:
            token_type = TokenType[value.upper()]
        else:
            token_type = TokenType.IDENTIFIER

        self.tokens.append(Token(token_type, value, start_line, start_col))

    def _read_symbol(self):
        start_line, start_col = self.line, self.column
        ch = self._advance()

        # Two-character operators
        if ch == '=' and self._peek() == '>':
            self._advance()
            self.tokens.append(Token(TokenType.ARROW, "=>", start_line, start_col))
        elif ch == '=' and self._peek() == '=':
            self._advance()
            self.tokens.append(Token(TokenType.EQ, "==", start_line, start_col))
        elif ch == '!' and self._peek() == '=':
            self._advance()
            self.tokens.append(Token(TokenType.NE, "!=", start_line, start_col))
        elif ch == '<' and self._peek() == '=':
            self._advance()
            self.tokens.append(Token(TokenType.LE, "<=", start_line, start_col))
        elif ch == '>' and self._peek() == '=':
            self._advance()
            self.tokens.append(Token(TokenType.GE, ">=", start_line, start_col))
        # Single-character operators
        elif ch == '{':
            self.tokens.append(Token(TokenType.LBRACE, ch, start_line, start_col))
        elif ch == '}':
            self.tokens.append(Token(TokenType.RBRACE, ch, start_line, start_col))
        elif ch == '(':
            self.tokens.append(Token(TokenType.LPAREN, ch, start_line, start_col))
        elif ch == ')':
            self.tokens.append(Token(TokenType.RPAREN, ch, start_line, start_col))
        elif ch == '[':
            self.tokens.append(Token(TokenType.LBRACKET, ch, start_line, start_col))
        elif ch == ']':
            self.tokens.append(Token(TokenType.RBRACKET, ch, start_line, start_col))
        elif ch == ',':
            self.tokens.append(Token(TokenType.COMMA, ch, start_line, start_col))
        elif ch == ':':
            self.tokens.append(Token(TokenType.COLON, ch, start_line, start_col))
        elif ch == '.':
            self.tokens.append(Token(TokenType.DOT, ch, start_line, start_col))
        elif ch == '=':
            self.tokens.append(Token(TokenType.EQUALS, ch, start_line, start_col))
        elif ch == '+':
            self.tokens.append(Token(TokenType.PLUS, ch, start_line, start_col))
        elif ch == '-':
            self.tokens.append(Token(TokenType.MINUS, ch, start_line, start_col))
        elif ch == '*':
            self.tokens.append(Token(TokenType.STAR, ch, start_line, start_col))
        elif ch == '/':
            self.tokens.append(Token(TokenType.SLASH, ch, start_line, start_col))
        elif ch == '%':
            self.tokens.append(Token(TokenType.PERCENT, ch, start_line, start_col))
        elif ch == '<':
            self.tokens.append(Token(TokenType.LT, ch, start_line, start_col))
        elif ch == '>':
            self.tokens.append(Token(TokenType.GT, ch, start_line, start_col))
        elif ch == '?':
            self.tokens.append(Token(TokenType.QUESTION, ch, start_line, start_col))
        elif ch == '&':
            self.tokens.append(Token(TokenType.AMPERSAND, ch, start_line, start_col))
        elif ch == '|':
            self.tokens.append(Token(TokenType.PIPE, ch, start_line, start_col))
        elif ch == '#':
            self.tokens.append(Token(TokenType.HASH, ch, start_line, start_col))
        else:
            raise SyntaxError(f"Unexpected character '{ch}' at line {start_line}, column {start_col}")


class Parser:
    """Recursive descent parser for Cosilico DSL."""

    def __init__(self, tokens: list[Token], source: str = ""):
        self.tokens = tokens
        self.pos = 0
        self.source = source  # Original source for extracting raw formula text
        self.source_lines = source.split('\n') if source else []

    def parse(self) -> Module:
        module = Module()

        while not self._is_at_end():
            if self._check(TokenType.MODULE):
                module.module_decl = self._parse_module_decl()
            elif self._check(TokenType.VERSION):
                module.version_decl = self._parse_version_decl()
            elif self._check(TokenType.JURISDICTION):
                module.jurisdiction_decl = self._parse_jurisdiction_decl()
            elif self._check(TokenType.IMPORT):
                module.legacy_imports.append(self._parse_import())
            elif self._check(TokenType.IMPORTS) or self._check(TokenType.REFERENCES):
                module.imports = self._parse_imports_block()
            elif self._check(TokenType.PARAMETERS):
                # Skip parameters block for now - parameters are loaded separately
                self._skip_parameters_block()
            elif self._check(TokenType.PARAMETER):
                # RAC v2 named parameter declaration
                module.parameters.append(self._parse_parameter())
            elif self._check(TokenType.INPUT):
                # RAC v2 input declaration
                module.inputs.append(self._parse_input())
            elif self._check(TokenType.PRIVATE) or self._check(TokenType.INTERNAL):
                visibility = self._advance().value
                if self._check(TokenType.VARIABLE):
                    var = self._parse_variable()
                    var.visibility = visibility
                    module.variables.append(var)
            elif self._check(TokenType.VARIABLE):
                module.variables.append(self._parse_variable())
            elif self._check(TokenType.ENUM):
                module.enums.append(self._parse_enum())
            elif self._check(TokenType.ENTITY):
                # Inline variable format (file-is-the-variable)
                # entity TaxUnit
                # period Year
                # dtype Money
                # formula:
                #   ...
                inline_var = self._parse_inline_variable()
                if inline_var:
                    module.variables.append(inline_var)
            else:
                # Skip unexpected tokens
                self._advance()

        return module

    def _is_at_end(self) -> bool:
        return self._peek().type == TokenType.EOF

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _previous(self) -> Token:
        return self.tokens[self.pos - 1]

    def _check(self, token_type: TokenType) -> bool:
        if self._is_at_end():
            return False
        return self._peek().type == token_type

    def _peek_next_is(self, token_type: TokenType) -> bool:
        """Check if the next token (after current) is of given type."""
        if self.pos + 1 >= len(self.tokens):
            return False
        return self.tokens[self.pos + 1].type == token_type

    def _advance(self) -> Token:
        if not self._is_at_end():
            self.pos += 1
        return self._previous()

    def _consume(self, token_type: TokenType, message: str) -> Token:
        if self._check(token_type):
            return self._advance()
        raise SyntaxError(f"{message} at line {self._peek().line}")

    def _extract_raw_formula_block(self, formula_line: int) -> str:
        """Extract raw formula text from source for Python formulas.

        Extracts all indented lines after 'formula:' or 'formula: |'
        """
        if not self.source_lines:
            return ""

        # Find the formula line (0-indexed)
        formula_idx = formula_line - 1
        if formula_idx < 0 or formula_idx >= len(self.source_lines):
            return ""

        # Find base indentation of formula: line
        formula_line_text = self.source_lines[formula_idx]
        base_indent = len(formula_line_text) - len(formula_line_text.lstrip())

        # Collect all subsequent lines with greater indentation
        formula_lines = []
        for i in range(formula_idx + 1, len(self.source_lines)):
            line = self.source_lines[i]

            # Empty lines are included if followed by more formula content
            if not line.strip():
                formula_lines.append("")
                continue

            # Check indentation
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                # End of formula block
                break

            # Strip the base indentation + one level (typically 2 spaces)
            # to get the actual formula content
            min_strip = base_indent + 2
            if current_indent >= min_strip:
                formula_lines.append(line[min_strip:])
            else:
                formula_lines.append(line.lstrip())

        # Remove trailing empty lines
        while formula_lines and not formula_lines[-1].strip():
            formula_lines.pop()

        return '\n'.join(formula_lines)

    def _skip_formula_tokens(self):
        """Skip tokens belonging to a Python formula block.

        Advances past formula content until hitting a variable-level field keyword.
        """
        # Keywords that indicate the end of formula content
        end_keywords = {
            TokenType.ENTITY, TokenType.PERIOD, TokenType.DTYPE,
            TokenType.LABEL, TokenType.DESCRIPTION, TokenType.UNIT,
            TokenType.FORMULA, TokenType.DEFINED_FOR, TokenType.DEFAULT,
            TokenType.VARIABLE, TokenType.ENUM, TokenType.PRIVATE,
            TokenType.INTERNAL, TokenType.MODULE, TokenType.VERSION,
            TokenType.IMPORTS, TokenType.REFERENCES, TokenType.PARAMETERS,
            TokenType.TESTS, TokenType.SYNTAX,
        }

        while not self._is_at_end():
            # Check if current token starts a new field/section
            if any(self._check(kw) for kw in end_keywords):
                break
            self._advance()

    def _parse_module_decl(self) -> ModuleDecl:
        self._consume(TokenType.MODULE, "Expected 'module'")
        path = self._parse_dotted_name()
        return ModuleDecl(path=path)

    def _parse_version_decl(self) -> VersionDecl:
        self._consume(TokenType.VERSION, "Expected 'version'")
        version = self._consume(TokenType.STRING, "Expected version string").value
        return VersionDecl(version=version)

    def _parse_jurisdiction_decl(self) -> JurisdictionDecl:
        self._consume(TokenType.JURISDICTION, "Expected 'jurisdiction'")
        jurisdiction = self._consume(TokenType.IDENTIFIER, "Expected jurisdiction name").value
        return JurisdictionDecl(jurisdiction=jurisdiction)

    def _parse_import(self) -> ImportDecl:
        self._consume(TokenType.IMPORT, "Expected 'import'")
        module_path = self._parse_dotted_name()

        self._consume(TokenType.LPAREN, "Expected '('")

        names = []
        if self._check(TokenType.STAR):
            self._advance()
            names = ["*"]
        else:
            names.append(self._consume(TokenType.IDENTIFIER, "Expected identifier").value)
            while self._check(TokenType.COMMA):
                self._advance()
                names.append(self._consume(TokenType.IDENTIFIER, "Expected identifier").value)

        self._consume(TokenType.RPAREN, "Expected ')'")

        alias = None
        # Check for 'as alias' pattern

        return ImportDecl(module_path=module_path, names=names, alias=alias)

    def _skip_parameters_block(self):
        """Skip over parameters block - these are loaded separately from YAML files."""
        self._consume(TokenType.PARAMETERS, "Expected 'parameters'")
        self._consume(TokenType.COLON, "Expected ':' after parameters")

        # Skip until we hit a top-level keyword at column 1
        # Keywords in paths (like 1001/parameters#key) should be skipped
        top_level_keywords = {
            TokenType.ENTITY, TokenType.PERIOD, TokenType.DTYPE,
            TokenType.LABEL, TokenType.DESCRIPTION, TokenType.UNIT,
            TokenType.FORMULA, TokenType.DEFINED_FOR, TokenType.DEFAULT,
            TokenType.VARIABLE, TokenType.ENUM, TokenType.PRIVATE,
            TokenType.INTERNAL, TokenType.MODULE, TokenType.VERSION,
            TokenType.IMPORTS, TokenType.REFERENCES, TokenType.PARAMETERS,
        }

        while not self._is_at_end():
            # Only consider keywords at column 1 as block terminators
            if self._peek().column == 1 and any(self._check(kw) for kw in top_level_keywords):
                break
            self._advance()

    def _parse_imports_block(self) -> ReferencesBlock:
        """Parse an imports block mapping aliases to file paths.

        Syntax (YAML-like with colon):
            imports:
              earned_income: statute/26/32/c/2/A/earned_income
              filing_status: statute/26/1/filing_status

        Also accepts 'references' for backwards compatibility.
        Block ends when we hit a top-level keyword (entity, period, formula, etc.)
        """
        # Accept either 'imports' or 'references' keyword
        if self._check(TokenType.IMPORTS):
            self._advance()
        else:
            self._consume(TokenType.REFERENCES, "Expected 'imports' or 'references'")

        # Expect colon after imports keyword
        self._consume(TokenType.COLON, "Expected ':' after imports")

        references = []

        # Parse references until we hit a top-level keyword
        top_level_keywords = {
            TokenType.ENTITY, TokenType.PERIOD, TokenType.DTYPE,
            TokenType.LABEL, TokenType.DESCRIPTION, TokenType.UNIT,
            TokenType.FORMULA, TokenType.DEFINED_FOR, TokenType.DEFAULT,
            TokenType.VARIABLE, TokenType.ENUM, TokenType.PRIVATE,
            TokenType.INTERNAL, TokenType.MODULE, TokenType.VERSION,
            TokenType.IMPORTS, TokenType.REFERENCES, TokenType.PARAMETERS,
        }

        while not self._is_at_end():
            # Check if we've hit a top-level keyword (end of imports block)
            if any(self._check(kw) for kw in top_level_keywords):
                break

            # Skip comments (already handled by lexer, but check for empty lines)
            if self._check(TokenType.EOF):
                break

            # Parse alias name
            alias = self._consume(TokenType.IDENTIFIER, "Expected alias name").value

            self._consume(TokenType.COLON, "Expected ':'")

            # Parse the import path: package:path#variable
            import_obj = self._parse_import_path()

            references.append(StatuteReference(
                alias=alias,
                statute_path=import_obj.full_path(),
                package=import_obj.package,
                file_path=import_obj.file_path,
                variable_name=import_obj.variable_name
            ))

        return ReferencesBlock(references=references)

    def _parse_variable_imports(self) -> list[VariableImport]:
        """Parse per-variable imports in YAML list format.

        Syntax:
            imports:
              - cosilico-us:statute/26/62/a#adjusted_gross_income
              - statute/26/32/c#earned_income as ei

        Or inline: imports: [path#var, path#var as alias]
        """
        imports: list[VariableImport] = []

        # Check for inline list format: [path, path, ...]
        if self._check(TokenType.LBRACKET):
            self._advance()  # consume '['
            while not self._check(TokenType.RBRACKET) and not self._is_at_end():
                # Parse path#variable format
                import_obj = self._parse_import_path()
                imports.append(import_obj)
                if self._check(TokenType.COMMA):
                    self._advance()
            self._consume(TokenType.RBRACKET, "Expected ']'")
            return imports

        # YAML list format: lines starting with '-'
        top_level_keywords = {
            TokenType.ENTITY, TokenType.PERIOD, TokenType.DTYPE,
            TokenType.LABEL, TokenType.DESCRIPTION, TokenType.UNIT,
            TokenType.FORMULA, TokenType.DEFINED_FOR, TokenType.DEFAULT,
            TokenType.VARIABLE, TokenType.ENUM, TokenType.PRIVATE,
            TokenType.INTERNAL, TokenType.MODULE, TokenType.VERSION,
            TokenType.PARAMETERS,
        }

        while not self._is_at_end():
            # Check if we've hit a top-level keyword (end of imports)
            if any(self._check(kw) for kw in top_level_keywords):
                break

            # Expect '-' for list item
            if self._check(TokenType.MINUS):
                self._advance()  # consume '-'
                import_obj = self._parse_import_path()
                imports.append(import_obj)
            else:
                # Not a list item, end of imports block
                break

        return imports

    def _parse_import_path(self) -> VariableImport:
        """Parse import path: package:path#variable as alias

        Examples:
            cosilico-us:statute/26/62/a#adjusted_gross_income
            statute/26/32/c#earned_income as ei
            26/62/a#agi
        """
        package: Optional[str] = None
        path_parts: list[str] = []
        variable_name: Optional[str] = None
        alias: Optional[str] = None

        # First, collect identifier(s) that might be package name or path start
        # Package names can have hyphens: cosilico-us
        first_part = ""
        if self._check(TokenType.IDENTIFIER):
            first_part = self._advance().value
            # Check for hyphenated name (like cosilico-us)
            while self._check(TokenType.MINUS):
                self._advance()  # consume '-'
                if self._check(TokenType.IDENTIFIER):
                    first_part += "-" + self._advance().value
                else:
                    break
        elif self._check(TokenType.NUMBER):
            first_part = str(int(self._advance().value))
        else:
            raise SyntaxError(f"Expected import path at line {self._peek().line}")

        # Check if next token is COLON (package prefix)
        if self._check(TokenType.COLON):
            # first_part is the package name
            package = first_part
            self._advance()  # consume ':'
            # Now parse the first path component after the package prefix
            if self._check(TokenType.IDENTIFIER):
                path_parts.append(self._advance().value)
            elif self._check(TokenType.NUMBER):
                num_val = self._advance().value
                path_parts.append(str(int(num_val)) if isinstance(num_val, float) else str(num_val))
        else:
            # No package prefix, first_part is start of path
            path_parts.append(first_part)

        # Keywords that can appear as path components (e.g., "26/1/h/parameters#var")
        # Only include keywords that could reasonably be directory/file names
        # Exclude declaration keywords like VARIABLE, ENTITY, FORMULA that indicate
        # the start of a new block
        path_keywords = {
            TokenType.PARAMETERS,  # Can be a directory name
        }

        # Parse path components until we hit # or end of path
        # Path components must be separated by /
        while not self._is_at_end():
            if self._check(TokenType.HASH):
                self._advance()  # consume '#'
                # Variable name after #
                if self._check(TokenType.IDENTIFIER):
                    variable_name = self._advance().value
                # Check for 'as alias' after variable name
                if self._check(TokenType.AS):
                    self._advance()  # consume 'as'
                    if self._check(TokenType.IDENTIFIER):
                        alias = self._advance().value
                break
            elif self._check(TokenType.SLASH):
                self._advance()  # consume '/'
                path_parts.append("/")
                # After slash, consume the next path component
                if self._check(TokenType.IDENTIFIER):
                    path_parts.append(self._advance().value)
                elif any(self._check(kw) for kw in path_keywords):
                    # Keywords like 'parameters' can appear as path components
                    path_parts.append(self._advance().value)
                elif self._check(TokenType.NUMBER):
                    num_val = self._advance().value
                    # Handle numbers like "26" - convert to int then string
                    path_parts.append(str(int(num_val)) if isinstance(num_val, float) else str(num_val))
                    # Handle cases like "25A" tokenized as NUMBER then IDENTIFIER
                    if self._check(TokenType.IDENTIFIER):
                        path_parts[-1] += self._advance().value
                else:
                    # Trailing slash - unusual but valid
                    break
            else:
                # Not a slash or hash - end of path
                break

        # Build the file path from parts
        file_path = "".join(path_parts)

        # If no variable name was found (no #), extract from last path component
        # This supports the references block format: earned_income: statute/26/32/c/2/A/earned_income
        if variable_name is None:
            if "/" in file_path:
                # Last component is the variable name, rest is the file path
                file_path, variable_name = file_path.rsplit("/", 1)
            else:
                # Whole thing is the variable name
                variable_name = file_path
                file_path = ""

        return VariableImport(
            file_path=file_path,
            variable_name=variable_name,
            package=package,
            alias=alias
        )

    def _parse_statute_path(self) -> str:
        """Parse a statute path like 'us/irc/subtitle_a/.../§32/c/2/A/variable_name'."""
        # Consume tokens until we hit something that's not part of a path
        # Path components: identifiers, numbers, §, /, .
        # Keywords like 'parameters', 'imports' can also appear in paths
        parts = []

        # Keywords that can appear in paths as identifiers
        path_keywords = {
            TokenType.PARAMETERS, TokenType.IMPORTS, TokenType.REFERENCES,
            TokenType.ENTITY, TokenType.PERIOD, TokenType.DTYPE,
            TokenType.VARIABLE, TokenType.FORMULA,
        }

        # First component must be identifier or path-allowed keyword
        if self._check(TokenType.IDENTIFIER):
            parts.append(self._advance().value)
        elif any(self._check(kw) for kw in path_keywords):
            parts.append(self._advance().value)
        else:
            parts.append(self._consume(TokenType.IDENTIFIER, "Expected path component").value)

        while True:
            if self._check(TokenType.SLASH):
                self._advance()
                parts.append("/")
                # Next can be identifier, number, keyword, or special chars
                if self._check(TokenType.IDENTIFIER):
                    parts.append(self._advance().value)
                elif self._check(TokenType.NUMBER):
                    parts.append(str(self._advance().value))
                    # Handle cases like "25A" tokenized as NUMBER then IDENTIFIER
                    if self._check(TokenType.IDENTIFIER):
                        parts.append(self._advance().value)
                elif any(self._check(kw) for kw in path_keywords):
                    parts.append(self._advance().value)
                else:
                    break
            elif self._check(TokenType.DOT):
                # Could be .. in path
                self._advance()
                parts.append(".")
                if self._check(TokenType.DOT):
                    self._advance()
                    parts.append(".")
            elif self._check(TokenType.HASH):
                # Fragment identifier like path#fragment or path#fragment.subpath or path#fragment/subpath
                self._advance()
                parts.append("#")
                # Fragment name must be identifier or keyword
                if self._check(TokenType.IDENTIFIER):
                    parts.append(self._advance().value)
                elif any(self._check(kw) for kw in path_keywords):
                    parts.append(self._advance().value)
                # After fragment, can have dot or slash-separated subpath
                while self._check(TokenType.DOT) or self._check(TokenType.SLASH):
                    sep = self._advance().value
                    parts.append(sep)
                    if self._check(TokenType.IDENTIFIER):
                        parts.append(self._advance().value)
                    elif self._check(TokenType.NUMBER):
                        parts.append(str(self._advance().value))
                    elif any(self._check(kw) for kw in path_keywords):
                        parts.append(self._advance().value)
                    else:
                        break
                break
            else:
                break

        return "".join(parts)

    def _parse_dotted_name(self) -> str:
        """Parse a dotted name that can contain identifiers or numbers.

        Examples:
            - gov.irs.eitc (identifiers only)
            - statute.26.32.a.1 (mixed identifiers and numbers)

        Note: The lexer may read "26.32" as a float. In dotted name context,
        we keep it as "26.32" which is the correct representation for statute paths.
        """
        # First component must be an identifier
        name = self._consume(TokenType.IDENTIFIER, "Expected identifier").value

        while self._check(TokenType.DOT):
            self._advance()
            # After a dot, we can have either an identifier or a number
            if self._check(TokenType.IDENTIFIER):
                name += "." + self._advance().value
            elif self._check(TokenType.NUMBER):
                # Convert number to string for the path
                num_value = self._advance().value
                # Handle both int and float
                if isinstance(num_value, int):
                    name += "." + str(num_value)
                elif isinstance(num_value, float):
                    # Check if it's actually an integer value stored as float
                    if num_value == int(num_value):
                        name += "." + str(int(num_value))
                    else:
                        # It's a true float (e.g., 26.32 in statute.26.32.a)
                        # Keep the float representation
                        name += "." + str(num_value)
                else:
                    name += "." + str(num_value)
            else:
                raise SyntaxError(f"Expected identifier or number after '.' at line {self._peek().line}")

        return name

    def _parse_inline_variable(self) -> Optional[VariableDef]:
        """Parse inline variable format (file-is-the-variable).

        Syntax (YAML-like):
            entity TaxUnit
            period Year
            dtype Money
            unit "USD"
            label "..."
            description "..."

            formula:
              let x = ...
              return ...

        Returns a VariableDef with name="inline" (to be set by caller based on filename).
        """
        var = VariableDef(
            name="inline",  # Caller should set based on filename
            entity="",
            period="",
            dtype="",
        )

        # Top-level keywords that end metadata and start formula
        formula_start = {TokenType.FORMULA}

        while not self._is_at_end():
            if self._check(TokenType.ENTITY):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after entity")
                var.entity = self._consume(TokenType.IDENTIFIER, "Expected entity type").value
            elif self._check(TokenType.PERIOD):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after period")
                var.period = self._consume(TokenType.IDENTIFIER, "Expected period type").value
            elif self._check(TokenType.DTYPE):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after dtype")
                var.dtype = self._parse_dtype()
            elif self._check(TokenType.LABEL):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after label")
                var.label = self._consume(TokenType.STRING, "Expected label string").value
            elif self._check(TokenType.DESCRIPTION):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after description")
                var.description = self._consume(TokenType.STRING, "Expected description string").value
            elif self._check(TokenType.UNIT):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after unit")
                # Accept quoted string, unquoted identifier, or /1 for unit
                if self._check(TokenType.STRING):
                    var.unit = self._advance().value
                elif self._check(TokenType.IDENTIFIER):
                    var.unit = self._advance().value
                elif self._check(TokenType.SLASH):
                    # Handle unit like /1 (dimensionless rate)
                    self._advance()  # Skip /
                    if self._check(TokenType.NUMBER):
                        var.unit = f"/{self._advance().value}"
                    else:
                        var.unit = "/"
                else:
                    raise SyntaxError(f"Expected unit value at line {self._peek().line}")
            elif self._check(TokenType.DEFAULT):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after default")
                var.default = self._parse_literal_value()
            elif self._check(TokenType.FORMULA):
                self._advance()
                # Expect colon after formula keyword
                self._consume(TokenType.COLON, "Expected ':' after formula")
                # Parse formula block (no braces in YAML-like syntax)
                var.formula = self._parse_inline_formula_block()
                break  # Formula is last, stop parsing
            elif self._check(TokenType.DEFINED_FOR):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after defined_for")
                var.defined_for = self._parse_expression()
            else:
                # Unknown token - stop parsing this variable
                break

        return var

    def _parse_inline_formula_block(self) -> FormulaBlock:
        """Parse formula block in YAML-like syntax (no braces).

        Syntax:
            formula:
              let earned = wages + salaries
              return earned * rate

        Ends at EOF or next top-level keyword.
        """
        bindings = []
        return_expr = None

        # Keywords that end the formula block
        end_keywords = {
            TokenType.ENTITY, TokenType.PERIOD, TokenType.DTYPE,
            TokenType.LABEL, TokenType.DESCRIPTION, TokenType.UNIT,
            TokenType.FORMULA, TokenType.VARIABLE, TokenType.ENUM,
            TokenType.MODULE, TokenType.VERSION, TokenType.IMPORTS,
            TokenType.REFERENCES, TokenType.PARAMETERS,
        }

        while not self._is_at_end():
            # Check if we've hit a top-level keyword (end of formula)
            if any(self._check(kw) for kw in end_keywords):
                break

            if self._check(TokenType.LET):
                bindings.append(self._parse_let_binding())
            elif self._check(TokenType.RETURN):
                self._advance()
                return_expr = self._parse_expression()
                break
            elif self._check(TokenType.IF):
                # Statement-level if: "if condition then \n return value"
                # This is an early-exit pattern, not an if-expression
                if_expr = self._parse_statement_if()
                if if_expr is not None:
                    # Early return with condition - wrap as conditional return
                    # Create a conditional binding that evaluates to the return value
                    # and continue parsing
                    # For now, we handle this as a conditional with early-exit semantics
                    # by wrapping remaining formula in the else branch
                    early_return_condition = if_expr.condition
                    early_return_value = if_expr.then_branch
                    # Parse rest of formula as the "else" case
                    rest_bindings, rest_expr = self._parse_rest_of_formula(end_keywords)
                    # Wrap in conditional: if condition then early_return else rest
                    return_expr = IfExpr(
                        condition=early_return_condition,
                        then_branch=early_return_value,
                        else_branch=self._wrap_bindings_as_expr(rest_bindings, rest_expr)
                    )
                    break
            elif self._check(TokenType.ELIF):
                # elif in statement context - parse as another if-return
                if_expr = self._parse_statement_elif()
                if if_expr is not None:
                    early_return_condition = if_expr.condition
                    early_return_value = if_expr.then_branch
                    rest_bindings, rest_expr = self._parse_rest_of_formula(end_keywords)
                    return_expr = IfExpr(
                        condition=early_return_condition,
                        then_branch=early_return_value,
                        else_branch=self._wrap_bindings_as_expr(rest_bindings, rest_expr)
                    )
                    break
            elif self._check(TokenType.ELSE):
                # Standalone else: after an if statement
                # Skip 'else' and optional ':'
                self._advance()
                if self._check(TokenType.COLON):
                    self._advance()
                # Continue parsing - the else body follows
            elif self._check(TokenType.IDENTIFIER):
                # Could be assignment: name = expr
                if self._peek_next_is(TokenType.EQUALS):
                    # Parse as let binding without 'let' keyword
                    name = self._advance().value
                    self._consume(TokenType.EQUALS, "Expected '='")
                    value = self._parse_expression()
                    bindings.append(LetBinding(name=name, value=value))
                else:
                    # Expression - treat as return
                    return_expr = self._parse_expression()
                    break
            else:
                # Unknown - treat as return expression
                return_expr = self._parse_expression()
                break

        return FormulaBlock(bindings=bindings, guards=[], return_expr=return_expr)

    def _parse_statement_if(self) -> Optional[IfExpr]:
        """Parse statement-level if: 'if condition:' followed by 'return value'.

        Returns an IfExpr with condition and then_branch (the return value),
        or None if this isn't a statement-level if.
        """
        self._consume(TokenType.IF, "Expected 'if'")
        condition = self._parse_expression()
        self._consume(TokenType.COLON, "Expected ':' after if condition")

        # Check if next token is RETURN (statement-level if)
        if self._check(TokenType.RETURN):
            self._advance()  # consume 'return'
            then_value = self._parse_expression()
            return IfExpr(condition=condition, then_branch=then_value, else_branch=Literal(value=0, dtype="number"))
        else:
            # This is an expression-level if, parse as normal
            then_branch = self._parse_expression()
            # Check for elif chain
            if self._check(TokenType.ELIF):
                else_branch = self._parse_elif_chain()
            else:
                self._consume(TokenType.ELSE, "Expected 'else'")
                else_branch = self._parse_expression()
            return IfExpr(condition=condition, then_branch=then_branch, else_branch=else_branch)

    def _parse_statement_elif(self) -> Optional[IfExpr]:
        """Parse statement-level elif: 'elif condition:' followed by 'return value'."""
        self._consume(TokenType.ELIF, "Expected 'elif'")
        condition = self._parse_expression()
        self._consume(TokenType.COLON, "Expected ':' after elif condition")

        if self._check(TokenType.RETURN):
            self._advance()
            then_value = self._parse_expression()
            return IfExpr(condition=condition, then_branch=then_value, else_branch=Literal(value=0, dtype="number"))
        else:
            then_branch = self._parse_expression()
            if self._check(TokenType.ELIF):
                else_branch = self._parse_elif_chain()
            else:
                self._consume(TokenType.ELSE, "Expected 'else'")
                else_branch = self._parse_expression()
            return IfExpr(condition=condition, then_branch=then_branch, else_branch=else_branch)

    def _parse_rest_of_formula(self, end_keywords: set) -> tuple[list[LetBinding], Optional[Expression]]:
        """Parse remaining bindings and return expression after an early-exit if."""
        bindings = []
        return_expr = None

        while not self._is_at_end():
            if any(self._check(kw) for kw in end_keywords):
                break

            if self._check(TokenType.LET):
                bindings.append(self._parse_let_binding())
            elif self._check(TokenType.RETURN):
                self._advance()
                return_expr = self._parse_expression()
                break
            elif self._check(TokenType.IF):
                # Another if-return statement, parse recursively
                if_expr = self._parse_statement_if()
                if if_expr is not None:
                    early_return_condition = if_expr.condition
                    early_return_value = if_expr.then_branch
                    rest_bindings, rest_expr = self._parse_rest_of_formula(end_keywords)
                    return_expr = IfExpr(
                        condition=early_return_condition,
                        then_branch=early_return_value,
                        else_branch=self._wrap_bindings_as_expr(rest_bindings, rest_expr)
                    )
                    break
            elif self._check(TokenType.ELIF):
                # elif in remaining formula
                if_expr = self._parse_statement_elif()
                if if_expr is not None:
                    early_return_condition = if_expr.condition
                    early_return_value = if_expr.then_branch
                    rest_bindings, rest_expr = self._parse_rest_of_formula(end_keywords)
                    return_expr = IfExpr(
                        condition=early_return_condition,
                        then_branch=early_return_value,
                        else_branch=self._wrap_bindings_as_expr(rest_bindings, rest_expr)
                    )
                    break
            elif self._check(TokenType.ELSE):
                # Standalone else - skip and continue
                self._advance()
                if self._check(TokenType.COLON):
                    self._advance()
            elif self._check(TokenType.IDENTIFIER):
                if self._peek_next_is(TokenType.EQUALS):
                    name = self._advance().value
                    self._consume(TokenType.EQUALS, "Expected '='")
                    value = self._parse_expression()
                    bindings.append(LetBinding(name=name, value=value))
                else:
                    return_expr = self._parse_expression()
                    break
            else:
                return_expr = self._parse_expression()
                break

        return bindings, return_expr

    def _wrap_bindings_as_expr(self, bindings: list[LetBinding], return_expr: Optional[Expression]) -> Expression:
        """Wrap a list of bindings and a return expression as a single expression.

        For execution, we need to represent let bindings + return as a single expression.
        We use a nested structure of function applications to simulate let bindings.
        """
        if not bindings:
            return return_expr if return_expr else Literal(value=0, dtype="number")

        # For now, if there are bindings, create a LetExpr-like structure
        # by using the last binding's value modified to include the return
        # This is a simplification - ideally we'd have proper let-in expressions
        # For the standard_deduction case: basic = ..., return basic + additional
        # We wrap as: (let basic = ... in basic + additional)

        # Create a simplified representation using FormulaBlock
        # The executor will need to handle this appropriately
        return FormulaBlock(bindings=bindings, guards=[], return_expr=return_expr)

    def _parse_parameter(self) -> ParameterDef:
        """Parse a RAC v2 named parameter declaration.

        Example:
            parameter credit_rate:
              description: "Credit rate"
              unit: USD
              source: "IRS"
              reference: "26 USC 32(b)(1)"
              values:
                2024-01-01: 0.34
        """
        self._consume(TokenType.PARAMETER, "Expected 'parameter'")
        name = self._consume(TokenType.IDENTIFIER, "Expected parameter name").value
        self._consume(TokenType.COLON, "Expected ':' after parameter name")

        param = ParameterDef(name=name)

        # Parse parameter attributes
        while not self._is_at_end():
            # Check for end of parameter block
            if self._check(TokenType.PARAMETER) or self._check(TokenType.INPUT) or \
               self._check(TokenType.VARIABLE) or self._check(TokenType.ENUM) or \
               self._check(TokenType.MODULE) or self._check(TokenType.PARAMETERS):
                break

            if self._check(TokenType.DESCRIPTION):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after description")
                param.description = self._consume(TokenType.STRING, "Expected description string").value
            elif self._check(TokenType.UNIT):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after unit")
                if self._check(TokenType.STRING):
                    param.unit = self._advance().value
                elif self._check(TokenType.IDENTIFIER):
                    param.unit = self._advance().value
                elif self._check(TokenType.SLASH):
                    # Handle unit like /1 (dimensionless rate)
                    self._advance()  # Skip /
                    if self._check(TokenType.NUMBER):
                        param.unit = f"/{self._advance().value}"
                    else:
                        param.unit = "/"
                else:
                    raise SyntaxError(f"Expected unit value at line {self._peek().line}")
            elif self._check(TokenType.IDENTIFIER) and self._peek().value == "source":
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after source")
                param.source = self._consume(TokenType.STRING, "Expected source string").value
            elif self._check(TokenType.IDENTIFIER) and self._peek().value == "reference":
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after reference")
                param.reference = self._consume(TokenType.STRING, "Expected reference string").value
            elif self._check(TokenType.IDENTIFIER) and self._peek().value == "values":
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after values")
                param.values = self._parse_parameter_values()
            else:
                # Skip unknown field or break if at next definition
                self._advance()

        return param

    def _parse_parameter_values(self) -> dict[str, Any]:
        """Parse parameter values block: date -> value mappings."""
        values = {}

        # Values can be inline dict or YAML-style multiline
        # For now, expect YAML-style with date keys
        while not self._is_at_end():
            # Check for end of values block
            if self._check(TokenType.PARAMETER) or self._check(TokenType.INPUT) or \
               self._check(TokenType.VARIABLE) or self._check(TokenType.ENUM) or \
               self._check(TokenType.DESCRIPTION) or self._check(TokenType.UNIT) or \
               self._check(TokenType.MODULE) or self._check(TokenType.PARAMETERS):
                break

            # Look for date pattern: 2024-01-01 or just year like 2024
            if self._check(TokenType.NUMBER):
                date_str = self._parse_date_key()
                self._consume(TokenType.COLON, "Expected ':' after date")
                value = self._parse_literal_value()
                values[date_str] = value
            elif self._check(TokenType.IDENTIFIER) and self._peek().value in ("source", "reference", "values", "indexed_by"):
                # Hit another field name, stop parsing values
                break
            else:
                # Skip unrecognized token
                self._advance()

        return values

    def _parse_date_key(self) -> str:
        """Parse a date key like 2024-01-01 or just year like 2024."""
        year = self._consume(TokenType.NUMBER, "Expected year").value
        # Check if this is a full date (YYYY-MM-DD) or just year (YYYY)
        if self._check(TokenType.MINUS):
            self._advance()  # Consume -
            month = self._consume(TokenType.NUMBER, "Expected month").value
            self._consume(TokenType.MINUS, "Expected '-' in date")
            day = self._consume(TokenType.NUMBER, "Expected day").value
            return f"{year}-{month:02d}-{day:02d}" if isinstance(month, int) else f"{year}-{month}-{day}"
        else:
            # Year only - convert to YYYY-01-01
            return f"{year}-01-01"

    def _parse_input(self) -> InputDef:
        """Parse a RAC v2 input declaration.

        Example:
            input earned_income:
              entity: TaxUnit
              period: Year
              dtype: Money
              unit: USD
              label: "Earned Income"
              description: "Wages plus self-employment"
              default: 0
        """
        self._consume(TokenType.INPUT, "Expected 'input'")
        name = self._consume(TokenType.IDENTIFIER, "Expected input name").value
        self._consume(TokenType.COLON, "Expected ':' after input name")

        inp = InputDef(
            name=name,
            entity="",
            period="",
            dtype="",
        )

        # Parse input attributes
        while not self._is_at_end():
            # Check for end of input block
            if self._check(TokenType.PARAMETER) or self._check(TokenType.INPUT) or \
               self._check(TokenType.VARIABLE) or self._check(TokenType.ENUM) or \
               self._check(TokenType.MODULE) or self._check(TokenType.PARAMETERS):
                break

            if self._check(TokenType.ENTITY):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after entity")
                inp.entity = self._consume(TokenType.IDENTIFIER, "Expected entity type").value
            elif self._check(TokenType.PERIOD):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after period")
                inp.period = self._consume(TokenType.IDENTIFIER, "Expected period type").value
            elif self._check(TokenType.DTYPE):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after dtype")
                inp.dtype = self._parse_dtype()
            elif self._check(TokenType.LABEL):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after label")
                inp.label = self._consume(TokenType.STRING, "Expected label string").value
            elif self._check(TokenType.DESCRIPTION):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after description")
                inp.description = self._consume(TokenType.STRING, "Expected description string").value
            elif self._check(TokenType.UNIT):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after unit")
                if self._check(TokenType.STRING):
                    inp.unit = self._advance().value
                elif self._check(TokenType.IDENTIFIER):
                    inp.unit = self._advance().value
                elif self._check(TokenType.SLASH):
                    # Handle unit like /1 (dimensionless rate)
                    self._advance()  # Skip /
                    if self._check(TokenType.NUMBER):
                        inp.unit = f"/{self._advance().value}"
                    else:
                        inp.unit = "/"
                else:
                    raise SyntaxError(f"Expected unit value at line {self._peek().line}")
            elif self._check(TokenType.DEFAULT):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after default")
                inp.default = self._parse_literal_value()
            else:
                # Skip unknown field
                self._advance()

        return inp

    def _parse_variable(self) -> VariableDef:
        self._consume(TokenType.VARIABLE, "Expected 'variable'")
        name = self._consume(TokenType.IDENTIFIER, "Expected variable name").value
        self._consume(TokenType.COLON, "Expected ':' after variable name")

        var = VariableDef(
            name=name,
            entity="",
            period="",
            dtype="",
        )

        # Parse until we hit a non-indented line or end of file
        # For now, parse until we see another top-level keyword or EOF
        while not self._is_at_end():
            # Check for end of variable block (next top-level element)
            # Note: IMPORTS inside variable block is per-variable imports, not module-level
            if self._check(TokenType.VARIABLE) or self._check(TokenType.ENUM) or \
               self._check(TokenType.MODULE) or self._check(TokenType.PARAMETERS) or \
               self._check(TokenType.PARAMETER) or self._check(TokenType.INPUT):
                break

            if self._check(TokenType.IMPORTS) or self._check(TokenType.REFERENCES):
                # Per-variable imports: imports: [path#var, ...] or imports:\n  - path#var
                self._advance()  # consume 'imports' or 'references'
                self._consume(TokenType.COLON, "Expected ':' after imports")
                var.imports = self._parse_variable_imports()
            elif self._check(TokenType.ENTITY):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after entity")
                var.entity = self._consume(TokenType.IDENTIFIER, "Expected entity type").value
            elif self._check(TokenType.PERIOD):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after period")
                var.period = self._consume(TokenType.IDENTIFIER, "Expected period type").value
            elif self._check(TokenType.DTYPE):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after dtype")
                var.dtype = self._parse_dtype()
            elif self._check(TokenType.LABEL):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after label")
                var.label = self._consume(TokenType.STRING, "Expected label string").value
            elif self._check(TokenType.DESCRIPTION):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after description")
                var.description = self._consume(TokenType.STRING, "Expected description string").value
            elif self._check(TokenType.UNIT):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after unit")
                # Accept quoted string, unquoted identifier, or /1 for unit
                if self._check(TokenType.STRING):
                    var.unit = self._advance().value
                elif self._check(TokenType.IDENTIFIER):
                    var.unit = self._advance().value
                elif self._check(TokenType.SLASH):
                    # Handle unit like /1 (dimensionless rate)
                    self._advance()  # Skip /
                    if self._check(TokenType.NUMBER):
                        var.unit = f"/{self._advance().value}"
                    else:
                        var.unit = "/"
                else:
                    raise SyntaxError(f"Expected unit value at line {self._peek().line}")
            elif self._check(TokenType.FORMULA):
                formula_start_token = self._peek()
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after formula")
                # Accept YAML pipe syntax: formula: |
                # This is optional - formulas can also start directly after colon
                has_pipe = False
                if self._check(TokenType.PIPE):
                    has_pipe = True
                    self._advance()  # Skip the pipe

                # If syntax is Python, extract raw formula text and skip DSL parsing
                if var.syntax == "python":
                    var.formula_source = self._extract_raw_formula_block(formula_start_token.line)
                    # Skip tokens until we hit the next field or end of variable
                    self._skip_formula_tokens()
                else:
                    var.formula = self._parse_formula_block_indent()
                # Continue parsing - tests may come after formula
            elif self._check(TokenType.TESTS):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after tests")
                var.tests = self._parse_tests()
            elif self._check(TokenType.DEFINED_FOR):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after defined_for")
                var.defined_for = self._parse_expression()
            elif self._check(TokenType.DEFAULT):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after default")
                var.default = self._parse_literal_value()
            elif self._check(TokenType.SYNTAX):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':' after syntax")
                syntax_token = self._consume(TokenType.IDENTIFIER, "Expected syntax type")
                allowed_syntax = []  # No alternative syntaxes allowed - DSL only
                if syntax_token.value not in allowed_syntax:
                    raise SyntaxError(
                        f"Invalid syntax '{syntax_token.value}' at line {syntax_token.line}. "
                        f"Only DSL syntax is supported (remove 'syntax:' field)."
                    )
                var.syntax = syntax_token.value
            elif self._check(TokenType.IDENTIFIER):
                # Unknown field - raise helpful error
                unknown = self._peek().value
                valid_fields = ["entity", "period", "dtype", "label", "description", "unit", "formula", "defined_for", "default", "tests", "imports", "syntax"]
                raise SyntaxError(
                    f"Unknown field '{unknown}' in variable definition at line {self._peek().line}. "
                    f"Valid fields: {', '.join(valid_fields)}"
                )
            else:
                # End of variable block
                break

        return var

    def _parse_tests(self) -> list[TestCase]:
        """Parse embedded test cases in YAML list format.

        Syntax:
            tests:
              - name: "Test name"
                period: 2024-01
                inputs:
                  var1: 100
                  var2: 200
                expect: 300
        """
        tests: list[TestCase] = []

        # Top-level keywords that end the tests block
        end_keywords = {
            TokenType.ENTITY, TokenType.PERIOD, TokenType.DTYPE,
            TokenType.LABEL, TokenType.DESCRIPTION, TokenType.UNIT,
            TokenType.FORMULA, TokenType.DEFINED_FOR, TokenType.DEFAULT,
            TokenType.VARIABLE, TokenType.ENUM, TokenType.PRIVATE,
            TokenType.INTERNAL, TokenType.MODULE, TokenType.VERSION,
            TokenType.PARAMETERS, TokenType.IMPORTS, TokenType.REFERENCES,
        }

        while not self._is_at_end():
            # Check if we've hit a top-level keyword (end of tests block)
            if any(self._check(kw) for kw in end_keywords):
                break

            # Expect '-' for list item
            if self._check(TokenType.MINUS):
                self._advance()  # consume '-'
                test_case = self._parse_single_test()
                tests.append(test_case)
            else:
                # Not a list item, end of tests block
                break

        return tests

    def _parse_single_test(self) -> TestCase:
        """Parse a single test case."""
        name = ""
        period = ""
        inputs: dict[str, Any] = {}
        expect: Any = None

        while not self._is_at_end():
            # Check for end conditions
            if self._check(TokenType.MINUS):
                # Another test case
                break
            if self._check(TokenType.VARIABLE) or self._check(TokenType.ENUM) or \
               self._check(TokenType.MODULE) or self._check(TokenType.TESTS):
                break

            # Handle 'name' field (IDENTIFIER)
            if self._check(TokenType.IDENTIFIER) and self._peek().value == "name":
                self._advance()
                self._consume(TokenType.COLON, "Expected ':'")
                name = self._consume(TokenType.STRING, "Expected test name string").value
            # Handle 'period' field (PERIOD keyword token)
            elif self._check(TokenType.PERIOD):
                self._advance()
                self._consume(TokenType.COLON, "Expected ':'")
                period = self._parse_period_value()
            # Handle 'inputs' field (IDENTIFIER)
            elif self._check(TokenType.IDENTIFIER) and self._peek().value == "inputs":
                self._advance()
                self._consume(TokenType.COLON, "Expected ':'")
                inputs = self._parse_test_inputs()
            # Handle 'expect' field (IDENTIFIER)
            elif self._check(TokenType.IDENTIFIER) and self._peek().value == "expect":
                self._advance()
                self._consume(TokenType.COLON, "Expected ':'")
                expect = self._parse_test_value()
            else:
                break

        return TestCase(name=name, period=period, inputs=inputs, expect=expect)

    def _parse_period_value(self) -> str:
        """Parse period value like '2024-01' or '1989-01'."""
        # Period can be: NUMBER (2024) MINUS NUMBER (01)
        # or: STRING ("2024-01")
        if self._check(TokenType.STRING):
            return self._advance().value

        # Parse as number-minus-number pattern
        if self._check(TokenType.NUMBER):
            year = str(int(self._advance().value))
            if self._check(TokenType.MINUS):
                self._advance()
                if self._check(TokenType.NUMBER):
                    month = str(int(self._advance().value)).zfill(2)
                    return f"{year}-{month}"
            return year

        return ""

    def _parse_test_inputs(self) -> dict[str, Any]:
        """Parse test inputs as key-value pairs."""
        inputs: dict[str, Any] = {}

        # Test-level field identifiers that end the inputs block
        test_fields = {"name", "inputs", "expect"}

        while not self._is_at_end():
            # Check for end conditions
            if self._check(TokenType.MINUS):
                # Another test case
                break
            if self._check(TokenType.VARIABLE) or self._check(TokenType.ENUM) or \
               self._check(TokenType.MODULE) or self._check(TokenType.TESTS) or \
               self._check(TokenType.PERIOD):  # PERIOD keyword ends inputs block
                break

            if self._check(TokenType.IDENTIFIER):
                field_name = self._peek().value
                # Check if this is a test-level field (end of inputs)
                if field_name in test_fields:
                    break

                # It's an input variable
                var_name = self._advance().value
                self._consume(TokenType.COLON, "Expected ':'")
                value = self._parse_test_value()
                inputs[var_name] = value
            else:
                break

        return inputs

    def _parse_test_value(self) -> Any:
        """Parse a test value (number, string, bool)."""
        if self._check(TokenType.NUMBER):
            return self._advance().value
        if self._check(TokenType.STRING):
            return self._advance().value
        if self._check(TokenType.TRUE):
            self._advance()
            return True
        if self._check(TokenType.FALSE):
            self._advance()
            return False
        if self._check(TokenType.MINUS):
            # Negative number
            self._advance()
            if self._check(TokenType.NUMBER):
                return -self._advance().value
        if self._check(TokenType.IDENTIFIER):
            # Could be an enum value or variable reference
            return self._advance().value
        return None

    def _parse_dtype(self) -> str:
        dtype = self._consume(TokenType.IDENTIFIER, "Expected data type").value
        # Handle parameterized types like Enum(T)
        if self._check(TokenType.LPAREN):
            self._advance()
            inner = self._consume(TokenType.IDENTIFIER, "Expected type parameter").value
            self._consume(TokenType.RPAREN, "Expected ')'")
            dtype = f"{dtype}({inner})"
        return dtype

    def _parse_enum(self) -> EnumDef:
        self._consume(TokenType.ENUM, "Expected 'enum'")
        name = self._consume(TokenType.IDENTIFIER, "Expected enum name").value
        self._consume(TokenType.COLON, "Expected ':' after enum name")

        values = []
        # Parse enum values until we hit a non-enum token
        while not self._is_at_end():
            if self._check(TokenType.IDENTIFIER):
                values.append(self._advance().value)
            elif self._check(TokenType.VARIABLE) or self._check(TokenType.ENUM) or \
                 self._check(TokenType.MODULE) or self._check(TokenType.ENTITY) or \
                 self._check(TokenType.IMPORTS) or self._check(TokenType.REFERENCES):
                break
            else:
                break

        return EnumDef(name=name, values=values)

    def _parse_formula_block_indent(self) -> FormulaBlock:
        """Parse indented formula block (Python-style, no braces)."""
        bindings = []
        guards = []
        return_expr = None

        # Parse until we see a non-indented line or top-level keyword
        while not self._is_at_end():
            # Check for end of formula block
            if self._check(TokenType.VARIABLE) or self._check(TokenType.ENUM) or \
               self._check(TokenType.MODULE) or self._check(TokenType.ENTITY) or \
               self._check(TokenType.PERIOD) or self._check(TokenType.DTYPE) or \
               self._check(TokenType.IMPORTS) or self._check(TokenType.REFERENCES) or \
               self._check(TokenType.LABEL) or self._check(TokenType.DESCRIPTION) or \
               self._check(TokenType.DEFAULT) or self._check(TokenType.TESTS):
                break

            if self._check(TokenType.LET):
                bindings.append(self._parse_let_binding())
            elif self._check(TokenType.IF):
                # Check if this is an if-guard or an if-expression
                guard = self._try_parse_if_guard()
                if guard:
                    guards.append(guard)
                else:
                    # It's an if-expression, parse as return expression
                    return_expr = self._parse_expression()
                    break
            elif self._check(TokenType.RETURN):
                self._advance()
                return_expr = self._parse_expression()
            elif self._check(TokenType.IDENTIFIER) and self._peek_next_is(TokenType.EQUALS):
                # Assignment without 'let' keyword: name = expr
                name = self._advance().value
                self._consume(TokenType.EQUALS, "Expected '='")
                value = self._parse_expression()
                bindings.append(LetBinding(name=name, value=value))
            elif self._check(TokenType.IDENTIFIER):
                # Plain expression like sum(...) - parse as return expression
                return_expr = self._parse_expression()
                break
            else:
                # Unknown token, end of block
                break

        # Build nested if-else from guards and final return
        if guards and return_expr:
            result = return_expr
            for condition, guard_value in reversed(guards):
                result = IfExpr(condition=condition, then_branch=guard_value, else_branch=result)
            return_expr = result

        return FormulaBlock(bindings=bindings, guards=[], return_expr=return_expr)

    def _parse_formula_block(self) -> FormulaBlock:
        bindings = []
        guards = []  # List of (condition, return_value) tuples for if-guards
        return_expr = None

        while not self._check(TokenType.RBRACE) and not self._is_at_end():
            if self._check(TokenType.LET):
                bindings.append(self._parse_let_binding())
            elif self._check(TokenType.IF):
                # Check if this is an if-guard statement (if ... then return ...)
                # or an if-expression (if ... then expr else expr)
                guard = self._try_parse_if_guard()
                if guard:
                    guards.append(guard)
                else:
                    # It's an if-expression, parse as return expression
                    return_expr = self._parse_expression()
                    break
            elif self._check(TokenType.RETURN):
                self._advance()
                return_expr = self._parse_expression()
                break
            else:
                # Implicit return - expression without 'return' keyword
                return_expr = self._parse_expression()
                break

        # Build nested if-else from guards and final return
        if guards and return_expr:
            # Transform guards into nested if-else expression
            # guards = [(cond1, val1), (cond2, val2)]
            # return_expr = final_val
            # Result: if cond1 then val1 else if cond2 then val2 else final_val
            result = return_expr
            for condition, guard_value in reversed(guards):
                result = IfExpr(condition=condition, then_branch=guard_value, else_branch=result)
            return_expr = result

        return FormulaBlock(bindings=bindings, guards=[], return_expr=return_expr)

    def _try_parse_if_guard(self) -> tuple | None:
        """Try to parse an if-guard statement: if <cond>: return <expr>

        Returns (condition, return_value) tuple if successful, None if this is
        a regular if-expression that should be parsed differently.
        """
        # Save position to backtrack if this isn't a guard
        saved_pos = self.pos

        self._advance()  # consume 'if'
        condition = self._parse_expression()

        if not self._check(TokenType.COLON):
            # Not a valid if, backtrack
            self.pos = saved_pos
            return None

        self._advance()  # consume ':'

        # Check if next token is 'return' - that makes this a guard
        if self._check(TokenType.RETURN):
            self._advance()  # consume 'return'
            return_value = self._parse_expression()
            return (condition, return_value)

        # Not a guard, backtrack and let caller parse as expression
        self.pos = saved_pos
        return None

    def _parse_let_binding(self) -> LetBinding:
        self._consume(TokenType.LET, "Expected 'let'")
        name = self._consume(TokenType.IDENTIFIER, "Expected variable name").value
        self._consume(TokenType.EQUALS, "Expected '='")
        value = self._parse_expression()
        return LetBinding(name=name, value=value)

    def _parse_expression(self) -> Expression:
        return self._parse_ternary()

    def _parse_ternary(self) -> Expression:
        """Parse ternary operator: condition ? then_value : else_value"""
        condition = self._parse_or_expr()

        if self._check(TokenType.QUESTION):
            self._advance()  # consume '?'
            then_branch = self._parse_expression()
            self._consume(TokenType.COLON, "Expected ':' in ternary expression")
            else_branch = self._parse_expression()
            return IfExpr(condition=condition, then_branch=then_branch, else_branch=else_branch)

        return condition

    def _parse_or_expr(self) -> Expression:
        left = self._parse_and_expr()

        while self._check(TokenType.OR) or self._check(TokenType.PIPE):
            self._advance()
            right = self._parse_and_expr()
            left = BinaryOp(op="or", left=left, right=right)

        return left

    def _parse_and_expr(self) -> Expression:
        left = self._parse_comparison()

        while self._check(TokenType.AND) or self._check(TokenType.AMPERSAND):
            self._advance()
            right = self._parse_comparison()
            left = BinaryOp(op="and", left=left, right=right)

        return left

    def _parse_comparison(self) -> Expression:
        left = self._parse_additive()

        while self._check(TokenType.EQ) or self._check(TokenType.NE) or \
              self._check(TokenType.LT) or self._check(TokenType.GT) or \
              self._check(TokenType.LE) or self._check(TokenType.GE):
            op = self._advance().value
            right = self._parse_additive()
            left = BinaryOp(op=op, left=left, right=right)

        return left

    def _parse_additive(self) -> Expression:
        left = self._parse_multiplicative()

        while self._check(TokenType.PLUS) or self._check(TokenType.MINUS):
            op = self._advance().value
            right = self._parse_multiplicative()
            left = BinaryOp(op=op, left=left, right=right)

        return left

    def _parse_multiplicative(self) -> Expression:
        left = self._parse_unary()

        while self._check(TokenType.STAR) or self._check(TokenType.SLASH) or self._check(TokenType.PERCENT):
            op = self._advance().value
            right = self._parse_unary()
            left = BinaryOp(op=op, left=left, right=right)

        return left

    def _parse_unary(self) -> Expression:
        if self._check(TokenType.MINUS) or self._check(TokenType.NOT):
            op = self._advance().value
            operand = self._parse_unary()
            return UnaryOp(op=op, operand=operand)

        return self._parse_primary()

    def _parse_primary(self) -> Expression:
        # If expression
        if self._check(TokenType.IF):
            return self._parse_if_expr()

        # Match expression
        if self._check(TokenType.MATCH):
            return self._parse_match_expr()

        # Parenthesized expression
        if self._check(TokenType.LPAREN):
            self._advance()
            expr = self._parse_expression()
            self._consume(TokenType.RPAREN, "Expected ')'")
            return expr

        # Literals
        if self._check(TokenType.NUMBER):
            value = self._advance().value
            return Literal(value=value, dtype="number")

        if self._check(TokenType.STRING):
            value = self._advance().value
            return Literal(value=value, dtype="string")

        if self._check(TokenType.TRUE):
            self._advance()
            return Literal(value=True, dtype="bool")

        if self._check(TokenType.FALSE):
            self._advance()
            return Literal(value=False, dtype="bool")

        # Special handling for variable() and parameter() as function calls
        # These are keywords but can also be used as function names
        if self._check(TokenType.VARIABLE) and self._peek_next_is(TokenType.LPAREN):
            name = self._advance().value  # "variable"
            return self._parse_function_call(name)

        # Special handling for 'parameters' keyword used as variable (e.g., parameters.lifeline.fpg_limit)
        if self._check(TokenType.PARAMETERS) and self._peek_next_is(TokenType.DOT):
            name = self._advance().value  # "parameters"
            # Parse dotted access
            while self._check(TokenType.DOT):
                self._advance()
                if self._check(TokenType.IDENTIFIER):
                    name += "." + self._advance().value
                elif self._check(TokenType.NUMBER):
                    name += "." + str(self._advance().value)
                else:
                    break
            # Check for indexing: parameters.rates[n]
            if self._check(TokenType.LBRACKET):
                self._advance()
                index = self._parse_expression()
                self._consume(TokenType.RBRACKET, "Expected ']'")
                return IndexExpr(base=Identifier(name=name), index=index)
            return Identifier(name=name)

        # Function calls or identifiers
        if self._check(TokenType.IDENTIFIER):
            name = self._advance().value

            # Check for function call
            if self._check(TokenType.LPAREN):
                return self._parse_function_call(name)

            # Check for dotted access (e.g., parameter path)
            while self._check(TokenType.DOT):
                self._advance()
                name += "." + self._consume(TokenType.IDENTIFIER, "Expected identifier").value

                # Check for method call
                if self._check(TokenType.LPAREN):
                    return self._parse_function_call(name)

            # Check for indexing: base[index]
            if self._check(TokenType.LBRACKET):
                self._advance()
                index = self._parse_expression()
                self._consume(TokenType.RBRACKET, "Expected ']'")
                # Return IndexExpr so base is evaluated as variable/expression first
                return IndexExpr(base=Identifier(name=name), index=index)

            return Identifier(name=name)

        raise SyntaxError(f"Unexpected token {self._peek().type} at line {self._peek().line}")

    def _parse_function_call(self, name: str) -> Expression:
        self._consume(TokenType.LPAREN, "Expected '('")

        args = []
        if not self._check(TokenType.RPAREN):
            args.append(self._parse_expression())
            while self._check(TokenType.COMMA):
                self._advance()
                args.append(self._parse_expression())

        self._consume(TokenType.RPAREN, "Expected ')'")

        # Special handling for variable() and parameter()
        if name == "variable":
            if args and isinstance(args[0], Identifier):
                return VariableRef(name=args[0].name)
            elif args and isinstance(args[0], Literal):
                return VariableRef(name=str(args[0].value))

        if name == "parameter":
            if args and isinstance(args[0], Identifier):
                return ParameterRef(path=args[0].name)
            elif args and isinstance(args[0], Literal):
                return ParameterRef(path=str(args[0].value))

        return FunctionCall(name=name, args=args)

    def _parse_if_expr(self) -> IfExpr:
        """Parse if/elif/else expression.

        Supports:
          if cond1: val1 elif cond2: val2 else val3
          if cond1: val1 else val2
        """
        self._consume(TokenType.IF, "Expected 'if'")
        condition = self._parse_expression()
        self._consume(TokenType.COLON, "Expected ':' after if condition")
        then_branch = self._parse_expression()

        # Check for elif chain
        if self._check(TokenType.ELIF):
            # Parse elif as a nested if
            else_branch = self._parse_elif_chain()
        else:
            self._consume(TokenType.ELSE, "Expected 'else'")
            else_branch = self._parse_expression()

        return IfExpr(condition=condition, then_branch=then_branch, else_branch=else_branch)

    def _parse_elif_chain(self) -> IfExpr:
        """Parse elif/else chain as nested IfExpr."""
        self._consume(TokenType.ELIF, "Expected 'elif'")
        condition = self._parse_expression()
        self._consume(TokenType.COLON, "Expected ':' after elif condition")
        then_branch = self._parse_expression()

        # Check for more elif or final else
        if self._check(TokenType.ELIF):
            else_branch = self._parse_elif_chain()
        else:
            self._consume(TokenType.ELSE, "Expected 'else'")
            else_branch = self._parse_expression()

        return IfExpr(condition=condition, then_branch=then_branch, else_branch=else_branch)

    def _parse_match_expr(self) -> MatchExpr:
        self._consume(TokenType.MATCH, "Expected 'match'")

        # Check if matching on a value (match x { ... }) or conditions (match { ... })
        match_value = None
        if not self._check(TokenType.LBRACE):
            match_value = self._parse_expression()

        self._consume(TokenType.LBRACE, "Expected '{'")

        cases = []
        while not self._check(TokenType.RBRACE) and not self._is_at_end():
            if self._check(TokenType.CASE):
                self._advance()
                condition = self._parse_expression()
                self._consume(TokenType.ARROW, "Expected '=>'")
                value = self._parse_expression()
                cases.append(MatchCase(condition=condition, value=value))
            elif self._check(TokenType.ELSE):
                self._advance()
                self._consume(TokenType.ARROW, "Expected '=>'")
                value = self._parse_expression()
                cases.append(MatchCase(condition=None, value=value))
            else:
                break

        self._consume(TokenType.RBRACE, "Expected '}'")
        return MatchExpr(match_value=match_value, cases=cases)

    def _parse_literal_value(self) -> Any:
        if self._check(TokenType.NUMBER):
            return self._advance().value
        if self._check(TokenType.STRING):
            return self._advance().value
        if self._check(TokenType.TRUE):
            self._advance()
            return True
        if self._check(TokenType.FALSE):
            self._advance()
            return False
        if self._check(TokenType.IDENTIFIER):
            return self._advance().value
        return None


def parse_dsl(source: str) -> Module:
    """Parse Cosilico DSL source code into an AST."""
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens, source)
    return parser.parse()


def parse_file(filepath: str) -> Module:
    """Parse a .rac file."""
    with open(filepath, 'r') as f:
        source = f.read()
    return parse_dsl(source)
