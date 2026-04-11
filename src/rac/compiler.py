"""Compiler: resolves temporal layers and produces IR for backends.

Takes parsed modules and an as_of date, resolves which temporal values apply,
and produces a flat variable graph.
"""

from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, ConfigDict

from . import ast
from .schema import Entity, Field, ForeignKey, ReverseRelation, Schema


class ResolvedVar(BaseModel):
    """A variable resolved to a single expression for a point in time."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: str
    entity: str | None = None
    source: str | None = None
    source_tier: str | None = None
    priority: int = 0
    label: str | None = None
    description: str | None = None
    unit: str | None = None
    dtype: str | None = None
    period: str | None = None
    indexed_by: str | None = None
    status: str | None = None
    expr: ast.Expr
    deps: set[str] = set()


class IR(BaseModel):
    """Intermediate representation: resolved variable graph + schema."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_: Schema
    variables: dict[str, ResolvedVar]
    order: list[str]  # topologically sorted variable paths


class CompileError(Exception):
    pass


SOURCE_TIER_RANKS = {
    "statute": 0,
    "projection": 10,
    "amendment": 20,
    "legislation": 30,
    "publication": 40,
}


def source_tier_rank(source_tier: str | None) -> int:
    if source_tier is None:
        return SOURCE_TIER_RANKS["amendment"]
    return SOURCE_TIER_RANKS.get(source_tier, SOURCE_TIER_RANKS["amendment"])


@dataclass
class LayerValue:
    temporal: ast.TemporalValue
    order: int
    source: str | None = None
    source_tier: str | None = None
    priority: int = 0
    label: str | None = None
    description: str | None = None
    unit: str | None = None
    dtype: str | None = None
    period: str | None = None
    indexed_by: str | None = None
    status: str | None = None

    def applies(self, as_of: date) -> bool:
        return self.temporal.start <= as_of and (
            self.temporal.end is None or as_of <= self.temporal.end
        )

    def precedence(self) -> tuple[int, int, int]:
        return (self.priority, source_tier_rank(self.source_tier), self.order)


@dataclass
class ResolvedLayer:
    expr: ast.Expr
    source: str | None
    source_tier: str | None
    priority: int
    label: str | None
    description: str | None
    unit: str | None
    dtype: str | None
    period: str | None
    indexed_by: str | None
    status: str | None


class TemporalLayer:
    """Tracks temporal values for a variable, with amendment stacking."""

    def __init__(
        self,
        path: str,
        entity: str | None = None,
        source: str | None = None,
        source_tier: str | None = "statute",
        label: str | None = None,
        description: str | None = None,
        unit: str | None = None,
        dtype: str | None = None,
        period: str | None = None,
        indexed_by: str | None = None,
        status: str | None = None,
        has_base_definition: bool = False,
    ):
        self.path = path
        self.entity = entity
        self.source = source
        self.source_tier = source_tier
        self.label = label
        self.description = description
        self.unit = unit
        self.dtype = dtype
        self.period = period
        self.indexed_by = indexed_by
        self.status = status
        self.has_base_definition = has_base_definition
        self.values: list[LayerValue] = []
        self.repealed_after: date | None = None
        self._next_order = 0

    def add_values(
        self,
        values: list[ast.TemporalValue],
        replace: bool = False,
        *,
        source: str | None = None,
        source_tier: str | None = None,
        priority: int = 0,
        label: str | None = None,
        description: str | None = None,
        unit: str | None = None,
        dtype: str | None = None,
        period: str | None = None,
        indexed_by: str | None = None,
        status: str | None = None,
    ) -> None:
        if replace:
            self.values = []
        for temporal in values:
            self.values.append(
                LayerValue(
                    temporal=temporal,
                    order=self._next_order,
                    source=source,
                    source_tier=source_tier,
                    priority=priority,
                    label=label,
                    description=description,
                    unit=unit,
                    dtype=dtype,
                    period=period,
                    indexed_by=indexed_by,
                    status=status,
                )
            )
            self._next_order += 1

    def repeal(self, effective: date) -> None:
        self.repealed_after = effective

    def resolve(self, as_of: date) -> ResolvedLayer | None:
        """Get the applicable value for a date using explicit precedence rules."""
        if self.repealed_after and as_of >= self.repealed_after:
            return None

        applicable = [value for value in self.values if value.applies(as_of)]
        if not applicable:
            return None

        winner = max(applicable, key=lambda value: value.precedence())
        return ResolvedLayer(
            expr=winner.temporal.expr,
            source=winner.source if winner.source is not None else self.source,
            source_tier=winner.source_tier if winner.source_tier is not None else self.source_tier,
            priority=winner.priority,
            label=winner.label if winner.label is not None else self.label,
            description=winner.description if winner.description is not None else self.description,
            unit=winner.unit if winner.unit is not None else self.unit,
            dtype=winner.dtype if winner.dtype is not None else self.dtype,
            period=winner.period if winner.period is not None else self.period,
            indexed_by=winner.indexed_by if winner.indexed_by is not None else self.indexed_by,
            status=winner.status if winner.status is not None else self.status,
        )


