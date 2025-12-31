# Cosilico Core

**The API layer for AI systems to access the law, encoded.**

Cosilico is building Stripe-quality APIs for tax and benefit law. As AI systems increasingly need to reason about legal and financial rules, they need reliable, programmatic access to encoded legislation - not PDFs or chatbot summaries.

## What We Build

- **Rules Engine** - Tax and benefit calculations with first-class legal citations
- **Microdata Infrastructure** - ML-enhanced datasets with imputed attributes
- **APIs for AI** - Structured access to encoded law for LLMs and agents

## Use Cases

- **AI Agents** - Give AI systems reliable tools to calculate taxes, benefits, eligibility
- **Microsimulation** - Calculate taxes and benefits for millions of households
- **Data Enrichment** - Impute income, demographics, consumption patterns to customer data
- **Benefit Administration** - Precise enough to power eligibility systems
- **Enterprise Scale** - Process census-scale datasets efficiently

We're less interested in flashy web apps - AIs will generate those in seconds. We're building the infrastructure those AIs need.

## Why a New Engine?

OpenFisca was designed 15 years ago. While it pioneered policy-as-code, modern requirements demand:

| Requirement | OpenFisca Limitation | Cosilico Solution |
|-------------|---------------------|-------------------|
| Multi-target deployment | Python-only | Compile to Python, JS, WASM, SQL |
| Static analysis | Runtime dependency discovery | Build-time DAG analysis |
| Memory efficiency | Full clone per scenario | Copy-on-write semantics |
| Incremental computation | Recompute everything | Change tracking |
| Type safety | Runtime type coercion | Static type checking |
| Licensing | AGPL (viral) | Apache 2.0 (permissive) |
| Legal citations | URLs as strings | First-class law semantics |
| Temporal tracking | Single time dimension | Bi-temporal (effective + knowledge) |
| Jurisdiction scale | Monolithic packages | Modular per-jurisdiction repos |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         RULE DEFINITION                          │
│  Python decorators + type hints → Validated rule specifications │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                         COMPILATION                              │
│  Parse → Analyze → Optimize → Generate target code              │
└─────────────────────────────────────────────────────────────────┘
                                ↓
        ┌───────────┬───────────┬───────────┬───────────┐
        ↓           ↓           ↓           ↓           ↓
    Python      JavaScript    WASM        SQL        Spark
   (NumPy)      (Browser)   (Native)   (Batch)   (Distributed)
```

## Quick Start

```python
from cosilico import variable, parameter, entity, Year, Money

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
cosilico compile rules/ --target python --output calculator.py

# JavaScript (for browser)
cosilico compile rules/ --target javascript --output calculator.js

# SQL (for batch processing)
cosilico compile rules/ --target sql --output calculator.sql
```

## Key Concepts

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

### Law Reference Semantics

Legal citations are first-class citizens, not just documentation URLs:

```python
from cosilico import variable, LegalCitation

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
    # Link formula components to specific law subsections
    formula_references={
        "phase_in_rate": "26 USC § 32(b)(1)(A)",
        "earned_income_threshold": "26 USC § 32(b)(2)(A)",
    }
)
def eitc(tax_unit, period):
    ...
```

### Bi-Temporal Parameters

Know what was legislated when - track both effective time and knowledge time:

```python
# What was the 2027 tax rate as known in early 2024 (before any extension)?
brackets.get(Date(2027, 1, 1), as_of=Date(2024, 1, 1))
# -> Returns pre-TCJA rates (sunset was law)

# What is the 2027 tax rate as known today (after hypothetical extension)?
brackets.get(Date(2027, 1, 1), as_of=Date(2026, 1, 1))
# -> Returns extended TCJA rates
```

### Jurisdiction Modularity

Split massive country packages into composable jurisdiction-specific modules:

```
rac-us/              # Federal-only
rac-us-ca/           # California (extends rac-us)
rac-us-ca-sf/        # San Francisco (extends rac-us-ca)
```

Compile only what you need:

```bash
# Minimal bundle with federal + California rules
cosilico compile --jurisdictions us,us.ca --variables income_tax,ca_eitc
```

## License

Apache 2.0 - Use freely in commercial and open-source projects.

## Validation Strategy

Cosilico uses a two-phase validation approach:

### Phase 1: Reference Validation (Once per Variable)
Each variable is validated against PolicyEngine (the reference implementation) to ensure correctness:
```bash
# Validate EITC against PolicyEngine-US
cosilico validate eitc --reference policyengine-us --cases 1000
```

This runs test cases through both Cosilico (Python target) and PolicyEngine, flagging any discrepancies.

### Phase 2: Cross-Compilation Consistency (Continuous)
Once validated against the reference, we ensure ALL compilation targets produce **identical results**:

```
    DSL Source
        │
        ├──► Python  ──┐
        ├──► JS      ──┼──► Must all produce identical output
        ├──► WASM    ──┤    for the same inputs
        └──► SQL     ──┘
```

Tests in `tests/test_cross_compilation.py` verify this property:
- Same inputs → same outputs across all targets
- Floating point precision handled consistently
- Edge cases (zero, negative, boolean) match exactly

This strategy means:
1. **Bug fixes are validated once** against PolicyEngine
2. **New targets automatically inherit correctness** - just prove they match existing targets
3. **CI is fast** - cross-compilation tests don't require PolicyEngine

## Status

🚧 **Early Development** - Not yet ready for production use.

See [DESIGN.md](docs/DESIGN.md) for detailed architecture documentation.
