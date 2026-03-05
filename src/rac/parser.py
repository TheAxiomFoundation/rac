"""Minimal parser for .rac files (engine format).

Grammar (simplified):
    module      = (entity | definition | amend)*
    entity      = "entity" NAME ":" field*
    field       = NAME ":" type
    definition  = (PATH | NAME) ":" [metadata*] ["entity:" NAME] temporal+
    temporal    = "from" DATE ["to" DATE] ":" expr
    amend       = "amend" PATH ":" temporal+
    expr        = match | cond | or_expr
    match       = "match" expr ":" case+
    case        = pattern "=>" expr
    cond        = "if" expr ":" expr "else:" expr
    or_expr     = and_expr ("or" and_expr)*
    and_expr    = cmp_expr ("and" cmp_expr)*
    cmp_expr    = add_expr (("<" | ">" | "<=" | ">=" | "==" | "!=") add_expr)?
    add_expr    = mul_expr (("+" | "-") mul_expr)*
    mul_expr    = unary (("*" | "/") unary)*
    unary       = "-" unary | "not" unary | call
    call        = primary ("(" args ")")? ("." NAME)*
    primary     = NUMBER | STRING | "true" | "false" | NAME | PATH | "(" expr ")"
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import ast


@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int


class ParseError(Exception):
    def __init__(self, msg: str, line: int, col: int):
        super().__init__(f"line {line}, col {col}: {msg}")
        self.line = line
        self.col = col


class Lexer:
    """Simple lexer for .rac files."""

    KEYWORDS = {
        "entity",
        "amend",
        "from",
        "to",
        "match",
        "if",
        "elif",
        "else",
        "and",
        "or",
        "not",
        "true",
        "false",
    }

    # Map capitalized variants to canonical keyword types
    KEYWORD_ALIASES = {
        "True": "TRUE",
        "False": "FALSE",
    }

    TOKEN_PATTERNS = [
        (re.compile(r"#[^\n]*"), "COMMENT"),
        (re.compile(r"\s+"), "WS"),
        (re.compile(r"\d{4}-\d{2}-\d{2}"), "DATE"),
        (re.compile(r"\d[\d_]*\.\d[\d_]*"), "FLOAT"),
        (re.compile(r"\d[\d_]*"), "INT"),
        (re.compile(r'"[^"]*"'), "STRING"),
        (re.compile(r"'[^']*'"), "STRING"),
        (re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*(/[a-zA-Z_][a-zA-Z0-9_]*)+"), "PATH"),
        (re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*"), "IDENT"),
        (re.compile(r"=>"), "ARROW"),
        (re.compile(r"<="), "LE"),
        (re.compile(r">="), "GE"),
        (re.compile(r"=="), "EQ"),
        (re.compile(r"!="), "NE"),
        (re.compile(r"->"), "FK"),
        (re.compile(r"="), "ASSIGN"),
        (re.compile(r":"), "COLON"),
        (re.compile(r"\+"), "PLUS"),
        (re.compile(r"-"), "MINUS"),
        (re.compile(r"\*"), "STAR"),
        (re.compile(r"/"), "SLASH"),
        (re.compile(r"<"), "LT"),
        (re.compile(r">"), "GT"),
        (re.compile(r"\("), "LPAREN"),
        (re.compile(r"\)"), "RPAREN"),
        (re.compile(r"\["), "LBRACKET"),
        (re.compile(r"\]"), "RBRACKET"),
        (re.compile(r","), "COMMA"),
        (re.compile(r"\."), "DOT"),
    ]

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: list[Token] = []
        self._tokenise()

    def _tokenise(self) -> None:
        while self.pos < len(self.source):
            # Skip triple-quoted text blocks (statute text in v2 .rac files)
            if self.source[self.pos:self.pos + 3] == '"""':
                end = self.source.find('"""', self.pos + 3)
                if end == -1:
                    end = len(self.source)
                else:
                    end += 3
                skipped = self.source[self.pos:end]
                for c in skipped:
                    if c == "\n":
                        self.line += 1
                        self.col = 1
                    else:
                        self.col += 1
                self.pos = end
                continue

            for pattern, ttype in self.TOKEN_PATTERNS:
                m = pattern.match(self.source, self.pos)
                if m:
                    value = m.group(0)
                    if ttype == "WS":
                        for c in value:
                            if c == "\n":
                                self.line += 1
                                self.col = 1
                            else:
                                self.col += 1
                    elif ttype != "COMMENT":
                        if ttype == "IDENT" and value in self.KEYWORDS:
                            ttype = value.upper()
                        elif ttype == "IDENT" and value in self.KEYWORD_ALIASES:
                            ttype = self.KEYWORD_ALIASES[value]
                        self.tokens.append(Token(ttype, value, self.line, self.col))
                        self.col += len(value)
                    self.pos += len(value)
                    break
            else:
                raise ParseError(
                    f"unexpected char: {self.source[self.pos]!r}",
                    self.line,
                    self.col,
                )

        self.tokens.append(Token("EOF", "", self.line, self.col))


