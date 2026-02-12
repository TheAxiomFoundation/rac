# RAC (Rules as Code)

**Parse, compile, and execute encoded law.**

RAC provides a pipeline for encoding tax and benefit rules as executable code:

```
.rac source → parse → compile (temporal resolution) → execute / Rust codegen
```

Part of the [Rules Foundation](https://rules.foundation) open-source infrastructure.

## Quick start

```bash
pip install rac
```

```python
from datetime import date
from rac import parse, compile, execute

module = parse("""
    entity person:
        income: float

    variable gov/rate:
        from 2024-01-01: 0.20

    variable person/tax:
        entity: person
        from 2024-01-01: income * gov/rate
""")

ir = compile([module], as_of=date(2024, 6, 1))
result = execute(ir, {"person": [{"id": 1, "income": 50000}]})

print(result.scalars)  # {'gov/rate': 0.2}
print(result.entities)  # {'person': {'person/tax': [10000.0]}}
```

## Pipeline

### Parse

The parser reads `.rac` source into a Pydantic AST:

```python
from rac import parse, parse_file

module = parse(source_string)
module = parse_file("path/to/rules.rac")
```

AST nodes: `Module`, `VariableDecl`, `EntityDecl`, `AmendDecl`, `TemporalValue`, `Expr`, etc.

### Compile

The compiler resolves temporal layers for a specific date and topologically sorts the variable graph:

```python
from rac import compile

ir = compile([base_module, reform_module], as_of=date(2024, 6, 1))
# ir.variables: dict of resolved expressions
# ir.order: topologically sorted variable paths
# ir.schema_: entity schema
```

### Execute

The Python executor evaluates the IR against input data:

```python
from rac import execute

result = execute(ir, {"person": [{"id": 1, "income": 50000}]})
result.scalars   # scalar variables
result.entities  # per-entity computed values
```

### Rust codegen

Generate Rust source for native compilation (~97M rows/sec):

```python
from rac import generate_rust, compile_to_binary

rust_code = generate_rust(ir)  # Rust source string
binary = compile_to_binary(ir)  # compiled native binary
```

### Model API

High-level API combining parse + compile + native binary:

```python
from rac import Model

model = Model.from_file("rules.rac", as_of=date(2024, 6, 1))
result = model.run({"person": large_dataset})

# Reform comparison
reform = Model.from_file("rules.rac", "reform.rac", as_of=date(2025, 1, 1))
comparison = model.compare(reform, data)
```

## Syntax

```yaml
# Entity declarations
entity person:
    income: float
    age: int
    household: -> household   # foreign key

# Scalar variables with temporal values
variable gov/tax/rate:
    from 2024-01-01: 0.20
    from 2025-01-01: 0.22

# Entity variables with formulas
variable person/tax:
    entity: person
    from 2024-01-01: income * gov/tax/rate

# Conditionals
variable person/benefit:
    entity: person
    from 2024-01-01:
        if income < 20000: 5000
        else: 0

# Amendments (for reform modeling)
amend gov/tax/rate:
    from 2025-06-01: 0.18
```

## Development

```bash
git clone https://github.com/RulesFoundation/rac
cd rac
pip install -e ".[dev]"
pytest tests/ -v
```

Rust toolchain needed for native compilation tests (auto-installs via rustup).

## License

Apache 2.0
