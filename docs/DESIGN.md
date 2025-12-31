# Cosilico Core Design Document

## Executive summary

Cosilico Core is a policy rules engine designed from first principles for modern use cases:

1. **Compile-time analysis** - Build complete dependency graph before execution
2. **Multi-target output** - Generate Python, JavaScript, WASM, SQL, Spark
3. **Memory efficiency** - Copy-on-write for scenarios, streaming for scale
4. **Type safety** - Catch errors at definition time, not runtime
5. **Permissive license** - Apache 2.0 enables enterprise adoption

This document outlines the architecture, key abstractions, and implementation strategy.

---

## 1. Problem statement

### Current pain points

Policy rules engines face several challenges:

| Challenge | Impact | Current solutions |
|-----------|--------|-------------------|
| **Scale** | Census-scale runs take >12 hours | Batch overnight jobs |
| **Latency** | API response times >1s | Heavy caching |
| **Deployment** | Requires Python runtime everywhere | Containerization |
| **Memory** | 8-64GB RAM for microsimulation | Cloud instances ($200-800/mo) |
| **Correctness** | Runtime errors in production | Extensive testing |
| **Licensing** | AGPL prevents enterprise use | Avoid or rewrite |

### Target use cases

1. **Microsimulation**: 100M+ households, research analysis
2. **Real-time API**: Production services
3. **Browser calculators**: No backend, offline-capable
4. **Benefit administration**: Auditable calculations
5. **Financial services**: Tax planning, portfolio optimization

### Design targets

We set the following targets. These are goals, not demonstrated results:

- **Scale**: Process 130M households in <1 hour on 32-core commodity hardware
- **Latency**: API p99 <100ms for single-household calculations
- **Bundle size**: <500KB browser bundle for typical calculator
- **Type safety**: Compile-time type checking (no runtime type errors by construction)
- **Auditability**: Every calculation traces to parameters, variables, and legal citations used

---

## 2. Architecture overview

### Language choice: custom DSL

Cosilico uses a purpose-built domain-specific language (`.rac` files) rather than Python decorators. See **[DSL.md](./DSL.md)** for the full specification.

**Key reasons for a custom DSL:**

1. **Safety** - Untrusted code (AI-generated, user-submitted) cannot escape sandbox
2. **Multi-target compilation** - Clean IR enables Python, JS, WASM, SQL, Spark backends
3. **Legal-first design** - Citations are syntax, not comments
4. **AI-native** - Constrained grammar is easier to generate correctly
5. **Formal verification** - Amenable to proving properties

```cosilico
# Example: EITC in Cosilico DSL
variable eitc {
  entity TaxUnit
  period Year
  dtype Money
  reference "26 USC § 32"

  formula {
    let phase_in = variable(eitc_phase_in)
    let max_credit = parameter(gov.irs.eitc.max_amount)
    return max(0, min(phase_in, max_credit) - variable(eitc_phase_out))
  }
}
```

### High-level design

```
┌─────────────────────────────────────────────────────────────────────┐
│                          DEFINITION LAYER                            │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │   .rac  │  │  parameters  │  │   entities   │               │
│  │    files     │  │    .yaml     │  │    .yaml     │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│         │                 │                 │                        │
│         └────────────────┬┴─────────────────┘                        │
│                          ↓                                           │
│                  ┌──────────────┐                                    │
│                  │    Parser    │                                    │
│                  │ (Tree-sitter │                                    │
│                  │    grammar)  │                                    │
│                  └──────────────┘                                    │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│                         ANALYSIS LAYER                               │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │  Dependency  │  │    Type      │  │   Period     │               │
│  │    Graph     │  │   Checker    │  │  Validator   │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│         │                 │                 │                        │
│         └────────────────┬┴─────────────────┘                        │
│                          ↓                                           │
│                  ┌──────────────┐                                    │
│                  │  Validated   │                                    │
│                  │     IR       │                                    │
│                  └──────────────┘                                    │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        OPTIMIZATION LAYER                            │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │    Dead      │  │   Constant   │  │    Common    │               │
│  │    Code      │  │   Folding    │  │  Subexpr     │               │
│  │  Elimination │  │              │  │ Elimination  │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│                          ↓                                           │
│                  ┌──────────────┐                                    │
│                  │  Optimized   │                                    │
│                  │     IR       │                                    │
│                  └──────────────┘                                    │
└─────────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        GENERATION LAYER                              │
│                                                                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │
│  │ Python  │ │   JS    │ │  WASM   │ │   SQL   │ │  Spark  │       │
│  │Generator│ │Generator│ │Generator│ │Generator│ │Generator│       │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘       │
│       ↓           ↓           ↓           ↓           ↓             │
│   ┌───────┐   ┌───────┐   ┌───────┐   ┌───────┐   ┌───────┐        │
│   │.py    │   │.js    │   │.wasm  │   │.sql   │   │.py    │        │
│   │NumPy  │   │TypedA │   │Native │   │Query  │   │PySpark│        │
│   └───────┘   └───────┘   └───────┘   └───────┘   └───────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

### Component responsibilities

| Component | Responsibility | Key outputs |
|-----------|---------------|-------------|
| **Parser** | Parse .rac files via Tree-sitter grammar | Raw AST nodes |
| **Dependency Graph** | Build variable dependency DAG | Topological order |
| **Type Checker** | Validate types, periods, entities | Type-annotated IR |
| **Period Validator** | Check period compatibility | Period-checked IR |
| **Optimizer** | Simplify, inline, eliminate dead code | Optimized IR |
| **Generators** | Emit target-specific code | Executable output |

---

## 3. Core abstractions

### 3.1 Variables

Variables are the fundamental unit of calculation.

```python
@dataclass(frozen=True)
class VariableSpec:
    """Specification of a variable."""
    name: str
    entity: EntitySpec
    period_type: PeriodType
    dtype: DataType
    formula: Optional[FormulaSpec]
    label: str
    description: str
    references: List[str]
    defined_for: Optional[str]  # Conditional computation
    default_value: Any
```

**Formula Specification:**

```python
@dataclass(frozen=True)
class FormulaSpec:
    """Specification of a formula."""
    parameters: List[str]          # Parameter paths used
    variables: List[str]           # Variable dependencies
    period_refs: List[PeriodRef]   # Period references (current, previous, etc.)
    entity_ops: List[EntityOp]     # Aggregations, broadcasts
    expression: IRExpression       # The computation itself
```

**Key Design Decisions:**

1. **Immutable specs** - Once parsed, specifications don't change
2. **Explicit dependencies** - All dependencies captured in spec
3. **Typed periods** - Period type is part of signature, not runtime
4. **No hidden state** - Everything needed is in the spec

### 3.2 Parameters

Parameters represent time-varying policy values.

```python
@dataclass(frozen=True)
class ParameterSpec:
    """Specification of a parameter."""
    path: str                      # e.g., "gov.irs.income.brackets"
    dtype: ParameterType           # Scalar, Scale, Node
    values: List[DatedValue]       # Time-varying values
    metadata: ParameterMetadata    # Unit, references, etc.


@dataclass(frozen=True)
class DatedValue:
    """A parameter value with effective date."""
    date: Date
    value: Any
    reference: Optional[str]
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class BracketScale:
    """A tax bracket scale."""
    brackets: List[Bracket]

    def calc(self, value: Money) -> Money:
        """Calculate tax through brackets."""
        ...


@dataclass(frozen=True)
class Bracket:
    """A single tax bracket."""
    threshold: Money
    rate: Optional[Rate]           # For marginal rate scales
    amount: Optional[Money]        # For flat amount scales
```

**Key Design Decisions:**

1. **Path-based addressing** - Hierarchical parameter organization
2. **Type-safe scales** - Bracket calculations are explicit, not magic
3. **Rich metadata** - References, units, effective dates tracked
4. **Immutable values** - Parameters frozen at compile time

### 3.3 Entities

Entities model the structure of calculations.

```python
@dataclass(frozen=True)
class EntitySpec:
    """Specification of an entity type."""
    name: str
    plural: str
    is_person: bool
    contains: Optional[str]        # Parent entity (for groups)
    roles: List[RoleSpec]          # Roles within group


@dataclass(frozen=True)
class RoleSpec:
    """A role within a group entity."""
    name: str
    max_count: Optional[int]
    description: str


@dataclass(frozen=True)
class EntityHierarchy:
    """The complete entity hierarchy."""
    entities: Dict[str, EntitySpec]
    person_entity: str
    relationships: List[EntityRelationship]

    def aggregation_path(self, from_entity: str, to_entity: str) -> List[str]:
        """Find path for aggregating from child to parent."""
        ...

    def broadcast_path(self, from_entity: str, to_entity: str) -> List[str]:
        """Find path for broadcasting from parent to child."""
        ...
```

**Entity Operations:**

```python
class EntityOp(Enum):
    SUM = "sum"           # Sum child values to parent
    ANY = "any"           # True if any child is true
    ALL = "all"           # True if all children are true
    MAX = "max"           # Maximum child value
    MIN = "min"           # Minimum child value
    COUNT = "count"       # Count children
    FIRST = "first"       # First child (with role)
    BROADCAST = "broadcast"  # Parent value to all children
```

**Key Design Decisions:**

1. **Multi-level hierarchy** - Not just person → group, but arbitrary depth
2. **Role-aware** - Can aggregate/filter by role (head, spouse, dependent)
3. **Path-finding** - Automatic discovery of aggregation/broadcast paths
4. **Explicit operations** - No magic, all entity ops are in IR

### 3.4 Periods

Periods represent time with explicit algebra.

```python
class PeriodType(Enum):
    INSTANT = "instant"    # Point in time
    DAY = "day"           # Single day
    MONTH = "month"       # Calendar month
    YEAR = "year"         # Calendar year
    ETERNITY = "eternity" # Never changes


@dataclass(frozen=True)
class Period:
    """A time period."""
    type: PeriodType
    start: Date
    size: int = 1

    @property
    def end(self) -> Date:
        ...

    def contains(self, other: 'Period') -> bool:
        ...

    def subdivide(self, unit: PeriodType) -> List['Period']:
        ...

    def offset(self, n: int) -> 'Period':
        """Return period n units before/after this one."""
        ...


class QuantityType(Enum):
    FLOW = "flow"    # Accumulates over time (income)
    STOCK = "stock"  # Point-in-time value (wealth)
```

**Period Conversion Rules:**

| From | To | Flow | Stock |
|------|-----|------|-------|
| Month | Year | Sum 12 months | Take December value |
| Year | Month | Divide by 12 | Use year value |
| Day | Month | Sum days | Take last day |

**Key Design Decisions:**

1. **Explicit types** - Period type in variable signature
2. **Automatic conversion** - Flow/Stock semantics explicit
3. **Period arithmetic** - Offset, subdivide operations
4. **Immutable** - Periods are value types

---

## 4. Intermediate representation (IR)

The IR is the key to multi-target compilation.

### 4.1 IR node types

```python
@dataclass(frozen=True)
class IRNode:
    """Base for all IR nodes."""
    id: str
    dtype: DataType
    entity: str
    period: Period


@dataclass(frozen=True)
class IRInput(IRNode):
    """An input variable."""
    name: str
    default: Any


@dataclass(frozen=True)
class IRParam(IRNode):
    """A parameter lookup."""
    path: str


@dataclass(frozen=True)
class IRBinaryOp(IRNode):
    """Binary operation."""
    op: BinaryOp  # ADD, SUB, MUL, DIV, AND, OR, GT, LT, etc.
    left: IRNode
    right: IRNode


@dataclass(frozen=True)
class IRUnaryOp(IRNode):
    """Unary operation."""
    op: UnaryOp  # NEG, NOT, ABS, FLOOR, CEIL, etc.
    operand: IRNode


@dataclass(frozen=True)
class IRConditional(IRNode):
    """If-then-else."""
    condition: IRNode
    if_true: IRNode
    if_false: IRNode


@dataclass(frozen=True)
class IRAggregation(IRNode):
    """Aggregate from child to parent entity."""
    source: IRNode
    method: EntityOp
    role_filter: Optional[str]


@dataclass(frozen=True)
class IRBroadcast(IRNode):
    """Broadcast from parent to child entity."""
    source: IRNode


@dataclass(frozen=True)
class IRBracketCalc(IRNode):
    """Calculate through a bracket scale."""
    input_value: IRNode
    scale: IRNode
    method: BracketMethod  # MARGINAL, AVERAGE, etc.


@dataclass(frozen=True)
class IRPeriodRef(IRNode):
    """Reference to another period."""
    source: IRNode
    offset: int  # -1 for previous year, etc.
```

### 4.2 IR graph

```python
@dataclass
class IRGraph:
    """Complete computation graph."""
    nodes: Dict[str, IRNode]
    outputs: List[str]

    def topological_order(self) -> List[str]:
        """Return nodes in dependency order."""
        ...

    def parallel_groups(self) -> List[List[str]]:
        """Return groups that can be computed in parallel."""
        ...

    def subgraph(self, outputs: List[str]) -> 'IRGraph':
        """Extract subgraph for specific outputs."""
        ...

    def dependencies(self, node_id: str) -> Set[str]:
        """All transitive dependencies of a node."""
        ...
