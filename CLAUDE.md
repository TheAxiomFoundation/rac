# RAC (Rules as Code)

Core DSL parser, executor, and vectorized runtime for encoding tax and benefit law.

## CRITICAL: No Country-Specific Rules

**This repo contains ONLY the DSL infrastructure. NO statute files.**

Country-specific rules (.rac files) belong in:
- `rac-us/` - US federal statutes (Title 26 IRC, Title 7 SNAP)
- `rac-uk/` - UK statutes (future)

This separation has been violated multiple times. DO NOT add statute files here.

## DSL syntax (unified)

```yaml
"""
Statute text as a top-level docstring.
"""

parameter_name:
    unit: /1
    from 2024-01-01: 0.10

variable_name:
    imports:
        - path#dependency
    entity: TaxUnit
    period: Year
    dtype: Money
    from 2024-01-01:
        return dependency * parameter_name
```

Key rules:
- No `parameter`/`variable` keyword prefix -- type inferred from fields
- `from YYYY-MM-DD:` for temporal values (scalar = parameter, code block = variable formula)
- Tests go in companion `.rac.test` files, not inline
- Old syntax (`parameter name:`, `variable name:`, `text: |`) still works

## What belongs here

- `src/rac/dsl_parser.py` - DSL parser
- `src/rac/dsl_executor.py` - Single-case executor
- `src/rac/vectorized_executor.py` - Microsimulation executor
- `src/rac/test_runner.py` - Test runner (embedded + .rac.test files)
- `src/rac/registry.py` - File discovery and indexing
- `src/rac/microsim.py` - CPS microdata runner (loads from rac-us)
- `tests/` - Unit tests with inline test fixtures only

## What does NOT belong here

- `statute/` directory - DELETE if it exists
- `.rac` files with real statute encodings
- `parameters.yaml` with real IRS values

## Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Tests
pytest tests/ -v

# Microsim (requires rac-us and cosilico-data-sources)
python -m rac.microsim --year 2024
```

## Related repos

- **rac-us** - US statute encodings
- **autorac** - AI-assisted encoding harness
- **rac-validators** - External calculator validation
- **rac-compile** - Multi-target compiler
