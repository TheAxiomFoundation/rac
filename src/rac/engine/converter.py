"""Converter: bridge v2 .rac format to engine AST/IR.

Translates the existing dsl_parser Module (with VariableDef, ParameterDef,
InputDef, and their expression AST) into the engine's Module format
(with VariableDecl, EntityDecl, and temporal values).
"""

from datetime import date
from typing import Any

from ..dsl_parser import (
    BinaryOp as V2BinaryOp,
    FunctionCall as V2FunctionCall,
    Identifier as V2Identifier,
    IfExpr as V2IfExpr,
    IndexExpr as V2IndexExpr,
    LetBinding as V2LetBinding,
    Literal as V2Literal,
    MatchCase as V2MatchCase,
    MatchExpr as V2MatchExpr,
    Module as V2Module,
    ParameterRef as V2ParameterRef,
    UnaryOp as V2UnaryOp,
    VariableRef as V2VariableRef,
)
from . import ast as engine_ast


class ConversionError(Exception):
    pass


def convert_v2_to_engine_module(
    v2_module: V2Module,
    module_path: str = "",
    default_date: date = date(2024, 1, 1),
) -> engine_ast.Module:
    """Convert a v2 Module to an engine Module.

    Args:
        v2_module: Parsed v2 module from dsl_parser.
        module_path: Path prefix for variable names (e.g., "statute/26/32").
        default_date: Default effective date for formulas without explicit dates.

    Returns:
        Engine Module with entities, variables, and temporal values.
    """
    converter = V2Converter(v2_module, module_path, default_date)
    return converter.convert()