class Parser:
    """Recursive descent parser for .rac files."""

    # Metadata field names allowed in definitions (v1 + v2 fields)
    METADATA_FIELDS = {
        "source", "label", "description", "unit",
        "dtype", "period", "default", "indexed_by",
        "status",
    }

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def at(self, *types: str) -> bool:
        return self.peek().type in types

    def consume(self, ttype: str) -> Token:
        tok = self.peek()
        if tok.type != ttype:
            raise ParseError(f"expected {ttype}, got {tok.type}", tok.line, tok.col)
        self.pos += 1
        return tok

    def match(self, *types: str) -> Token | None:
        if self.at(*types):
            tok = self.peek()
            self.pos += 1
            return tok
        return None

    def parse_module(self, path: str = "") -> ast.Module:
        """Parse a complete module."""
        module = ast.Module(path=path)

        while not self.at("EOF"):
            if self.at("ENTITY"):
                module.entities.append(self.parse_entity())
            elif self.at("AMEND"):
                module.amendments.append(self.parse_amend())
            elif self.at("IDENT", "PATH") and self.peek(1).type == "COLON":
                # Skip bare status/metadata declarations (e.g., "status: boilerplate")
                if (
                    self.at("IDENT")
                    and self.peek().value in ("status",)
                    and self.peek(2).type in ("IDENT", "STRING")
                    and self.peek(3).type not in ("COLON",)
                ):
                    self.pos += 3  # skip "status : value"
                    continue
                # Skip enum declarations (e.g., "enum FilingStatus:")
                if self.at("IDENT") and self.peek().value == "enum":
                    while not self.at("EOF") and not (
                        self.at("IDENT", "PATH") and self.peek(1).type == "COLON"
                        and self.peek().value != "enum"
                    ) and not self.at("ENTITY", "AMEND"):
                        self.pos += 1
                    continue
                module.variables.append(self.parse_variable())
            elif self.at("IDENT") and self.peek().value == "enum":
                # Skip enum declarations (e.g., "enum FilingStatus: values: - A - B")
                self.pos += 1  # skip "enum"
                if self.at("IDENT"):
                    self.pos += 1  # skip enum name (e.g., "FilingStatus")
                if self.at("COLON"):
                    self.pos += 1  # skip ":"
                # Skip values list and entries until next real declaration
                while not self.at("EOF"):
                    if self.at("ENTITY", "AMEND"):
                        break
                    if (self.at("IDENT", "PATH") and self.peek(1).type == "COLON"
                        and self.peek().value not in ("values",)):
                        break
                    self.pos += 1
            else:
                tok = self.peek()
                raise ParseError(f"unexpected token: {tok.type}", tok.line, tok.col)

        return module

    def parse_entity(self) -> ast.EntityDecl:
        """Parse entity declaration."""
        self.consume("ENTITY")
        name = self.consume("IDENT").value
        self.consume("COLON")

        fields = []
        foreign_keys = []
        reverse_relations = []

        while self.at("IDENT"):
            field_name = self.consume("IDENT").value
            self.consume("COLON")

            if self.at("FK"):  # foreign key: -> entity
                self.consume("FK")
                target = self.consume("IDENT").value
                foreign_keys.append((field_name, target))
            elif self.at("LBRACKET"):  # reverse relation: [entity]
                self.consume("LBRACKET")
                source_entity = self.consume("IDENT").value
                self.consume("RBRACKET")
                reverse_relations.append((field_name, source_entity, field_name))
            else:
                dtype = self.consume("IDENT").value
                fields.append((field_name, dtype))

        return ast.EntityDecl(
            name=name,
            fields=fields,
            foreign_keys=foreign_keys,
            reverse_relations=reverse_relations,
        )

    def parse_variable(self) -> ast.VariableDecl:
        """Parse definition (parameter or computed value, inferred from fields)."""
        path = self._parse_path()
        self.consume("COLON")

        entity = None
        metadata: dict[str, str] = {}

        # Parse entity and metadata fields (any order, before temporal values)
        while True:
            # Skip 'imports:' blocks (v2 cross-file import lists)
            if self.at("IDENT") and self.peek().value == "imports" and self.peek(1).type == "COLON":
                self.consume("IDENT")  # imports
                self.consume("COLON")
                # Skip import list entries (- path#var). The # makes the var
                # name a comment, so we just skip INT/SLASH/IDENT/PATH tokens.
                while self.at("MINUS"):
                    self.consume("MINUS")
                    # Skip all path tokens (INT, SLASH, IDENT, PATH)
                    while self.at("INT", "SLASH", "IDENT", "PATH"):
                        self.pos += 1
                continue

            if self.at("ENTITY"):
                self.consume("ENTITY")
                self.consume("COLON")
                entity = self.consume("IDENT").value
            elif (
                self.at("IDENT")
                and self.peek().value in self.METADATA_FIELDS
                and self.peek(1).type == "COLON"
            ):
                field_name = self.consume("IDENT").value
                self.consume("COLON")
                tok = self.peek()
                if tok.type == "STRING":
                    value = self.consume("STRING").value[1:-1]  # strip quotes
                elif tok.type in ("IDENT", "INT", "FLOAT"):
                    value = self.consume(tok.type).value
                    # Handle Enum[...] or other bracket-suffixed types
                    if self.at("LBRACKET"):
                        self.consume("LBRACKET")
                        bracket_depth = 1
                        while bracket_depth > 0 and not self.at("EOF"):
                            if self.at("LBRACKET"):
                                bracket_depth += 1
                            elif self.at("RBRACKET"):
                                bracket_depth -= 1
                            self.pos += 1
                elif tok.type == "MINUS" and self.peek(1).type in ("INT", "FLOAT"):
                    self.consume("MINUS")
                    value = "-" + self.consume(self.peek().type).value
                elif tok.type in ("TRUE", "FALSE"):
                    value = self.consume(tok.type).value
                else:
                    # Skip unknown metadata value format
                    value = ""
                    while not self.at("FROM", "IDENT", "PATH", "EOF", "ENTITY", "AMEND"):
                        self.pos += 1
                metadata[field_name] = value
            else:
                break

        values = self._parse_temporal_values()
        return ast.VariableDecl(path=path, entity=entity, values=values, **metadata)

    def parse_amend(self) -> ast.AmendDecl:
        """Parse amendment declaration."""
        self.consume("AMEND")
        target = self._parse_path()
        self.consume("COLON")
        values = self._parse_temporal_values()
        return ast.AmendDecl(target=target, values=values)

    def _parse_path(self) -> str:
        """Parse a path (either PATH token or IDENT)."""
        if self.at("PATH"):
            return self.consume("PATH").value
        return self.consume("IDENT").value

    def _parse_temporal_values(self) -> list[ast.TemporalValue]:
        """Parse temporal value blocks."""
        values = []

        while self.at("FROM"):
            self.consume("FROM")
            start = self._parse_date()
            end = None
            if self.at("TO"):
                self.consume("TO")
                end = self._parse_date()
            self.consume("COLON")
            expr = self.parse_expr()
            values.append(ast.TemporalValue(start=start, end=end, expr=expr))

        return values

    def _parse_date(self) -> date:
        tok = self.consume("DATE")
        return date.fromisoformat(tok.value)

    def parse_expr(self) -> ast.Expr:
        """Parse expression, including let-bindings (name = value then body)."""
        # Check for let-binding: IDENT ASSIGN ...
        if (
            self.at("IDENT")
            and self.peek(1).type == "ASSIGN"
            # Make sure this isn't at the top level (metadata like `label = ...`)
            # by checking the IDENT isn't a metadata field followed by COLON
        ):
            name = self.consume("IDENT").value
            self.consume("ASSIGN")
            value = self._parse_single_expr()
            body = self.parse_expr()
            return ast.Let(name=name, value=value, body=body)
        return self._parse_single_expr()

    def _parse_single_expr(self) -> ast.Expr:
        """Parse a single expression (non-let)."""
        if self.at("MATCH"):
            return self.parse_match()
        if self.at("IF"):
            return self.parse_cond()
        return self.parse_or()

    def parse_match(self) -> ast.Match:
        """Parse match expression."""
        self.consume("MATCH")
        subject = self.parse_or()
        self.consume("COLON")

        cases = []

        while self.at("STRING", "INT", "FLOAT", "TRUE", "FALSE", "IDENT"):
            pattern = self.parse_primary()
            self.consume("ARROW")
            result = self.parse_expr()
            cases.append((pattern, result))

        return ast.Match(subject=subject, cases=cases, default=None)

    def parse_cond(self) -> ast.Cond:
        """Parse conditional expression: if COND: EXPR (elif COND: EXPR)* else: EXPR."""
        self.consume("IF")
        condition = self.parse_or()
        self.consume("COLON")
        then_expr = self._parse_single_expr()
        if self.match("ELIF"):
            elif_cond = self.parse_or()
            self.consume("COLON")
            elif_then = self._parse_single_expr()
            else_expr = self._parse_elif_chain(elif_cond, elif_then)
        else:
            self.consume("ELSE")
            self.consume("COLON")
            else_expr = self._parse_single_expr()
        return ast.Cond(condition=condition, then_expr=then_expr, else_expr=else_expr)

    def _parse_elif_chain(self, cond: ast.Expr, then_expr: ast.Expr) -> ast.Cond:
        """Parse remaining elif/else chain into nested Cond nodes."""
        if self.match("ELIF"):
            next_cond = self.parse_or()
            self.consume("COLON")
            next_then = self._parse_single_expr()
            else_expr = self._parse_elif_chain(next_cond, next_then)
        else:
            self.consume("ELSE")
            self.consume("COLON")
            else_expr = self._parse_single_expr()
        return ast.Cond(condition=cond, then_expr=then_expr, else_expr=else_expr)

    def parse_or(self) -> ast.Expr:
        left = self.parse_and()
        while self.match("OR"):
            right = self.parse_and()
            left = ast.BinOp(op="or", left=left, right=right)
        return left

    def parse_and(self) -> ast.Expr:
        left = self.parse_cmp()
        while self.match("AND"):
            right = self.parse_cmp()
            left = ast.BinOp(op="and", left=left, right=right)
        return left

    def parse_cmp(self) -> ast.Expr:
        left = self.parse_add()
        op_map = {
            "LT": "<",
            "GT": ">",
            "LE": "<=",
            "GE": ">=",
            "EQ": "==",
            "NE": "!=",
        }
        if tok := self.match("LT", "GT", "LE", "GE", "EQ", "NE"):
            right = self.parse_add()
            return ast.BinOp(op=op_map[tok.type], left=left, right=right)
        return left

    def parse_add(self) -> ast.Expr:
        left = self.parse_mul()
        op_map = {"PLUS": "+", "MINUS": "-"}
        while tok := self.match("PLUS", "MINUS"):
            right = self.parse_mul()
            left = ast.BinOp(op=op_map[tok.type], left=left, right=right)
        return left

    def parse_mul(self) -> ast.Expr:
        left = self.parse_unary()
        op_map = {"STAR": "*", "SLASH": "/"}
        while tok := self.match("STAR", "SLASH"):
            right = self.parse_unary()
            left = ast.BinOp(op=op_map[tok.type], left=left, right=right)
        return left

    def parse_unary(self) -> ast.Expr:
        if self.match("MINUS"):
            return ast.UnaryOp(op="-", operand=self.parse_unary())
        if self.match("NOT"):
            return ast.UnaryOp(op="not", operand=self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self) -> ast.Expr:
        """Parse postfix operations (function calls, field access)."""
        expr = self.parse_primary()

        while True:
            if self.at("LPAREN"):
                if not isinstance(expr, ast.Var):
                    tok = self.peek()
                    raise ParseError("can only call named functions", tok.line, tok.col)
                self.consume("LPAREN")
                args = []
                if not self.at("RPAREN"):
                    args.append(self.parse_expr())
                    while self.at("COMMA"):
                        self.consume("COMMA")
                        args.append(self.parse_expr())
                self.consume("RPAREN")
                expr = ast.Call(func=expr.path, args=args)
            elif self.at("DOT"):
                self.consume("DOT")
                fld = self.consume("IDENT").value
                expr = ast.FieldAccess(obj=expr, field=fld)
            else:
                break

        return expr

    def parse_primary(self) -> ast.Expr:
        """Parse primary expression."""
        if self.at("INT"):
            return ast.Literal(value=int(self.consume("INT").value.replace("_", "")))
        if self.at("FLOAT"):
            return ast.Literal(value=float(self.consume("FLOAT").value.replace("_", "")))
        if self.at("STRING"):
            return ast.Literal(value=self.consume("STRING").value[1:-1])
        if self.match("TRUE"):
            return ast.Literal(value=True)
        if self.match("FALSE"):
            return ast.Literal(value=False)
        if tok := self.match("PATH", "IDENT"):
            return ast.Var(path=tok.value)
        if self.match("LPAREN"):
            expr = self.parse_expr()
            self.consume("RPAREN")
            return expr

        tok = self.peek()
        raise ParseError(
            f"unexpected token in expression: {tok.type}", tok.line, tok.col
        )


def parse(source: str, path: str = "") -> ast.Module:
    """Parse .rac source code into an AST."""
    lexer = Lexer(source)
    parser = Parser(lexer.tokens)
    return parser.parse_module(path)


def parse_file(filepath: str | Path) -> ast.Module:
    """Parse a .rac file."""
    filepath = Path(filepath)
    source = filepath.read_text()
    return parse(source, str(filepath))
