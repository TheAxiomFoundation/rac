"""Vectorized DSL executor for microsimulation.

Compiles RAC DSL formulas to vectorized NumPy operations for
high-performance execution across millions of households.

Design principles:
1. All operations work on arrays (shape: [n_entities])
2. Entity relationships handled via broadcasting and indexing
3. Parameters broadcast to match entity dimensions
4. Lazy evaluation with caching to avoid redundant computation
5. Copy-on-write scenarios for reform comparisons
6. Parallel execution of independent variable groups

Performance targets (from DESIGN.md):
- 130M households in <1 hour on 32-core commodity hardware
- API p99 <100ms for single-household calculations
- Vectorized operations via NumPy, with JIT compilation via Numba optional
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

from .dsl_parser import (
    BinaryOp,
    Expression,
    FormulaBlock,
    FunctionCall,
    Identifier,
    IfExpr,
    IndexExpr,
    LetBinding,
    Literal,
    MatchExpr,
    Module,
    ParameterRef,
    ReferencesBlock,
    UnaryOp,
    VariableDef,
    VariableRef,
    parse_dsl,
)
from .python_formula_compiler import (
    execute_formula as execute_python_formula,
)

# Try to import numba for JIT compilation (optional)
try:
    from numba import jit as numba_jit

    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    numba_jit = None


# NOTE: is_python_syntax_formula was removed - syntax: python is now rejected
# by the parser as a security risk (arbitrary code execution).


@dataclass
class EntityIndex:
    """Maps between entity levels (Person -> TaxUnit -> Household).

    For a simulation with N persons across M tax units:
    - person_to_tax_unit[i] = tax_unit index for person i
    - tax_unit_to_household[j] = household index for tax_unit j
    """

    person_to_tax_unit: np.ndarray  # shape: [n_persons]
    tax_unit_to_household: np.ndarray  # shape: [n_tax_units]

    # Counts for broadcasting
    n_persons: int
    n_tax_units: int
    n_households: int


@dataclass
class VectorizedContext:
    """Runtime context for vectorized formula evaluation."""

    # Input arrays by variable name, shape depends on entity
    inputs: dict[str, np.ndarray]

    # Parameter values (scalar or array by index dimension)
    parameters: dict[str, Any]

    # Variable definitions from parsed module
    variables: dict[str, VariableDef]

    # Cached computed values
    computed: dict[str, np.ndarray] = field(default_factory=dict)

    # Entity relationship indices
    entity_index: EntityIndex | None = None

    # References block for alias resolution
    references: ReferencesBlock | None = None

    # Current entity context (for formula evaluation)
    current_entity: str = "Person"

    # Enum values from module declarations (flattened set of all enum member names)
    enum_values: set[str] = field(default_factory=set)

    def get_variable(self, name: str) -> np.ndarray:
        """Get variable value as array, computing if needed."""
        # Check cache
        if name in self.computed:
            return self.computed[name]

        # Check inputs
        if name in self.inputs:
            return self.inputs[name]

        # Check parameters (for dict/array parameters used in IndexExpr)
        if name in self.parameters:
            return self.parameters[name]

        # Resolve alias
        if self.references:
            path = self.references.get_path(name)
            if path:
                actual_name = path.split("/")[-1]
                if actual_name != name:
                    return self.get_variable(actual_name)

        if name in self.variables:
            var_def = self.variables[name]
            formula = self._resolve_temporal_formula(var_def)

            # Check for Python formula (formula_source is set)
            if var_def.formula_source:
                # Set entity context for proper broadcasting
                old_entity = self.current_entity
                self.current_entity = var_def.entity

                # Execute Python formula using PythonFormulaExecutor
                value = execute_python_formula(
                    var_def.formula_source, self.inputs, self.parameters, return_var="_return_"
                )
                self.computed[name] = value

                self.current_entity = old_entity
                return value

            elif formula or var_def.formula:
                # Set entity context for proper broadcasting
                old_entity = self.current_entity
                self.current_entity = var_def.entity

                value = evaluate_formula_vectorized(formula or var_def.formula, self)
                self.computed[name] = value

                self.current_entity = old_entity
                return value

        # Return zeros with appropriate shape
        return self._zeros_for_entity(self.current_entity)

    def _resolve_temporal_formula(self, var_def: VariableDef) -> "FormulaBlock | None":
        """Return the latest temporal formula, or None."""
        if not var_def.temporal_formulas:
            return None

        from .dsl_parser import FormulaBlock

        latest_date = max(var_def.temporal_formulas.keys())
        formula = var_def.temporal_formulas[latest_date]
        return formula if isinstance(formula, FormulaBlock) else None

    def get_parameter(self, path: str, index: str | None = None) -> np.ndarray:
        """Get parameter value, broadcasting to entity dimension."""
        # Get base parameter value
        value = self.parameters.get(path, 0)

        if index is not None:
            # Indexed parameter (e.g., rate[count_children])
            index_values = self.get_variable(index)

            if isinstance(value, dict):
                # Vectorized lookup from dict
                result = np.zeros_like(index_values, dtype=float)
                for k, v in value.items():
                    mask = index_values == k
                    result[mask] = v
                return result
            elif isinstance(value, np.ndarray):
                # Direct array indexing
                return value[index_values.astype(int)]

        # Broadcast scalar to entity shape
        if np.isscalar(value):
            return np.full(self._entity_size(self.current_entity), value)

        return np.asarray(value)

    def aggregate_to_parent(
        self, values: np.ndarray, from_entity: str, to_entity: str, agg_func: str = "sum"
    ) -> np.ndarray:
        """Aggregate values from child entity to parent entity.

        Example: sum Person incomes to TaxUnit level.
        """
        if self.entity_index is None:
            raise ValueError("Entity index required for aggregation")

        if from_entity == "Person" and to_entity == "TaxUnit":
            mapping = self.entity_index.person_to_tax_unit
            n_target = self.entity_index.n_tax_units
        elif from_entity == "TaxUnit" and to_entity == "Household":
            mapping = self.entity_index.tax_unit_to_household
            n_target = self.entity_index.n_households
        else:
            raise ValueError(f"Unsupported aggregation: {from_entity} -> {to_entity}")

        # Vectorized aggregation using np.bincount
        if agg_func == "sum":
            return np.bincount(mapping, weights=values, minlength=n_target)
        elif agg_func == "max":
            result = np.full(n_target, -np.inf)
            np.maximum.at(result, mapping, values)
            result[result == -np.inf] = 0
            return result
        elif agg_func == "min":
            result = np.full(n_target, np.inf)
            np.minimum.at(result, mapping, values)
            result[result == np.inf] = 0
            return result
        elif agg_func == "count":
            return np.bincount(mapping, minlength=n_target).astype(float)
        elif agg_func == "any":
            return np.bincount(mapping, weights=values.astype(float), minlength=n_target) > 0
        elif agg_func == "all":
            # For 'all', we need count of True == count of members
            true_count = np.bincount(mapping, weights=values.astype(float), minlength=n_target)
            total_count = np.bincount(mapping, minlength=n_target)
            return true_count == total_count
        else:
            raise ValueError(f"Unknown aggregation function: {agg_func}")

    def broadcast_to_child(
        self, values: np.ndarray, from_entity: str, to_entity: str
    ) -> np.ndarray:
        """Broadcast parent entity values to child entity level.

        Example: broadcast TaxUnit filing_status to Person level.
        """
        if self.entity_index is None:
            raise ValueError("Entity index required for broadcasting")

        if from_entity == "TaxUnit" and to_entity == "Person":
            mapping = self.entity_index.person_to_tax_unit
        elif from_entity == "Household" and to_entity == "TaxUnit":
            mapping = self.entity_index.tax_unit_to_household
        else:
            raise ValueError(f"Unsupported broadcast: {from_entity} -> {to_entity}")

        return values[mapping]

    def _entity_size(self, entity: str) -> int:
        """Get the number of entities of given type."""
        if self.entity_index is None:
            # Fall back to input shapes
            for v in self.inputs.values():
                return len(v)
            return 1

        if entity == "Person":
            return self.entity_index.n_persons
        elif entity == "TaxUnit":
            return self.entity_index.n_tax_units
        elif entity == "Household":
            return self.entity_index.n_households
        return 1

    def _zeros_for_entity(self, entity: str) -> np.ndarray:
        """Create zero array with shape for given entity."""
        return np.zeros(self._entity_size(entity))


def evaluate_expression_vectorized(expr: Expression, ctx: VectorizedContext) -> np.ndarray:
    """Evaluate expression to array result."""

    if isinstance(expr, Literal):
        # Broadcast scalar to entity dimension
        size = ctx._entity_size(ctx.current_entity)
        return np.full(size, expr.value)

    if isinstance(expr, Identifier):
        # Check if it's an enum value first (e.g., JOINT, SINGLE)
        if ctx.enum_values and expr.name in ctx.enum_values:
            # Return the string value broadcast to current entity size
            size = ctx._entity_size(ctx.current_entity)
            return np.full(size, expr.name, dtype=object)
        return ctx.get_variable(expr.name)

    if isinstance(expr, VariableRef):
        return ctx.get_variable(expr.name)

    if isinstance(expr, ParameterRef):
        return ctx.get_parameter(expr.path, expr.index)

    if isinstance(expr, IndexExpr):
        # Evaluate base and index, then perform lookup
        # Base could be a dict (parameter table) or array
        base_value = evaluate_expression_vectorized(expr.base, ctx)
        index_value = evaluate_expression_vectorized(expr.index, ctx)

        # If base is scalar/array and we have index values, do vectorized lookup
        if isinstance(base_value, dict):
            # Dict lookup: base_value[index_value] for each element
            result = np.zeros_like(index_value, dtype=float)
            for k, v in base_value.items():
                mask = index_value == k
                result[mask] = v
            return result
        elif isinstance(base_value, np.ndarray) and base_value.ndim > 0:
            # Array indexing
            return base_value[index_value.astype(int)]
        else:
            # Scalar base - return as-is (unusual case)
            return base_value

    if isinstance(expr, BinaryOp):
        left = evaluate_expression_vectorized(expr.left, ctx)
        right = evaluate_expression_vectorized(expr.right, ctx)
        return _apply_binary_op_vectorized(expr.op, left, right)

    if isinstance(expr, UnaryOp):
        operand = evaluate_expression_vectorized(expr.operand, ctx)
        return _apply_unary_op_vectorized(expr.op, operand)

    if isinstance(expr, FunctionCall):
        return _call_builtin_vectorized(expr.name, expr.args, ctx)

    if isinstance(expr, IfExpr):
        condition = evaluate_expression_vectorized(expr.condition, ctx)
        then_val = evaluate_expression_vectorized(expr.then_branch, ctx)
        else_val = evaluate_expression_vectorized(expr.else_branch, ctx)
        return np.where(condition, then_val, else_val)

    if isinstance(expr, MatchExpr):
        # Vectorized match: evaluate all conditions, use first match
        result = np.zeros(ctx._entity_size(ctx.current_entity))
        matched = np.zeros(len(result), dtype=bool)

        # If we have a match value (match x { ... }), compare case patterns against it
        match_value = None
        if expr.match_value is not None:
            match_value = evaluate_expression_vectorized(expr.match_value, ctx)

        for case in expr.cases:
            if case.condition is None:  # else case
                result[~matched] = evaluate_expression_vectorized(case.value, ctx)[~matched]
            else:
                if match_value is not None:
                    # Compare match_value against case.condition (pattern matching)
                    pattern = evaluate_expression_vectorized(case.condition, ctx)
                    cond = match_value == pattern
                else:
                    # Original behavior: evaluate condition as boolean
                    cond = evaluate_expression_vectorized(case.condition, ctx).astype(bool)

                mask = cond & ~matched
                if np.any(mask):
                    result[mask] = evaluate_expression_vectorized(case.value, ctx)[mask]
                    matched |= cond

        return result

    if isinstance(expr, LetBinding):
        return evaluate_expression_vectorized(expr.value, ctx)

    raise ValueError(f"Unknown expression type: {type(expr)}")


def evaluate_formula_vectorized(formula: FormulaBlock, ctx: VectorizedContext) -> np.ndarray:
    """Evaluate formula block with let bindings."""
    # Process let bindings
    for binding in formula.bindings:
        value = evaluate_expression_vectorized(binding.value, ctx)
        ctx.computed[binding.name] = value

    # Evaluate return expression
    if formula.return_expr:
        return evaluate_expression_vectorized(formula.return_expr, ctx)

    return ctx._zeros_for_entity(ctx.current_entity)


def _apply_binary_op_vectorized(op: str, left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Apply binary operator element-wise."""
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        return np.divide(left, right, out=np.zeros_like(left), where=right != 0)
    if op == "%":
        return np.mod(left, right, out=np.zeros_like(left), where=right != 0)
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "<":
        return left < right
    if op == ">":
        return left > right
    if op == "<=":
        return left <= right
    if op == ">=":
        return left >= right
    if op == "and":
        return np.logical_and(left, right)
    if op == "or":
        return np.logical_or(left, right)

    raise ValueError(f"Unknown operator: {op}")


