"""AST nodes for the RAC engine."""

from datetime import date
from typing import Annotated, Any
from typing import Literal as TypingLiteral

from pydantic import BaseModel, Field


# Expressions - using discriminated union for type safety
class Literal(BaseModel):
    type: TypingLiteral["literal"] = "literal"
    value: Any  # int, float, str, bool


class Var(BaseModel):
    """Variable reference (e.g., 'age' or 'gov/irs/standard_deduction')."""

    type: TypingLiteral["var"] = "var"
    path: str


class BinOp(BaseModel):
    type: TypingLiteral["binop"] = "binop"
    op: str  # +, -, *, /, >, <, >=, <=, ==, !=, and, or
    left: "Expr"
    right: "Expr"


class UnaryOp(BaseModel):
    type: TypingLiteral["unaryop"] = "unaryop"
    op: str  # -, not
    operand: "Expr"


class Call(BaseModel):
    """Function call (e.g., max(0, x), sum(members.income))."""

    type: TypingLiteral["call"] = "call"
    func: str
    args: list["Expr"]


class FieldAccess(BaseModel):
    """Field access on entity (e.g., members.income)."""

    type: TypingLiteral["field_access"] = "field_access"
    obj: "Expr"
    field: str


class Match(BaseModel):
    """Match expression."""

    type: TypingLiteral["match"] = "match"
    subject: "Expr"
    cases: list[tuple["Expr", "Expr"]]  # [(pattern, result), ...]
    default: "Expr | None" = None


class Cond(BaseModel):
    """Conditional expression (if/else)."""

    type: TypingLiteral["cond"] = "cond"
    condition: "Expr"
    then_expr: "Expr"
    else_expr: "Expr"


# Expression union type
Expr = Annotated[
    Literal | Var | BinOp | UnaryOp | Call | FieldAccess | Match | Cond,
    Field(discriminator="type"),
]


# Declarations
class TemporalValue(BaseModel):
    """A value with temporal bounds."""

    start: date
    end: date | None = None  # None = no end
    expr: Expr


class VariableDecl(BaseModel):
    """Variable declaration."""

    path: str  # e.g., gov/irs/standard_deduction
    entity: str | None = None  # entity this applies to, or None for scalar
    values: list[TemporalValue] = []


class AmendDecl(BaseModel):
    """Amendment to an existing variable.

    Amendments can:
    - Add new temporal periods
    - Override existing periods (later amendments win)
    - Completely replace a variable's formula

    This mirrors how legislation works: new laws amend existing statutes.
    """

    target: str  # path of variable being amended
    values: list[TemporalValue] = []
    replace: bool = False  # if True, completely replaces (not merges) temporal values


class RepealDecl(BaseModel):
    """Repeal an existing variable (makes it undefined after a date)."""

    target: str
    effective: date


class EntityDecl(BaseModel):
    """Entity type declaration."""

    name: str
    fields: list[tuple[str, str]] = []  # [(name, type), ...]
    foreign_keys: list[tuple[str, str]] = []  # [(field_name, target_entity), ...]
    reverse_relations: list[tuple[str, str, str]] = []  # [(name, source, source_field), ...]


class ImportDecl(BaseModel):
    """Import another module."""

    path: str  # module path to import


class Module(BaseModel):
    """A parsed .rac file."""

    path: str = ""  # file path
    imports: list[ImportDecl] = []
    entities: list[EntityDecl] = []
    variables: list[VariableDecl] = []
    amendments: list[AmendDecl] = []
    repeals: list[RepealDecl] = []


# Rebuild models for forward references
BinOp.model_rebuild()
UnaryOp.model_rebuild()
Call.model_rebuild()
FieldAccess.model_rebuild()
Match.model_rebuild()
Cond.model_rebuild()
TemporalValue.model_rebuild()