```

### 4.3 Example IR

```python
# Source:
@variable(entity=TaxUnit, period=Year, dtype=Money)
def income_tax(tax_unit, period):
    agi = tax_unit("adjusted_gross_income", period)
    brackets = parameter("gov.irs.income.brackets", period)
    return brackets.calc(agi)

# Compiles to IR:
IRGraph(
    nodes={
        "agi": IRInput(
            id="agi",
            name="adjusted_gross_income",
            entity="tax_unit",
            dtype=Money,
            period=Year(2024),
            default=0,
        ),
        "brackets": IRParam(
            id="brackets",
            path="gov.irs.income.brackets",
            entity="tax_unit",
            dtype=BracketScale,
            period=Year(2024),
        ),
        "income_tax": IRBracketCalc(
            id="income_tax",
            input_value="agi",
            scale="brackets",
            method=BracketMethod.MARGINAL,
            entity="tax_unit",
            dtype=Money,
            period=Year(2024),
        ),
    },
    outputs=["income_tax"],
)
```

---

## 5. Code generation

### 5.1 Python generator

**Target**: NumPy-based vectorized code for microsimulation.

```python
class PythonGenerator:
    def generate(self, graph: IRGraph, params: ParameterValues) -> str:
        lines = [
            "import numpy as np",
            "",
            "def calculate(inputs, n_entities):",
        ]

        for node_id in graph.topological_order():
            node = graph.nodes[node_id]
            lines.append(f"    {self.generate_node(node, params)}")

        lines.append("")
        lines.append("    return {")
        for output in graph.outputs:
            lines.append(f"        '{output}': {output},")
        lines.append("    }")

        return "\n".join(lines)

    def generate_node(self, node: IRNode, params: ParameterValues) -> str:
        match node:
            case IRInput(name=name, default=default):
                return f"{node.id} = inputs.get('{name}', np.full(n_entities, {default}))"

            case IRBinaryOp(op=op, left=left, right=right):
                op_str = {BinaryOp.ADD: "+", BinaryOp.MUL: "*", ...}[op]
                return f"{node.id} = {left} {op_str} {right}"

            case IRConditional(condition=cond, if_true=t, if_false=f):
                return f"{node.id} = np.where({cond}, {t}, {f})"

            case IRBracketCalc(input_value=val, scale=scale):
                brackets = params.get(scale)
                return self.generate_bracket_calc(node.id, val, brackets)
```

**Output Example:**

```python
import numpy as np

def calculate(inputs, n_entities):
    agi = inputs.get('adjusted_gross_income', np.full(n_entities, 0))

    # Inlined bracket calculation
    income_tax = np.zeros(n_entities)
    income_tax = np.where(agi <= 11600, agi * 0.10, income_tax)
    income_tax = np.where((agi > 11600) & (agi <= 47150),
                          1160 + (agi - 11600) * 0.12, income_tax)
    # ... more brackets

    return {
        'income_tax': income_tax,
    }
```

### 5.2 JavaScript generator

**Target**: Browser-executable code with typed arrays.

```python
class JavaScriptGenerator:
    def generate(self, graph: IRGraph, params: ParameterValues) -> str:
        lines = [
            "// Generated by Cosilico Core",
            "",
            "function calculate(inputs) {",
            "  const n = inputs.n_entities || 1;",
        ]

        for node_id in graph.topological_order():
            node = graph.nodes[node_id]
            lines.append(f"  {self.generate_node(node, params)}")

        lines.append("")
        lines.append("  return {")
        for output in graph.outputs:
            lines.append(f"    {output},")
        lines.append("  };")
        lines.append("}")
        lines.append("")
        lines.append("export { calculate };")

        return "\n".join(lines)
```

**Output Example:**

```javascript
// Generated by Cosilico Core

function calculate(inputs) {
  const n = inputs.n_entities || 1;
  const agi = inputs.adjusted_gross_income ?? new Float64Array(n).fill(0);

  // Bracket calculation
  const income_tax = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const v = agi[i];
    if (v <= 11600) {
      income_tax[i] = v * 0.10;
    } else if (v <= 47150) {
      income_tax[i] = 1160 + (v - 11600) * 0.12;
    }
    // ... more brackets
  }

  return {
    income_tax,
  };
}

export { calculate };
```

### 5.3 SQL generator

**Target**: Batch processing in data warehouses.

```python
class SQLGenerator:
    def generate(self, graph: IRGraph, params: ParameterValues) -> str:
        # Build CTE chain
        ctes = []
        for node_id in graph.topological_order():
            ctes.append(self.generate_cte(node_id, graph.nodes[node_id], params))

        return f"""
WITH
{',\n'.join(ctes)}

SELECT
  {', '.join(graph.outputs)}
FROM
  {graph.outputs[-1]}
"""
```

**Output Example:**

```sql
WITH
agi AS (
  SELECT
    entity_id,
    COALESCE(adjusted_gross_income, 0) as value
  FROM inputs
),

income_tax AS (
  SELECT
    entity_id,
    CASE
      WHEN value <= 11600 THEN value * 0.10
      WHEN value <= 47150 THEN 1160 + (value - 11600) * 0.12
      -- ... more brackets
    END as value
  FROM agi
)

SELECT
  entity_id,
  value as income_tax
FROM income_tax
```

---

## 6. Execution strategies

### 6.1 Single household (API)

```python
class SingleHouseholdExecutor:
    def __init__(self, compiled_module):
        self.calculate = compiled_module.calculate

    def execute(self, inputs: Dict) -> Dict:
        # Convert inputs to arrays of length 1
        array_inputs = {k: np.array([v]) for k, v in inputs.items()}
        array_inputs['n_entities'] = 1

        # Execute
        results = self.calculate(array_inputs)

        # Extract scalar results
        return {k: v[0] for k, v in results.items()}
```

**Target**: <1ms per calculation (based on similar vectorized operations in NumPy)

### 6.2 Batch (microsimulation)

```python
class BatchExecutor:
    def __init__(self, compiled_module, chunk_size=100_000):
        self.calculate = compiled_module.calculate
        self.chunk_size = chunk_size

    def execute(self, data: pd.DataFrame) -> pd.DataFrame:
        results = []

        for chunk in self.chunks(data):
            inputs = self.prepare_inputs(chunk)
            chunk_results = self.calculate(inputs)
            results.append(pd.DataFrame(chunk_results))

        return pd.concat(results)

    def chunks(self, data):
        for i in range(0, len(data), self.chunk_size):
            yield data.iloc[i:i + self.chunk_size]
```

**Target**: 1M households/second on 8-core machine (extrapolating from PolicyEngine's 100K/s on similar hardware)

### 6.3 Distributed (census scale)

```python
class SparkExecutor:
    def __init__(self, compiled_module):
        self.calculate_udf = self.create_udf(compiled_module)

    def execute(self, df: SparkDataFrame) -> SparkDataFrame:
        return df.withColumn(
            "results",
            self.calculate_udf(*self.input_columns)
        )
```

**Target**: 100M households in <1 hour on 100-node cluster (linear scaling assumption from batch executor)

---

## 7. Memory management

### 7.1 Copy-on-write for scenarios

```python
class Scenario:
    """A calculation scenario with copy-on-write semantics."""

    def __init__(self, base: 'Scenario' = None):
        self.base = base
        self.overrides: Dict[str, np.ndarray] = {}
        self.cache: Dict[str, np.ndarray] = {}

    def get(self, variable: str) -> np.ndarray:
        # Check local override
        if variable in self.overrides:
            return self.overrides[variable]

        # Check local cache
        if variable in self.cache:
            return self.cache[variable]

        # Delegate to base
        if self.base:
            return self.base.get(variable)

        raise KeyError(variable)

    def set(self, variable: str, value: np.ndarray):
        # Only store the override, don't copy base data
        self.overrides[variable] = value

    def fork(self) -> 'Scenario':
        """Create a child scenario."""
        return Scenario(base=self)