def _apply_unary_op_vectorized(op: str, operand: np.ndarray) -> np.ndarray:
    """Apply unary operator element-wise."""
    if op == "-":
        return -operand
    if op == "not":
        return ~operand.astype(bool)

    raise ValueError(f"Unknown unary operator: {op}")


def _call_builtin_vectorized(
    name: str, args: list[Expression], ctx: VectorizedContext
) -> np.ndarray:
    """Call built-in function with vectorized semantics."""

    # Handle dotted names
    parts = name.split(".")
    func_name = parts[-1] if len(parts) > 1 else name

    # Aggregation functions (child -> parent entity)
    if func_name == "sum" and len(args) == 2:
        # sum(members, variable) - aggregate Person to TaxUnit
        values = evaluate_expression_vectorized(args[1], ctx)
        return ctx.aggregate_to_parent(values, "Person", "TaxUnit", "sum")

    if func_name == "count":
        if len(args) == 2:
            # count(members, condition) - aggregate Person to TaxUnit
            values = evaluate_expression_vectorized(args[1], ctx)
            return ctx.aggregate_to_parent(values.astype(float), "Person", "TaxUnit", "sum")
        elif len(args) == 1:
            # person.count(condition) - 1-arg form, aggregate Person to TaxUnit
            # The "person" prefix indicates we're counting at Person level
            values = evaluate_expression_vectorized(args[0], ctx)
            return ctx.aggregate_to_parent(values.astype(float), "Person", "TaxUnit", "sum")

    if func_name == "any" and len(args) == 2:
        values = evaluate_expression_vectorized(args[1], ctx)
        return ctx.aggregate_to_parent(values, "Person", "TaxUnit", "any")

    if func_name == "all" and len(args) == 2:
        values = evaluate_expression_vectorized(args[1], ctx)
        return ctx.aggregate_to_parent(values, "Person", "TaxUnit", "all")

    # Element-wise math functions
    evaluated_args = [evaluate_expression_vectorized(arg, ctx) for arg in args]

    if func_name == "min":
        if len(evaluated_args) == 1:
            return evaluated_args[0]  # Single arg, return as-is
        # Handle mixed scalar/array args by broadcasting
        if len(evaluated_args) == 2:
            return np.minimum(evaluated_args[0], evaluated_args[1])
        return np.minimum.reduce(evaluated_args)

    if func_name == "max":
        if len(evaluated_args) == 1:
            return evaluated_args[0]
        # Handle mixed scalar/array args by broadcasting
        if len(evaluated_args) == 2:
            return np.maximum(evaluated_args[0], evaluated_args[1])
        return np.maximum.reduce(evaluated_args)

    if func_name == "abs":
        return (
            np.abs(evaluated_args[0])
            if evaluated_args
            else ctx._zeros_for_entity(ctx.current_entity)
        )

    if func_name == "floor":
        return (
            np.floor(evaluated_args[0])
            if evaluated_args
            else ctx._zeros_for_entity(ctx.current_entity)
        )

    if func_name == "ceil":
        return (
            np.ceil(evaluated_args[0])
            if evaluated_args
            else ctx._zeros_for_entity(ctx.current_entity)
        )

    if func_name == "round":
        if len(evaluated_args) == 1:
            return np.round(evaluated_args[0])
        elif len(evaluated_args) == 2:
            return np.round(evaluated_args[0], int(evaluated_args[1][0]))
        return ctx._zeros_for_entity(ctx.current_entity)

    if func_name == "clamp":
        if len(evaluated_args) >= 3:
            return np.clip(evaluated_args[0], evaluated_args[1], evaluated_args[2])
        return evaluated_args[0] if evaluated_args else ctx._zeros_for_entity(ctx.current_entity)

    # Unknown function - return zeros
    return ctx._zeros_for_entity(ctx.current_entity)


