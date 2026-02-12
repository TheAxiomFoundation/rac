# RAC (Rules as Code)

Parse, compile, and execute encoded law. Pipeline: `.rac` source -> AST -> IR -> Python executor / Rust native binary.

## CRITICAL: No country-specific rules

**This repo contains ONLY the DSL infrastructure. NO statute files.**

Country-specific rules (.rac files) belong in:
- `rac-us/` - US federal statutes (Title 26 IRC, Title 7 SNAP)
- `rac-uk/` - UK statutes (future)

## Architecture

```
src/rac/
  ast.py        - Pydantic AST nodes (Module, VariableDecl, Expr, etc.)
  parser.py     - Recursive descent parser (lexer + parser, ~420 lines)
  compiler.py   - Temporal resolution + topo sort -> IR
  executor.py   - Python interpreter for IR
  schema.py     - Entity/Field/ForeignKey/Data model
  model.py      - High-level Model API (parse + compile + native)
  native.py     - Rust binary compilation + execution
  codegen/      - Code generators (Rust)
  validate.py   - Schema + import validation CLI for statute repos
```

## Syntax

```yaml
entity person:
    income: float

variable gov/rate:
    from 2024-01-01: 0.20
    from 2025-01-01: 0.22

variable person/tax:
    entity: person
    from 2024-01-01: income * gov/rate

amend gov/rate:
    from 2025-06-01: 0.18
```

Key rules:
- `variable` keyword required (explicit declaration)
- `from YYYY-MM-DD:` for temporal values (scalar literals or expressions)
- `entity:` field ties a variable to an entity type
- `amend` overrides existing variables (for reform modeling)
- Expression-based formulas (no `return` keyword)
- Builtins: `max`, `min`, `abs`, `round`, `sum`, `len`, `clip`, `any`, `all`

## Commands

```bash
pip install -e .
pytest tests/ -v
ruff check src/ tests/
python examples/run_reform.py
```

## Related repos

- **rac-us** - US statute encodings
- **autorac** - AI-assisted encoding harness
- **rac-validators** - External calculator validation
- **rac-compile** - Multi-target compiler