```

### 7.2 Memory budget

```python
class MemoryBudget:
    """Manage memory usage during calculation."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self.current_bytes = 0
        self.eviction_candidates: List[str] = []

    def allocate(self, size: int, variable: str) -> bool:
        if self.current_bytes + size > self.max_bytes:
            self.evict_until(self.max_bytes - size)

        self.current_bytes += size
        self.eviction_candidates.append(variable)
        return True

    def evict_until(self, target: int):
        while self.current_bytes > target and self.eviction_candidates:
            var = self.eviction_candidates.pop(0)
            # Spill to disk or recompute later
            ...
```

---

## 8. Error handling and debugging

### 8.1 Compile-time errors

```python
@dataclass
class CompileError:
    """A compilation error."""
    location: SourceLocation
    message: str
    code: str
    suggestions: List[str]


class TypeMismatchError(CompileError):
    """Type mismatch in formula."""
    expected: DataType
    actual: DataType


class PeriodMismatchError(CompileError):
    """Period type mismatch."""
    expected: PeriodType
    actual: PeriodType


class CyclicDependencyError(CompileError):
    """Circular dependency detected."""
    cycle: List[str]
```

### 8.2 Explanation generation

```python
@dataclass
class Explanation:
    """Explanation of a calculation."""
    variable: str
    value: Any
    formula: str
    inputs: Dict[str, 'Explanation']
    parameters: Dict[str, Any]
    references: List[str]


class ExplainableExecutor:
    """Executor that generates explanations."""

    def execute_with_explanation(self, inputs: Dict) -> Tuple[Dict, Explanation]:
        trace = {}

        def traced_calculate(var, period):
            result = self.calculate(var, period)
            trace[var] = {
                'value': result,
                'inputs': self.current_inputs,
                'formula': self.formulas[var],
            }
            return result

        results = traced_calculate(self.target, self.period)
        explanation = self.build_explanation(trace)

        return results, explanation
```

---

## 9. Testing strategy

### 9.1 Unit tests

```python
def test_bracket_calculation():
    """Test bracket calculation generates correct code."""
    spec = VariableSpec(
        name="income_tax",
        formula=FormulaSpec(
            expression=IRBracketCalc(
                input_value="agi",
                scale="brackets",
                method=BracketMethod.MARGINAL,
            )
        )
    )

    code = PythonGenerator().generate_node(spec)

    # Execute generated code
    result = exec_generated(code, agi=50000)

    # Compare with known correct value
    assert abs(result - expected_tax(50000)) < 0.01
```

### 9.2 Property-based tests

```python
from hypothesis import given, strategies as st

@given(st.floats(min_value=0, max_value=1_000_000))
def test_tax_is_monotonic(income):
    """Tax should be monotonically increasing with income."""
    tax1 = calculate(income=income)['income_tax']
    tax2 = calculate(income=income + 1)['income_tax']
    assert tax2 >= tax1


@given(st.floats(min_value=0, max_value=1_000_000))
def test_marginal_rate_bounded(income):
    """Marginal rate should be between 0 and 1."""
    epsilon = 0.01
    tax1 = calculate(income=income)['income_tax']
    tax2 = calculate(income=income + epsilon)['income_tax']
    marginal_rate = (tax2 - tax1) / epsilon
    assert 0 <= marginal_rate <= 1
```

### 9.3 Golden file tests

```python
def test_against_known_returns():
    """Test against database of known tax returns."""
    for case in load_test_cases("golden/irs_returns.json"):
        result = calculate(**case['inputs'])

        for var, expected in case['expected'].items():
            assert abs(result[var] - expected) < 0.01, \
                f"Mismatch for {case['id']}: {var}"
```

### 9.4 Cross-target consistency

```python
def test_python_js_consistency():
    """Python and JavaScript should produce identical results."""
    py_code = PythonGenerator().generate(graph)
    js_code = JavaScriptGenerator().generate(graph)

    for inputs in sample_inputs(1000):
        py_result = exec_python(py_code, inputs)
        js_result = exec_js(js_code, inputs)

        assert_results_equal(py_result, js_result)
```

---

## 10. Migration strategy

### Phase 1: Core IR (month 1-2)

- [ ] Define IR data structures
- [ ] Build Python formula parser
- [ ] Implement type checker
- [ ] Generate simple Python output

### Phase 2: Entity model (month 2-3)

- [ ] Define entity hierarchy spec
- [ ] Implement aggregation/broadcast in IR
- [ ] Generate entity-aware Python code
- [ ] Port subset of PE-US variables

### Phase 3: JavaScript target (month 3-4)

- [ ] Implement JavaScript generator
- [ ] Add TypeScript type declarations
- [ ] Build browser test harness
- [ ] Validate against Python output

### Phase 4: Parameters (month 4-5)

- [ ] Define parameter spec format
- [ ] Build parameter compiler
- [ ] Support bracket scales
- [ ] Handle time-varying values

### Phase 5: Optimization (month 5-6)

- [ ] Dead code elimination
- [ ] Constant folding
- [ ] Common subexpression elimination
- [ ] Benchmark against PE-Core

### Phase 6: Production ready (month 6-8)

- [ ] SQL generator
- [ ] Spark generator
- [ ] Memory management
- [ ] Documentation

---

## 11. Law reference semantics

A key differentiator: treating legal citations as first-class citizens, not just documentation URLs.

### 11.1 Citation model

```python
@dataclass(frozen=True)
class LegalCitation:
    """A precise reference to law/regulation."""
    jurisdiction: str              # "us", "us.ca", "uk"
    code: str                      # "usc", "cfr", "act"
    title: Optional[str]           # "26" (for 26 USC)
    section: str                   # "32"
    subsection: Optional[str]      # "(a)(1)(A)"
    paragraph: Optional[str]       # "(i)"
    effective_date: Optional[Date] # When this version applies
    source_url: Optional[str]      # Link to authoritative text

    def __str__(self) -> str:
        """Human-readable citation."""
        # "26 USC § 32(a)(1)(A)(i)"
        parts = []
        if self.title:
            parts.append(self.title)
        parts.append(self.code.upper())
        parts.append(f"§ {self.section}")
        if self.subsection:
            parts.append(self.subsection)
        if self.paragraph:
            parts.append(self.paragraph)
        return " ".join(parts)

    def canonical_id(self) -> str:
        """Machine-readable identifier."""
        # "us/usc/26/32/a/1/A/i"
        return "/".join(filter(None, [
            self.jurisdiction, self.code, self.title,
            self.section, self.subsection, self.paragraph
        ]))


@dataclass(frozen=True)
class CitationRange:
    """A range of citations (e.g., 'sections 32-36')."""
    start: LegalCitation
    end: LegalCitation


@dataclass(frozen=True)
class RegulatoryHistory:
    """Track how a citation has changed over time."""
    citation: LegalCitation
    versions: List['LawVersion']


@dataclass(frozen=True)
class LawVersion:
    """A specific version of a law provision."""
    text: str
    effective_date: Date
    enacted_date: Date        # When the law was passed
    public_law: Optional[str] # "P.L. 117-169" (Inflation Reduction Act)
    bill: Optional[str]       # "H.R. 5376"
```

### 11.2 Semantic law layer

Build a queryable knowledge base of the law:

```python
class LawRegistry:
    """Registry of all law provisions used in the system."""

    def __init__(self):
        self.citations: Dict[str, LegalCitation] = {}
        self.cross_references: Dict[str, Set[str]] = {}  # citation -> citations it references
        self.used_by: Dict[str, Set[str]] = {}  # citation -> variables using it

    def register(self, citation: LegalCitation, used_by: str):
        """Register a citation as used by a variable."""
        cid = citation.canonical_id()
        self.citations[cid] = citation
        self.used_by.setdefault(cid, set()).add(used_by)

    def get_text(self, citation: LegalCitation, as_of: Date = None) -> str:
        """Get the text of a provision as of a date."""
        ...

    def what_references(self, citation: LegalCitation) -> List[LegalCitation]:
        """Find what other provisions reference this one."""
        ...

    def variables_affected_by(self, citation: LegalCitation) -> List[str]:
        """Find all variables that depend on this citation."""
        ...

    def changes_between(self, start: Date, end: Date) -> List[LawChange]:
        """Find all law changes between two dates."""
        ...
```

### 11.3 Variable-to-law mapping

```python
@variable(
    entity=TaxUnit,
    period=Year,
    dtype=Money,
    # Precise legal citations, not just URLs
    references=[
        LegalCitation(
            jurisdiction="us",
            code="usc",
            title="26",
            section="32",
            subsection="(a)(1)",
            source_url="https://uscode.house.gov/view.xhtml?req=26+USC+32"
        ),
        LegalCitation(
            jurisdiction="us",
            code="cfr",
            title="26",
            section="1.32-2",  # Treasury regulations
        ),
    ],
    # Link specific parts of formula to specific subsections
    formula_references={
        "phase_in_rate": "26 USC § 32(b)(1)(A)",
        "phase_out_rate": "26 USC § 32(b)(1)(B)",
        "earned_income_threshold": "26 USC § 32(b)(2)(A)",
    }
)
def eitc(tax_unit, period):
    ...
```

### 11.4 Impact analysis

When a law changes, understand the ripple effects:

```python
class ImpactAnalyzer:
    """Analyze impact of law changes on the model."""

    def citation_impact(self, citation: LegalCitation) -> ImpactReport:
        """What happens if this citation changes?"""
        affected_vars = self.registry.variables_affected_by(citation)
        downstream = self.graph.all_dependents(affected_vars)

        return ImpactReport(
            citation=citation,
            directly_affected=affected_vars,
            transitively_affected=downstream,
            test_cases=self.find_relevant_tests(affected_vars),
        )

    def bill_impact(self, bill: Bill) -> ImpactReport:
        """What happens if this bill passes?"""
        affected_citations = bill.sections_amended
        return self.merge_impacts([
            self.citation_impact(c) for c in affected_citations
        ])
```

---

## 12. Bi-temporal parameter model

The "2024-vintage 2027 tax rate" problem: know what was legislated when.

### 12.1 Temporal dimensions

Policy parameters have TWO time dimensions:

1. **Effective Time (T_eff)**: When the policy applies
2. **Knowledge Time (T_know)**: When we knew about it

```python
@dataclass(frozen=True)
class BiTemporalValue:
    """A value with two temporal dimensions."""
    value: Any
    effective_date: Date      # When the policy takes effect
    vintage: Date      # When this value was enacted/known
    superseded_date: Optional[Date]  # When this was replaced by newer knowledge

    # Provenance
    enacted_by: Optional[str]  # "P.L. 117-169"
    source: Optional[str]      # Where we learned this


@dataclass
class BiTemporalParameter:
    """A parameter with full temporal history."""
    path: str
    values: List[BiTemporalValue]

    def get(self, effective: Date, as_of: Date = None) -> Any:
        """
        Get the parameter value for effective date,
        as known at as_of date.

        Examples:
        - get(Date(2027, 1, 1), as_of=Date(2024, 1, 1))
          -> 2027 rate as known in early 2024 (before IRA)

        - get(Date(2027, 1, 1), as_of=Date(2024, 8, 1))
          -> 2027 rate as known after IRA passed
        """
        if as_of is None:
            as_of = Date.today()

        # Find values that:
        # 1. Were known by as_of date
        # 2. Apply to the effective date
        # 3. Haven't been superseded by as_of
        candidates = [
            v for v in self.values
            if v.vintage <= as_of
            and v.effective_date <= effective
            and (v.superseded_date is None or v.superseded_date > as_of)
        ]

        if not candidates:
            raise NoValueError(self.path, effective, as_of)

        # Return most recently enacted applicable value
        return max(candidates, key=lambda v: v.effective_date).value
```

### 12.2 Example: TCJA sunset

```python
# The Tax Cuts and Jobs Act (2017) set rates through 2025,
# with automatic reversion to pre-TCJA rates in 2026

federal_tax_brackets = BiTemporalParameter(
    path="gov.irs.income.brackets.single",
    values=[
        # Pre-TCJA brackets (known since forever, effective through 2017)
        BiTemporalValue(
            value=PRE_TCJA_BRACKETS,
            effective_date=Date(2017, 1, 1),
            vintage=Date(2000, 1, 1),  # Approximate
            superseded_date=Date(2017, 12, 22),  # When TCJA was signed
        ),

        # TCJA brackets (known Dec 2017, effective 2018-2025)
        BiTemporalValue(
            value=TCJA_BRACKETS_2018,
            effective_date=Date(2018, 1, 1),
            vintage=Date(2017, 12, 22),
        ),
        # ... 2019-2025 values ...

        # Sunset provision: revert to pre-TCJA in 2026
        # This was ALSO known as of Dec 2017!
        BiTemporalValue(
            value=PRE_TCJA_BRACKETS_INFLATION_ADJUSTED,
            effective_date=Date(2026, 1, 1),
            vintage=Date(2017, 12, 22),  # Sunset was in original law
        ),

        # IF Congress extends TCJA, we'd add:
        BiTemporalValue(
            value=EXTENDED_BRACKETS_2026,
            effective_date=Date(2026, 1, 1),
            vintage=Date(2025, 12, 15),  # Hypothetical extension date
            superseded_date=None,  # Now the current knowledge
        ),
    ]
)

# Queries:
brackets.get(Date(2027, 1, 1), as_of=Date(2024, 1, 1))
# -> Returns PRE_TCJA_BRACKETS (sunset was law as of 2024)

brackets.get(Date(2027, 1, 1), as_of=Date(2026, 1, 1))
# -> Returns EXTENDED_BRACKETS (after hypothetical extension)
```

### 12.3 Storage strategy

Git timestamps have a 1970 limit, but we can use other approaches:

```python
class ParameterStore:
    """Store bi-temporal parameters."""

    # Option 1: Database with temporal tables
    def _db_store(self):
        """
        CREATE TABLE parameter_values (
            path TEXT,
            value JSONB,
            effective_date DATE,
            vintage DATE,
            superseded_date DATE,
            enacted_by TEXT,
            PRIMARY KEY (path, effective_date, vintage)
        );
        """
        ...

    # Option 2: Structured YAML with explicit dates
    def _yaml_structure(self):
        """
        gov/irs/income/brackets.yaml:

        path: gov.irs.income.brackets
        history:
          - vintage: 2017-12-22
            enacted_by: P.L. 115-97  # TCJA
            values:
              - effective: 2018-01-01
                value: {brackets: [...]}
              - effective: 2026-01-01  # Sunset
                value: {brackets: [...]}  # Pre-TCJA rates

          - vintage: 2025-12-15  # Hypothetical future
            enacted_by: P.L. 119-XX  # Extension
            supersedes: 2017-12-22  # Supersedes sunset provision
            values:
              - effective: 2026-01-01
                value: {brackets: [...]}  # Extended TCJA rates
        """
        ...

    # Option 3: Git with metadata files (preferred)
    def _git_with_metadata(self):
        """
        Use git for version control, but don't rely on git dates.
        Each parameter file includes explicit metadata:

        parameters/
          gov/irs/income/brackets/
            values.yaml          # Current values
            history.yaml         # Bi-temporal history
            _meta.yaml           # Knowledge dates, enactments

        Git provides:
        - Collaboration (PRs, reviews)
        - Audit trail (who changed what)
        - Branching (proposed legislation)

        Metadata provides:
        - Bi-temporal queries
        - Legal provenance
        """
        ...
```

### 12.4 Projections and scenarios

```python
class ParameterScenario:
    """A scenario with specific parameter assumptions."""

    name: str
    description: str
    base: 'ParameterStore'
    overrides: Dict[str, BiTemporalValue]

    def get(self, path: str, effective: Date, as_of: Date = None) -> Any:
        if path in self.overrides:
            return self.overrides[path].value
        return self.base.get(path, effective, as_of)


# Create scenarios for policy analysis
current_law = ParameterScenario(name="Current Law")

tcja_extended = ParameterScenario(
    name="TCJA Extended",
    description="Assume TCJA rates extended permanently",
    base=current_law,
    overrides={
        "gov.irs.income.brackets": BiTemporalValue(
            value=TCJA_BRACKETS_EXTENDED,
            effective_date=Date(2026, 1, 1),
            vintage=Date.today(),
        ),
    }
)

# Compare scenarios
baseline = simulate(scenario=current_law, year=2027)
reform = simulate(scenario=tcja_extended, year=2027)
impact = compare(baseline, reform)
```

---

## 13. Jurisdiction modularity

Solve the "policyengine-us is too big" problem with proper jurisdiction separation.

### 13.1 Jurisdiction hierarchy

```python
@dataclass(frozen=True)
class Jurisdiction:
    """A legislative jurisdiction."""
    id: str                    # "us.ca.sf" (US > California > San Francisco)
    name: str                  # "San Francisco"
    parent: Optional[str]      # "us.ca"
    type: JurisdictionType     # COUNTRY, STATE, COUNTY, CITY, TERRITORY

    @property
    def ancestors(self) -> List[str]:
        """Get all parent jurisdictions."""
        if self.parent is None:
            return []
        return [self.parent] + Jurisdiction.get(self.parent).ancestors

    @property
    def country(self) -> str:
        """Get top-level country code."""
        return self.id.split(".")[0]


class JurisdictionType(Enum):
    COUNTRY = "country"
    STATE = "state"           # US states, Canadian provinces
    TERRITORY = "territory"   # Puerto Rico, Guam
    COUNTY = "county"
    CITY = "city"
    DISTRICT = "district"     # School districts, special districts
```

### 13.2 Modular repository structure

Split into jurisdiction-specific packages:

```
rac-us/              # Federal-only, minimal
├── cosilico_us/
│   ├── federal/          # Federal tax/benefit rules
│   │   ├── irs/          # IRS rules
│   │   ├── ssa/          # Social Security
│   │   └── treasury/     # Treasury regulations
│   └── entities.py       # Person, TaxUnit, etc.

rac-us-ca/           # California (imports rac-us)
├── cosilico_us_ca/
│   ├── ftb/              # Franchise Tax Board
│   ├── edd/              # Employment Development Dept
│   └── entities.py       # CA-specific entities if any

rac-us-ca-sf/        # San Francisco (imports rac-us-ca)
├── cosilico_us_ca_sf/
│   ├── taxes/            # Local taxes
│   └── benefits/         # Local programs
```

### 13.3 Bidirectional jurisdiction dependencies

Jurisdiction dependencies flow BOTH directions:

**Downward (Federal → State → Local)**:
- States use federal AGI as starting point
- States conform to federal definitions
- Local taxes often use state taxable income

**Upward (Local → State → Federal)**:
- SALT deduction: Federal tax depends on state/local taxes paid
- Foreign tax credit: Federal depends on foreign jurisdiction
- Reciprocal agreements between states

```python
class JurisdictionGraph:
    """Model bidirectional jurisdiction dependencies."""

    def __init__(self):
        self.downward: Dict[str, Set[str]] = {}   # parent -> children
        self.upward: Dict[str, Set[str]] = {}     # child -> parents

    def add_dependency(self, from_jur: str, to_jur: str, direction: str):
        """
        Add a dependency between jurisdictions.

        direction: "down" (parent provides to child)
                   "up" (child provides to parent)
        """
        if direction == "down":
            self.downward.setdefault(from_jur, set()).add(to_jur)
        else:
            self.upward.setdefault(from_jur, set()).add(to_jur)

    def calculation_order(self, jurisdictions: List[str]) -> List[str]:
        """
        Determine correct calculation order for interdependent jurisdictions.

        For most households: federal → state → local → federal_final

        The SALT deduction creates a cycle that requires iteration
        or algebraic solving.
        """
        ...


# Example: SALT deduction creates bidirectional dependency
#
# federal_agi -> ca_taxable_income -> ca_income_tax
#                                          |
#                                          v
# federal_income_tax <- salt_deduction <---+
#
# Resolution strategies:
# 1. Iteration: Compute federal, then state, then re-compute federal
# 2. Algebraic: Solve simultaneously for simple cases
# 3. Approximation: Use prior-year state taxes (common in practice)
```

### 13.4 Dependency resolution

```python
class JurisdictionResolver:
    """Resolve jurisdiction-specific rules with bidirectional dependencies."""

    def __init__(self, jurisdictions: List[str]):
        """
        Initialize with list of applicable jurisdictions.

        Example: ["us", "us.ca", "us.ca.sf"]
        """
        self.jurisdictions = jurisdictions
        self.packages = self._load_packages()
        self.dep_graph = self._build_dependency_graph()

    def get_variable(self, name: str) -> VariableSpec:
        """
        Get variable, preferring more specific jurisdictions.

        If "income_tax" exists in both "us" and "us.ca",
        return the California version when jurisdiction is us.ca.
        """
        for jur in reversed(self.jurisdictions):  # Most specific first
            if name in self.packages[jur].variables:
                return self.packages[jur].variables[name]
        raise VariableNotFoundError(name)

    def get_parameter(self, path: str, effective: Date) -> Any:
        """
        Get parameter with jurisdiction fallback.

        If "gov.income_tax.rate" doesn't exist for "us.ca",
        fall back to "us" (federal default).
        """
        for jur in reversed(self.jurisdictions):
            try:
                return self.packages[jur].parameters.get(path, effective)
            except ParameterNotFoundError:
                continue
        raise ParameterNotFoundError(path)

    def resolve_bidirectional(self, variable: str) -> CalculationPlan:
        """
        Create a calculation plan that handles bidirectional dependencies.

        Returns a plan that may include:
        - Linear dependencies (compute in order)
        - Iterative loops (for cycles like SALT)
        - Parallel groups (independent jurisdictions)
        """
        deps = self._analyze_cross_jurisdiction_deps(variable)

        if deps.has_cycle:
            return IterativeCalculationPlan(
                initial_pass=deps.downward_order,
                iterative_vars=deps.cycle_vars,
                max_iterations=10,
                tolerance=0.01,  # $0.01 convergence
            )
        else:
            return LinearCalculationPlan(deps.topological_order)
```

### 13.5 Composition model

```python
@dataclass
class JurisdictionPackage:
    """A package of rules for a jurisdiction."""
    jurisdiction: Jurisdiction
    variables: Dict[str, VariableSpec]
    parameters: ParameterStore
    entities: Dict[str, EntitySpec]

    def extend(self, base: 'JurisdictionPackage') -> 'JurisdictionPackage':
        """Extend a parent jurisdiction's rules."""
        return JurisdictionPackage(
            jurisdiction=self.jurisdiction,
            variables={**base.variables, **self.variables},
            parameters=self.parameters.with_fallback(base.parameters),
            entities={**base.entities, **self.entities},
        )


