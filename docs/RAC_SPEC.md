# .rac file specification

Self-contained statute encoding format for tax and benefit rules.
Parsed by a recursive descent parser into a typed AST.

## File structure

```yaml
# path/to/section.rac - Title

"""
Statute text here...
"""

# Statute text also appears in comments
# (a) In general.— ...

param_name:
  description: "..."
  unit: USD
  from 2024-01-01: 100
  from 2023-01-01: 95

var_name:
  imports:
    - path#var
    - path#var2 as alias
  entity: TaxUnit
  period: Year
  dtype: Money
  from 2024-01-01:
    if not eligible: 0
    else: param_name * input_value
```

## Top-level declarations

No keyword prefix — type is inferred from fields:

| Declaration | Syntax | Purpose |
|-------------|--------|---------|
| Text block | `"""..."""` | Statute text |
| Comment | `# ...` | Statute text, section headers |
| Definition | `name:` | Parameter or computed value (inferred from fields) |
| `entity` | `entity name:` | Entity type with fields |
| `amend` | `amend path:` | Override for reform modeling |

Definitions without `entity:` are parameters (pure scalar values).
Definitions with `entity:` are computed per-entity.

## Parameter attributes

```yaml
contribution_rate:
  description: "Household contribution as share of net income"
  unit: USD           # Optional: USD, /1, years, months, persons
  source: "USDA FNS"  # Optional: data source
  reference: "7 USC 2017(a)"  # Optional: legal citation
  from 2024-01-01: 0.30
  from 2023-01-01: 0.30
```

Parameters are in scope for all definitions in the file.

## Computed value attributes

```yaml
snap_allotment:
  imports:
    - 7/2014#household_size
    - 7/2014/a#snap_eligible
  entity: Household       # Required: Person, TaxUnit, Household, Family
  period: Month           # Required: Year, Month, Day
  dtype: Money            # Required: Money, Rate, Boolean, Integer, Enum[...]
  unit: "USD"             # Optional
  label: "SNAP Benefit"   # Optional
  description: "..."      # Optional
  default: 0              # Optional
  from 2024-01-01:
    if not snap_eligible: 0
    else: max_allotment - net_income * contribution_rate
```

## Import syntax

```yaml
imports:
  - 7/2014#household_size           # Import as-is
  - 7/2014/e#snap_net_income        # From nested path
  - 26/32#earned_income as ei       # With alias
```

Path format: `title/section/subsection#variable_name`

## Scoping rules

| Source | In scope for |
|--------|--------------|
| Same-file parameter | All definitions in file |
| Same-file computed value | Later definitions (dependency order) |
| Imported definition | That definition's formula only |

## Expression syntax

Expression-based — the last expression in a block is the value. No `return` keyword.

- Conditionals: `if cond: expr elif cond: expr else: expr`
- Let-bindings: `name = expr` (followed by body expression)
- Logic: `and`, `or`, `not`
- Comparison: `<`, `<=`, `>`, `>=`, `==`, `!=`
- Built-ins: `max`, `min`, `abs`, `round`, `sum`, `len`, `clip`, `any`, `all`
- Field access: `person.income`
- Boolean literals: `True`, `False`, `true`, `false`
- **No magic numbers** — only -1, 0, 1, 2, 3 in formulas (use parameters)

```yaml
# Simple conditional
snap_allotment:
  entity: Household
  from 2024-01-01:
    if not snap_eligible: 0
    else: max_allotment - net_income * contribution_rate

# Let-bindings
actc_amount:
  entity: TaxUnit
  from 2018-01-01:
    uncapped = min(ctc_after_phaseout, actc_limitation)
    max_refundable = qualifying_child_count * actc_max_per_child
    min(uncapped, max_refundable)

# Multi-branch conditionals
applicable_percentage:
  entity: TaxUnit
  from 2026-01-01:
    if fpl_pct < tier_1_threshold: rate_1
    elif fpl_pct < tier_2_threshold: rate_2
    elif fpl_pct < tier_3_threshold: rate_3
    else: rate_4
```

## Temporal values

Use `from YYYY-MM-DD:` for effective dates:

```yaml
ctc_base_amount:
  from 1998-01-01: 400
  from 1999-01-01: 500
  from 2001-01-01: 600
  from 2003-01-01: 1000
  from 2018-01-01: 2000
  from 2025-01-01: 2200
```

## Test syntax (inline)

Tests live in a separate `.rac.test` file alongside the `.rac` file:

```yaml
# file.rac.test
snap_allotment:
  - name: "Family of 4"
    period: 2024-01
    inputs:
      household_size: 4
      snap_net_income: 500
      snap_eligible: true
    expect: 823

  - name: "Ineligible"
    period: 2024-01
    inputs:
      snap_eligible: false
    expect: 0
```

## Amendments (reforms, legislative updates, and annual publications)

```yaml
amend gov/tax/personal_allowance:
    from 2025-04-06: 15000

amend gov/tax/standard_deduction:
    source: "Rev. Proc. 2026-34"
    source_tier: publication
    from 2026-01-01: 15600
```

Amendments may include:

- `source:` controlling legal or publication citation
- `source_tier:` one of `projection`, `amendment`, `legislation`, `publication`
- `priority:` integer tie-breaker within the same tier
- `replace: true` to fully replace earlier temporal values for the target

Precedence is:

`publication > legislation > amendment > projection > statute`

Within the same tier, higher `priority` wins; if still tied, later declarations win.

## File naming

Filepath = legal citation:
```
statute/7/2017/a.rac      → 7 USC § 2017(a)
statute/26/24/d/1/B.rac   → 26 USC § 24(d)(1)(B)
statute/26/32/b.rac       → 26 USC § 32(b)
```
