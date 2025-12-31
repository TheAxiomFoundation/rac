# RAC (Rules as Code)

Core DSL parser, executor, and vectorized runtime for encoding tax and benefit law.

## ⚠️ CRITICAL: No Country-Specific Rules ⚠️

**This repo contains ONLY the DSL infrastructure. NO statute files.**

Country-specific rules (.rac files) belong in:
- `rac-us/` - US federal statutes (Title 26 IRC, Title 7 SNAP)
- `rac-uk/` - UK statutes (future)

This separation has been violated multiple times. DO NOT add statute files here.

## What Belongs Here

- `src/rac/parser.py` - DSL parser
- `src/rac/executor.py` - Single-case executor
- `src/rac/vectorized.py` - Microsimulation executor
- `src/rac/microsim.py` - CPS microdata runner (loads from rac-us)
- `tests/` - Unit tests with inline test fixtures only

## What Does NOT Belong Here

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

## Related Repos

- **rac-us** - US statute encodings
- **autorac** - AI-assisted encoding harness
- **rac-validators** - External calculator validation
- **cosilico-data-sources** - CPS microdata, parameters
- **cosilico-compile** - Multi-target compiler