# Build California model by extending US federal
us_federal = load_package("rac-us")
us_ca = load_package("rac-us-ca").extend(us_federal)
us_ca_sf = load_package("rac-us-ca-sf").extend(us_ca)

# Calculate for a San Francisco resident
result = calculate(
    variables=["income_tax", "state_income_tax", "local_tax"],
    jurisdiction=us_ca_sf,
    inputs={...}
)
```

### 13.6 Version compatibility

```python
# Each package declares compatible versions
# rac-us-ca/pyproject.toml:
# [project]
# dependencies = [
#     "rac-us>=2024.1,<2025.0",
# ]

class CompatibilityChecker:
    """Check compatibility between jurisdiction packages."""

    def check(self, packages: List[JurisdictionPackage]) -> List[Issue]:
        issues = []

        # Check version compatibility
        for pkg in packages:
            for dep in pkg.dependencies:
                if not self._version_compatible(dep, packages):
                    issues.append(VersionMismatch(pkg, dep))

        # Check entity compatibility
        if not self._entities_compatible(packages):
            issues.append(EntityMismatch(...))

        # Check variable signature compatibility
        for var in self._find_overridden_variables(packages):
            if not self._signatures_compatible(var):
                issues.append(SignatureMismatch(var))

        return issues
```

### 13.7 Selective compilation

```python
class JurisdictionCompiler:
    """Compile rules for specific jurisdictions."""

    def compile(
        self,
        jurisdictions: List[str],
        variables: List[str],
        target: Target
    ) -> CompiledOutput:
        """
        Compile only what's needed for specific jurisdictions.

        compile(
            jurisdictions=["us", "us.ca"],
            variables=["income_tax", "eitc", "ca_eitc"],
            target=Target.JAVASCRIPT
        )

        This produces a minimal bundle with only federal + CA rules.
        """
        resolver = JurisdictionResolver(jurisdictions)

        # Resolve variables (with overrides)
        resolved_vars = {
            name: resolver.get_variable(name)
            for name in variables
        }

        # Find all transitive dependencies
        all_deps = self._find_all_dependencies(resolved_vars)

        # Resolve parameters (with fallbacks)
        params = self._resolve_parameters(all_deps, resolver)

        # Generate code for target
        generator = self._get_generator(target)
        return generator.generate(
            variables=all_deps,
            parameters=params,
            jurisdictions=jurisdictions
        )
```

### 13.8 State package template

Standardized structure for state packages:

```
rac-us-{state}/
├── pyproject.toml
├── cosilico_us_{state}/
│   ├── __init__.py
│   ├── entities.py           # State-specific entities (if any)
│   ├── variables/
│   │   ├── tax/              # State income tax
│   │   │   ├── income.py
│   │   │   ├── deductions.py
│   │   │   └── credits.py
│   │   └── benefits/         # State benefits
│   │       ├── snap_state.py # State SNAP options
│   │       └── tanf.py       # State TANF implementation
│   ├── parameters/
│   │   └── gov/
│   │       └── {state}/      # State-specific parameters
│   └── tests/
│       ├── tax/
│       └── benefits/
└── README.md
```

### 13.9 Cross-jurisdiction analysis

```python
class MultiJurisdictionAnalyzer:
    """Analyze policies across jurisdictions."""

    def compare_jurisdictions(
        self,
        variable: str,
        jurisdictions: List[str],
        inputs: Dict
    ) -> pd.DataFrame:
        """
        Compare a variable across jurisdictions.

        compare_jurisdictions(
            variable="effective_tax_rate",
            jurisdictions=["us.ca", "us.tx", "us.ny", "us.fl"],
            inputs={"income": 100_000, "filing_status": "single"}
        )
        """
        results = []
        for jur in jurisdictions:
            resolver = JurisdictionResolver([jur.split(".")])
            result = calculate(variable, resolver, inputs)
            results.append({
                "jurisdiction": jur,
                "value": result
            })
        return pd.DataFrame(results)

    def portability_analysis(
        self,
        from_jur: str,
        to_jur: str,
        household: Dict
    ) -> PortabilityReport:
        """
        What happens if this household moves jurisdictions?
        """
        from_result = calculate(jurisdiction=from_jur, **household)
        to_result = calculate(jurisdiction=to_jur, **household)

        return PortabilityReport(
            from_jurisdiction=from_jur,
            to_jurisdiction=to_jur,
            tax_difference=to_result["total_tax"] - from_result["total_tax"],
            benefit_difference=to_result["total_benefits"] - from_result["total_benefits"],
            net_impact=...,
            key_drivers=[...]  # Which variables drove the difference
        )
```

---

## 14. Parameter storage: code vs database

### 14.1 Trade-offs

| Aspect | Code (YAML/Python) | Database |
|--------|-------------------|----------|
| **Version Control** | Native git | Requires migration system |
| **Review Process** | PRs, diffs | Custom UI needed |
| **Querying** | Load all, filter | SQL, indexed |
| **Bi-temporal** | Manual in YAML | Native support |
| **Scale** | Works to ~100K params | Unlimited |
| **Offline** | Yes | Requires connection |
| **Type Safety** | Schema validation | Constraints |
| **Branching** | Git branches | Row versioning |

### 14.2 Hybrid approach

```python
class HybridParameterStore:
    """
    Use code for structure and stable values,
    database for frequently-changing and historical values.
    """

    def __init__(self):
        # Code-based: structure, metadata, stable values
        self.code_store = YAMLParameterStore("parameters/")

        # Database: bi-temporal history, projections
        self.db_store = DatabaseParameterStore(connection_string)

    def get(self, path: str, effective: Date, as_of: Date = None) -> Any:
        # Try database first (most recent knowledge)
        try:
            return self.db_store.get(path, effective, as_of)
        except ParameterNotFoundError:
            pass

        # Fall back to code store
        return self.code_store.get(path, effective)

    def get_history(self, path: str) -> List[BiTemporalValue]:
        """Get full history from database."""
        return self.db_store.get_history(path)

    def propose_change(self, path: str, value: BiTemporalValue) -> ChangeProposal:
        """
        Propose a parameter change (for review).
        Creates a PR for code changes or a staged DB entry.
        """
        ...
```

### 14.3 Recommended approach

For Cosilico:

1. **Structure in Code** (YAML): Parameter paths, types, metadata, references
2. **Stable Values in Code**: Well-established historical values
3. **Recent/Projected in DB**: New legislation, projections, scenarios
4. **Bi-temporal in DB**: Full temporal history with efficient querying

```yaml
# parameters/gov/irs/income/brackets.yaml
path: gov.irs.income.brackets
type: bracket_scale
unit: usd
metadata:
  references:
    - citation: "26 USC § 1"
      url: "https://uscode.house.gov/..."

# Stable historical values in code
values:
  - effective: 2018-01-01
    knowledge: 2017-12-22
    enacted_by: P.L. 115-97
    value:
      - threshold: 0
        rate: 0.10
      # ...

