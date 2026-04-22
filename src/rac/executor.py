"""Executor: evaluates compiled IR against input data."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from . import ast
from .compiler import IR
from .schema import Data, Schema


class ExecutionError(Exception):
    pass


class Context(BaseModel):
    """Runtime context for evaluation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: Data
    schema_: Schema | None = None
    computed: dict[str, Any] = {}
    current_row: dict | None = None
    current_entity: str | None = None

    def get(self, path: str) -> Any:
        if path in self.computed:
            return self.computed[path]
        if self.current_row and path in self.current_row:
            return self.current_row[path]
        # Reverse-relation access: `members` on a household row returns the
        # list of related child rows, each already augmented with their
        # computed columns so downstream FieldAccess sees them.
        related = self._resolve_reverse_relation(path)
        if related is not None:
            return related
        raise ExecutionError(f"undefined: {path}")

    def _resolve_reverse_relation(self, path: str) -> list[dict] | None:
        if (
            self.schema_ is None
            or self.current_entity is None
            or self.current_row is None
        ):
            return None
        entity = self.schema_.entities.get(self.current_entity)
        if entity is None or path not in entity.reverse_relations:
            return None
        rel = entity.reverse_relations[path]
        pk = self.current_row.get("id")
        return self.data.get_related(rel.source, rel.source_field, pk)

    def get_related(self, entity: str, fk_field: str) -> list[dict]:
        if self.current_row is None:
            raise ExecutionError("no current row for relation lookup")
        pk = self.current_row.get("id")
        return self.data.get_related(entity, fk_field, pk)

    def get_fk_target(self, fk_value: Any, target_entity: str) -> dict | None:
        return self.data.get_row(target_entity, fk_value)

    def resolve_fk(self, field_name: str) -> dict | None:
        """Dereference a foreign-key field on the current entity to its target row."""
        if (
            self.schema_ is None
            or self.current_entity is None
            or self.current_row is None
        ):
            return None
        entity = self.schema_.entities.get(self.current_entity)
        if entity is None or field_name not in entity.foreign_keys:
            return None
        fk = entity.foreign_keys[field_name]
        pk_val = self.current_row.get(field_name)
        if pk_val is None:
            return None
        return self.data.get_row(fk.target, pk_val)


BUILTINS = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "sum": sum,
    "len": len,
    "clip": lambda x, lo, hi: max(lo, min(hi, x)),
    "any": any,
    "all": all,
}


def evaluate(expr: ast.Expr, ctx: Context) -> Any:
    """Evaluate an expression in context."""
    match expr:
        case ast.Literal(value=v):
            return v

        case ast.Var(path=path):
            return ctx.get(path)

        case ast.BinOp(op=op, left=left, right=right):
            left_val = evaluate(left, ctx)
            right_val = evaluate(right, ctx)
            match op:
                case "+":
                    return left_val + right_val
                case "-":
                    return left_val - right_val
                case "*":
                    return left_val * right_val
                case "/":
                    return left_val / right_val if right_val != 0 else 0
                case "<":
                    return left_val < right_val
                case ">":
                    return left_val > right_val
                case "<=":
                    return left_val <= right_val
                case ">=":
                    return left_val >= right_val
                case "==":
                    return left_val == right_val
                case "!=":
                    return left_val != right_val
                case "and":
                    return left_val and right_val
                case "or":
                    return left_val or right_val
                case _:
                    raise ExecutionError(f"unknown op: {op}")

        case ast.UnaryOp(op=op, operand=operand):
            v = evaluate(operand, ctx)
            match op:
                case "-":
                    return -v
                case "not":
                    return not v
                case _:
                    raise ExecutionError(f"unknown unary op: {op}")

        case ast.Call(func=func, args=args):
            if func not in BUILTINS:
                raise ExecutionError(f"unknown function: {func}")
            arg_vals = [evaluate(a, ctx) for a in args]
            return BUILTINS[func](*arg_vals)

        case ast.FieldAccess(obj=obj, field=fld):
            # FK forward access: `household.size` on a person row resolves
            # the FK field to the target row, then reads the field from it.
            if isinstance(obj, ast.Var):
                target_row = ctx.resolve_fk(obj.path)
                if target_row is not None:
                    return target_row.get(fld)
            o = evaluate(obj, ctx)
            if isinstance(o, dict):
                return o.get(fld)
            if isinstance(o, list):
                return [
                    item.get(fld) if isinstance(item, dict) else getattr(item, fld) for item in o
                ]
            return getattr(o, fld)

        case ast.Match(subject=subject, cases=cases, default=default):
            val = evaluate(subject, ctx)
            for pattern, result in cases:
                pattern_val = evaluate(pattern, ctx)
                if val == pattern_val:
                    return evaluate(result, ctx)
            if default:
                return evaluate(default, ctx)
            raise ExecutionError(f"no match for: {val}")

        case ast.Cond(condition=cond, then_expr=then_e, else_expr=else_e):
            if evaluate(cond, ctx):
                return evaluate(then_e, ctx)
            return evaluate(else_e, ctx)

        case ast.Let(name=name, value=value, body=body):
            val = evaluate(value, ctx)
            ctx.computed[name] = val
            result = evaluate(body, ctx)
            return result

        case _:
            raise ExecutionError(f"unknown expr type: {type(expr)}")


class Result(BaseModel):
    """Execution result.

    Attributes:
        scalars: Computed scalar variables keyed by path.
        entities: Per-entity computed columns: ``entities[entity][path]``
            is the list of per-row values.
        citations: Maps each computed variable path to its statutory
            citation string (``source`` metadata on the declaration), if
            one was provided. Variables with no citation are omitted.
            See ``docs/citations.md`` for the propagation contract.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    scalars: dict[str, Any]
    entities: dict[str, dict[str, list[Any]]]
    citations: dict[str, str] = {}


class Executor:
    """Executes compiled IR against data."""

    def __init__(self, ir: IR):
        self.ir = ir

    def execute(self, data: Data) -> Result:
        # Shallow-copy the rows so we can write computed columns back into
        # each row. That way, when a parent entity asks for its related
        # children via a reverse relation, it sees the augmented rows
        # (input fields plus already-computed per-row variables).
        working = Data(
            tables={
                name: [dict(row) for row in rows]
                for name, rows in data.tables.items()
            }
        )
        ctx = Context(data=working, schema_=self.ir.schema_)
        entities: dict[str, dict[str, list[Any]]] = {}
        citations: dict[str, str] = {}

        for path in self.ir.order:
            var = self.ir.variables[path]

            # Propagate citation metadata onto the result envelope. Only
            # variables that carry a ``source`` (statutory citation) are
            # emitted; unannotated paths are omitted to keep the map tight.
            if getattr(var, "source", None):
                citations[path] = var.source

            if var.entity is None:
                ctx.computed[path] = evaluate(var.expr, ctx)
            else:
                entity_name = var.entity
                rows = working.get_rows(entity_name)

                if entity_name not in entities:
                    entities[entity_name] = {}
                entities[entity_name][path] = []

                for row in rows:
                    ctx.current_row = row
                    ctx.current_entity = entity_name
                    val = evaluate(var.expr, ctx)
                    entities[entity_name][path].append(val)
                    row[path] = val
                    ctx.current_row = None
                    ctx.current_entity = None

        return Result(scalars=ctx.computed, entities=entities, citations=citations)


def run(ir: IR, data: Data | dict[str, list[dict]]) -> Result:
    """Execute IR against data."""
    if isinstance(data, dict):
        data = Data(tables=data)
    return Executor(ir).execute(data)
