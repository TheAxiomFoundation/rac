# Cosilico Parameter System

## Overview

Cosilico uses YAML files for parameter declarations, separate from DSL formulas.
Parameters are stored at paths that mirror the statute structure - the file path
itself serves as the citation (no separate `reference` field needed).

Key features:
- **Separation of Concerns**: Policy values separate from calculation logic
- **Auto-Resolution**: Index variables can be automatically looked up
- **Reform Modeling**: Easy to create policy variants by overriding parameters
- **Time Travel**: Built-in support for historical and future values

## Parameter Patterns

### 1. Simple Time-Varying Parameters

```yaml
# statute/26/3101/b/1/rate.yaml
# Path IS the reference: 26 USC § 3101(b)(1)

description: Medicare tax rate
unit: /1

values:
  1986-01-01: 0.0145
```

### 2. Parameters with Numeric Index (Brackets)

For parameters indexed by a numeric dimension (children, income), specify the
full path to the indexing variable:

```yaml
# statute/26/32/b/1/A/credit_percentage.yaml

description: EITC credit percentage by qualifying children
unit: /1
index: statute/26/32/c/1/num_qualifying_children

brackets:
  - threshold: 0
    values:
      1975-01-01: 0.0765
  - threshold: 1
    values:
      1975-01-01: 0.34
  - threshold: 2
    values:
      1975-01-01: 0.40
  - threshold: 3
    values:
      1975-01-01: 0.45
```

The `index` field specifies the full path to the variable used for bracket lookup.
This enables **auto-resolution** - the executor can look up the index variable
automatically without it being passed explicitly.

### 3. Parameters Varying by Filing Status

For parameters that differ by filing status:

```yaml
# statute/26/1411/a/1/threshold.yaml

description: Net Investment Income Tax threshold
unit: currency-USD
index: statute/26/1/filing_status

SINGLE:
  values:
    2013-01-01: 200_000
HEAD_OF_HOUSEHOLD:
  values:
    2013-01-01: 200_000
JOINT:
  values:
    2013-01-01: 250_000
SEPARATE:
  values:
    2013-01-01: 125_000
SURVIVING_SPOUSE:
  values:
    2013-01-01: 250_000
```

### 4. Combined: Filing Status + Brackets

When both dimensions are needed, list both index paths:

```yaml
# statute/26/32/b/2/A/phase_out_start.yaml

description: EITC phase-out start threshold
unit: currency-USD
index:
  - statute/26/1/filing_status
  - statute/26/32/c/1/num_qualifying_children

SINGLE:
  brackets:
    - threshold: 0
      values:
        2024-01-01: 10_330
    - threshold: 1
      values:
        2024-01-01: 22_720

JOINT:
  brackets:
    - threshold: 0
      values:
        2024-01-01: 17_250
    - threshold: 1
      values:
        2024-01-01: 29_640
```

## DSL Reference Syntax

### Auto-Resolution (Recommended)

When the parameter specifies its index path, no argument needed:

```cosilico
# Executor automatically looks up statute/26/32/c/1/num_qualifying_children
let rate = parameter("statute/26/32/b/1/A/credit_percentage")
```

### Explicit Index (For Clarity or Reuse)

You can still pass the index explicitly:

```cosilico
# Explicit - useful for clarity or when reusing parameter in different context
let rate = parameter("statute/26/32/b/1/A/credit_percentage", num_qualifying_children)
```

### Combined Lookup

For multi-dimensional parameters:

```cosilico
# Auto-resolves both filing_status and num_qualifying_children
let threshold = parameter("statute/26/32/b/2/A/phase_out_start")

# Or explicit
let threshold = parameter(
  "statute/26/32/b/2/A/phase_out_start",
  filing_status,
  num_qualifying_children
)
```

## Parameter Resolution

1. **Path Resolution**: `statute/26/32/b/1/A/credit_percentage` maps to
   `statute/26/32/b/1/A/credit_percentage.yaml`

2. **Time Resolution**: The executor uses the simulation period to select
   the appropriate value from the `values` block (finds most recent <= period)

3. **Index Auto-Resolution**: If parameter has `index` field and no index
   argument passed, executor looks up the variable at that path

4. **Bracket Resolution**: For bracket parameters, finds the bracket where
   threshold <= index value (uses highest matching threshold)

## Metadata Fields

| Field | Required | Description |
|-------|----------|-------------|
| `description` | Yes | Human-readable description |
| `unit` | Yes | Data type: `currency-USD`, `/1` (rate), `year`, etc. |
| `index` | No | Path(s) to indexing variable(s) for auto-resolution |
| `values` | * | Date -> value mapping (for simple parameters) |
| `brackets` | * | Array of {threshold, values} (for indexed parameters) |

\* One of `values` or `brackets` (or filing status keys containing these) required.

## File Organization

Parameters live alongside their statute encodings:

```
rac-us/
  statute/
    26/                           # Title 26 - IRC
      32/                         # § 32 - EITC
        b/
          1/
            A/
              credit_percentage.yaml
              formula.rac
          2/
            A/
              phase_out_start.yaml
      1411/                       # § 1411 - NIIT
        a/
          1/
            threshold.yaml
```

The file path serves as the legal citation - no redundant `reference` field needed.
