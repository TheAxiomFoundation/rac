"""Compile Python formula syntax to vectorized NumPy operations.

Supports a restricted subset of Python that can be vectorized:

ALLOWED:
  - Assignments: x = expr
  - Arithmetic: +, -, *, /, //, %, **
  - Comparisons: ==, !=, <, <=, >, >=
  - Boolean ops: and, or, not
  - If/elif/else (transformed to np.where)
  - Builtins: max, min, abs, sum, round
  - Return statements
  - Comments

NOT ALLOWED (raises error):
  - Loops: for, while
  - Comprehensions: [x for x in y]
  - Function definitions: def, lambda
  - Classes: class
  - Try/except
  - With statements
  - Import statements
  - Walrus operator: :=
  - Augmented assignment: +=, -=, etc.

Example:
    if filing_status == 'JOINT':
        threshold = 250000
    elif filing_status == 'SEPARATE':
        threshold = 125000
    else:
        threshold = 200000

Compiles to:
    threshold = np.where(
        filing_status == 'JOINT', 250000,
        np.where(filing_status == 'SEPARATE', 125000, 200000)
    )
"""

import ast
from typing import Any
import numpy as np


class UnsupportedSyntaxError(Exception):
    """Raised when formula contains unsupported Python syntax."""
    pass


class FormulaValidator(ast.NodeVisitor):
    """Validate that formula only uses allowed Python constructs."""

    FORBIDDEN_NODES = {
        ast.For: "for loops",
        ast.While: "while loops",
        ast.FunctionDef: "function definitions",
        ast.AsyncFunctionDef: "async function definitions",
        ast.ClassDef: "class definitions",
        ast.Lambda: "lambda expressions",
        ast.ListComp: "list comprehensions",
        ast.SetComp: "set comprehensions",
        ast.DictComp: "dict comprehensions",
        ast.GeneratorExp: "generator expressions",
        ast.Try: "try/except blocks",
        ast.With: "with statements",
        ast.AsyncWith: "async with statements",
        ast.AsyncFor: "async for loops",
        ast.Import: "import statements",
        ast.ImportFrom: "import statements",
        ast.Global: "global statements",
        ast.Nonlocal: "nonlocal statements",
        ast.Raise: "raise statements",
        ast.Assert: "assert statements",
        ast.Delete: "delete statements",
        ast.AugAssign: "augmented assignment (+=, -=, etc.)",
        ast.NamedExpr: "walrus operator (:=)",
        ast.Yield: "yield expressions",
        ast.YieldFrom: "yield from expressions",
        ast.Await: "await expressions",
    }

    def __init__(self):
        self.errors = []

    def validate(self, tree: ast.AST) -> list[str]:
        """Validate AST and return list of errors."""
        self.errors = []
        self.visit(tree)
        return self.errors

    def visit(self, node: ast.AST):
        """Check each node against forbidden list."""
        node_type = type(node)
        if node_type in self.FORBIDDEN_NODES:
            desc = self.FORBIDDEN_NODES[node_type]
            line = getattr(node, 'lineno', '?')
            self.errors.append(f"Line {line}: {desc} not allowed in formulas")
        self.generic_visit(node)