@dataclass
class DependencyGraph:
    """Dependency graph for variables, enabling parallel execution."""

    # Variable name -> list of dependencies
    dependencies: dict[str, list[str]] = field(default_factory=dict)

    # Cached topological order
    _topo_order: list[str] | None = None
    _parallel_groups: list[list[str]] | None = None

    def add_variable(self, name: str, deps: list[str]):
        """Add a variable with its dependencies."""
        self.dependencies[name] = deps
        self._topo_order = None
        self._parallel_groups = None

    def topological_order(self) -> list[str]:
        """Return variables in dependency order (compute order)."""
        if self._topo_order is not None:
            return self._topo_order

        # Kahn's algorithm
        in_degree = {v: 0 for v in self.dependencies}
        for deps in self.dependencies.values():
            for d in deps:
                if d in in_degree:
                    in_degree[d] = in_degree.get(d, 0)

        # Build reverse graph
        for v, deps in self.dependencies.items():
            for d in deps:
                if d in in_degree:
                    in_degree[v] += 1

        queue = [v for v, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            v = queue.pop(0)
            result.append(v)
            for other, deps in self.dependencies.items():
                if v in deps:
                    in_degree[other] -= 1
                    if in_degree[other] == 0:
                        queue.append(other)

        self._topo_order = result
        return result

    def parallel_groups(self) -> list[list[str]]:
        """Return groups of variables that can be computed in parallel.

        Variables in the same group have no dependencies on each other.
        """
        if self._parallel_groups is not None:
            return self._parallel_groups

        computed = set()
        groups = []

        while len(computed) < len(self.dependencies):
            # Find all variables whose dependencies are satisfied
            ready = [
                v
                for v in self.dependencies
                if v not in computed
                and all(d in computed or d not in self.dependencies for d in self.dependencies[v])
            ]
            if not ready:
                # Cycle detected or empty
                break
            groups.append(ready)
            computed.update(ready)

        self._parallel_groups = groups
        return groups


@dataclass
class Scenario:
    """A calculation scenario with copy-on-write semantics.

    Enables efficient reform comparisons by sharing base data
    and only storing overrides.
    """

    base: Optional["Scenario"] = None
    overrides: dict[str, np.ndarray] = field(default_factory=dict)
    cache: dict[str, np.ndarray] = field(default_factory=dict)

    def get(self, variable: str) -> np.ndarray | None:
        """Get a variable value, checking cache and base."""
        # Check local override
        if variable in self.overrides:
            return self.overrides[variable]

        # Check local cache
        if variable in self.cache:
            return self.cache[variable]

        # Delegate to base
        if self.base:
            return self.base.get(variable)

        return None

    def set(self, variable: str, value: np.ndarray):
        """Set a variable override."""
        self.overrides[variable] = value
        # Invalidate cache for dependent variables
        self.cache.clear()

    def cache_result(self, variable: str, value: np.ndarray):
        """Cache a computed result."""
        self.cache[variable] = value

    def fork(self) -> "Scenario":
        """Create a child scenario that inherits from this one."""
        return Scenario(base=self)


class VectorizedExecutor:
    """High-performance vectorized DSL executor for microsimulation."""

    def __init__(
        self,
        parameters: dict[str, Any] | None = None,
        n_workers: int = 1,
        use_numba: bool = False,
        dependency_resolver: Any | None = None,
    ):
        """Initialize with parameter values.

        Args:
            parameters: Dict of parameter paths to values
            n_workers: Number of parallel workers (1 = sequential)
            use_numba: Whether to JIT compile hot paths with Numba
            dependency_resolver: Optional DependencyResolver for cross-file refs
        """
        self.parameters = parameters or {}
        self.n_workers = n_workers
        self.use_numba = use_numba
        self.dependency_resolver = dependency_resolver
        self._compiled_formulas: dict[str, Callable] = {}

    def execute(
        self,
        code: str,
        inputs: dict[str, np.ndarray],
        entity_index: EntityIndex | None = None,
        output_variables: list[str] | None = None,
        scenario: Scenario | None = None,
        parallel: bool = False,
    ) -> dict[str, np.ndarray]:
        """Execute DSL code on vectorized inputs.

        Args:
            code: DSL source code
            inputs: Dict of variable name -> array of values
            entity_index: Entity relationship mappings
            output_variables: Variables to compute (default: all with formulas)
            scenario: Optional scenario for caching/copy-on-write
            parallel: Whether to use parallel execution for independent groups

        Returns:
            Dict of variable name -> computed array
        """
        # Parse DSL
        module = parse_dsl(code)

        # Build variable lookup and dependency graph
        variables = {var.name: var for var in module.variables}
        dep_graph = self._build_dependency_graph(module)

        # Collect all enum values for identifier resolution
        enum_values: set[str] = set()
        for enum_def in module.enums:
            enum_values.update(enum_def.values)

        # Create execution context
        ctx = VectorizedContext(
            inputs=inputs,
            parameters=self.parameters,
            variables=variables,
            entity_index=entity_index,
            references=module.imports,
            enum_values=enum_values,
        )

        # Use scenario cache if provided
        if scenario:
            for var_name, value in scenario.cache.items():
                ctx.computed[var_name] = value
            for var_name, value in scenario.overrides.items():
                ctx.inputs[var_name] = value

        # Determine which variables to compute
        if output_variables is None:
            output_variables = [v.name for v in module.variables if v.formula]

        # Execute in parallel groups or sequentially
        if parallel and self.n_workers > 1:
            results = self._execute_parallel(ctx, variables, dep_graph, output_variables)
        else:
            results = self._execute_sequential(ctx, variables, output_variables)

        # Update scenario cache
        if scenario:
            for var_name, value in ctx.computed.items():
                scenario.cache_result(var_name, value)

        return results

    def execute_with_dependencies(
        self,
        entry_point: str,
        inputs: dict[str, np.ndarray],
        entity_index: EntityIndex | None = None,
        output_variables: list[str] | None = None,
    ) -> dict[str, np.ndarray]:
        """Execute DSL code with cross-file dependency resolution.

        Args:
            entry_point: Statute path to entry point (e.g. "statute/26/32/a/1/eitc")
            inputs: Dict of variable name -> array of values
            entity_index: Entity relationship mappings
            output_variables: Variables to compute (default: all from entry point)

        Returns:
            Dict of variable name -> computed array
        """
        if not self.dependency_resolver:
            raise ValueError("No dependency_resolver configured")

        # Resolve all dependencies
        resolved_modules = self.dependency_resolver.resolve_all(entry_point)

        # Build combined context with all inputs
        all_computed: dict[str, np.ndarray] = dict(inputs)

        # Execute modules in dependency order
        for resolved in resolved_modules:
            if resolved.module is None:
                continue  # Skip placeholders (unresolvable refs)

            # Build variable lookup
            variables = {var.name: var for var in resolved.module.variables}

            # Create execution context
            ctx = VectorizedContext(
                inputs=all_computed,  # Include previously computed values
                parameters=self.parameters,
                variables=variables,
                entity_index=entity_index,
                references=resolved.module.references,
            )

            # Execute all formulas in this module
            for var in resolved.module.variables:
                # Skip if already provided as input (inputs take precedence)
                if var.name in all_computed:
                    continue

                # Check for Python formula (formula_source is set)
                if var.formula_source:
                    value = execute_python_formula(
                        var.formula_source,
                        all_computed,  # Use all computed values as inputs
                        self.parameters,
                        return_var="_return_",
                    )
                    ctx.computed[var.name] = value
                    all_computed[var.name] = value
                elif var.formula:
                    value = evaluate_formula_vectorized(var.formula, ctx)
                    ctx.computed[var.name] = value
                    all_computed[var.name] = value

        # Return requested output variables
        if output_variables:
            return {k: all_computed[k] for k in output_variables if k in all_computed}
        return all_computed

    def execute_lazy(
        self,
        entry_point: str,
        inputs: dict[str, np.ndarray],
        output_variables: list[str],
        entity_index: EntityIndex | None = None,
    ) -> dict[str, np.ndarray]:
        """Execute DSL code with lazy dependency resolution (like OpenFisca).

        Unlike execute_with_dependencies which does topological sort upfront,
        this method computes variables on-demand with memoization. This handles
        circular dependencies gracefully as long as required inputs are provided.

        Args:
            entry_point: Statute path to entry point (e.g. "statute/26/24/a")
            inputs: Dict of variable name -> array of values (breaks cycles)
            output_variables: Variables to compute
            entity_index: Entity relationship mappings

        Returns:
            Dict of variable name -> computed array
        """
        if not self.dependency_resolver:
            raise ValueError("No dependency_resolver configured")

        # Cache for computed values (memoization)
        cache: dict[str, np.ndarray] = dict(inputs)

        # Cache for loaded modules
        module_cache: dict[str, Module] = {}

        # Variables currently being computed (for cycle detection)
        computing: set[str] = set()

        def load_module(path: str) -> Module | None:
            """Load and cache a module."""
            if path in module_cache:
                return module_cache[path]

            from .dsl_parser import parse_file

            # Get statute_root from dependency_resolver
            if (
                hasattr(self.dependency_resolver, "module_resolver")
                and self.dependency_resolver.module_resolver
            ):
                statute_root = self.dependency_resolver.module_resolver.statute_root
            elif hasattr(self.dependency_resolver, "statute_root"):
                statute_root = self.dependency_resolver.statute_root
            else:
                return None

            # Normalize path - strip leading 'statute/' if present
            norm_path = path
            if path.startswith("statute/"):
                norm_path = path[8:]  # len('statute/') = 8

            # Try multiple path resolutions
            paths_to_try = [
                statute_root / f"statute/{norm_path}.rac",  # rac-us/statute/26/24/a.rac
                statute_root / f"statute/{norm_path}",  # Already has extension
                statute_root / f"{norm_path}.rac",  # Without statute/ prefix
                statute_root / norm_path,  # Direct path
            ]

            for file_path in paths_to_try:
                try:
                    if file_path.exists() and file_path.is_file():
                        module = parse_file(file_path)
                        module_cache[path] = module
                        return module
                except Exception:
                    continue

            return None

        def find_variable(
            var_name: str, hint_module: Module | None = None
        ) -> tuple[VariableDef, Module] | None:
            """Find a variable definition, checking local module first."""
            # Check hint module first (same-file references)
            if hint_module:
                for var in hint_module.variables:
                    if var.name == var_name:
                        return (var, hint_module)

            # Check all loaded modules
            for mod in module_cache.values():
                for var in mod.variables:
                    if var.name == var_name:
                        return (var, mod)

            return None

        def resolve_import(import_spec: str) -> tuple[str, Module] | None:
            """Resolve an import like '26/24/h/2#credit_amount'."""
            if "#" in import_spec:
                path, var_name = import_spec.split("#", 1)
            else:
                return None

            module = load_module(path)
            if module:
                return (var_name, module)
            return None

        def aggregate_if_needed(
            value: np.ndarray,
            from_entity: str | None,
            to_entity: str | None,
        ) -> np.ndarray:
            """Aggregate values if entity levels differ.

            Sums Person→TaxUnit or TaxUnit→Household when a higher-level
            variable imports a lower-level variable.
            """
            if not entity_index or not from_entity or not to_entity:
                return value
            if from_entity == to_entity:
                return value

            # Person → TaxUnit aggregation (sum)
            if from_entity == "Person" and to_entity == "TaxUnit":
                mapping = entity_index.person_to_tax_unit
                aggregated = np.bincount(
                    mapping, weights=value.astype(float), minlength=entity_index.n_tax_units
                )
                return aggregated

            # TaxUnit → Household aggregation (sum)
            if from_entity == "TaxUnit" and to_entity == "Household":
                mapping = entity_index.tax_unit_to_household
                aggregated = np.bincount(
                    mapping, weights=value.astype(float), minlength=entity_index.n_households
                )
                return aggregated

            return value

        def compute(
            var_name: str, current_module: Module | None = None, depth: int = 0
        ) -> np.ndarray:
            """Compute a variable's value (with memoization)."""
            "  " * depth
            # Check cache first
            if var_name in cache:
                return cache[var_name]

            # Check parameters
            if var_name in self.parameters:
                return self.parameters[var_name]

            # Cycle detection
            if var_name in computing:
                raise RuntimeError(
                    f"Circular dependency on '{var_name}'. "
                    f"Provide it as input to break the cycle. "
                    f"Currently computing: {computing}"
                )

            # Find the variable definition
            var_info = find_variable(var_name, current_module)
            if not var_info:
                # Try to find via imports in current module
                if current_module:
                    for imp in getattr(current_module, "imports", []):
                        if isinstance(imp, str):
                            imp_str = imp
                        else:
                            imp_str = str(imp)
                        if "#" + var_name in imp_str or imp_str.endswith("/" + var_name):
                            result = resolve_import(imp_str)
                            if result:
                                target_name, target_module = result
                                return compute(target_name, target_module)
                raise ValueError(f"Variable '{var_name}' not found in any loaded module")

            var_def, source_module = var_info

            # Mark as computing (for cycle detection)
            computing.add(var_name)

            try:
                # Load imports for this variable (cross-file dependencies)
                for imp in var_def.imports:
                    # Handle VariableImport objects
                    if hasattr(imp, "file_path") and hasattr(imp, "variable_name"):
                        path = imp.file_path
                        imported_var = imp.variable_name
                        alias = imp.alias or imported_var
                    elif isinstance(imp, str) and "#" in imp:
                        path, imported_var = imp.split("#", 1)
                        if " as " in imported_var:
                            imported_var, alias = imported_var.split(" as ", 1)
                        else:
                            alias = imported_var
                    else:
                        continue

                    # Load the module to get variable definition (for entity info)
                    target_module = load_module(path)
                    if not target_module:
                        continue

                    # Get the imported variable's entity
                    imported_entity = None
                    for v in target_module.variables:
                        if v.name == imported_var:
                            imported_entity = v.entity
                            break

                    # Check if value is already in cache (from inputs)
                    if alias in cache:
                        # Aggregate cached value if entity levels differ
                        cached_value = cache[alias]
                        if imported_entity and var_def.entity and imported_entity != var_def.entity:
                            cache[alias] = aggregate_if_needed(
                                cached_value, imported_entity, var_def.entity
                            )
                        continue

                    # Compute the imported variable
                    value = compute(imported_var, target_module, depth + 1)

                    # Aggregate if needed (Person→TaxUnit, TaxUnit→Household)
                    value = aggregate_if_needed(value, imported_entity, var_def.entity)
                    cache[alias] = value

                # Find same-file variable references (not in imports but in formula)
                # These are other variables in the same module that this formula references
                same_file_vars = set()
                module_var_names = {v.name for v in source_module.variables}
                import_names = set()
                for imp in var_def.imports:
                    imp_str = imp if isinstance(imp, str) else str(imp)
                    if "#" in imp_str:
                        _, imported_var = imp_str.split("#", 1)
                        if " as " in imported_var:
                            _, alias = imported_var.split(" as ", 1)
                            import_names.add(alias)
                        else:
                            import_names.add(imported_var)

                # Extract variable references from formula
                import re

                # For DSL formulas, extract text from the formula object
                if var_def.formula:
                    # Simple extraction from DSL - get identifiers from formula
                    # Use the _extract_dependencies method logic
                    dsl_deps = self._extract_dependencies(var_def)
                    for dep in dsl_deps:
                        if dep in module_var_names and dep not in import_names and dep != var_name:
                            if dep not in cache:
                                same_file_vars.add(dep)

                # Also check Python formula source if present
                if var_def.formula_source:
                    # Find potential variable references (identifiers not in Python keywords)
                    tokens = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", var_def.formula_source)
                    for token in tokens:
                        if (
                            token in module_var_names
                            and token not in import_names
                            and token != var_name
                        ):
                            if token not in cache:
                                same_file_vars.add(token)

                # Compute same-file dependencies
                for dep_var in same_file_vars:
                    if dep_var not in cache and dep_var not in computing:
                        compute(dep_var, source_module, depth + 1)

                # Build namespace for formula execution
                namespace = dict(cache)
                namespace.update(self.parameters)

                # Execute the formula
                if var_def.formula_source:
                    # Python syntax formula
                    value = execute_python_formula(
                        var_def.formula_source, namespace, self.parameters, return_var="_return_"
                    )
                elif var_def.formula:
                    # DSL syntax formula
                    # Build context for DSL execution
                    variables = {v.name: v for v in source_module.variables}
                    ctx = VectorizedContext(
                        inputs=namespace,
                        parameters=self.parameters,
                        variables=variables,
                        entity_index=entity_index,
                        references=source_module.references
                        if hasattr(source_module, "references")
                        else None,
                    )
                    value = evaluate_formula_vectorized(var_def.formula, ctx)
                else:
                    # No formula - use default
                    sample_input = next(iter(inputs.values()))
                    value = np.full_like(
                        sample_input,
                        var_def.default if var_def.default is not None else 0,
                        dtype=float,
                    )

                # Cache result
                cache[var_name] = value
                return value

            finally:
                computing.discard(var_name)

        # Load entry point module
        entry_module = load_module(entry_point)
        if not entry_module:
            raise ValueError(f"Entry point module not found: {entry_point}")

        # Compute requested output variables
        results = {}
        for var_name in output_variables:
            try:
                results[var_name] = compute(var_name, entry_module)
            except Exception as e:
                # Re-raise with more context
                raise RuntimeError(f"Failed to compute '{var_name}': {e}") from e

        return results

    def _build_dependency_graph(self, module: Module) -> DependencyGraph:
        """Build dependency graph from parsed module."""
        graph = DependencyGraph()

        for var in module.variables:
            deps = self._extract_dependencies(var)
            graph.add_variable(var.name, deps)

        return graph

    def _extract_dependencies(self, var: VariableDef) -> list[str]:
        """Extract variable dependencies from a variable definition."""
        deps = []
        if var.formula:
            self._collect_deps_from_formula(var.formula, deps)
        return deps

    def _collect_deps_from_formula(self, formula: FormulaBlock, deps: list[str]):
        """Recursively collect dependencies from formula."""
        for binding in formula.bindings:
            self._collect_deps_from_expr(binding.value, deps)
        if formula.return_expr:
            self._collect_deps_from_expr(formula.return_expr, deps)

    def _collect_deps_from_expr(self, expr: Expression, deps: list[str]):
        """Recursively collect dependencies from expression."""
        if isinstance(expr, Identifier):
            if expr.name not in deps:
                deps.append(expr.name)
        elif isinstance(expr, VariableRef):
            if expr.name not in deps:
                deps.append(expr.name)
        elif isinstance(expr, BinaryOp):
            self._collect_deps_from_expr(expr.left, deps)
            self._collect_deps_from_expr(expr.right, deps)
        elif isinstance(expr, UnaryOp):
            self._collect_deps_from_expr(expr.operand, deps)
        elif isinstance(expr, FunctionCall):
            for arg in expr.args:
                self._collect_deps_from_expr(arg, deps)
        elif isinstance(expr, IfExpr):
            self._collect_deps_from_expr(expr.condition, deps)
            self._collect_deps_from_expr(expr.then_branch, deps)
            self._collect_deps_from_expr(expr.else_branch, deps)
        elif isinstance(expr, MatchExpr):
            for case in expr.cases:
                if case.condition:
                    self._collect_deps_from_expr(case.condition, deps)
                self._collect_deps_from_expr(case.value, deps)
        elif isinstance(expr, LetBinding):
            self._collect_deps_from_expr(expr.value, deps)

    def _execute_sequential(
        self,
        ctx: VectorizedContext,
        variables: dict[str, VariableDef],
        output_variables: list[str],
    ) -> dict[str, np.ndarray]:
        """Execute variables sequentially."""
        results = {}
        for var_name in output_variables:
            if var_name in variables:
                results[var_name] = ctx.get_variable(var_name)
        return results

    def _execute_parallel(
        self,
        ctx: VectorizedContext,
        variables: dict[str, VariableDef],
        dep_graph: DependencyGraph,
        output_variables: list[str],
    ) -> dict[str, np.ndarray]:
        """Execute variables in parallel groups."""
        groups = dep_graph.parallel_groups()

        # Filter to only groups needed for output
        needed = set(output_variables)
        for var_name in output_variables:
            self._add_transitive_deps(var_name, dep_graph, needed)

        with ThreadPoolExecutor(max_workers=self.n_workers) as executor:
            for group in groups:
                # Filter group to needed variables
                group_needed = [v for v in group if v in needed]
                if not group_needed:
                    continue

                # Submit all variables in group
                futures = {
                    executor.submit(ctx.get_variable, var_name): var_name
                    for var_name in group_needed
                }

                # Wait for all to complete
                for future in futures:
                    var_name = futures[future]
                    ctx.computed[var_name] = future.result()

        # Extract requested outputs
        return {
            var_name: ctx.computed.get(var_name, ctx.get_variable(var_name))
            for var_name in output_variables
            if var_name in variables
        }

    def _add_transitive_deps(self, var_name: str, dep_graph: DependencyGraph, needed: set[str]):
        """Add all transitive dependencies to needed set."""
        if var_name not in dep_graph.dependencies:
            return
        for dep in dep_graph.dependencies[var_name]:
            if dep not in needed:
                needed.add(dep)
                self._add_transitive_deps(dep, dep_graph, needed)

    def benchmark(
        self,
        code: str,
        n_entities: int = 1_000_000,
        n_iterations: int = 10,
    ) -> dict[str, float]:
        """Benchmark execution performance.

        Args:
            code: DSL source code
            n_entities: Number of entities to simulate
            n_iterations: Number of timing iterations

        Returns:
            Dict with timing statistics
        """
        import time

        # Create synthetic inputs
        inputs = {
            "earned_income": np.random.uniform(0, 100000, n_entities),
            "adjusted_gross_income": np.random.uniform(0, 150000, n_entities),
            "count_qualifying_children": np.random.randint(0, 4, n_entities),
            "filing_status": np.random.choice(["single", "joint"], n_entities),
        }

        # Warmup
        self.execute(code, inputs)

        # Timed iterations
        times = []
        for _ in range(n_iterations):
            start = time.perf_counter()
            self.execute(code, inputs)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        return {
            "n_entities": n_entities,
            "mean_time_ms": np.mean(times) * 1000,
            "std_time_ms": np.std(times) * 1000,
            "entities_per_second": n_entities / np.mean(times),
        }

    # -------------------------------------------------------------------------
    # DataFrame support
    # -------------------------------------------------------------------------

    def execute_dataframe(
        self,
        code: str,
        df: "pd.DataFrame",
        entity_columns: dict[str, str] | None = None,
        output_variables: list[str] | None = None,
        inplace: bool = False,
    ) -> "pd.DataFrame":
        """Execute DSL code on a pandas DataFrame.

        Converts DataFrame to dict of arrays, executes vectorized formulas,
        and returns results as a new DataFrame with computed columns added.

        Supports hierarchical entity structure (Person → TaxUnit → Household)
        by inferring entity relationships from ID columns.

        Args:
            code: DSL source code
            df: Input pandas DataFrame (one row per entity)
            entity_columns: Mapping of entity level to ID column name, e.g.:
                {"person": "person_id", "tax_unit": "tax_unit_id", "household": "household_id"}
                If None, assumes flat structure (all rows are same entity level)
            output_variables: Variables to compute (default: all with formulas)
            inplace: If True, add columns to input df; if False, return copy

        Returns:
            DataFrame with computed variable columns added

        Example:
            >>> executor = VectorizedExecutor(parameters=params)
            >>> df = pd.read_parquet("cps_persons.parquet")
            >>> result = executor.execute_dataframe(
            ...     code=eitc_code,
            ...     df=df,
            ...     entity_columns={
            ...         "person": "person_id",
            ...         "tax_unit": "tax_unit_id",
            ...         "household": "household_id",
            ...     },
            ...     output_variables=["earned_income_credit"],
            ... )
        """

        # Build entity index from columns if hierarchical
        entity_index = None
        if entity_columns:
            entity_index = self._infer_entity_index(df, entity_columns)

        # Convert DataFrame to dict of numpy arrays
        inputs = self._dataframe_to_inputs(df)

        # Execute vectorized
        results = self.execute(
            code=code,
            inputs=inputs,
            entity_index=entity_index,
            output_variables=output_variables,
        )

        # Convert results back to DataFrame
        if inplace:
            result_df = df
        else:
            result_df = df.copy()

        # Add computed columns
        for var_name, values in results.items():
            # Only add if not already in inputs (avoid overwriting)
            if var_name not in df.columns:
                result_df[var_name] = values

        return result_df

    def _infer_entity_index(
        self,
        df: "pd.DataFrame",
        entity_columns: dict[str, str],
    ) -> EntityIndex:
        """Build EntityIndex from DataFrame ID columns.

        Infers the person → tax_unit → household mapping from
        the ID columns in the DataFrame.

        Args:
            df: DataFrame with entity ID columns
            entity_columns: Mapping of entity level to column name

        Returns:
            EntityIndex with relationship mappings
        """

        # Get column names (with defaults)
        person_col = entity_columns.get("person", "person_id")
        tax_unit_col = entity_columns.get("tax_unit", "tax_unit_id")
        household_col = entity_columns.get("household", "household_id")

        # Check which columns exist
        has_person = person_col in df.columns
        has_tax_unit = tax_unit_col in df.columns
        has_household = household_col in df.columns

        # Build mappings based on available columns
        n_rows = len(df)

        if has_person and has_tax_unit and has_household:
            # Full hierarchy: Person → TaxUnit → Household
            df[person_col].values
            tax_unit_ids = df[tax_unit_col].values
            household_ids = df[household_col].values

            # Get unique IDs and create index mappings
            _, person_to_tax_unit = np.unique(tax_unit_ids, return_inverse=True)
            unique_tax_units, tax_unit_to_household = np.unique(
                household_ids[np.unique(tax_unit_ids, return_index=True)[1]], return_inverse=True
            )

            # Count entities at each level
            n_persons = n_rows
            n_tax_units = len(np.unique(tax_unit_ids))
            n_households = len(np.unique(household_ids))

            # Build the tax_unit → household mapping
            # For each row's tax_unit, find which household it belongs to
            tu_to_hh_mapping = {}
            for i, (tu_id, hh_id) in enumerate(zip(tax_unit_ids, household_ids)):
                if tu_id not in tu_to_hh_mapping:
                    tu_to_hh_mapping[tu_id] = hh_id

            # Create array indexed by tax_unit index
            unique_tu = np.unique(tax_unit_ids)
            unique_hh, hh_inverse = np.unique(household_ids, return_inverse=True)
            hh_id_to_idx = {hh: i for i, hh in enumerate(unique_hh)}

            tax_unit_to_household = np.array(
                [hh_id_to_idx[tu_to_hh_mapping[tu]] for tu in unique_tu]
            )

        elif has_tax_unit and has_household:
            # TaxUnit-level DataFrame: TaxUnit → Household
            tax_unit_ids = df[tax_unit_col].values
            household_ids = df[household_col].values

            # Person level = TaxUnit level (one "person" per tax unit)
            person_to_tax_unit = np.arange(n_rows)

            # TaxUnit → Household mapping
            unique_hh, tax_unit_to_household = np.unique(household_ids, return_inverse=True)

            n_persons = n_rows
            n_tax_units = n_rows
            n_households = len(unique_hh)

        else:
            # Flat structure: all rows are independent entities
            person_to_tax_unit = np.arange(n_rows)
            tax_unit_to_household = np.arange(n_rows)
            n_persons = n_rows
            n_tax_units = n_rows
            n_households = n_rows

        return EntityIndex(
            person_to_tax_unit=person_to_tax_unit,
            tax_unit_to_household=tax_unit_to_household,
            n_persons=n_persons,
            n_tax_units=n_tax_units,
            n_households=n_households,
        )

    def _dataframe_to_inputs(self, df: "pd.DataFrame") -> dict[str, np.ndarray]:
        """Convert DataFrame columns to dict of numpy arrays.

        Args:
            df: Input DataFrame

        Returns:
            Dict mapping column names to numpy arrays
        """
        inputs = {}
        for col in df.columns:
            values = df[col].values
            # Convert categorical/object columns to appropriate types
            if values.dtype == object:
                # Try to keep as string array for enum matching
                inputs[col] = values.astype(str)
            else:
                inputs[col] = values
        return inputs

    def execute_entity_dataframes(
        self,
        code: str,
        persons: Optional["pd.DataFrame"] = None,
        tax_units: Optional["pd.DataFrame"] = None,
        households: Optional["pd.DataFrame"] = None,
        output_variables: list[str] | None = None,
    ) -> dict[str, "pd.DataFrame"]:
        """Execute DSL code on separate DataFrames per entity level.

        This is the preferred approach for hierarchical data, avoiding
        redundancy and keeping entity-level data cleanly separated.

        Each DataFrame must have an ID column matching its level:
        - persons: "person_id", "tax_unit_id" (which tax unit this person belongs to)
        - tax_units: "tax_unit_id", "household_id" (which household this unit belongs to)
        - households: "household_id"

        Args:
            code: DSL source code
            persons: Person-level DataFrame (one row per person)
            tax_units: TaxUnit-level DataFrame (one row per tax unit)
            households: Household-level DataFrame (one row per household)
            output_variables: Variables to compute (default: all with formulas)

        Returns:
            Dict with keys "persons", "tax_units", "households", each containing
            a copy of the input DataFrame with computed columns added.

        Example:
            >>> executor = VectorizedExecutor(parameters=params)
            >>> persons_df = pd.read_parquet("cps_persons.parquet")
            >>> tax_units_df = pd.read_parquet("cps_tax_units.parquet")
            >>> households_df = pd.read_parquet("cps_households.parquet")
            >>> results = executor.execute_entity_dataframes(
            ...     code=eitc_code,
            ...     persons=persons_df,
            ...     tax_units=tax_units_df,
            ...     households=households_df,
            ...     output_variables=["earned_income_credit"],
            ... )
            >>> # Results contain computed columns at appropriate entity level
            >>> results["tax_units"]["earned_income_credit"]
        """

        # Validate we have at least one DataFrame
        if persons is None and tax_units is None and households is None:
            raise ValueError("At least one entity DataFrame must be provided")

        # Build entity index from the DataFrames
        entity_index = self._build_entity_index_from_dataframes(persons, tax_units, households)

        # Combine all inputs into single dict, prefixing with entity level
        # for disambiguation (but also include raw names for formula access)
        inputs = {}

        if persons is not None:
            for col in persons.columns:
                values = persons[col].values
                if values.dtype == object:
                    values = values.astype(str)
                inputs[col] = values
                inputs[f"person_{col}"] = values

        if tax_units is not None:
            for col in tax_units.columns:
                values = tax_units[col].values
                if values.dtype == object:
                    values = values.astype(str)
                # Tax unit values need to be broadcast to person level
                if persons is not None and col not in ["tax_unit_id", "household_id"]:
                    # Broadcast: tax_units[col][person_to_tax_unit] gives person-level
                    inputs[col] = values[entity_index.person_to_tax_unit]
                    inputs[f"tax_unit_{col}"] = values
                else:
                    inputs[col] = values
                    inputs[f"tax_unit_{col}"] = values

        if households is not None:
            for col in households.columns:
                values = households[col].values
                if values.dtype == object:
                    values = values.astype(str)
                # Household values need to be broadcast to person level
                if persons is not None and col not in ["household_id"]:
                    # Broadcast through tax_unit → household → person
                    tu_level = values[entity_index.tax_unit_to_household]
                    inputs[col] = tu_level[entity_index.person_to_tax_unit]
                    inputs[f"household_{col}"] = values
                elif tax_units is not None and col not in ["household_id"]:
                    inputs[col] = values[entity_index.tax_unit_to_household]
                    inputs[f"household_{col}"] = values
                else:
                    inputs[col] = values
                    inputs[f"household_{col}"] = values

        # Execute
        results = self.execute(
            code=code,
            inputs=inputs,
            entity_index=entity_index,
            output_variables=output_variables,
        )

        # Build output DataFrames
        output = {}

        if persons is not None:
            persons_out = persons.copy()
            for var_name, values in results.items():
                # Add person-level results (same length as persons)
                if len(values) == len(persons) and var_name not in persons.columns:
                    persons_out[var_name] = values
            output["persons"] = persons_out

        if tax_units is not None:
            tax_units_out = tax_units.copy()
            for var_name, values in results.items():
                # Add tax_unit-level results
                if len(values) == len(tax_units) and var_name not in tax_units.columns:
                    tax_units_out[var_name] = values
            output["tax_units"] = tax_units_out

        if households is not None:
            households_out = households.copy()
            for var_name, values in results.items():
                # Add household-level results
                if len(values) == len(households) and var_name not in households.columns:
                    households_out[var_name] = values
            output["households"] = households_out

        return output

    def _build_entity_index_from_dataframes(
        self,
        persons: Optional["pd.DataFrame"],
        tax_units: Optional["pd.DataFrame"],
        households: Optional["pd.DataFrame"],
    ) -> EntityIndex:
        """Build EntityIndex from separate entity DataFrames.

        Args:
            persons: Person-level DataFrame with person_id, tax_unit_id columns
            tax_units: TaxUnit-level DataFrame with tax_unit_id, household_id columns
            households: Household-level DataFrame with household_id column

        Returns:
            EntityIndex with relationship mappings
        """
        # Determine entity counts
        n_persons = len(persons) if persons is not None else 0
        n_tax_units = len(tax_units) if tax_units is not None else 0
        n_households = len(households) if households is not None else 0

        # Build person → tax_unit mapping
        if persons is not None and "tax_unit_id" in persons.columns:
            # Create mapping from tax_unit_id to index
            if tax_units is not None:
                tu_id_to_idx = {tu_id: i for i, tu_id in enumerate(tax_units["tax_unit_id"])}
                person_to_tax_unit = np.array(
                    [tu_id_to_idx.get(tu_id, 0) for tu_id in persons["tax_unit_id"]]
                )
            else:
                # No tax_units df, use inverse mapping from person's tax_unit_id
                _, person_to_tax_unit = np.unique(persons["tax_unit_id"], return_inverse=True)
                n_tax_units = len(np.unique(persons["tax_unit_id"]))
        else:
            # Flat: each person is their own tax unit
            person_to_tax_unit = np.arange(max(n_persons, n_tax_units))
            if n_persons > 0 and n_tax_units == 0:
                n_tax_units = n_persons

        # Build tax_unit → household mapping
        if tax_units is not None and "household_id" in tax_units.columns:
            if households is not None:
                hh_id_to_idx = {hh_id: i for i, hh_id in enumerate(households["household_id"])}
                tax_unit_to_household = np.array(
                    [hh_id_to_idx.get(hh_id, 0) for hh_id in tax_units["household_id"]]
                )
            else:
                # No households df, use inverse mapping
                _, tax_unit_to_household = np.unique(tax_units["household_id"], return_inverse=True)
                n_households = len(np.unique(tax_units["household_id"]))
        else:
            # Flat: each tax unit is their own household
            tax_unit_to_household = np.arange(max(n_tax_units, n_households))
            if n_tax_units > 0 and n_households == 0:
                n_households = n_tax_units

        return EntityIndex(
            person_to_tax_unit=person_to_tax_unit,
            tax_unit_to_household=tax_unit_to_household,
            n_persons=n_persons if n_persons > 0 else n_tax_units,
            n_tax_units=n_tax_units if n_tax_units > 0 else n_persons,
            n_households=n_households if n_households > 0 else n_tax_units,
        )
