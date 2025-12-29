# .rac File Specification v2

Self-contained statute encoding format for tax and benefit rules.

## File Structure

```yaml
# path/to/section.rac - Title

text: """
Statute text here...
"""

parameter param_name:
  description: "..."
  unit: USD
  values:
    1988-01-01: 5_000

variable var_name:
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

## Top-Level Declarations

All declarations are named (no block-style grouping):

| Declaration | Syntax | Purpose |
|-------------|--------|---------|
| `text:` | `text: """..."""` | Statute text |
| `parameter` | `parameter name:` | Policy value |
| `variable` | `variable name:` | Computed value |
| `input` | `input name:` | User-provided input |
| `enum` | `enum name:` | Enumeration type |
| `function` | `function name:` | Helper function |
| `indexing_rule` | `indexing_rule name:` | Inflation adjustment rule |

## Parameter Attributes

```yaml
parameter contribution_rate:
  description: "Household contribution as share of net income"
  unit: USD           # Optional: USD, rate, years, months, persons
  indexed_by: path/to/indexing_rule  # Optional: inflation adjustment
  values:
    1988-01-01: 5_000  # Base statutory value
```

Parameters are in scope for all variables in the file.

## Variable Attributes

```yaml
variable snap_allotment:
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

## Indexing Rule Attributes

```yaml
indexing_rule standard_deduction_inflation:
  description: "Cost-of-living adjustment for standard deduction"
  base_year: 1987
  rounding: 50      # round down to nearest $50
  series: bls/chained_cpi_u  # resolves to indices schema
```

| Attribute | Required | Description |
|-----------|----------|-------------|
| `description` | Yes | Human-readable description |
| `base_year` | Yes | Year from which indexing begins |
| `rounding` | Yes | Round down to nearest N dollars |
| `series` | Yes | Path to economic series in indices schema |

Parameters reference indexing rules via `indexed_by`:

```yaml
parameter basic_single:
  indexed_by: 26/63/c/4  # path to file containing indexing_rule
  values:
    1988-01-01: 3_000  # base statutory value
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
| Same-file parameter | All variables in file |
| Same-file variable | Later variables (dependency order) |
| Imported variable | That variable's formula only |

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

## Style Rules

### Thousands Separator

Use underscore `_` for numbers >= 1000 for readability:

```yaml
# Good
values:
  1988-01-01: 5_000
  2024-01-01: 29_200

# Bad
values:
  1988-01-01: 5000
  2024-01-01: 29200
```

### File Naming

Filepath = legal citation:
```
statute/7/2017/a.rac      → 7 USC § 2017(a)
statute/26/24/d/1/B.rac   → 26 USC § 24(d)(1)(B)
```

## Versioning (Temporal)

For statutes with formula changes over time:

```yaml
variable additional_ctc:
  entity: TaxUnit
  period: Year
  dtype: Money

  versions:
    2018-01-01:
      enacted_by: "P.L. 115-97 § 11022"
      parameters:
        threshold: 2_500
        cap: 1_400
      formula: |
        ...TCJA formula...

    2026-01-01:
      enacted_by: "P.L. 115-97 sunset"
      reverts_to: 2001-01-01
```