# Recent/projected values: see database
# Query: SELECT * FROM parameters WHERE path = 'gov.irs.income.brackets'
```

---

## 15. Structured law layer

Beyond encoding rules computationally, Cosilico aims to represent the law itself as structured data, enabling bidirectional translation between legal text and executable simulations.

### 15.1 Architecture overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LEGAL TEXT SOURCES                                 │
│                                                                              │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │    USC    │  │    CFR    │  │   State   │  │  Program  │  │    Tax    │ │
│  │ (Statutes)│  │  (Regs)   │  │   Codes   │  │  Manuals  │  │   Forms   │ │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘ │
│         │             │             │              │              │         │
│         └─────────────┴─────────────┴──────────────┴──────────────┘         │
│                                     ↓                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LEGAL KNOWLEDGE GRAPH                               │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Statute Database                              │   │
│  │  • Hierarchical structure (Title → Chapter → Section → Subsection)  │   │
│  │  • Cross-references between sections                                 │   │
│  │  • Amendment history with effective dates                            │   │
│  │  • Definitions and term usage                                        │   │
│  │  • Delegation chains (statute → regulation → guidance)               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                     ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Semantic Annotations                            │   │
│  │  • Computational intent (threshold, rate, eligibility test)          │   │
│  │  • Entity references (taxpayer, dependent, household)                │   │
│  │  • Temporal markers (taxable year, calendar year, fiscal year)       │   │
│  │  • Conditions and exceptions                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                     ↓                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BIDIRECTIONAL LINKAGE                                │
│                                                                              │
│  ┌──────────────────────┐              ┌──────────────────────┐            │
│  │                      │   encodes    │                      │            │
│  │    Legal Text        │ ──────────→  │   Cosilico Rules     │            │
│  │                      │              │                      │            │
│  │  "The credit under   │              │  @variable           │            │
│  │   this section       │              │  def eitc(...):      │            │
│  │   shall be..."       │  ←──────────  │    ...               │            │
│  │                      │   generates  │                      │            │
│  └──────────────────────┘              └──────────────────────┘            │
│                                                                              │
│  Every rule knows its source sections.                                       │
│  Every statute section knows which rules implement it.                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AI ENCODING PIPELINE                                │
│                                                                              │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐               │
│  │  Bill Text    │ →  │   AI Parser   │ →  │ Draft Rules   │               │
│  │  (new/amended)│    │  (understand  │    │ (Cosilico DSL)│               │
│  │               │    │   legal       │    │               │               │
│  │               │    │   semantics)  │    │               │               │
│  └───────────────┘    └───────────────┘    └───────────────┘               │
│                              ↓                     ↓                        │
│                       ┌───────────────┐    ┌───────────────┐               │
│                       │ Human Review  │ ←  │  Validation   │               │
│                       │ & Refinement  │    │  (type check, │               │
│                       │               │    │   test cases) │               │
│                       └───────────────┘    └───────────────┘               │
│                              ↓                                              │
│                       ┌───────────────┐                                     │
│                       │  Production   │                                     │
│                       │    Rules      │                                     │
│                       └───────────────┘                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LEGISLATIVE GENERATION                                  │
│                                                                              │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐               │
│  │   Reform in   │ →  │   Generator   │ →  │  Bill Text    │               │
│  │   Cosilico    │    │  (Cosilico →  │    │  (legal       │               │
│  │               │    │   legal       │    │   language)   │               │
│  │               │    │   language)   │    │               │               │
│  └───────────────┘    └───────────────┘    └───────────────┘               │
│                                                                              │
│  User designs policy → generates draft legislation with proper amendments   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 15.2 Statute data model

```python
@dataclass
class StatuteSection:
    """A section of statutory law."""

    # Identity
    jurisdiction: Jurisdiction  # US, CA, NY, etc.
    code: str                   # "USC", "IRC", "CA_WIC"
    title: str                  # "26" (Internal Revenue Code)
    section: str                # "32"
    subsection: Optional[str]   # "(a)(1)(A)"

    # Hierarchy
    parent: Optional[StatuteSection]
    children: List[StatuteSection]

    # Content
    heading: str                # "Earned income credit"
    text: str                   # Full statutory text

    # Temporality
    enacted_date: date
    effective_date: date
    amended_by: List[Amendment]
    superseded_by: Optional[StatuteSection]

    # Cross-references
    references: List[StatuteRef]      # Sections this cites
    referenced_by: List[StatuteRef]   # Sections that cite this

    # Delegation
    implementing_regs: List[RegulationSection]

    # Computational mapping
    cosilico_rules: List[RuleRef]     # Rules that implement this


@dataclass
class Amendment:
    """A change to statutory text."""

    public_law: str             # "P.L. 117-169"
    bill: str                   # "H.R. 5376"
    name: str                   # "Inflation Reduction Act of 2022"
    enacted_date: date
    effective_date: date

    # What changed
    section_affected: StatuteSection
    change_type: Literal["add", "amend", "repeal", "redesignate"]
    old_text: Optional[str]
    new_text: Optional[str]

    # Mapping
    cosilico_changes: List[RuleChange]  # Resulting rule updates


@dataclass
class RuleRef:
    """Reference from statute to Cosilico rule."""

    rule_id: str                    # "us.irs.credits.eitc"
    coverage: Coverage              # FULL, PARTIAL, REFERENCED
    notes: Optional[str]            # Explanation of mapping


class Coverage(Enum):
    FULL = "full"           # Rule fully implements this section
    PARTIAL = "partial"     # Rule implements part of this section
    REFERENCED = "ref"      # Rule references but doesn't implement
```

### 15.3 Bill tracking pipeline

```python
class BillTracker:
    """Monitor legislative activity and trigger encoding."""

    async def track_jurisdiction(self, jurisdiction: Jurisdiction):
        """Track all bills in a jurisdiction."""

        sources = {
            Jurisdiction.US_FEDERAL: CongressGovAPI(),
            Jurisdiction.US_CA: CALegInfoAPI(),
            Jurisdiction.US_NY: NYSenateAPI(),
            # ... all 50 states + DC + territories
        }

        async for bill in sources[jurisdiction].stream_bills():
            # Filter for relevant subject areas
            if not self._is_tax_benefit_related(bill):
                continue

            # Parse bill structure
            parsed = await self.parse_bill(bill)

            # Identify affected statutes
            affected = self.identify_affected_sections(parsed)

            # Generate draft Cosilico rules
            draft = await self.ai_encode(parsed, affected)

            # Queue for human review
            await self.queue_for_review(bill, draft)


    async def ai_encode(
        self,
        bill: ParsedBill,
        affected: List[StatuteSection]
    ) -> DraftRules:
        """Use AI to generate draft Cosilico rules from bill text."""

        # Get current rules for affected sections
        current_rules = self.get_rules_for_sections(affected)

        # Build context for AI
        context = EncodingContext(
            bill_text=bill.text,
            bill_structure=bill.sections,
            affected_statutes=[s.text for s in affected],
            current_rules=current_rules,
            parameter_schema=self.get_param_schema(),
            entity_definitions=self.get_entity_defs(),
        )

        # AI generates draft rules
        draft = await self.encoder_model.generate(
            context,
            output_format="cosilico_dsl",
            include_tests=True,
            include_citations=True,
        )

        # Validate draft compiles
        validation = self.validate_draft(draft)

        return DraftRules(
            rules=draft.rules,
            parameters=draft.parameters,
            tests=draft.tests,
            validation=validation,
            confidence=draft.confidence,
            uncertain_sections=draft.uncertain,
        )
```

### 15.4 Legislative text generation

```python
class LegislativeGenerator:
    """Generate bill text from Cosilico reforms."""

    def generate_bill(
        self,
        reform: Reform,
        target_jurisdiction: Jurisdiction,
        style: LegislativeStyle = LegislativeStyle.AMENDMENT,
    ) -> GeneratedBill:
        """Convert a Cosilico reform to draft legislation."""

        # Analyze what the reform changes
        changes = self.analyze_reform(reform)

        # Map changes to statute sections
        section_changes = []
        for change in changes:
            # Find statute section this rule implements
            section = self.find_source_section(change.rule)

            if change.type == ChangeType.PARAMETER:
                # Parameter change → amend specific text
                amendment = self.generate_parameter_amendment(
                    section, change.parameter, change.old_value, change.new_value
                )
            elif change.type == ChangeType.NEW_RULE:
                # New rule → add new section
                amendment = self.generate_new_section(
                    section.parent, change.rule
                )
            elif change.type == ChangeType.MODIFY_FORMULA:
                # Formula change → rewrite section
                amendment = self.generate_section_rewrite(
                    section, change.rule
                )

            section_changes.append(amendment)

        # Assemble into bill format
        bill = self.assemble_bill(
            title=reform.name,
            short_title=reform.short_name,
            findings=reform.rationale,
            amendments=section_changes,
            effective_date=reform.effective_date,
            style=style,
        )

        # Include fiscal note based on microsimulation
        fiscal_note = self.generate_fiscal_note(reform)

        return GeneratedBill(
            text=bill,
            fiscal_note=fiscal_note,
            affected_sections=section_changes,
            cosilico_reform=reform,
        )


    def generate_parameter_amendment(
        self,
        section: StatuteSection,
        parameter: str,
        old_value: Any,
        new_value: Any,
    ) -> Amendment:
        """Generate amendment text for a parameter change."""

        # Find where value appears in statute text
        location = self.find_value_in_text(section.text, old_value)

        # Generate amendment language
        if location:
            return Amendment(
                section=section,
                text=f'''Section {section.section}{section.subsection or ""} is amended by striking "{old_value}" and inserting "{new_value}".''',
                change_type="amend",
            )
        else:
            # Value is in regulations or implicit
            return Amendment(
                section=section,
                text=f'''Section {section.section} is amended by adding at the end the following: "For purposes of this section, the {parameter} shall be {new_value}."''',
                change_type="amend",
            )
```

### 15.5 Comparison with OpenStates

| Aspect | OpenStates | Cosilico Legal Layer |
|--------|------------|---------------------|
| **Scope** | Bills and votes | Bills + statutes + regulations + forms |
| **Bill tracking** | Introduced, passed, vetoed | + computational impact |
| **Statute text** | No | Full structured database |
| **Cross-references** | No | Full citation graph |
| **Amendments** | Text diff | Semantic understanding |
| **Computational mapping** | No | Bidirectional rule linkage |
| **AI encoding** | No | Bill → simulation |
| **Bill generation** | No | Reform → legislation |

OpenStates is valuable infrastructure for bill tracking. Cosilico builds on this foundation but adds:
1. Deeper understanding of what bills *do* (not just that they exist)
2. Connection to executable simulations
3. Bidirectional translation (law ↔ code)

### 15.6 Document hierarchy

Legal authority flows from statutes through regulations to agency guidance. Each level can create policy:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         STATUTES                                     │
│  Highest authority. Enacted by legislatures.                        │
│  Examples: Internal Revenue Code, Social Security Act               │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                       REGULATIONS                                    │
│  Implement statutes. Notice-and-comment rulemaking.                 │
│  Examples: Treasury Regulations, CFR Title 20 (SSA)                 │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     AGENCY GUIDANCE                                  │
│  Interpret regulations. Less formal but binding in practice.        │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Tax Forms   │  │   Program    │  │   Revenue    │              │
│  │ & Instructions│  │   Manuals   │  │   Rulings    │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                      │
│  Examples:                                                           │
│  - IRS Form 1040 instructions (define "income" in practice)        │
│  - SSA POMS (Program Operations Manual System)                     │
│  - SNAP Handbook (state-specific benefit rules)                    │
│  - Medicaid State Plan Amendments                                  │
│  - Revenue Rulings, Revenue Procedures, PLRs                       │
└─────────────────────────────────────────────────────────────────────┘
```

**Why agency guidance matters:**

Many policy details exist only in guidance, not in statute or regulation:
- Tax form worksheets define computational steps
- Program manuals specify verification procedures
- State handbooks interpret federal rules locally
- Agency memos clarify ambiguous statutory language

### 15.7 Data sources

| Source | Document Type | Content | Format | Update Frequency |
|--------|---------------|---------|--------|------------------|
| **USLM** | Statute | US Code | XML (USLM schema) | Continuous |
| **eCFR** | Regulation | Code of Federal Regulations | XML | Daily |
| **Congress.gov** | Bill | Federal legislation | XML/JSON API | Real-time |
| **State legislatures** | Bill | State legislation | Varies (50 different) | Real-time |
| **IRS.gov/forms** | Form | Tax forms & instructions | PDF/XML | Annual + updates |
| **IRS.gov/irb** | Guidance | Revenue rulings, procedures | PDF/HTML | Weekly |
| **SSA POMS** | Manual | Social Security operations | HTML | Continuous |
| **CMS.gov** | Manual | Medicare/Medicaid guidance | PDF/HTML | Varies |
| **FNS.gov** | Manual | SNAP policy guidance | PDF | Periodic |
| **State DHS/DSS** | Manual | State benefit handbooks | PDF/HTML | Varies |
| **State tax agencies** | Form | State tax forms | PDF | Annual |
| **Cornell LII** | Aggregator | Free legal resources | HTML | Weekly |
| **Westlaw/LexisNexis** | Annotator | Annotated statutes | Proprietary | N/A (cost) |

### 15.7.1 Existing statute APIs and why we need our own

**The problem:** US law is public domain, but no open source project provides structured statute text via API with historical versions.