class Compiler:
    """Compiles parsed modules into IR."""

    def __init__(self, modules: list[ast.Module]):
        self.modules = modules
        self.schema = Schema()
        self.layers: dict[str, TemporalLayer] = {}

    def compile(self, as_of: date) -> IR:
        for module in self.modules:
            self._collect_entities(module)
            self._collect_variables(module)
            self._apply_amendments(module)
            self._apply_repeals(module)

        self.schema.infer_reverse_relations()
        resolved = self._resolve_temporal(as_of)

        for var in resolved.values():
            self._walk_deps(var.expr, var.deps)

        order = self._topo_sort(resolved)

        return IR(schema_=self.schema, variables=resolved, order=order)

    def _collect_entities(self, module: ast.Module) -> None:
        for decl in module.entities:
            entity = Entity(name=decl.name)
            for name, dtype in decl.fields:
                entity.fields[name] = Field(name=name, dtype=dtype)
            for name, target in decl.foreign_keys:
                entity.foreign_keys[name] = ForeignKey(name=name, target=target)
            for name, source, source_field in decl.reverse_relations:
                entity.reverse_relations[name] = ReverseRelation(
                    name=name, source=source, source_field=source_field
                )
            self.schema.add_entity(entity)

    def _collect_variables(self, module: ast.Module) -> None:
        for decl in module.variables:
            layer = self.layers.get(decl.path)
            if layer is not None and layer.has_base_definition:
                raise CompileError(f"duplicate variable: {decl.path}")
            if layer is None:
                layer = TemporalLayer(
                    decl.path,
                    entity=decl.entity,
                    source=decl.source,
                    source_tier="statute",
                    label=decl.label,
                    description=decl.description,
                    unit=decl.unit,
                    dtype=decl.dtype,
                    period=decl.period,
                    indexed_by=decl.indexed_by,
                    status=decl.status,
                    has_base_definition=True,
                )
                self.layers[decl.path] = layer
            else:
                layer.entity = decl.entity
                layer.source = decl.source
                layer.source_tier = "statute"
                layer.label = decl.label
                layer.description = decl.description
                layer.unit = decl.unit
                layer.dtype = decl.dtype
                layer.period = decl.period
                layer.indexed_by = decl.indexed_by
                layer.status = decl.status
                layer.has_base_definition = True
            layer.add_values(
                decl.values,
                source=decl.source,
                source_tier="statute",
                label=decl.label,
                description=decl.description,
                unit=decl.unit,
                dtype=decl.dtype,
                period=decl.period,
                indexed_by=decl.indexed_by,
                status=decl.status,
            )

    def _apply_amendments(self, module: ast.Module) -> None:
        for amend in module.amendments:
            if amend.target not in self.layers:
                self.layers[amend.target] = TemporalLayer(
                    amend.target,
                    source=amend.source,
                    source_tier=amend.source_tier or "amendment",
                    has_base_definition=False,
                )
            self.layers[amend.target].add_values(
                amend.values,
                replace=amend.replace,
                source=amend.source,
                source_tier=amend.source_tier or "amendment",
                priority=amend.priority,
            )

    def _apply_repeals(self, module: ast.Module) -> None:
        for repeal in module.repeals:
            if repeal.target in self.layers:
                self.layers[repeal.target].repeal(repeal.effective)

    def _resolve_temporal(self, as_of: date) -> dict[str, ResolvedVar]:
        resolved = {}
        for path, layer in self.layers.items():
            current = layer.resolve(as_of)
            if current is not None:
                resolved[path] = ResolvedVar(
                    path=path,
                    entity=layer.entity,
                    source=current.source,
                    source_tier=current.source_tier,
                    priority=current.priority,
                    label=current.label,
                    description=current.description,
                    unit=current.unit,
                    dtype=current.dtype,
                    period=current.period,
                    indexed_by=current.indexed_by,
                    status=current.status,
                    expr=current.expr,
                )
        return resolved

    def _walk_deps(self, expr: ast.Expr, deps: set[str]) -> None:
        match expr:
            case ast.Literal():
                pass
            case ast.Var(path=path):
                if path in self.layers or "/" in path:
                    deps.add(path)
            case ast.BinOp(left=left, right=right):
                self._walk_deps(left, deps)
                self._walk_deps(right, deps)
            case ast.UnaryOp(operand=operand):
                self._walk_deps(operand, deps)
            case ast.Call(args=args):
                for arg in args:
                    self._walk_deps(arg, deps)
            case ast.FieldAccess(obj=obj):
                self._walk_deps(obj, deps)
            case ast.Match(subject=subject, cases=cases, default=default):
                self._walk_deps(subject, deps)
                for _, result in cases:
                    self._walk_deps(result, deps)
                if default:
                    self._walk_deps(default, deps)
            case ast.Cond(condition=cond, then_expr=then_e, else_expr=else_e):
                self._walk_deps(cond, deps)
                self._walk_deps(then_e, deps)
                self._walk_deps(else_e, deps)

    def _topo_sort(self, variables: dict[str, ResolvedVar]) -> list[str]:
        visited: set[str] = set()
        order: list[str] = []
        temp: set[str] = set()

        def visit(path: str) -> None:
            if path in temp:
                raise CompileError(f"circular dependency involving {path}")
            if path in visited:
                return
            temp.add(path)
            if path in variables:
                for dep in variables[path].deps:
                    visit(dep)
            temp.remove(path)
            visited.add(path)
            if path in variables:
                order.append(path)

        for path in variables:
            visit(path)

        return order
