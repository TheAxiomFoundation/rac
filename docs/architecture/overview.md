# Architecture Overview

Cosilico is a rules engine for encoding tax and benefit law as executable code.

## Core Design Principles

1. **Statute-Organized Code** - File paths mirror legal citations
2. **Explicit References** - Dependencies declared, not inferred
3. **Multi-Jurisdiction** - Each jurisdiction in its own repo
4. **Full Versioning** - Parameters, forecasts, and calculations reproducible across time
5. **AI-Native** - Designed for automated encoding and verification

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                       COSILICO SYSTEM                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ rac │  │   cosilico-us   │  │  cosilico-uk    │ │
│  │                 │  │                 │  │                 │ │
│  │  - DSL Compiler │  │  - Federal IRC  │  │  - UK Tax       │ │
│  │  - Runtime      │  │  - CFR Regs     │  │  - Benefits     │ │
│  │  - AI Encoder   │  │  - IRS Guidance │  │  - HMRC         │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                    │                    │          │
│           └────────────────────┼────────────────────┘          │
│                                │                               │
│                                ▼                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                    Calculation Engine                    │  │
│  │                                                          │  │
│  │  - Dependency resolution across jurisdictions            │  │
│  │  - Entity/period injection                               │  │
│  │  - Circular dependency handling (SALT)                   │  │
│  │  - Vintage pinning                                       │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## Key Concepts

### Variables

Atomic units of calculation, one per statutory clause:

```python
# us/irc/.../§32/(a)/(2)/(A)/variables/initial_credit_amount.rac

references:
  earned_income: us/irc/.../§32/(c)/(2)/(A)/earned_income
  credit_percentage: us/irc/.../§32/(b)/(1)/credit_percentage

def initial_credit_amount() -> Money:
    return credit_percentage * min(earned_income, earned_income_amount)
```

### Parameters

Time-varying policy values stored as YAML:

```yaml
# us/irc/.../§32/(b)/(1)/parameters/credit_percentage.yaml

citation: 26 USC §32(b)(1)
values:
  2024-01-01:
    no_children: 0.0765
    one_child: 0.34
    two_children: 0.40
    three_plus: 0.45
```

### References

Named mappings from aliases to absolute statutory paths:

```python
references:
  federal_agi: us/irc/.../§62/(a)/adjusted_gross_income
  prior_year_agi: us/irc/.../§62/(a)/adjusted_gross_income@year-1
```

## Learn More

- {doc}`statute-organization` - How code mirrors legal structure
- {doc}`references` - Dependency declaration and vintage pinning
- {doc}`jurisdictions` - Multi-repo architecture
- {doc}`parameters` - Time-varying values and versioning
- {doc}`versioning` - Bi-temporal reproducibility
