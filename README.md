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

RAC uses a clean, YAML-like DSL for encoding law:

```yaml
"""
(a) In general. - There shall be imposed a tax equal to
3.8 percent of the lesser of net investment income or
the excess of modified AGI over the threshold amount.
"""

niit_rate:
    unit: /1
    from 2013-01-01: 0.038

threshold:
    unit: USD
    from 2013-01-01: 200000

net_investment_income_tax:
    imports:
        - 26/1411/c#net_investment_income
    entity: TaxUnit
    period: Year
    dtype: Money
    from 2013-01-01:
        excess = max(0, magi - threshold)
        return niit_rate * min(net_investment_income, excess)
```

Key features of the syntax:
- **No keyword prefixes** -- definitions are just `name:` (type inferred from fields)
- **`from YYYY-MM-DD:`** -- temporal values (parameters) and formulas (variables)
- **Top-level `""" """`** -- statute text as a docstring
- **`.rac.test` companion files** -- tests live alongside but separate from rules

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

Variables are the atomic units of calculation. Defined with `entity`, `period`, `dtype`, and a formula:

```yaml
earned_income_credit:
    entity: TaxUnit
    period: Year
    dtype: Money
    from 2024-01-01:
        if not is_eligible:
            return 0
        return max(0, initial_credit - reduction)
```

### Parameters

Parameters are time-varying policy values. Defined with `unit` and `from` entries:

```yaml
credit_rate:
    unit: /1
    from 2018-01-01: 0.34
    from 2024-01-01: 0.36
```

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

Legal citations are embedded in the file structure. Each `.rac` file maps to a statute section, with the file path mirroring the legal hierarchy:

```
statute/26/32/a.rac    -> 26 USC Section 32(a) (EITC)
statute/26/1411/a.rac  -> 26 USC Section 1411(a) (NIIT)
```

Cross-references use the `imports` field:

```yaml
eitc:
    imports:
        - 26/32/c#earned_income
        - 26/32/b/1#credit_percentage
    entity: TaxUnit
    period: Year
    dtype: Money
    from 2024-01-01:
        return credit_percentage * earned_income
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
