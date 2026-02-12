"""Minimal parser for .rac files (engine format).

Grammar (simplified):
    module      = (entity | variable | amend)*
    entity      = "entity" NAME ":" field*
    field       = NAME ":" type
    variable    = "variable" PATH ":" ["entity:" NAME] temporal+
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
        "variable",
        "amend",
        "from",
        "to",
        "match",
        "if",
        "else",
        "and",
        "or",
        "not",
        "true",
        "false",
    }

    TOKEN_PATTERNS = [
        (r"#[^\n]*", "COMMENT"),
        (r"\s+", "WS"),
        (r"\d{4}-\d{2}-\d{2}", "DATE"),
        (r"\d+\.\d+", "FLOAT"),
        (r"\d+", "INT"),
        (r'"[^"]*"', "STRING"),
        (r"'[^']*'", "STRING"),
        (r"[a-zA-Z_][a-zA-Z0-9_]*(/[a-zA-Z_][a-zA-Z0-9_]*)+", "PATH"),
        (r"[a-zA-Z_][a-zA-Z0-9_]*", "IDENT"),
        (r"=>", "ARROW"),
        (r"<=", "LE"),
        (r">=", "GE"),
        (r"==", "EQ"),
        (r"!=", "NE"),
        (r"->", "FK"),
        (r":", "COLON"),
        (r"\+", "PLUS"),
        (r"-", "MINUS"),
        (r"\*", "STAR"),
        (r"/", "SLASH"),
        (r"<", "LT"),
        (r">", "GT"),
        (r"\(", "LPAREN"),
        (r"\)", "RPAREN"),
        (r"\[", "LBRACKET"),
        (r"\]", "RBRACKET"),
        (r",", "COMMA"),
        (r"\.", "DOT"),
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
            matched = False
            for pattern, ttype in self.TOKEN_PATTERNS:
                m = re.match(pattern, self.source[self.pos :])
                if m:
                    value = m.group(0)
                    if ttype == "WS":
                        for c in value:
                            if c == "\n":
                                self.line += 1
                                self.col = 1
                            else:
                                self.col += 1
                    elif ttype == "COMMENT":
                        pass  # skip comments
                    else:
                        if ttype == "IDENT" and value in self.KEYWORDS:
                            ttype = value.upper()
                        self.tokens.append(Token(ttype, value, self.line, self.col))
                        self.col += len(value)
                    self.pos += len(value)
                    matched = True
                    break

            if not matched:
                raise ParseError(f"unexpected char: {self.source[self.pos]!r}", self.line, self.col)

        self.tokens.append(Token("EOF", "", self.line, self.col))


class Parser:
    """Recursive descent parser for .rac files."""

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
            elif self.at("VARIABLE"):
                module.variables.append(self.parse_variable())
            elif self.at("AMEND"):
                module.amendments.append(self.parse_amend())
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
        relations = []

        while self.at("IDENT"):
            field_name = self.consume("IDENT").value
            self.consume("COLON")

            if self.at("FK"):  # foreign key: -> entity
                self.consume("FK")
                target = self.consume("IDENT").value
                relations.append((field_name, target, False))
            elif self.at("LBRACKET"):  # reverse relation: [entity]
                self.consume("LBRACKET")
                target = self.consume("IDENT").value
                self.consume("RBRACKET")
                relations.append((field_name, target, True))
            else:
                dtype = self.consume("IDENT").value
                fields.append((field_name, dtype))

        return ast.EntityDecl(name=name, fields=fields, relations=relations)

    def parse_variable(self) -> ast.VariableDecl:
        """Parse variable declaration."""
        self.consume("VARIABLE")
        path = self._parse_path()
        self.consume("COLON")

        entity = None
        if self.at("ENTITY"):
            self.consume("ENTITY")
            self.consume("COLON")
            entity = self.consume("IDENT").value

        values = self._parse_temporal_values()
        return ast.VariableDecl(path=path, entity=entity, values=values)

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
        """Parse expression."""
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
        """Parse conditional expression."""
        self.consume("IF")
        condition = self.parse_or()
        self.consume("COLON")
        then_expr = self.parse_expr()
        self.consume("ELSE")
        self.consume("COLON")
        else_expr = self.parse_expr()
        return ast.Cond(condition=condition, then_expr=then_expr, else_expr=else_expr)

    def parse_or(self) -> ast.Expr:
        left = self.parse_and()
        while self.at("OR"):
            self.consume("OR")
            right = self.parse_and()
            left = ast.BinOp(op="or", left=left, right=right)
        return left

    def parse_and(self) -> ast.Expr:
        left = self.parse_cmp()
        while self.at("AND"):
            self.consume("AND")
            right = self.parse_cmp()
            left = ast.BinOp(op="and", left=left, right=right)
        return left

    def parse_cmp(self) -> ast.Expr:
        left = self.parse_add()
        if self.at("LT", "GT", "LE", "GE", "EQ", "NE"):
            op_map = {"LT": "<", "GT": ">", "LE": "<=", "GE": ">=", "EQ": "==", "NE": "!="}
            tok = self.match("LT", "GT", "LE", "GE", "EQ", "NE")
            right = self.parse_add()
            return ast.BinOp(op=op_map[tok.type], left=left, right=right)
        return left

    def parse_add(self) -> ast.Expr:
        left = self.parse_mul()
        while self.at("PLUS", "MINUS"):
            op = "+" if self.match("PLUS") else (self.consume("MINUS"), "-")[1]
            right = self.parse_mul()
            left = ast.BinOp(op=op, left=left, right=right)
        return left

    def parse_mul(self) -> ast.Expr:
        left = self.parse_unary()
        while self.at("STAR", "SLASH"):
            op = "*" if self.match("STAR") else (self.consume("SLASH"), "/")[1]
            right = self.parse_unary()
            left = ast.BinOp(op=op, left=left, right=right)
        return left

    def parse_unary(self) -> ast.Expr:
        if self.at("MINUS"):
            self.consume("MINUS")
            return ast.UnaryOp(op="-", operand=self.parse_unary())
        if self.at("NOT"):
            self.consume("NOT")
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
            return ast.Literal(value=int(self.consume("INT").value))
        if self.at("FLOAT"):
            return ast.Literal(value=float(self.consume("FLOAT").value))
        if self.at("STRING"):
            val = self.consume("STRING").value
            return ast.Literal(value=val[1:-1])  # strip quotes
        if self.at("TRUE"):
            self.consume("TRUE")
            return ast.Literal(value=True)
        if self.at("FALSE"):
            self.consume("FALSE")
            return ast.Literal(value=False)
        if self.at("PATH"):
            return ast.Var(path=self.consume("PATH").value)
        if self.at("IDENT"):
            return ast.Var(path=self.consume("IDENT").value)
        if self.at("LPAREN"):
            self.consume("LPAREN")
            expr = self.parse_expr()
            self.consume("RPAREN")
            return expr

        tok = self.peek()
        raise ParseError(f"unexpected token in expression: {tok.type}", tok.line, tok.col)


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
