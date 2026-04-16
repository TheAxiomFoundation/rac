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


class Let(BaseModel):
    """Let-binding: introduces a named value for use in a body expression.

    Surface syntax (see docs/RAC_SPEC.md, "Expression syntax"):

        name = value_expr
        body_expr

    Semantics:
        1. ``value`` is evaluated first, in the surrounding environment
           (``name`` is NOT yet in scope, so a Let cannot reference itself).
        2. The resulting value is bound to ``name`` in the evaluation
           context.
        3. ``body`` is evaluated with ``name`` in scope and the Let node's
           result is the result of ``body``.

    Scope: the binding is visible throughout ``body``, including nested
    Let-bindings. Nested Lets with the same ``name`` shadow the outer
    binding for the duration of the inner body. In the current Python
    executor the binding is written into the shared ``Context.computed``
    dict, which means names leak after the Let body completes; callers
    should treat Let as block-scoped and avoid relying on that leakage.

    Evaluation order is strictly: value, then body. ``value`` is evaluated
    exactly once per Let encounter (no lazy / call-by-name semantics).

    Let is produced by :meth:`rac.parser.Parser.parse_expr` when it sees
    the ``name = expr`` surface syntax; there is no ``let`` keyword in
    the grammar.
    """

    type: TypingLiteral["let"] = "let"
    name: str
    value: "Expr"
    body: "Expr"


# Expression union type
Expr = Annotated[
    Literal | Var | BinOp | UnaryOp | Call | FieldAccess | Match | Cond | Let,
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
    source: str | None = None  # statutory citation (e.g., "26 USC 32")
    label: str | None = None  # human-readable display name
    description: str | None = None  # longer explanation
    unit: str | None = None  # currency/type hint (e.g., "USD", "percent")
    default: str | None = None  # default value for input variables
    values: list[TemporalValue] = []


class AmendDecl(BaseModel):
    """Amendment to an existing variable.

    Amendments can:
    - Add new temporal periods
    - Override existing periods (later amendments win)
    - Completely replace a variable's formula
    - Supply an updated citation that overrides the underlying statute's
      ``source`` (e.g., a publication-tier amendment pointing at a
      Revenue Procedure rather than the statutory section).

    This mirrors how legislation works: new laws amend existing statutes.
    """

    target: str  # path of variable being amended
    source: str | None = None  # updated citation; overrides the layer's source when set
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
Let.model_rebuild()
TemporalValue.model_rebuild()
