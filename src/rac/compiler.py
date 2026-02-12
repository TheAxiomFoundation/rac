"""Compiler: resolves temporal layers and produces IR for backends.

Takes parsed modules and an as_of date, resolves which temporal values apply,
and produces a flat variable graph.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict

from . import ast
from .schema import Entity, Field, ForeignKey, ReverseRelation, Schema


class ResolvedVar(BaseModel):
    """A variable resolved to a single expression for a point in time."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: str
    entity: str | None = None
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


class TemporalLayer:
    """Tracks temporal values for a variable, with amendment stacking."""

    def __init__(self, path: str, entity: str | None = None):
        self.path = path
        self.entity = entity
        self.values: list[ast.TemporalValue] = []
        self.repealed_after: date | None = None

    def add_values(self, values: list[ast.TemporalValue], replace: bool = False) -> None:
        if replace:
            self.values = list(values)
        else:
            self.values.extend(values)

    def repeal(self, effective: date) -> None:
        self.repealed_after = effective

    def resolve(self, as_of: date) -> ast.Expr | None:
        """Get the applicable expression for a date. Later values win."""
        if self.repealed_after and as_of >= self.repealed_after:
            return None

        result = None
        for tv in self.values:
            if tv.start <= as_of and (tv.end is None or as_of <= tv.end):
                result = tv.expr
        return result


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
            if decl.path in self.layers:
                raise CompileError(f"duplicate variable: {decl.path}")
            layer = TemporalLayer(decl.path, decl.entity)
            layer.add_values(decl.values)
            self.layers[decl.path] = layer

    def _apply_amendments(self, module: ast.Module) -> None:
        for amend in module.amendments:
            if amend.target not in self.layers:
                self.layers[amend.target] = TemporalLayer(amend.target)
            self.layers[amend.target].add_values(amend.values, replace=amend.replace)

    def _apply_repeals(self, module: ast.Module) -> None:
        for repeal in module.repeals:
            if repeal.target in self.layers:
                self.layers[repeal.target].repeal(repeal.effective)

    def _resolve_temporal(self, as_of: date) -> dict[str, ResolvedVar]:
        resolved = {}
        for path, layer in self.layers.items():
            expr = layer.resolve(as_of)
            if expr is not None:
                resolved[path] = ResolvedVar(path=path, entity=layer.entity, expr=expr)
        return resolved

    def _walk_deps(self, expr: ast.Expr, deps: set[str]) -> None:
        match expr:
            case ast.Literal():
                pass
            case ast.Var(path=path):
                if "/" in path:
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
            order.append(path)

        for path in variables:
            visit(path)

        return order
