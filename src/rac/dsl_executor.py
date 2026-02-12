"""RAC DSL executor.

Evaluates parsed DSL modules against test cases. This is the runtime
that executes formulas with inputs and parameters.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dsl_parser import (
    BinaryOp,
    Expression,
    FormulaBlock,
    FunctionCall,
    Identifier,
    IfExpr,
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
from .parameters.loader import ParameterStore as NewParameterStore
from .parameters.loader import load_parameters
from .types import ExecutionResult, GeneratedCode, TestCase


@dataclass
class ParameterStore:
    """Stores parameter values for execution.

    Supports both:
    1. YAML-loaded parameters from rules/ directory
    2. Programmatically set parameters (legacy/testing)
    """

    params: dict[str, Any]
    yaml_store: Any = None  # Optional: parameters.ParameterStore

    def get(self, path: str, index: Any | None = None, **indices: Any) -> Any:
        """Get a parameter value by path.

        Path format: "gov.irs.eitc.phase_in_rate"
        Index: for parameterized values like rate[n_children]
        """
        # Try YAML store first if available
        if self.yaml_store is not None:
            try:
                if index is not None:
                    # Determine index name from path
                    if "n_children" in str(index) or isinstance(index, int):
                        return self.yaml_store.get(path, n_children=index, **indices)
                    elif index in (
                        "SINGLE",
                        "JOINT",
                        "HEAD_OF_HOUSEHOLD",
                        "MARRIED_FILING_SEPARATELY",
                    ):
                        return self.yaml_store.get(path, filing_status=index, **indices)
                    else:
                        return self.yaml_store.get(path, **{str(index): index}, **indices)
                return self.yaml_store.get(path, **indices)
            except (KeyError, ValueError):
                pass  # Fall through to legacy lookup

        # Legacy nested dict lookup
        parts = path.split(".")
        current = self.params

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return 0

        if index is not None and isinstance(current, dict):
            return current.get(index, current.get(0, 0))

        return current


@dataclass
class ExecutionContext:
    """Runtime context for formula evaluation."""

    inputs: dict[str, Any]
    parameters: ParameterStore
    variables: dict[str, VariableDef]
    computed: dict[str, Any]  # Cache of computed variable values
    references: ReferencesBlock | None = None  # Statute-path references
    period: str | None = None  # Current evaluation period (e.g., "2024-01")

    def resolve_reference(self, alias: str) -> str | None:
        """Resolve an alias to its statute path.

        Returns the statute path if alias is in references, None otherwise.
        """
        if self.references:
            return self.references.get_path(alias)
        return None

    def get_variable(self, name: str) -> Any:
        """Get a variable value - from inputs, computed, or compute it.

        If the name is an alias in the references block, it will be resolved
        to the underlying variable. For now, we extract the variable name
        from the statute path (last component after /).
        """
        # Check computed cache first
        if name in self.computed:
            return self.computed[name]

        # Check inputs
        if name in self.inputs:
            return self.inputs[name]

        # Check if this is an aliased reference
        statute_path = self.resolve_reference(name)
        if statute_path:
            # Extract variable name from path (last component)
            # e.g., "us/irc/.../§32/c/2/A/earned_income" -> "earned_income"
            actual_name = statute_path.split("/")[-1]
            # Avoid infinite recursion
            if actual_name != name:
                return self.get_variable(actual_name)

        # Try to compute from variable definition
        if name in self.variables:
            var_def = self.variables[name]
            formula = self._resolve_temporal_formula(var_def)
            if formula:
                value = evaluate_formula(formula, self)
                self.computed[name] = value
                return value
            if var_def.formula:
                value = evaluate_formula(var_def.formula, self)
                self.computed[name] = value
                return value

        # Default value
        return 0

    def _resolve_temporal_formula(self, var_def: VariableDef) -> "FormulaBlock | None":
        """Find the most recent temporal formula with a date <= the current period."""
        if not var_def.temporal_formulas:
            return None

        from .dsl_parser import FormulaBlock

        period_str = self.period or "9999-12-31"
        if len(period_str) == 7:  # "2024-01" -> "2024-01-31"
            period_str = f"{period_str}-31"

        # Walk sorted dates in reverse to find the first applicable one
        for date_str in sorted(var_def.temporal_formulas.keys(), reverse=True):
            if date_str <= period_str:
                formula = var_def.temporal_formulas[date_str]
                if isinstance(formula, FormulaBlock):
                    return formula
                # Raw string formulas can't be evaluated as FormulaBlocks
                return None

        return None

    def get_parameter(self, path: str, index: str | None = None) -> Any:
        """Get a parameter value."""
        index_val = None
        if index:
            # Resolve index to actual value
            index_val = self.get_variable(index)
            if index_val is None:
                index_val = self.inputs.get(index, 0)

        return self.parameters.get(path, index_val)


def evaluate_expression(expr: Expression, ctx: ExecutionContext) -> Any:
    """Evaluate an expression in the given context."""

    if isinstance(expr, Literal):
        return expr.value

    if isinstance(expr, Identifier):
        # Could be a variable reference or enum value
        return ctx.get_variable(expr.name)

    if isinstance(expr, VariableRef):
        return ctx.get_variable(expr.name)

    if isinstance(expr, ParameterRef):
        return ctx.get_parameter(expr.path, expr.index)

    if isinstance(expr, BinaryOp):
        left = evaluate_expression(expr.left, ctx)
        right = evaluate_expression(expr.right, ctx)
        return _apply_binary_op(expr.op, left, right)

    if isinstance(expr, UnaryOp):
        operand = evaluate_expression(expr.operand, ctx)
        return _apply_unary_op(expr.op, operand)

    if isinstance(expr, FunctionCall):
        # Special case: parameter() is a pseudo-function that wraps a ParameterRef
        # The ParameterRef is already evaluated when we process the args
        if expr.name == "parameter" and len(expr.args) == 1:
            return evaluate_expression(expr.args[0], ctx)

        # Special case: variable() references another variable
        if expr.name == "variable" and len(expr.args) == 1:
            arg = expr.args[0]
            if isinstance(arg, Identifier):
                return ctx.get_variable(arg.name)
            # If it's already a name string
            return ctx.get_variable(str(evaluate_expression(arg, ctx)))

        args = [evaluate_expression(arg, ctx) for arg in expr.args]
        return _call_builtin(expr.name, args, ctx)

    if isinstance(expr, IfExpr):
        condition = evaluate_expression(expr.condition, ctx)
        if condition:
            return evaluate_expression(expr.then_branch, ctx)
        else:
            return evaluate_expression(expr.else_branch, ctx)

    if isinstance(expr, MatchExpr):
        for case in expr.cases:
            if case.condition is None:  # else case
                return evaluate_expression(case.value, ctx)
            if evaluate_expression(case.condition, ctx):
                return evaluate_expression(case.value, ctx)
        return 0  # No match found

    if isinstance(expr, LetBinding):
        # This shouldn't be called directly - let bindings are handled in formula
        return evaluate_expression(expr.value, ctx)

    raise ValueError(f"Unknown expression type: {type(expr)}")


def evaluate_formula(formula: FormulaBlock, ctx: ExecutionContext) -> Any:
    """Evaluate a formula block."""
    # Process let bindings first
    for binding in formula.bindings:
        value = evaluate_expression(binding.value, ctx)
        ctx.computed[binding.name] = value

    # Evaluate return expression
    if formula.return_expr:
        return evaluate_expression(formula.return_expr, ctx)

    return 0


def _apply_binary_op(op: str, left: Any, right: Any) -> Any:
    """Apply a binary operator."""
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        return left / right if right != 0 else 0
    if op == "%":
        return left % right if right != 0 else 0
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
        return left and right
    if op == "or":
        return left or right

    raise ValueError(f"Unknown operator: {op}")


def _apply_unary_op(op: str, operand: Any) -> Any:
    """Apply a unary operator."""
    if op == "-":
        return -operand
    if op == "not":
        return not operand

    raise ValueError(f"Unknown unary operator: {op}")


def _call_builtin(name: str, args: list[Any], ctx: ExecutionContext) -> Any:
    """Call a built-in function."""
    # Handle dotted names (e.g., brackets.marginal_rate)
    parts = name.split(".")
    func_name = parts[-1] if len(parts) > 1 else name

    if func_name == "min":
        return min(args)
    if func_name == "max":
        return max(args)
    if func_name == "abs":
        return abs(args[0]) if args else 0
    if func_name == "floor":
        import math

        return math.floor(args[0]) if args else 0
    if func_name == "ceil":
        import math

        return math.ceil(args[0]) if args else 0
    if func_name == "round":
        if len(args) == 1:
            return round(args[0])
        elif len(args) == 2:
            return round(args[0], int(args[1]))
        return 0
    if func_name == "clamp":
        if len(args) >= 3:
            return max(args[1], min(args[0], args[2]))
        return args[0] if args else 0

    # Bracket scale methods (legacy)
    if func_name == "marginal_rate":
        # Need to get the bracket scale from the base path
        if len(parts) > 1:
            base_path = ".".join(parts[:-1])
            brackets = ctx.get_parameter(base_path)
            if isinstance(brackets, dict) and "thresholds" in brackets and "rates" in brackets:
                return _calculate_marginal_rate(brackets, args[0] if args else 0)
        return 0

    # New bracket functions: cut and marginal_agg
    if func_name == "cut":
        from .brackets import cut as bracket_cut

        # cut(amount, schedule, threshold_by=None, amount_by=None)
        # Args: amount, schedule, [threshold_by], [amount_by]
        if len(args) >= 2:
            amount = args[0]
            schedule = args[1]
            threshold_by = args[2] if len(args) > 2 else None
            amount_by = args[3] if len(args) > 3 else None
            return bracket_cut(amount, schedule, threshold_by=threshold_by, amount_by=amount_by)
        return 0

    if func_name == "marginal_agg":
        from .brackets import marginal_agg as bracket_marginal_agg

        # marginal_agg(amount, brackets, threshold_by=None, rate_by=None)
        # Args: amount, brackets, [threshold_by], [rate_by]
        if len(args) >= 2:
            amount = args[0]
            brackets = args[1]
            threshold_by = args[2] if len(args) > 2 else None
            rate_by = args[3] if len(args) > 3 else None
            return bracket_marginal_agg(
                amount, brackets, threshold_by=threshold_by, rate_by=rate_by
            )
        return 0

    # If function not found, return 0
    return 0


def _calculate_marginal_rate(brackets: dict, amount: float) -> float:
    """Calculate tax using marginal rates from bracket scale."""
    thresholds = brackets.get("thresholds", [])
    rates = brackets.get("rates", [])

    if not thresholds or not rates:
        return 0

    total_tax = 0
    prev_threshold = 0

    for i, (threshold, rate) in enumerate(zip(thresholds, rates)):
        if amount <= threshold:
            total_tax += (amount - prev_threshold) * rate
            break
        else:
            total_tax += (threshold - prev_threshold) * rate
            prev_threshold = threshold
    else:
        # Amount exceeds all thresholds - apply last rate
        if len(rates) > len(thresholds):
            total_tax += (amount - prev_threshold) * rates[-1]

    return total_tax


class DSLExecutor:
    """Executes DSL code against test cases."""

    def __init__(
        self,
        parameters: dict | None = None,
        rules_dir: str | None = None,
        use_yaml_params: bool = True,
    ):
        """Initialize with parameter values.

        Args:
            parameters: Dict of parameter values (legacy format), e.g.:
                {
                    "gov": {
                        "irs": {
                            "eitc": {
                                "phase_in_rate": {0: 0.0765, 1: 0.34, ...}
                            }
                        }
                    }
                }
            rules_dir: Directory containing YAML parameter files.
                       If None, tries to load from rac-us.
            use_yaml_params: If True, load parameters from YAML files
        """
        yaml_store = None
        if use_yaml_params:
            try:
                if rules_dir:
                    yaml_store = load_parameters(rules_dir)
                else:
                    # Try rac-us first
                    yaml_store = load_rac_us_parameters()
            except Exception as e:
                print(f"Warning: Could not load YAML parameters: {e}")

        self.parameter_store = ParameterStore(
            params=parameters or {},
            yaml_store=yaml_store,
        )

    def set_parameters(self, params: dict):
        """Set parameter values (preserves YAML store)."""
        self.parameter_store = ParameterStore(
            params=params,
            yaml_store=self.parameter_store.yaml_store,
        )

    def execute(
        self,
        code: GeneratedCode | str,
        test_cases: list[TestCase],
    ) -> list[ExecutionResult]:
        """Execute DSL code against test cases.

        Args:
            code: DSL source code (as GeneratedCode or string)
            test_cases: List of test cases to run

        Returns:
            List of execution results
        """
        source = code.source if isinstance(code, GeneratedCode) else code

        # Try to parse DSL
        try:
            module = parse_dsl(source)
        except Exception as e:
            # Return parse error for all cases
            return [
                ExecutionResult(
                    case_id=tc.id,
                    error=f"Parse error: {e}",
                )
                for tc in test_cases
            ]

        # Build variable lookup
        variables = {var.name: var for var in module.variables}

        # Execute each test case
        results = []
        for tc in test_cases:
            result = self._execute_case(module, variables, tc)
            results.append(result)

        return results

    def _execute_case(
        self,
        module: Module,
        variables: dict[str, VariableDef],
        test_case: TestCase,
    ) -> ExecutionResult:
        """Execute against a single test case."""
        try:
            # Create execution context with references from module
            ctx = ExecutionContext(
                inputs=test_case.inputs,
                parameters=self.parameter_store,
                variables=variables,
                computed={},
                references=module.imports,  # Pass imports block
            )

            # Find the main variable to compute
            # Use the first variable with a formula, or the first expected output key
            main_var = None
            expected_keys = list(test_case.expected.keys())

            for key in expected_keys:
                if key in variables:
                    main_var = variables[key]
                    break

            if not main_var and module.variables:
                # Use first variable with a formula
                for var in module.variables:
                    if var.formula:
                        main_var = var
                        break

            if not main_var:
                return ExecutionResult(
                    case_id=test_case.id,
                    error="No variable with formula found",
                )

            # Evaluate the variable
            if main_var.formula:
                value = evaluate_formula(main_var.formula, ctx)
            else:
                value = ctx.get_variable(main_var.name)

            output = {main_var.name: value}

            # Compare with expected
            match = self._compare_outputs(output, test_case.expected)

            return ExecutionResult(
                case_id=test_case.id,
                output=output,
                expected=test_case.expected,
                match=match,
            )

        except Exception as e:
            return ExecutionResult(
                case_id=test_case.id,
                error=f"Runtime error: {e}",
            )

    def _compare_outputs(
        self,
        output: dict[str, Any],
        expected: dict[str, Any],
        tolerance: float = 1.0,
    ) -> bool:
        """Compare outputs with tolerance for numerical values."""
        # Get the main output value
        out_val = None
        for key in output:
            out_val = output[key]
            break

        # Get the expected value
        exp_val = None
        for key in expected:
            exp_val = expected[key]
            break

        if out_val is None or exp_val is None:
            return False

        # Compare with tolerance for numbers
        if isinstance(out_val, (int, float)) and isinstance(exp_val, (int, float)):
            return abs(out_val - exp_val) <= tolerance

        return out_val == exp_val


def get_rac_us_path() -> Path | None:
    """Find rac-us directory relative to this package."""
    candidates = [
        Path.home() / "RulesFoundation" / "rac-us",
        Path(__file__).parent.parent.parent.parent / "rac-us",
        Path.cwd().parent / "rac-us",
    ]
    for path in candidates:
        if path.exists() and (path / "statute").exists():
            return path
    return None


def load_rac_us_parameters() -> NewParameterStore | None:
    """Load parameters from rac-us repository statute/ directory."""
    us_path = get_rac_us_path()
    if us_path:
        # Only load from statute/ to avoid .venv and other dirs
        statute_path = us_path / "statute"
        if statute_path.exists():
            return load_parameters(statute_path)
    return None


def get_default_parameters() -> dict:
    """Get default 2024 IRS parameters for testing."""
    return {
        "gov": {
            "irs": {
                "eitc": {
                    "phase_in_rate": {
                        0: 0.0765,
                        1: 0.34,
                        2: 0.40,
                        3: 0.45,
                    },
                    "earned_income_amount": {
                        0: 7840,
                        1: 11750,
                        2: 16510,
                        3: 16510,
                    },
                    "max_amount": {
                        0: 632,
                        1: 4213,
                        2: 6960,
                        3: 7830,
                    },
                    "phase_out_start": {
                        "SINGLE": {0: 9800, 1: 21560, 2: 21560, 3: 21560},
                        "JOINT": {0: 16370, 1: 28120, 2: 28120, 3: 28120},
                    },
                    "phase_out_rate": {
                        0: 0.0765,
                        1: 0.1598,
                        2: 0.2106,
                        3: 0.2106,
                    },
                },
                "standard_deduction": {
                    "SINGLE": 14600,
                    "JOINT": 29200,
                    "MARRIED_FILING_SEPARATELY": 14600,
                    "HEAD_OF_HOUSEHOLD": 21900,
                },
                "ctc": {
                    "amount": 2000,
                    "max_refundable": 1700,
                    "phase_out_start": {
                        "SINGLE": 200000,
                        "JOINT": 400000,
                    },
                    "phase_out_rate": 0.05,
                },
                "savers_credit": {
                    "rate_thresholds": {
                        "SINGLE": [23000, 25000, 38250],
                        "JOINT": [46000, 50000, 76500],
                    },
                    "rates": [0.50, 0.20, 0.10, 0.00],
                    "max_contribution": 2000,
                },
                "salt_cap": {
                    "SINGLE": 10000,
                    "JOINT": 10000,
                    "MARRIED_FILING_SEPARATELY": 5000,
                    "HEAD_OF_HOUSEHOLD": 10000,
                },
                "cdcc": {
                    "max_expenses": {
                        1: 3000,
                        2: 6000,
                    },
                    "rate_schedule": [
                        {"threshold": 15000, "rate": 0.35},
                        {"threshold": 17000, "rate": 0.34},
                        {"threshold": 19000, "rate": 0.33},
                        {"threshold": 21000, "rate": 0.32},
                        {"threshold": 23000, "rate": 0.31},
                        {"threshold": 25000, "rate": 0.30},
                        {"threshold": 27000, "rate": 0.29},
                        {"threshold": 29000, "rate": 0.28},
                        {"threshold": 31000, "rate": 0.27},
                        {"threshold": 33000, "rate": 0.26},
                        {"threshold": 35000, "rate": 0.25},
                        {"threshold": 37000, "rate": 0.24},
                        {"threshold": 39000, "rate": 0.23},
                        {"threshold": 41000, "rate": 0.22},
                        {"threshold": 43000, "rate": 0.21},
                        {"threshold": float("inf"), "rate": 0.20},
                    ],
                },
                # §152(c)(3) - Qualifying child age requirements
                "qualifying_child": {
                    "age_limit_general": 19,  # Under 19 at end of year
                    "age_limit_student": 24,  # Under 24 if full-time student
                },
            },
        },
    }
