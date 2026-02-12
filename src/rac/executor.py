"""Code executor for running generated RAC DSL."""

import re
from typing import Any

from .types import ExecutionResult, GeneratedCode, TestCase


class Executor:
    """Executes generated code against test cases.

    Supports three code formats:
    1. Python functions (def calculate)
    2. New RAC DSL (variable { ... })
    3. Legacy YAML-like DSL (variable name:)
    """

    def __init__(self, parameters: dict | None = None):
        """Initialize with optional parameter values."""
        self.parameters = parameters

    def execute(
        self,
        code: GeneratedCode,
        test_cases: list[TestCase],
    ) -> list[ExecutionResult]:
        """Execute code against test cases.

        Supports Python functions, new DSL, and legacy DSL.
        """
        source = code.source.strip()

        # Check if this is Python code (has def calculate)
        if "def calculate" in source:
            return self._execute_python(source, test_cases)

        # Check if this is new RAC DSL (has "variable name {")
        if re.search(r"variable\s+\w+\s*\{", source):
            return self._execute_new_dsl(source, test_cases)

        # Otherwise treat as legacy DSL
        parsed = self._parse(source)
        if parsed.get("error"):
            return [
                ExecutionResult(
                    case_id=tc.id,
                    error=f"Parse error: {parsed['error']}",
                )
                for tc in test_cases
            ]

        results = []
        for tc in test_cases:
            result = self._execute_case(parsed, tc)
            results.append(result)

        return results

    def _execute_new_dsl(
        self,
        source: str,
        test_cases: list[TestCase],
    ) -> list[ExecutionResult]:
        """Execute new RAC DSL code."""
        try:
            from .dsl_executor import DSLExecutor, get_default_parameters

            executor = DSLExecutor(parameters=self.parameters or get_default_parameters())
            return executor.execute(source, test_cases)
        except Exception as e:
            return [
                ExecutionResult(case_id=tc.id, error=f"DSL execution error: {e}")
                for tc in test_cases
            ]

    def _execute_python(
        self,
        source: str,
        test_cases: list[TestCase],
    ) -> list[ExecutionResult]:
        """Execute Python code against test cases."""
        # Extract just the function definition
        # Find the code block if wrapped in markdown
        if "```python" in source:
            start = source.find("```python") + 9
            end = source.find("```", start)
            source = source[start:end].strip()
        elif "```" in source:
            start = source.find("```") + 3
            end = source.find("```", start)
            source = source[start:end].strip()

        # Compile the function
        try:
            exec_globals = {"__builtins__": __builtins__}
            exec(source, exec_globals)
            calculate_fn = exec_globals.get("calculate")
            if not calculate_fn:
                return [
                    ExecutionResult(case_id=tc.id, error="No 'calculate' function found")
                    for tc in test_cases
                ]
        except Exception as e:
            return [
                ExecutionResult(case_id=tc.id, error=f"Compile error: {e}") for tc in test_cases
            ]

        # Execute each test case
        results = []
        for tc in test_cases:
            try:
                output = calculate_fn(tc.inputs)
                match = self._compare_outputs(output, tc.expected, tolerance=1.0)
                results.append(
                    ExecutionResult(
                        case_id=tc.id,
                        output=output,
                        expected=tc.expected,
                        match=match,
                    )
                )
            except Exception as e:
                results.append(
                    ExecutionResult(
                        case_id=tc.id,
                        error=f"Runtime error: {e}",
                    )
                )

        return results

    def _parse(self, source: str) -> dict[str, Any]:
        """Parse RAC DSL into a structured representation.

        This is a simplified parser for v1 - just extracts key components.
        """
        try:
            result = {
                "name": None,
                "entity": None,
                "period": None,
                "dtype": None,
                "references": {},
                "formula": None,
            }

            lines = source.strip().split("\n")

            # Extract variable name
            for line in lines:
                if line.strip().startswith("variable "):
                    match = re.match(r"variable\s+(\w+):", line.strip())
                    if match:
                        result["name"] = match.group(1)
                    break

            # Extract simple key-value fields
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("entity:"):
                    result["entity"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("period:"):
                    result["period"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("dtype:"):
                    result["dtype"] = stripped.split(":", 1)[1].strip()

            # Extract references block
            in_references = False
            for line in lines:
                stripped = line.strip()
                if stripped == "references:":
                    in_references = True
                    continue
                if in_references:
                    if stripped.startswith("formula:"):
                        break
                    if ":" in stripped and not stripped.startswith("#"):
                        key, value = stripped.split(":", 1)
                        result["references"][key.strip()] = value.strip()

            # Extract formula
            in_formula = False
            formula_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped == "formula:":
                    in_formula = True
                    continue
                if in_formula and stripped and not stripped.startswith("#"):
                    formula_lines.append(stripped)

            result["formula"] = " ".join(formula_lines) if formula_lines else None

            return result

        except Exception as e:
            return {"error": str(e)}

    def _execute_case(
        self,
        parsed: dict[str, Any],
        test_case: TestCase,
    ) -> ExecutionResult:
        """Execute parsed code against a single test case."""
        try:
            # Get formula
            formula = parsed.get("formula")
            if not formula:
                return ExecutionResult(
                    case_id=test_case.id,
                    error="No formula found in parsed code",
                )

            # Build evaluation context from inputs
            context = dict(test_case.inputs)

            # Add mock parameter values (these would come from param store in production)
            context["param"] = self._get_mock_params()

            # Add standard deduction values
            context["standard_deduction_amounts"] = {
                "SINGLE": 14600,
                "JOINT": 29200,
                "MARRIED_FILING_SEPARATELY": 14600,
                "HEAD_OF_HOUSEHOLD": 21900,
            }

            # Add SALT cap values
            context["salt_cap_amounts"] = {
                "SINGLE": 10000,
                "JOINT": 10000,
                "MARRIED_FILING_SEPARATELY": 5000,
                "HEAD_OF_HOUSEHOLD": 10000,
            }

            # Add saver's credit parameters
            context["savers_credit_params"] = {
                "thresholds": [46000, 50000, 76500],
                "rates": [0.50, 0.20, 0.10, 0.00],
            }

            # Evaluate formula
            output_value = self._evaluate_formula(formula, context, parsed.get("references", {}))

            # Compare to expected
            var_name = parsed.get("name", "output")
            output = {var_name: output_value}

            # Check if it matches expected (within tolerance for Money)
            match = self._compare_outputs(output, test_case.expected, tolerance=1.0)

            return ExecutionResult(
                case_id=test_case.id,
                output=output,
                expected=test_case.expected,
                match=match,
            )

        except Exception as e:
            return ExecutionResult(
                case_id=test_case.id,
                error=f"Runtime error: {str(e)}",
            )

    def _get_mock_params(self) -> dict:
        """Get mock parameter values for EITC.

        In production, these come from the parameter store.
        2024 values from IRS.
        """
        return {
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
                    "max_credit": {
                        0: 600,
                        1: 3995,
                        2: 6604,
                        3: 7430,
                    },
                }
            }
        }

    def _evaluate_formula(
        self,
        formula: str,
        context: dict[str, Any],
        references: dict[str, str],
    ) -> float:
        """Evaluate a formula string.

        This is a simple interpreter for v1. Production would compile to bytecode.
        """
        expr = formula

        # First, resolve reference aliases to their paths/values
        # Build a map of what each alias resolves to
        resolved = {}
        for alias, path in references.items():
            if path.startswith("param."):
                # Parameter reference - navigate to the dict
                resolved[alias] = self._navigate_path(path, context)
            else:
                # Variable reference - get direct value
                leaf = path.split("/")[-1]
                resolved[alias] = context.get(leaf, 0)

        # Get the n_children value for indexing
        n_children = context.get("n_qualifying_children", context.get("n_children", 0))

        # Substitute values into formula
        # Handle indexed references like earned_income_amount[n_qualifying_children]
        # Sort by length descending to avoid partial matches (e.g., earned_income before earned_income_amount)
        for alias, value in sorted(resolved.items(), key=lambda x: len(x[0]), reverse=True):
            if isinstance(value, dict):
                # This is a parameter dict - substitute with indexed value
                indexed_pattern = f"{alias}\\[\\w+\\]"
                if __import__("re").search(indexed_pattern, expr):
                    indexed_value = value.get(n_children, value.get(0, 0))
                    expr = __import__("re").sub(indexed_pattern, str(indexed_value), expr)
                else:
                    expr = expr.replace(alias, str(value.get(n_children, value.get(0, 0))))
            else:
                expr = expr.replace(alias, str(value))

        # Handle if-then-else expressions (convert to Python ternary)
        expr = self._convert_conditionals(expr)

        # Evaluate the expression
        # SECURITY NOTE: In production, use a proper expression parser, not eval
        # This is only for prototype/testing
        try:
            # Add string comparison support
            safe_builtins = {"min": min, "max": max, "abs": abs}
            result = eval(expr, {"__builtins__": safe_builtins}, context)
            return float(result)
        except Exception as e:
            raise ValueError(f"Failed to evaluate '{expr}': {e}")

    def _convert_conditionals(self, expr: str) -> str:
        """Convert DSL if-then-else to Python ternary expressions."""
        # Pattern: if <cond> then <true_val> else <false_val>
        # Convert to: (<true_val> if <cond> else <false_val>)

        # Handle nested if-then-else by working from innermost out
        max_iterations = 10
        for _ in range(max_iterations):
            # Find innermost if-then-else (one without nested if in its branches)
            match = re.search(
                r"\bif\s+(.+?)\s+then\s+([^if]+?)\s+else\s+([^if]+?)(?=\s*$|\s*\))",
                expr,
                re.IGNORECASE,
            )
            if not match:
                # Try simpler pattern for remaining cases
                match = re.search(r"\bif\s+(.+?)\s+then\s+(.+?)\s+else\s+(.+)", expr, re.IGNORECASE)
            if not match:
                break

            cond, true_val, false_val = match.groups()
            # Convert to Python ternary
            python_expr = f"({true_val.strip()} if {cond.strip()} else {false_val.strip()})"
            expr = expr[: match.start()] + python_expr + expr[match.end() :]

        return expr

    def _expand_indexing(self, expr: str, context: dict[str, Any]) -> str:
        """Expand array indexing like param.irs.eitc.phase_in_rate[n_qualifying_children]."""
        # Find patterns like xxx[variable_name]
        pattern = r"(\w+(?:\.\w+)*)\[(\w+)\]"

        def replace_index(match):
            base_path = match.group(1)
            index_var = match.group(2)

            # Get the index value
            index_value = context.get(index_var)
            if index_value is None:
                # Try n_children as fallback
                index_value = context.get("n_children", 0)

            # Navigate to the base value
            value = self._navigate_path(base_path, context)
            if isinstance(value, dict):
                return str(value.get(index_value, value.get(0, 0)))
            return str(value)

        return re.sub(pattern, replace_index, expr)

    def _resolve_reference(self, path: str, context: dict[str, Any]) -> Any:
        """Resolve a reference path to a value."""
        # Handle param paths
        if path.startswith("param."):
            return self._navigate_path(path, context)

        # Handle direct context values
        # Path like "us/irs/income/earned_income" -> use leaf as key
        leaf = path.split("/")[-1]
        if leaf in context:
            return context[leaf]

        return 0

    def _navigate_path(self, path: str, context: dict[str, Any]) -> Any:
        """Navigate a dot-separated path in context."""
        parts = path.split(".")
        current = context

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return 0

        return current

    def _compare_outputs(
        self,
        output: dict[str, Any],
        expected: dict[str, Any],
        tolerance: float = 1.0,
    ) -> bool:
        """Compare outputs with tolerance for numerical values."""
        # Find the main output value (EITC)
        out_val = None
        for key in ["eitc_phase_in_credit", "eitc", "output"]:
            if key in output:
                out_val = output[key]
                break
        if out_val is None:
            out_val = list(output.values())[0] if output else 0

        exp_val = None
        for key in ["eitc_phase_in_credit", "eitc", "output"]:
            if key in expected:
                exp_val = expected[key]
                break
        if exp_val is None:
            exp_val = list(expected.values())[0] if expected else 0

        # Compare with tolerance
        if isinstance(out_val, (int, float)) and isinstance(exp_val, (int, float)):
            return abs(out_val - exp_val) <= tolerance

        return out_val == exp_val