class PythonFormulaCompiler(ast.NodeTransformer):
    """Transform Python AST to vectorized operations."""

    def __init__(self, parameters: dict[str, Any] = None):
        self.parameters = parameters or {}
        self.vectorized_code = []

    def compile(self, source: str, validate: bool = True) -> str:
        """Compile Python formula to vectorized Python code.

        Args:
            source: Python source code
            validate: If True, reject unsupported syntax

        Raises:
            UnsupportedSyntaxError: If formula uses forbidden constructs
        """
        tree = ast.parse(source)

        if validate:
            validator = FormulaValidator()
            errors = validator.validate(tree)
            if errors:
                raise UnsupportedSyntaxError(
                    "Formula contains unsupported syntax:\n" +
                    "\n".join(f"  - {e}" for e in errors)
                )

        transformed = self.visit(tree)
        ast.fix_missing_locations(transformed)
        return ast.unparse(transformed)

    def visit_If(self, node: ast.If) -> ast.AST:
        """Transform if/elif/else chains to np.where.

        Pattern:
            if cond1:
                x = val1
            elif cond2:
                x = val2
            else:
                x = val3

        Becomes:
            x = np.where(cond1, val1, np.where(cond2, val2, val3))
        """
        # Check if this is a simple assignment pattern
        assignments = self._extract_conditional_assignments(node)
        if assignments:
            target, where_expr = self._build_where_chain(assignments)
            return ast.Assign(
                targets=[ast.Name(id=target, ctx=ast.Store())],
                value=where_expr
            )

        # Fall back to visiting children normally
        return self.generic_visit(node)

    def _extract_conditional_assignments(self, node: ast.If) -> list[tuple]:
        """Extract (condition, target, value) tuples from if/elif/else chain.

        Returns None if pattern doesn't match simple conditional assignment.
        """
        assignments = []
        current = node
        target_name = None

        while current:
            # Each branch should have exactly one assignment
            if len(current.body) != 1:
                return None
            stmt = current.body[0]
            if not isinstance(stmt, ast.Assign):
                return None
            if len(stmt.targets) != 1:
                return None
            if not isinstance(stmt.targets[0], ast.Name):
                return None

            name = stmt.targets[0].id
            if target_name is None:
                target_name = name
            elif name != target_name:
                return None  # Different targets in branches

            assignments.append((current.test, stmt.value))

            # Handle elif chain
            if len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
                current = current.orelse[0]
            elif len(current.orelse) == 1 and isinstance(current.orelse[0], ast.Assign):
                # Final else branch
                else_stmt = current.orelse[0]
                if (isinstance(else_stmt.targets[0], ast.Name) and
                    else_stmt.targets[0].id == target_name):
                    assignments.append((None, else_stmt.value))  # None = else
                current = None
            elif len(current.orelse) == 0:
                return None  # No else branch - can't vectorize safely
            else:
                return None

        return (target_name, assignments) if assignments else None

    def _build_where_chain(self, extracted: tuple) -> tuple[str, ast.AST]:
        """Build nested np.where from extracted assignments."""
        target_name, assignments = extracted

        # Start from the innermost (else) and work outward
        # assignments is [(cond1, val1), (cond2, val2), (None, else_val)]
        result = None

        for cond, value in reversed(assignments):
            if cond is None:
                # This is the else branch
                result = self.visit(value)
            else:
                # Wrap in np.where(cond, value, result)
                result = ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id='np', ctx=ast.Load()),
                        attr='where',
                        ctx=ast.Load()
                    ),
                    args=[self.visit(cond), self.visit(value), result],
                    keywords=[]
                )

        return target_name, result

    def visit_Return(self, node: ast.Return) -> ast.AST:
        """Transform return statement to assignment to _return_."""
        if node.value is None:
            return ast.Pass()
        return ast.Assign(
            targets=[ast.Name(id='_return_', ctx=ast.Store())],
            value=self.visit(node.value)
        )

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        """Transform 'and'/'or' to bitwise &/| for numpy arrays."""
        # and -> &, or -> |
        if isinstance(node.op, ast.And):
            op = ast.BitAnd()
        else:  # ast.Or
            op = ast.BitOr()

        # Chain: a and b and c -> (a & b) & c
        result = self.visit(node.values[0])
        for value in node.values[1:]:
            result = ast.BinOp(
                left=result,
                op=op,
                right=self.visit(value)
            )
        return result

    def visit_Call(self, node: ast.Call) -> ast.AST:
        """Transform built-in functions to numpy equivalents."""
        if isinstance(node.func, ast.Name):
            name = node.func.id
            # Map Python builtins to numpy
            numpy_funcs = {'max': 'maximum', 'min': 'minimum', 'abs': 'abs'}
            if name in numpy_funcs:
                return ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id='np', ctx=ast.Load()),
                        attr=numpy_funcs[name],
                        ctx=ast.Load()
                    ),
                    args=[self.visit(arg) for arg in node.args],
                    keywords=node.keywords
                )
        return self.generic_visit(node)


def compile_formula(source: str, parameters: dict = None) -> str:
    """Compile a Python formula to vectorized code.

    Args:
        source: Python source code for the formula
        parameters: Dict of parameter names to values

    Returns:
        Vectorized Python code string
    """
    compiler = PythonFormulaCompiler(parameters)
    return compiler.compile(source)


