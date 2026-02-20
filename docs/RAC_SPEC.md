# .rac File Specification v2

Self-contained statute encoding format for tax and benefit rules.

## File Structure

```yaml
# path/to/section.rac - Title

text: """
Statute text here...
"""

param_name:
  description: "..."
  unit: USD
  source: "..."
  values:
    2024-01-01: 100
    2023-01-01: 95

var_name:
  imports: [path#var, path#var2 as alias]
  entity: Household
  period: Month
  dtype: Money
  formula: |
    ...
  tests:
    - inputs: {...}
      expect: ...
```

## Top-level declarations

No keyword prefix — type is inferred from fields:

| Declaration | Syntax | Purpose |
|-------------|--------|---------|
| `text:` | `text: """..."""` | Statute text |
| Definition | `name:` | Parameter or computed value (inferred from fields) |
| `input` | `input name:` | User-provided input |
| `enum` | `enum name:` | Enumeration type |
| `function` | `function name:` | Helper function |

Definitions without `entity:` are parameters (pure scalar values).
Definitions with `entity:` are computed per-entity.

## Parameter attributes

```yaml
contribution_rate:
  description: "Household contribution as share of net income"
  unit: USD           # Optional: USD, rate, years, months, persons
  source: "USDA FNS"  # Optional: data source
  reference: "7 USC 2017(a)"  # Optional: legal citation
  values:
    2024-01-01: 0.30
    2023-01-01: 0.30
```

Parameters are in scope for all definitions in the file.

## Computed value attributes

```yaml
snap_allotment:
  imports: [7/2014#household_size, 7/2014/a#snap_eligible]
  entity: Household       # Required: Person, TaxUnit, Household, Family
  period: Month           # Required: Year, Month, Day
  dtype: Money            # Required: Money, Rate, Boolean, Integer, Enum[...]
  unit: "USD"             # Optional
  label: "SNAP Benefit"   # Optional
  description: "..."      # Optional
  default: 0              # Optional
  formula: |
    if not snap_eligible:
      return 0
    return max_allotment - net_income * contribution_rate
  tests:
    - name: "Basic case"  # Optional
      inputs: {household_size: 4, snap_net_income: 500}
      expect: 823
```

## Import Syntax

```yaml
imports:
  - 7/2014#household_size           # Import as-is
  - 7/2014/e#snap_net_income        # From nested path
  - 26/32#earned_income as ei       # With alias
```

Path format: `title/section/subsection#variable_name`

## Scoping Rules

| Source | In Scope For |
|--------|--------------|
| Same-file parameter | All definitions in file |
| Same-file computed value | Later definitions (dependency order) |
| Imported definition | That definition's formula only |

## Formula Syntax

Python-like with restrictions:
- Keywords: `if`, `else`, `return`, `for`, `break`, `and`, `or`, `not`, `in`
- Built-ins: `max`, `min`, `abs`, `round`, `sum`, `len`
- **No numeric literals** except -1, 0, 1, 2, 3 (use parameters)

```yaml
formula: |
  if household_size <= minimum_benefit_max_size:
    return minimum_benefit
  return 0
```

## Test Syntax

```yaml
tests:
  - name: "Family of 4"           # Optional name
    period: 2024-01               # Optional: defaults to current
    inputs:
      household_size: 4
      snap_net_income: 500
      snap_eligible: true
    expect: 823                   # Expected output value
```

## Versioning (Temporal)

For statutes with formula changes over time:

```yaml
additional_ctc:
  entity: TaxUnit
  period: Year
  dtype: Money

  versions:
    2018-01-01:
      enacted_by: "P.L. 115-97 § 11022"
      parameters:
        threshold: 2500
        cap: 1400
      formula: |
        ...TCJA formula...

    2026-01-01:
      enacted_by: "P.L. 115-97 sunset"
      reverts_to: 2001-01-01
```

## File Naming

Filepath = legal citation:
```
statute/7/2017/a.rac      → 7 USC § 2017(a)
statute/26/24/d/1/B.rac   → 26 USC § 24(d)(1)(B)
```

## Migration from v1

Old format (separate files):
- `variable.rac` + `parameters.yaml` + `tests.yaml`

New format (self-contained):
- Single `.rac` with definitions and `tests:` inline

Use `scripts/convert_to_new_format.py` for automated migration.