| Service | Coverage | Open Source? | API? | Historical? | Notes |
|---------|----------|--------------|------|-------------|-------|
| **[OpenLaws.us](https://openlaws.us/api/)** | Federal + 50 states | ❌ No | ✅ Yes | ✅ Yes | Commercial; pricing opaque |
| **[Free Law Project](https://github.com/freelawproject)** | Case law only | ✅ Yes | ✅ Yes | ✅ Yes | CourtListener, no statutes |
| **[Open Law Library](https://github.com/openlawlibrary)** | Municipal codes | ✅ Yes | ⚠️ Limited | ✅ Yes | Infrastructure for govs |
| **[uscode.house.gov](https://uscode.house.gov/download/download.shtml)** | Federal only | ✅ Public domain | ❌ Download only | ✅ Yes | Official USLM XML |
| **[Congress.gov API](https://api.congress.gov/)** | Bills, not enacted law | ✅ Public | ✅ Yes | ✅ Yes | Legislative process only |
| **Cornell LII** | Federal + states | ❌ No | ❌ No | ❌ No | Web scraping prohibited |
| **LegiScan** | Bills, 50 states | ❌ No | ✅ Yes | ✅ Yes | Commercial |

**Gap analysis:**
- OpenLaws.us is closest to what we need but is proprietary
- Free Law Project is excellent for case law but explicitly excludes statutes
- Open Law Library helps municipalities publish, not aggregate/serve
- Official government sources (USLM) require download + self-hosting

**Why build `cosilico/lawarchive`:**
1. **Public good** — Law should be freely accessible via API
2. **AI training data** — We need statute text for our RL encoding pipeline
3. **Citation verification** — Our statute-linked paths need authoritative text
4. **Change tracking** — Detect when Congress amends sections we've encoded
5. **Open source moat** — Others can build on our archive, creating network effects

### 15.8 Implementation phases

**Phase 1: Foundation (Months 1-6)**
- Statute data model and storage
- Federal tax code ingestion (Title 26)
- Basic cross-reference parsing
- Bidirectional linking infrastructure

**Phase 2: AI Encoding (Months 6-12)**
- Bill tracking integration
- AI-assisted encoding pipeline
- Human review interface
- Test case generation

**Phase 3: Multi-jurisdiction (Months 12-18)**
- State code ingestion (start with CA, NY, TX)
- Regulation layer (CFR, state regs)
- Program manual integration

**Phase 4: Generation (Months 18-24)**
- Legislative text generation
- Fiscal note automation
- Amendment drafting assistance

### 15.9 Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Legal text parsing errors** | Wrong rules | Human review required; confidence scores |
| **AI hallucination** | Incorrect encoding | Validation against test cases; citation verification |
| **Copyright issues** | Legal liability | Use government sources (public domain) |
| **Keeping up with changes** | Stale rules | Real-time bill tracking; automated alerts |
| **State variation** | 50 different formats | Incremental rollout; jurisdiction-specific parsers |

---

## 16. Microdata calibration layer

### Problem statement

Microsimulation requires representative population data. Survey microdata (CPS, ACS, SCF) must be **calibrated** to match known administrative totals. The challenge: calibration targets include both:

1. **Observed variables** - Wages, demographics (straightforward)
2. **Calculated variables** - Income tax, SNAP benefits (requires rules engine)
3. **Intermediate calculated variables** - E.g., UK voluntary student loan repayments require first calculating required repayment

This creates a **bidirectional dependency** between the rules engine and microdata layer:

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Survey    │─────▶│    Rules    │─────▶│ Calculated  │
│  Microdata  │      │   Engine    │      │  Variables  │
└─────────────┘      └─────────────┘      └─────────────┘
       │                                         │
       │         ┌─────────────┐                 │
       └────────▶│ Calibration │◀────────────────┘
                 │   Engine    │
                 └─────────────┘
                        │
                        ▼
                 ┌─────────────┐
                 │  Calibrated │
                 │  Microdata  │
                 └─────────────┘
```

### Calibration target types

```python
@dataclass(frozen=True)
class CalibrationTarget:
    """A target for microdata calibration."""
    name: str
    target_value: float              # Administrative total (e.g., $3.2T wages)
    source: str                      # Citation (e.g., "IRS SOI Table 1.1")
    variable_type: CalibrationVarType

class CalibrationVarType(Enum):
    OBSERVED = "observed"            # Direct survey variable (wages, age)
    CALCULATED = "calculated"        # Rules engine output (income_tax, snap)
    INTERMEDIATE = "intermediate"    # Calculated, then used for another calibration


@dataclass(frozen=True)
class IntermediateCalibrationTarget(CalibrationTarget):
    """Target that requires prior calculation for calibration logic."""
    prerequisite_variable: str       # Variable to calculate first
    calibration_formula: str         # How to derive calibration target from prerequisite
    # Example: voluntary_student_loan_repayment calibrates based on
    # (actual_repayment - required_student_loan_repayment) for those who overpay
```

### UK voluntary student loan repayment example

This is a concrete example of the intermediate calibration pattern:

```python
# Survey has: total_student_loan_repayment (what people actually paid)
# We need to calibrate: voluntary_student_loan_repayment (overpayments)
# But voluntary = actual - required, where required is calculated

class VoluntaryStudentLoanCalibration:
    """
    Steps:
    1. Calculate required_student_loan_repayment for each person (rules engine)
    2. Derive voluntary = actual - required (where actual > required)
    3. Calibrate voluntary repayments to administrative total
    """

    prerequisite_variable = "required_student_loan_repayment"

    def derive_target_variable(self, actual: Array, required: Array) -> Array:
        """Voluntary repayment is the excess over required."""
        return np.maximum(0, actual - required)

    target = CalibrationTarget(
        name="voluntary_student_loan_repayment",
        target_value=1_200_000_000,  # £1.2B administrative total
        source="Student Loans Company Annual Report 2024",
        variable_type=CalibrationVarType.INTERMEDIATE,
    )
```

### Calibration pipeline architecture

The calibration pipeline must handle these dependencies correctly:

```
Phase 1: Pre-Calibration Calculation
├── Load raw survey microdata
├── Run rules engine to calculate prerequisite variables
│   ├── required_student_loan_repayment
│   ├── Any other intermediate variables
└── Derive calibration target variables

Phase 2: Calibration
├── Collect all calibration targets
│   ├── Observed: wages, employment count, demographics
│   ├── Calculated: income_tax, snap, eitc
│   └── Intermediate: voluntary_student_loan_repayment
├── Run calibration algorithm (entropy balancing, raking)
└── Output: calibrated weights

Phase 3: Post-Calibration Validation
├── Run full rules engine on calibrated data
├── Verify calculated totals match administrative targets
└── Generate calibration quality report
```

### Calibration engine interface

```python
class MicrodataCalibrator:
    """Calibrates microdata weights to match administrative totals."""

    def __init__(
        self,
        rules_engine: RulesEngine,
        targets: List[CalibrationTarget],
    ):
        self.rules_engine = rules_engine
        self.targets = targets
        self._classify_targets()

    def _classify_targets(self):
        """Separate targets by type for processing order."""
        self.observed_targets = [t for t in self.targets
                                  if t.variable_type == CalibrationVarType.OBSERVED]
        self.calculated_targets = [t for t in self.targets
                                    if t.variable_type == CalibrationVarType.CALCULATED]
        self.intermediate_targets = [t for t in self.targets
                                      if t.variable_type == CalibrationVarType.INTERMEDIATE]

    def calibrate(self, microdata: MicrodataSet) -> CalibratedMicrodataSet:
        """
        Main calibration pipeline.

        Returns calibrated microdata with adjusted weights.
        """
        # Phase 1: Calculate intermediate prerequisites
        for target in self.intermediate_targets:
            prereq = target.prerequisite_variable
            microdata = self._calculate_variable(microdata, prereq)
            microdata = self._derive_intermediate(microdata, target)

        # Phase 2: Calculate all calibration target variables
        for target in self.calculated_targets:
            microdata = self._calculate_variable(microdata, target.name)

        # Phase 3: Run calibration algorithm
        calibrated_weights = self._solve_calibration(microdata)

        # Phase 4: Validation
        self._validate_calibration(microdata, calibrated_weights)

        return CalibratedMicrodataSet(microdata, calibrated_weights)

    def _calculate_variable(
        self,
        microdata: MicrodataSet,
        variable: str
    ) -> MicrodataSet:
        """Use rules engine to calculate a variable for all records."""
        results = self.rules_engine.calculate_batch(
            microdata.to_situations(),
            variables=[variable],
        )
        microdata.add_column(variable, results[variable])
        return microdata
```

### Calibration algorithm options

```python
class CalibrationMethod(Enum):
    RAKING = "raking"                    # Iterative proportional fitting
    ENTROPY_BALANCING = "entropy"        # Minimum entropy distance
    GENERALIZED_RAKING = "greg"          # Generalized regression estimator
    QUANTILE_CALIBRATION = "quantile"    # Match distribution, not just total

@dataclass
class CalibrationConfig:
    """Configuration for calibration algorithm."""
    method: CalibrationMethod = CalibrationMethod.ENTROPY_BALANCING
    max_weight_ratio: float = 10.0       # Max ratio of calibrated to original weight
    convergence_tolerance: float = 1e-6
    max_iterations: int = 1000

    # For quantile calibration
    quantile_targets: Optional[Dict[str, List[float]]] = None  # Percentile targets
```

### Integration with rules engine

The key architectural requirement is that the rules engine must support **batch calculation** efficiently for calibration:

```python
class RulesEngine:
    def calculate_batch(
        self,
        situations: List[Situation],
        variables: List[str],
        period: Period,
    ) -> Dict[str, Array]:
        """
        Calculate variables for many households efficiently.

        This is the primary interface for calibration - must be vectorized.
        """
        # Use compiled vectorized code for efficiency
        compiled = self.compile(variables, target="numpy")
        return compiled.execute_batch(situations, period)
```

### Calibration targets registry

```yaml
# calibration/targets/us_2024.yaml
targets:
  # Observed variables
  - name: total_wages
    value: 10_500_000_000_000  # $10.5T
    source: "IRS SOI Table 1.1, Tax Year 2024"
    type: observed

  - name: total_employment
    value: 160_000_000
    source: "BLS Current Employment Statistics, Dec 2024"
    type: observed

  # Calculated variables (rules engine required)
  - name: total_income_tax
    value: 2_400_000_000_000  # $2.4T
    source: "IRS Data Book 2024, Table 1"
    type: calculated

  - name: total_snap_benefits
    value: 112_000_000_000  # $112B
    source: "USDA FNS Program Data, FY2024"
    type: calculated

  - name: total_eitc
    value: 64_000_000_000  # $64B
    source: "IRS SOI EITC Statistics 2024"
    type: calculated

# calibration/targets/uk_2024.yaml
targets:
  - name: total_income_tax
    value: 268_000_000_000  # £268B
    source: "HMRC Tax Receipts 2024-25"
    type: calculated

  - name: voluntary_student_loan_repayment
    value: 1_200_000_000  # £1.2B
    source: "Student Loans Company Annual Report 2024"
    type: intermediate
    prerequisite: required_student_loan_repayment
    derivation: "max(0, actual_repayment - required_repayment)"
```

### Performance considerations

Calibration requires running the rules engine on the full microdata (potentially 100K+ records). Key optimizations:

1. **Vectorized calculation** - Use NumPy/compiled code, not per-household loops
2. **Selective calculation** - Only calculate variables needed for calibration targets
3. **Caching** - Cache calculated variables across calibration iterations
4. **Incremental updates** - For iterative calibration, only recalculate weight-dependent variables

```python
@dataclass
class CalibrationPerformance:
    """Target performance metrics for calibration."""

    # For 200K household microdata:
    phase1_calculation_time: float = 60.0    # 60s for prerequisite calculation
    phase2_calibration_time: float = 30.0    # 30s for weight optimization
    phase3_validation_time: float = 60.0     # 60s for full validation

    # Memory
    peak_memory_gb: float = 8.0              # Fits on 16GB RAM instances
```

---

## 17. Business model: open source code, paid data services

### 17.1 Core principle

**100% of code is open source. Paid services are for data and compute.**

Anyone can clone our repos and run everything themselves. We charge when they use our infrastructure.

### 17.2 What's open source (Apache 2.0)

Everything in git is free forever:

| Repository | Contents |
|------------|----------|
| `rac` | Rules DSL, compiler, runtime |
| `rac-us` | US federal + state rules and parameters |
| `cosilico-uk` | UK rules and parameters |
| `cosilico-data-pipelines` | Microdata processing, calibration, imputation |
| `cosilico-archives` | Document archival scripts and tooling |
| `cosilico-api` | API server code |

Users can:
- Fork and modify anything
- Run microdata pipelines with their own Census API keys
- Archive documents to their own storage
- Host their own API
- Use in commercial products without restriction

### 17.3 What's paid (our infrastructure)

When users call `api.rac.ai`, they pay for:

| Service | Cost Driver | Why Paid |
|---------|-------------|----------|
| API calls | Compute | Server costs |
| Microdata access | Storage + bandwidth | Terabytes of processed data |
| Document downloads | Bandwidth | PDFs, archived sources |
| Large microsimulations | Compute | Census-scale processing |
| Historical vintages | Storage | Years of versioned data |

### 17.4 Pricing tiers

```yaml
free:
  description: "Core mission - calculations accessible to all"
  includes:
    - Single-household calculations (unlimited)
    - Parameter lookups
    - Rules inspection
    - Document metadata (not downloads)
    - Small microsimulations (≤1,000 households)
  rate_limit: 1,000 requests/day

pro:
  price: $X/month
  description: "For researchers and small organizations"
  includes:
    - Everything in Free
    - Document downloads
    - Full-text document search
    - Medium microsimulations (≤100,000 households)
    - Historical vintage access
  rate_limit: 50,000 requests/day

enterprise:
  price: Custom
  description: "For large organizations and production systems"
  includes:
    - Everything in Pro
    - Full microdata access
    - Census-scale microsimulations
    - Dedicated compute
    - SLA guarantees
    - Custom jurisdictions
    - Priority support
  rate_limit: Unlimited
```

### 17.5 The value proposition

"Yes, you *could* run this yourself. But do you want to?"

Self-hosting requires:
- Processing CPS, ACS, SCF, PUF microdata (months of work)
- Running calibration against IRS SOI targets
- Archiving documents across 50 states
- Maintaining forecast vintages
- Petabytes of storage
- DevOps for high-availability API

Or just call our API.

### 17.6 Precedents

This model works well for:

| Company | Open Source | Paid Service |
|---------|-------------|--------------|
| GitLab | GitLab CE | GitLab.com |
| Elasticsearch | Elasticsearch | Elastic Cloud |
| PostHog | PostHog | PostHog Cloud |
| Hugging Face | Transformers | Inference API |
| Supabase | Supabase | Supabase Cloud |

### 17.7 Why this works for Cosilico

1. **Mission alignment** - Core rules engine free means maximum policy impact
2. **Moat is data** - Rules are easy to copy; calibrated microdata is not
3. **Enterprise trust** - Apache 2.0 removes license objections
4. **Community contributions** - Open rules means more eyes on correctness
5. **Sustainable revenue** - Data services fund continued development

---

## 18. Dynamics layer: behavioral responses

> **Note**: The dynamics layer is **out of scope** for `rac`. This section documents the design for an orchestration layer (e.g., `cosilico-api` or `cosilico-sim`) that consumes the rules engine.
>
> The rules engine is intentionally **pure**: it answers "what does the law say?" without behavioral assumptions. Dynamics, microdata, and calibration belong in a separate orchestrator.

The rules engine calculates **static** impacts: "If this policy existed today, what would change?" But real policy analysis often requires **behavioral** responses: "How will people change their behavior in response to policy changes?"

The dynamics layer is **separate from rules** and lives in a different repository:

```
┌─────────────────────────────────────────────────────────────┐
│                       cosilico                              │
│              (main Python package users install)            │
│                                                             │
│  - Dynamics (elasticities, take-up)                        │
│  - Microdata loading & calibration                         │
│  - Scenario comparison                                      │
│  - High-level API: cosilico.simulate(reform, ...)          │
└─────────────────────────────────────────────────────────────┘
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
     ┌───────────┐ ┌───────────┐ ┌───────────┐
     │rac-us│ │cosilico-uk│ │cosilico-ca│
     │  (rules)  │ │  (rules)  │ │  (rules)  │
     └───────────┘ └───────────┘ └───────────┘
            │             │             │
            └─────────────┼─────────────┘
                          ▼
                  ┌───────────────┐
                  │rac│
                  │ (DSL, parser, │
                  │   executor)   │
                  └───────────────┘
```

### 18.1 Why dynamics is separate from rules

The rules layer encodes **law**: what the statute says. Dynamics encode **behavior**: how people respond to incentives. These have different:

| Aspect | Rules | Dynamics |
|--------|-------|----------|
| Source | Statutory text | Empirical research |
| Certainty | Deterministic | Probabilistic (with confidence intervals) |
| Stability | Changes with legislation | Updates with new research |
| Scope | Specific to program | Cross-cutting (labor supply affects many programs) |

Mixing them would conflate "what the law says" with "what we estimate will happen."

### 18.2 Types of behavioral responses

#### Labor supply responses

How work effort changes with marginal tax rates:

```yaml
# dynamics/labor_supply/intensive.yaml
intensive_margin:
  description: Change in hours worked given MTR change

  estimates:
    - elasticity: 0.25
      confidence_interval: [0.15, 0.35]
      source: "Chetty et al. 2011"
      population: general

    - elasticity: 0.10
      confidence_interval: [0.05, 0.20]
      source: "Saez et al. 2012"
      population: high_income

  input: statute/*/marginal_tax_rate
  modifies: core/person/hours_worked

extensive_margin:
  description: Change in labor force participation given participation tax rate

  estimates:
    - elasticity: 0.50
      confidence_interval: [0.25, 0.75]
      source: "Meghir & Phillips 2010"
      population: secondary_earners

    - elasticity: 0.25
      confidence_interval: [0.10, 0.40]
      source: "Chetty et al. 2011"
      population: primary_earners

  input: statute/*/participation_tax_rate
  modifies: core/person/is_employed
```

#### Taxable income elasticity

Broader response including income shifting, timing, avoidance:

```yaml
# dynamics/taxable_income/elasticity.yaml
taxable_income_elasticity:
  description: Percent change in taxable income per percent change in net-of-tax rate

  estimates:
    - elasticity: 0.25
      confidence_interval: [0.10, 0.40]
      source: "Saez 2010"
      population: general

    - elasticity: 0.50
      confidence_interval: [0.30, 0.80]
      source: "Gruber & Saez 2002"
      population: high_income
      threshold: 100_000  # AGI > $100k

  input: statute/26/1/marginal_rate
  modifies: statute/26/62/a/adjusted_gross_income
```

#### Take-up rates

Not everyone claims benefits they're eligible for:

```yaml
# dynamics/takeup/eitc.yaml
eitc_takeup:
  description: Fraction of eligible filers who claim EITC

  estimates:
    - rate: 0.78
      source: "IRS 2022"
      population: all_eligible

    - rate: 0.85
      source: "CBPP 2021"
      population: with_children

    - rate: 0.65
      source: "IRS 2022"
      population: childless

  varies_by:
    - filing_complexity
    - count_qualifying_children
    - income_volatility

  applies_to: statute/26/32/a/1/earned_income_credit
```

```yaml
# dynamics/takeup/snap.yaml
snap_takeup:
  description: Fraction of eligible households participating in SNAP

  estimates:
    - rate: 0.82
      source: "USDA FNS 2023"
      population: all_eligible

    - rate: 0.91
      source: "USDA FNS 2023"
      population: income_below_50_percent_poverty

    - rate: 0.72
      source: "USDA FNS 2023"
      population: elderly

  varies_by:
    - income_to_poverty_ratio
    - state  # State-level variation in outreach
    - age

  applies_to: statute/7/2011/snap_benefit
```

### 18.3 Simulation modes

The executor supports multiple scoring modes:

```python
class ScoringMode(Enum):
    STATIC = "static"              # No behavioral response
    BEHAVIORAL = "behavioral"      # Short-run elasticity responses
    DYNAMIC = "dynamic"            # Long-run with equilibrium effects

@dataclass
class SimulationConfig:
    mode: ScoringMode = ScoringMode.STATIC

    # For behavioral/dynamic modes
    elasticity_source: str = "central"  # "central", "low", "high"
    include_takeup: bool = True
    max_iterations: int = 10  # For convergence
    convergence_threshold: float = 0.001
```

#### Static scoring (default)

```python
# Day-after impact: what if policy changed with no behavioral response?
results = executor.execute(
    code,
    microdata,
    scenario=reform,
    config=SimulationConfig(mode=ScoringMode.STATIC)
)
```

#### Behavioral scoring

```python
# Short-run impact with labor supply response
config = SimulationConfig(
    mode=ScoringMode.BEHAVIORAL,
    elasticity_source="central",
    include_takeup=True,
)

# Iteration 1: Calculate policy impact
baseline = executor.execute(code, microdata, scenario=baseline_scenario)
reform = executor.execute(code, microdata, scenario=reform_scenario)

# Iteration 2+: Apply behavioral responses, recalculate
mtr_change = reform["mtr"] - baseline["mtr"]
hours_response = mtr_change * labor_supply_elasticity
adjusted_microdata = apply_labor_response(microdata, hours_response)
reform_behavioral = executor.execute(code, adjusted_microdata, scenario=reform_scenario)
```

#### Dynamic scoring

```python
# Long-run with macro feedback (iterate to equilibrium)
config = SimulationConfig(
    mode=ScoringMode.DYNAMIC,
    max_iterations=10,
)

for i in range(config.max_iterations):
    results = executor.execute(code, microdata, scenario=reform_scenario)
    microdata = dynamics.apply_all_responses(microdata, results)

    if dynamics.has_converged(results, previous_results):
        break
```

### 18.4 Heterogeneous responses

Elasticities vary by population. The dynamics layer supports conditional estimates:

```yaml
labor_supply_elasticity:
  default: 0.25

  by_population:
    - condition: "is_secondary_earner"
      elasticity: 0.50
      source: "Blundell & MaCurdy 1999"

    - condition: "age >= 55"
      elasticity: 0.15
      source: "French 2005"

    - condition: "has_young_children and is_female"
      elasticity: 0.60
      source: "Blau & Kahn 2007"
```

This translates to vectorized conditional application:

```python
def apply_heterogeneous_elasticity(
    microdata: MicrodataSet,
    elasticity_config: dict,
    mtr_change: np.ndarray,
) -> np.ndarray:
    """Apply population-specific elasticities."""

    response = np.zeros_like(mtr_change)

    for spec in elasticity_config["by_population"]:
        mask = evaluate_condition(microdata, spec["condition"])
        response[mask] = mtr_change[mask] * spec["elasticity"]

    # Default for unmatched
    unmatched = response == 0
    response[unmatched] = mtr_change[unmatched] * elasticity_config["default"]

    return response
```

### 18.5 Uncertainty quantification

Every behavioral estimate has uncertainty. The dynamics layer supports distributional analysis:

```python
@dataclass
class UncertaintyConfig:
    method: str = "monte_carlo"  # or "bounds"
    n_samples: int = 100

def run_with_uncertainty(
    executor: VectorizedExecutor,
    microdata: MicrodataSet,
    dynamics: DynamicsConfig,
    uncertainty: UncertaintyConfig,
) -> DistributionalResult:
    """Run simulation with sampled behavioral parameters."""

    results = []
    for _ in range(uncertainty.n_samples):
        # Sample elasticities from confidence intervals
        sampled_dynamics = dynamics.sample()

        result = executor.execute_behavioral(
            microdata,
            dynamics=sampled_dynamics
        )
        results.append(result)

    return DistributionalResult(
        mean=np.mean(results, axis=0),
        std=np.std(results, axis=0),
        percentiles={
            5: np.percentile(results, 5, axis=0),
            95: np.percentile(results, 95, axis=0),
        }
    )
```

### 18.6 Structural reforms and dynamics

Parameter reforms have well-established elasticities. But **structural reforms** (new programs, program abolition) are harder:

```yaml
# How do people respond to UBI that doesn't exist yet?
reform:
  introduces:
    - universal_basic_income: $1000/month

dynamics:
  # No direct elasticity estimate - must reason from components
  ubi_response:
    type: composite
    components:
      - income_effect:
          source: "implied by labor supply literature"
          estimate: -0.05  # 5% hours reduction from income effect
          uncertainty: high
      - mtb_reduction:
          source: "if UBI replaces means-tested benefits"
          applies_when: replaces_snap or replaces_tanf
          estimate: +0.02  # Reduced MTR → increased work
```

For novel policies, we:
1. Decompose into known response channels
2. Apply existing elasticities to each channel
3. Flag high uncertainty explicitly
4. Report bounds rather than point estimates

### 18.7 Repository structure

The dynamics layer lives in the main `cosilico` package, separate from the engine and rules:

```
cosilico/                    # Main package (pip install cosilico)
├── dynamics/                # Behavioral parameters (research-linked)
│   ├── labor_supply/
│   │   ├── intensive.yaml
│   │   └── extensive.yaml
│   ├── taxable_income/
│   │   └── elasticity.yaml
│   ├── takeup/
│   │   ├── eitc.yaml
│   │   ├── snap.yaml
│   │   └── medicaid.yaml
│   └── macro/
│       └── wage_feedback.yaml
├── microdata/               # Survey → statute mappings
│   ├── cps/
│   │   └── mapping.yaml
│   └── calibration/
│       └── targets.yaml
└── src/
    └── cosilico/
        ├── simulation.py    # High-level API
        └── dynamics.py      # Behavioral executor

rac/             # DSL engine (this repo)
└── src/
    └── cosilico/
        ├── dsl_parser.py
        └── vectorized_executor.py

rac-us/                 # US rules (pure law)
└── statute/
    └── 26/32/...
```

### 18.8 Integration with microdata calibration

The dynamics layer interacts with calibration (Section 16):

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Raw Survey  │───▶│ Calibration │───▶│ Calibrated  │
│ Microdata   │    │ (Section 16)│    │ Microdata   │
└─────────────┘    └─────────────┘    └─────────────┘
                                             │
                   ┌─────────────┐           │
                   │    Rules    │◀──────────┤
                   │  (statute)  │           │
                   └─────────────┘           │
                          │                  │
                          ▼                  │
                   ┌─────────────┐           │
                   │  Dynamics   │◀──────────┘
                   │ (behavior)  │
                   └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │   Results   │
                   │ (with CI)   │
                   └─────────────┘
```

Calibration ensures microdata matches administrative totals under **current law with current behavior**. Dynamics then model how behavior changes under **counterfactual policy**.

---

## 19. Law Archive: unified source of truth

The **law as code** paradigm requires tight integration between statute text and executable encodings. `cosilico/lawarchive` serves as the single source of truth for both.

### 19.1 Architecture: law archive as central hub

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            LAW ARCHIVE (cosilico-lawarchive)                 │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Statute Storage                              │   │
│  │                                                                      │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │   │
│  │  │  Raw Text    │───▶│  Structured  │───▶│   Encoded    │          │   │
│  │  │  (USLM XML)  │    │   Rules      │    │   Formula    │          │   │
│  │  │              │    │  (DSL/AST)   │    │ (Python/JS)  │          │   │
│  │  └──────────────┘    └──────────────┘    └──────────────┘          │   │
│  │                                                                      │   │
│  │  Indexed by: citation + vintage + application_period                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│                                     │                                        │
│              ┌──────────────────────┼──────────────────────┐                │
│              ▼                      ▼                      ▼                │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐        │
│  │    REST API      │   │   CLI (pull/     │   │    AI Agent      │        │
│  │  (production)    │   │   push/sync)     │   │   (encoder)      │        │
│  └──────────────────┘   └──────────────────┘   └──────────────────┘        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          COSILICO ENGINE                                     │
│                                                                              │
│  Pulls formulas from lawarchive → compiles to Python/JS/WASM/SQL            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 19.2 Bi-temporal model for logic (not just parameters)

Section 12 introduced bi-temporal parameters. The same model applies to **formula logic**:

| Dimension | Parameter Example | Logic Example |
|-----------|-------------------|---------------|
| **Vintage** | CTC max = $2000 (TCJA) | Refundable = min($1400, 15% of EI over $2500) |
| **Application date** | CTC in 2025 vs 2030 | Phase-out applies after 2025 |

**Key insight:** The law may specify different formulas for different application periods, all enacted at the same vintage.

```python
# Example: CTC refundability under different vintages

# TCJA vintage (2017-12-22) - applies 2018-2025
class ctc_refundable__tcja(Variable):
    vintage = "2017-12-22"
    applies_from = "2018-01-01"
    applies_to = "2025-12-31"

    def formula(person, period):
        earned_income = person("earned_income", period)
        return min(1400, 0.15 * max(0, earned_income - 2500))

# TCJA vintage ALSO specifies post-sunset logic
class ctc_refundable__tcja_sunset(Variable):
    vintage = "2017-12-22"  # Same vintage!
    applies_from = "2026-01-01"

    def formula(person, period):
        earned_income = person("earned_income", period)
        return 0.15 * max(0, earned_income - 3000)  # Pre-TCJA rules

# ARPA vintage (2021-03-11) - 2021 only
class ctc_refundable__arpa(Variable):
    vintage = "2021-03-11"
    applies_from = "2021-01-01"
    applies_to = "2021-12-31"

    def formula(person, period):
        return person("ctc_max_amount", period)  # Fully refundable
```

**Query semantics:**

```python
# "Under TCJA rules, what is refundable CTC formula for 2030?"
formula = lawarchive.get_formula(
    variable="ctc_refundable",
    vintage="2017-12-22",
    application_date="2030-01-01"
)
# Returns: ctc_refundable__tcja_sunset (sunset kicks in)

# "Under current law (2024), what is refundable CTC formula for 2025?"
formula = lawarchive.get_formula(
    variable="ctc_refundable",
    vintage="2024-01-01",  # Latest known law
    application_date="2025-01-01"
)
# Returns: ctc_refundable__tcja (still in effect)
```

### 19.3 Law archive data model

```python
@dataclass
class LawSection:
    """A section of law with its encodings."""

    # Identity
    citation: Citation           # e.g., "26 USC 32"
    vintage: date               # When this version was enacted
    public_law: str             # e.g., "P.L. 117-169"

    # Raw content
    text: str                   # Statute text
    subsections: list[Subsection]

    # Application period (what the law says it applies to)
    applies_from: date          # "For taxable years beginning after..."
    applies_to: Optional[date]  # Sunset date, if any

    # Structured representation
    rules: list[Rule]           # Parsed rules with conditions/values
    parameters: list[Parameter] # Extracted parameters

    # Encoded implementation
    formula_source: str         # Cosilico DSL code
    compiled_python: str        # Generated Python
    compiled_js: Optional[str]  # Generated JavaScript

    # Provenance
    encoded_by: str             # "claude-opus-4" / "human:jsmith"
    encoded_at: datetime
    verified_by: list[str]      # Review trail
    test_cases: list[TestCase]  # Validation tests


@dataclass
class LawArchiveIndex:
    """Index for querying law sections."""

    def get(
        self,
        citation: str,
        vintage: Optional[date] = None,      # Default: latest
        application_date: Optional[date] = None,  # Default: today
    ) -> LawSection:
        """Get law section matching citation + temporal criteria."""
        ...

    def get_formula(
        self,
        variable: str,
        vintage: Optional[date] = None,
        application_date: Optional[date] = None,
    ) -> Formula:
        """Get encoded formula for a variable."""
        ...

    def history(self, citation: str) -> list[LawSection]:
        """Get all versions of a section across vintages."""
        ...
```

### 19.4 CLI workflow: pull/push/sync

Developers (human or AI) work locally, then sync with the central archive:

```bash
# Authenticate (once)
lawarchive auth

# Pull statute + encoding to work locally
lawarchive pull "26 USC 32" --vintage=2024-01-01

# Creates local workspace:
# ~/.lawarchive/workspace/federal/statute/26/32/
#   ├── statute.md          # Raw text (read-only reference)
#   ├── rules.rac      # DSL encoding (editable)
#   ├── tests.yaml          # Test cases
#   └── metadata.json       # Vintage, provenance

# Edit locally (Claude or human)
claude "update rules.rac to handle the new phase-out"

# Validate before push
lawarchive validate ./26/32/
# ✓ DSL parses correctly
# ✓ Types check
# ✓ 47/47 test cases pass
# ✓ Citations verify against statute text

# Push back to archive
lawarchive push ./26/32/
# → Uploads to central DB
# → Records provenance (who, when, what changed)

# Sync (bidirectional)
lawarchive sync
# → Pulls updates from remote
# → Pushes local changes
# → Handles conflicts
```

### 19.5 AI encoding workflow

The AI agent uses lawarchive as both input and output:

```python
class AIEncoder:
    """AI agent that encodes statutes into Cosilico DSL."""

    def encode_section(self, citation: str, vintage: date) -> Encoding:
        # 1. Pull statute from lawarchive
        section = lawarchive.get(citation, vintage=vintage)

        # 2. Get related context
        references = lawarchive.get_references(citation)
        similar_encodings = lawarchive.search_similar(section.text)

        # 3. Generate encoding
        encoding = self.llm.encode(
            statute_text=section.text,
            subsections=section.subsections,
            reference_encodings=similar_encodings,  # Learn from existing
            test_cases=self._generate_test_cases(section),
        )

        # 4. Validate
        validation = lawarchive.validate(encoding)
        if not validation.passed:
            encoding = self._fix_errors(encoding, validation.errors)

        # 5. Push back to lawarchive
        lawarchive.store_encoding(
            citation=citation,
            vintage=vintage,
            formula=encoding.dsl,
            test_cases=encoding.tests,
            encoded_by=f"claude-{self.model_version}",
        )

        return encoding
```

### 19.6 Engine integration

The Cosilico engine pulls formulas from lawarchive at compile time:

```python
class CosilicoCompiler:
    """Compiles rules from lawarchive into executable code."""

    def compile(
        self,
        jurisdiction: str = "us",
        vintage: date = None,
        application_date: date = None,
    ) -> CompiledRules:
        # Fetch all formulas for this jurisdiction + temporal context
        formulas = lawarchive.get_all_formulas(
            jurisdiction=jurisdiction,
            vintage=vintage or date.today(),
            application_date=application_date or date.today(),
        )

        # Build dependency graph
        dag = self._build_dag(formulas)

        # Compile to target
        return self._compile_dag(dag, target="python")
```

### 19.7 Storage backend

Law archive uses PostgreSQL (Supabase) for production scale:

```sql
CREATE TABLE law_sections (
    id TEXT PRIMARY KEY,              -- "federal/statute/26/32"
    citation TEXT NOT NULL,
    vintage DATE NOT NULL,
    public_law TEXT,

    -- Raw content
    text TEXT,
    subsections JSONB,

    -- Application period
    applies_from DATE,
    applies_to DATE,

    -- Encodings
    formula_source TEXT,              -- Cosilico DSL
    compiled_python TEXT,
    compiled_js TEXT,

    -- Provenance
    encoded_by TEXT,
    encoded_at TIMESTAMP,
    verified_by JSONB,
    test_cases JSONB,

    UNIQUE(citation, vintage)
);

-- Indexes for temporal queries
CREATE INDEX idx_law_sections_citation_vintage
ON law_sections(citation, vintage DESC);

CREATE INDEX idx_law_sections_application
ON law_sections(applies_from, applies_to);

-- Full-text search
CREATE INDEX idx_law_sections_text_search
ON law_sections USING GIN (
    to_tsvector('english', COALESCE(text, ''))
);
```

### 19.8 Implementation status

| Component | Status | Repository |
|-----------|--------|------------|
| Raw statute ingestion | ✅ Implemented | [cosilico-lawarchive](https://github.com/CosilicoAI/cosilico-lawarchive) |
| USLM parser | ✅ Implemented | cosilico-lawarchive |
| SQLite storage (dev) | ✅ Implemented | cosilico-lawarchive |
| PostgreSQL storage | ✅ Implemented | cosilico-lawarchive |
| REST API | ✅ Implemented | cosilico-lawarchive |
| CLI (basic) | ✅ Implemented | cosilico-lawarchive |
| Bi-temporal model | 🔲 Planned | cosilico-lawarchive |
| Encoding storage | 🔲 Planned | cosilico-lawarchive |
| Pull/push/sync | 🔲 Planned | cosilico-lawarchive |
| AI encoding pipeline | 🔲 Planned | cosilico-lawarchive |
| Engine integration | 🔲 Planned | rac |

---

## Appendix A: Comparison with OpenFisca

Based on analysis of [OpenFisca-Core](https://github.com/openfisca/openfisca-core) and [PolicyEngine-Core](https://github.com/PolicyEngine/policyengine-core) source code:

| Aspect | OpenFisca | Cosilico (design goal) |
|--------|-----------|------------------------|
| **Dependency resolution** | Runtime recursive calls | Compile-time DAG construction |
| **Type checking** | Runtime NumPy coercion | Compile-time validation |
| **Memory model** | Full clone per scenario | Copy-on-write (planned) |
| **Compilation targets** | Python only | Python first, then JS/WASM/SQL/Spark |
| **Period handling** | Implicit conversion via holders | Explicit period types in signatures |
| **Entity model** | Single parent per group | Multi-level hierarchy (planned) |
| **Caching** | Per-variable holder cache | Graph-aware invalidation (planned) |
| **Error messages** | Python stack traces | Source-mapped with suggestions (planned) |
| **License** | AGPL-3.0 | Apache 2.0 |

Note: "Cosilico" column reflects design goals. Items marked "(planned)" are not yet implemented.

---

## Appendix B: License considerations

**Why Apache 2.0?**

1. **Enterprise adoption** - AGPL's network clause scares enterprises
2. **Embedding** - Can be included in proprietary products
3. **Patent grant** - Explicit patent license (unlike MIT)
4. **Attribution** - Requires attribution (brand visibility)
5. **Contribution** - Compatible with most other licenses

**Clean-Room Implementation**

To avoid any AGPL contamination:
- No code copied from OpenFisca/PE-Core
- Independent design (this document)
- Fresh implementation from specifications
- Separate contributors (ideally)

---

## Appendix C: Related work

- **OpenFisca** - Original policy-as-code framework
- **PolicyEngine** - OpenFisca fork with improvements
- **TaxBrain** - PSL tax microsimulation
- **EUROMOD** - EU microsimulation model
- **TRIM3** - Urban Institute model
- **Tax-Calculator** - US federal income tax model
- **Catala** - Legal DSL (academic)
