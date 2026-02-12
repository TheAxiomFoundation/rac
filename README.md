# RAC (Rules as Code)

**DSL parser, executor, and vectorized runtime for encoding tax and benefit law.**

RAC is the core infrastructure for encoding statutes as executable code. It provides a purpose-built DSL for defining tax and benefit rules with first-class legal citations, time-varying parameters, and multi-target compilation.

Part of the [Rules Foundation](https://rules.foundation) open-source infrastructure.

## What RAC provides

- **Rules Engine** - Tax and benefit calculations with first-class legal citations
- **Microdata Infrastructure** - ML-enhanced datasets with imputed attributes
- **Multi-target compilation** - Compile to Python, JS, WASM, SQL

## Use cases

- **AI Agents** - Give AI systems reliable tools to calculate taxes, benefits, eligibility
- **Microsimulation** - Calculate taxes and benefits for millions of households
- **Data Enrichment** - Impute income, demographics, consumption patterns to customer data
- **Benefit Administration** - Precise enough to power eligibility systems
- **Enterprise Scale** - Process census-scale datasets efficiently

## Architecture

```
               RULE DEFINITION (.rac files)
                        |
                    COMPILATION
     Parse -> Analyze -> Optimize -> Generate
                        |
        +--------+------+------+--------+
        |        |      |      |        |
     Python     JS    WASM    SQL     Spark
    (NumPy)  (Browser)(Native)(Batch)(Distributed)
```

## Quick start

```python
from rac import variable, parameter, entity, Year, Money

@entity
class Person:
    pass

@entity(contains=Person)
class TaxUnit:
    pass

@variable(entity=Person, period=Year, dtype=Money)
def wages(person, period):
    return person.input("wages", period)

@variable(entity=TaxUnit, period=Year, dtype=Money)
def total_income(tax_unit, period):
    return tax_unit.sum(wages)

@variable(entity=TaxUnit, period=Year, dtype=Money)
def income_tax(tax_unit, period):
    income = total_income(tax_unit, period)
    brackets = parameter("gov.irs.income.brackets", period)
    return brackets.calc(income)
```

Compile to different targets:

```bash
# Python (for microsimulation)
rac compile rules/ --target python --output calculator.py

# JavaScript (for browser)
rac compile rules/ --target javascript --output calculator.js

# SQL (for batch processing)
rac compile rules/ --target sql --output calculator.sql
```

## Key concepts

### Variables

Variables are the atomic units of calculation. Each variable:
- Belongs to an **entity** (Person, TaxUnit, Household, etc.)
- Has a **period** (Year, Month, Day, Instant)
- Has a **data type** (Money, Rate, Boolean, Integer, Enum)
- Has a **formula** (computation from other variables/inputs)

### Parameters

Parameters are time-varying policy values:
- Tax rates, thresholds, brackets
- Benefit amounts, phase-outs
- Eligibility criteria

Parameters are defined separately from formulas, enabling:
- What-if analysis (reforms)
- Historical calculations
- Projections

### Entities

Entities model the structure of who/what is being calculated:
- **Person** - Individual
- **TaxUnit** - Tax filing unit
- **Household** - Residential unit
- **SPMUnit** - Supplemental Poverty Measure unit
- **State/Region** - Geographic groupings

Entities form a hierarchy enabling aggregation (sum, any, max) and broadcasting.

### Periods

Explicit time handling:
- **Year** - Calendar or fiscal year
- **Month** - Calendar month
- **Day** - Specific date
- **Instant** - Point in time (for stocks vs flows)

### Law reference semantics

Legal citations are first-class citizens, not just documentation URLs:

```python
from rac import variable, LegalCitation

@variable(
    entity=TaxUnit,
    period=Year,
    dtype=Money,
    references=[
        LegalCitation(
            jurisdiction="us",
            code="usc",
            title="26",
            section="32",
            subsection="(a)(1)",
        ),
    ],
    formula_references={
        "phase_in_rate": "26 USC 32(b)(1)(A)",
        "earned_income_threshold": "26 USC 32(b)(2)(A)",
    }
)
def eitc(tax_unit, period):
    ...
```

### Bi-temporal parameters

Track both effective time and knowledge time:

```python
# What was the 2027 tax rate as known in early 2024 (before any extension)?
brackets.get(Date(2027, 1, 1), as_of=Date(2024, 1, 1))
# -> Returns pre-TCJA rates (sunset was law)

# What is the 2027 tax rate as known today (after hypothetical extension)?
brackets.get(Date(2027, 1, 1), as_of=Date(2026, 1, 1))
# -> Returns extended TCJA rates
```

### Jurisdiction modularity

Split massive country packages into composable jurisdiction-specific modules:

```
rac-us/              # Federal-only
rac-us-ca/           # California (extends rac-us)
rac-us-ca-sf/        # San Francisco (extends rac-us-ca)
```

Compile only what you need:

```bash
rac compile --jurisdictions us,us.ca --variables income_tax,ca_eitc
```

## Validation strategy

RAC uses a two-phase validation approach:

### Phase 1: Reference validation (once per variable)
Each variable is validated against PolicyEngine (the reference implementation):
```bash
rac validate eitc --reference policyengine-us --cases 1000
```

### Phase 2: Cross-compilation consistency (continuous)
All compilation targets must produce identical results:

```
    DSL Source
        |
        +---> Python  --+
        +---> JS      --+-- Must all produce identical output
        +---> WASM    --+   for the same inputs
        +---> SQL     --+
```

## License

Apache 2.0 - Use freely in commercial and open-source projects.

## Status

Early development - not yet ready for production use.

See [DESIGN.md](docs/DESIGN.md) for detailed architecture documentation.