class V2Converter:
    def __init__(self, v2_module: V2Module, module_path: str, default_date: date):
        self.v2 = v2_module
        self.path = module_path
        self.default_date = default_date
        self.entities: dict[str, engine_ast.EntityDecl] = {}
        self.variables: list[engine_ast.VariableDecl] = []
        # Maps v2 parameter names to their engine paths
        self.param_paths: dict[str, str] = {}
        # Maps v2 input names to their entity
        self.input_entities: dict[str, str] = {}
        # Maps local binding names to their converted expressions (per-variable)
        self._binding_map: dict[str, engine_ast.Expr] = {}

    def convert(self) -> engine_ast.Module:
        self._convert_inputs()
        self._convert_parameters()
        self._convert_variables()

        return engine_ast.Module(
            path=self.path,
            entities=list(self.entities.values()),
            variables=self.variables,
        )

    def _var_path(self, name: str) -> str:
        if self.path:
            return f"{self.path}/{name}"
        return name

    def _convert_inputs(self) -> None:
        """Convert v2 InputDefs to engine entity declarations."""
        for inp in self.v2.inputs:
            entity_name = inp.entity.lower()
            self.input_entities[inp.name] = entity_name

            if entity_name not in self.entities:
                self.entities[entity_name] = engine_ast.EntityDecl(
                    name=entity_name,
                    fields=[],
                )

            # Map v2 dtype to engine field type
            dtype_map = {
                "Money": "float",
                "Float": "float",
                "Rate": "float",
                "Integer": "int",
                "Int": "int",
                "Boolean": "bool",
                "Bool": "bool",
                "String": "str",
                "Enum": "str",
            }
            engine_dtype = dtype_map.get(inp.dtype, "float")

            entity = self.entities[entity_name]
            if (inp.name, engine_dtype) not in entity.fields:
                entity.fields.append((inp.name, engine_dtype))

    def _convert_parameters(self) -> None:
        """Convert v2 ParameterDefs to engine scalar variables with temporal values."""
        for param in self.v2.parameters:
            param_path = self._var_path(param.name)
            self.param_paths[param.name] = param_path

            temporal_values = []
            if param.values:
                # Sort by date
                sorted_dates = sorted(param.values.keys())
                for i, date_str in enumerate(sorted_dates):
                    start = date.fromisoformat(date_str)
                    value = param.values[date_str]

                    # Convert value to engine Literal
                    expr = engine_ast.Literal(value=_coerce_value(value))

                    temporal_values.append(engine_ast.TemporalValue(
                        start=start,
                        end=None,
                        expr=expr,
                    ))

            if not temporal_values:
                # Parameter with no values — skip or use default
                continue

            self.variables.append(engine_ast.VariableDecl(
                path=param_path,
                entity=None,  # Parameters are scalars
                values=temporal_values,
            ))

    def _earliest_date(self) -> date:
        """Find the earliest date across all parameter values."""
        earliest = self.default_date
        for param in self.v2.parameters:
            for date_str in param.values:
                d = date.fromisoformat(date_str)
                if d < earliest:
                    earliest = d
        return earliest

    def _convert_variables(self) -> None:
        """Convert v2 VariableDefs with formulas to engine variables."""
        # Formula variables are valid from the earliest parameter date
        formula_start = self._earliest_date()

        for var in self.v2.variables:
            if var.formula is None:
                continue

            var_path = self._var_path(var.name)
            entity_name = var.entity.lower() if var.entity else None

            # Clear binding map for each variable
            self._binding_map = {}
            # Convert the formula expression to engine AST
            expr = self._convert_formula(var.formula)

            self.variables.append(engine_ast.VariableDecl(
                path=var_path,
                entity=entity_name,
                values=[engine_ast.TemporalValue(
                    start=formula_start,
                    expr=expr,
                )],
            ))

    def _convert_formula(self, formula) -> engine_ast.Expr:
        """Convert a v2 FormulaBlock to engine expression.

        A FormulaBlock has: bindings (let), guards (if-return), return_expr.
        We inline bindings and convert guards to nested conditionals.
        """
        # Build substitution map from local bindings
        if formula.bindings:
            for binding in formula.bindings:
                # Convert binding expression (may reference earlier bindings)
                self._binding_map[binding.name] = self._convert_expr(binding.value)

        # If there are guards (if-return statements), build nested conditionals
        if formula.guards:
            # Build from bottom up: last guard's else is the return_expr
            result = self._convert_expr(formula.return_expr)
            for condition, value in reversed(formula.guards):
                result = engine_ast.Cond(
                    condition=self._convert_expr(condition),
                    then_expr=self._convert_expr(value),
                    else_expr=result,
                )
            return result

        # Simple return expression
        return self._convert_expr(formula.return_expr)

    def _convert_expr(self, expr: Any) -> engine_ast.Expr:
        """Convert a v2 expression to engine AST."""
        if isinstance(expr, V2Literal):
            return engine_ast.Literal(value=_coerce_value(expr.value))

        if isinstance(expr, V2VariableRef):
            name = expr.name
            # Check local bindings first (inlined let-bindings)
            if name in self._binding_map:
                return self._binding_map[name]
            # If it maps to a parameter, use the parameter path
            if name in self.param_paths:
                return engine_ast.Var(path=self.param_paths[name])
            # If it's a known input, use just the name (resolved at entity level)
            if name in self.input_entities:
                return engine_ast.Var(path=name)
            # Otherwise, try with module path prefix
            return engine_ast.Var(path=self._var_path(name))

        if isinstance(expr, V2ParameterRef):
            path = expr.path
            if path in self.param_paths:
                return engine_ast.Var(path=self.param_paths[path])
            return engine_ast.Var(path=self._var_path(path))

        if isinstance(expr, V2Identifier):
            name = expr.name
            # Check local bindings first
            if name in self._binding_map:
                return self._binding_map[name]
            if name in self.param_paths:
                return engine_ast.Var(path=self.param_paths[name])
            if name in self.input_entities:
                return engine_ast.Var(path=name)
            return engine_ast.Var(path=self._var_path(name))

        if isinstance(expr, V2BinaryOp):
            return engine_ast.BinOp(
                op=expr.op,
                left=self._convert_expr(expr.left),
                right=self._convert_expr(expr.right),
            )

        if isinstance(expr, V2UnaryOp):
            return engine_ast.UnaryOp(
                op=expr.op,
                operand=self._convert_expr(expr.operand),
            )

        if isinstance(expr, V2FunctionCall):
            return engine_ast.Call(
                func=expr.name,
                args=[self._convert_expr(a) for a in expr.args],
            )

        if isinstance(expr, V2IfExpr):
            return engine_ast.Cond(
                condition=self._convert_expr(expr.condition),
                then_expr=self._convert_expr(expr.then_branch),
                else_expr=self._convert_expr(expr.else_branch),
            )

        if isinstance(expr, V2MatchExpr):
            if expr.match_value is not None:
                # match value: case => result
                subject = self._convert_expr(expr.match_value)
                cases = []
                default = None
                for case in expr.cases:
                    if case.condition is None:
                        default = self._convert_expr(case.value)
                    else:
                        cases.append((
                            self._convert_expr(case.condition),
                            self._convert_expr(case.value),
                        ))
                return engine_ast.Match(
                    subject=subject,
                    cases=cases,
                    default=default,
                )
            else:
                # condition-only match (like chained if/elif)
                # Convert to nested Cond
                result: engine_ast.Expr = engine_ast.Literal(value=0)
                for case in reversed(expr.cases):
                    if case.condition is None:
                        result = self._convert_expr(case.value)
                    else:
                        result = engine_ast.Cond(
                            condition=self._convert_expr(case.condition),
                            then_expr=self._convert_expr(case.value),
                            else_expr=result,
                        )
                return result

        if isinstance(expr, V2IndexExpr):
            # base[index] — convert to function call or match depending on context
            return engine_ast.Call(
                func="index",
                args=[self._convert_expr(expr.base), self._convert_expr(expr.index)],
            )

        if isinstance(expr, V2LetBinding):
            # Let bindings should have been inlined already
            raise ConversionError(f"Unexpected let binding in expression: {expr.name}")

        raise ConversionError(f"Unknown v2 expression type: {type(expr).__name__}")


def _coerce_value(value: Any) -> int | float | str | bool:
    """Coerce a v2 literal value to a Python primitive."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        try:
            # Try numeric coercion for string values from YAML
            if "." in value:
                return float(value)
            return int(value)
        except (ValueError, TypeError):
            return value
    return value