def execute_formula(
    source: str,
    inputs: dict[str, np.ndarray],
    parameters: dict[str, Any] = None,
    return_var: str = None,
) -> dict[str, np.ndarray] | np.ndarray:
    """Execute a Python formula with vectorized operations.

    Args:
        source: Python source code for the formula
        inputs: Dict of input variable names to arrays
        parameters: Dict of parameter names to values
        return_var: If specified, return just this variable as array

    Returns:
        Dict of variable name -> result arrays, or single array if return_var
    """
    # Compile to vectorized code
    compiled = compile_formula(source, parameters)

    # Build execution namespace
    namespace = {'np': np}
    namespace.update(parameters or {})
    namespace.update(inputs)

    # Execute and capture results
    exec(compiled, namespace)

    # Handle return statement - look for _return_ variable
    if '_return_' in namespace:
        if return_var:
            return namespace['_return_']
        return {'_return_': namespace['_return_']}

    # Extract non-input results
    input_keys = set(inputs.keys()) | set(parameters.keys() if parameters else [])
    input_keys.add('np')
    results = {k: v for k, v in namespace.items()
               if k not in input_keys and not k.startswith('_') and isinstance(v, (np.ndarray, int, float))}

    if return_var:
        return results.get(return_var, np.zeros_like(list(inputs.values())[0]))

    return results


class PythonFormulaExecutor:
    """Executor for Python-syntax .rac formulas.

    Simpler alternative to VectorizedExecutor when formulas use Python syntax.
    """

    def __init__(self, parameters: dict[str, Any] = None):
        self.parameters = parameters or {}

    def execute(
        self,
        formula: str,
        inputs: dict[str, np.ndarray],
        output_var: str = None,
    ) -> np.ndarray | dict[str, np.ndarray]:
        """Execute a Python formula.

        Args:
            formula: Python formula source code
            inputs: Dict of input variable names to arrays
            output_var: Name of variable to return (optional)

        Returns:
            Computed array(s)
        """
        return execute_formula(
            formula,
            inputs,
            self.parameters,
            return_var=output_var,
        )


# Quick test
if __name__ == "__main__":
    # Test valid formula
    formula = '''
# Section 1411(b): Threshold based on filing status
if filing_status == 'JOINT':
    threshold = threshold_joint
elif filing_status == 'SEPARATE':
    threshold = threshold_separate
else:
    threshold = threshold_other

excess = max(0, magi - threshold)
result = min(nii, excess) * rate
'''

    print("=== Valid Formula ===")
    print(formula)
    print("\nCompiled to:")
    print(compile_formula(formula))

    # Test execution
    inputs = {
        'filing_status': np.array(['JOINT', 'SEPARATE', 'SINGLE', 'JOINT', 'SINGLE']),
        'magi': np.array([300000, 150000, 250000, 200000, 180000]),
        'nii': np.array([50000, 30000, 40000, 10000, 20000]),
    }
    params = {
        'threshold_joint': 250000,
        'threshold_separate': 125000,
        'threshold_other': 200000,
        'rate': 0.038,
    }

    print("\nInputs:")
    for k, v in inputs.items():
        print(f"  {k}: {v}")

    results = execute_formula(formula, inputs, params)
    print("\nResults:")
    for k, v in results.items():
        print(f"  {k}: {v}")

    # Test invalid formulas
    print("\n=== Invalid Formulas (should error) ===")

    invalid_formulas = [
        ("for loop", "for i in range(10):\n    x = i"),
        ("while loop", "while x > 0:\n    x = x - 1"),
        ("list comprehension", "x = [i * 2 for i in items]"),
        ("lambda", "f = lambda x: x * 2"),
        ("function def", "def helper(x):\n    return x * 2"),
        ("augmented assign", "x += 1"),
        ("try/except", "try:\n    x = 1\nexcept:\n    x = 0"),
    ]

    for name, code in invalid_formulas:
        try:
            compile_formula(code)
            print(f"  {name}: FAILED (should have raised error)")
        except UnsupportedSyntaxError as e:
            print(f"  {name}: correctly rejected")
        except Exception as e:
            print(f"  {name}: unexpected error: {e}")
