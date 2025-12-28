# Cosilico DSL Specification

## Executive summary

Cosilico uses a purpose-built domain-specific language for encoding tax and benefit rules. This is a deliberate choice over Python decorators (OpenFisca/PolicyEngine approach) for five strategic reasons:

1. **Safety** - Untrusted code (AI-generated, user-submitted, third-party) cannot escape the sandbox
2. **Multi-target compilation** - Clean IR enables Python, JS, WASM, SQL, Spark backends
3. **Legal-first design** - Citations are syntax, not comments
4. **AI-native** - Constrained grammar is easier to generate correctly and validate
5. **Formal verification** - Amenable to proving properties (monotonicity, boundedness)

This document specifies the language syntax, semantics, and tooling requirements.

---

## 1. Design principles

### 1.1 Safety over flexibility

```
PRINCIPLE: Any .rac file can be executed without risk.
```

Unlike Python, where `@variable` decorated functions can import os, make network calls, or modify global state, Cosilico DSL is:
- **Pure** - No side effects, no I/O
- **Terminating** - No unbounded recursion or loops
- **Bounded** - Runtime enforces memory and compute limits
- **Sandboxed** - No access to filesystem, network, or system calls

This enables:
- Running user-submitted reforms in production
- AI agents writing rules without human review for safety (only correctness)
- Third-party jurisdiction packages without security audits

### 1.2 Compilation over interpretation

```
PRINCIPLE: Rules are compiled, not interpreted.
```

The DSL compiles to an Intermediate Representation (IR) that is then code-generated to targets:

```
.rac files → Parser → IR → Optimizer → Code Generator → Target
                                                              ├── Python (NumPy)
                                                              ├── JavaScript (TypedArrays)
                                                              ├── WASM (native)
                                                              ├── SQL (CTEs)
                                                              └── Spark (PySpark)
```

This design:
- Allows the same rules to run on all targets without modification
- Enables target-specific optimizations (vectorization for Python, loops for JS)
- Moves error detection from runtime to compile time

### 1.3 Citations as syntax

```
PRINCIPLE: Every rule traces to law.
```

Legal citations are not documentation strings or comments—they are part of the language grammar:

```cosilico
# Citation is required, compiler enforces
variable eitc_phase_in_rate {
  reference "26 USC § 32(b)(1)(A)"
  # ...
}

# Formula components can have inline citations
formula {
  let base_amount = parameter(gov.irs.eitc.max_amount)  # 26 USC § 32(b)(2)
}
```

This enables:
- Automated compliance checking ("which rules implement § 32?")
- Impact analysis ("what breaks if § 32(b) changes?")
- Audit trails ("why did this household get $3,200?")

### 1.4 AI-native grammar

```
PRINCIPLE: Optimize for AI generation and review.
```

The syntax is designed for:
- **Context-free grammar** - Enables single-pass parsing
- **Structural consistency** - Same patterns everywhere
- **Explicit over implicit** - No hidden defaults or implicit dependencies
- **Diff-friendly** - Changes are localized, reviewable

```cosilico
# Good: explicit, structural, unambiguous
variable income_tax {
  entity TaxUnit
  period Year
  dtype Money
  reference "26 USC § 1"

  formula {
    let agi = variable(adjusted_gross_income)
    let brackets = parameter(gov.irs.income.brackets)
    return brackets.marginal_rate(agi)
  }
}

# Compare to Python decorator approach: implicit dependencies
@variable
def income_tax(tax_unit, period):
    return tax_unit("agi", period).apply(brackets)  # Where does brackets come from?
```

---

## 2. Language specification

### 2.1 File structure

Files use `.rac` extension and follow this statute-organized structure:

```
us/26/32/
├── a/1/earned_income_credit.rac        # §32(a)(1)
├── a/2/A/initial_credit_amount.rac     # §32(a)(2)(A)
├── a/2/B/credit_reduction_amount.rac   # §32(a)(2)(B)
├── b/1/credit_percentage.yaml               # §32(b)(1) parameters
├── b/2/A/amounts.yaml                       # §32(b)(2)(A) parameters
├── c/2/A/earned_income.rac             # §32(c)(2)(A) definition
└── c/3/A/num_qualifying_children.rac   # §32(c)(3)(A) definition
```

**The path IS the legal citation.** Folder structure mirrors statute structure.

```cosilico
# us/26/32/a/1/earned_income_credit.rac

# File metadata
module us.26.32.a.1
version "2024.1"
jurisdiction us

# References: alias variables by their statute paths
references {
  earned_income: us/26/32/c/2/A/earned_income
  adjusted_gross_income: us/irc/subtitle_a/chapter_1/subchapter_b/part_i/§62/a/adjusted_gross_income
  filing_status: us/irc/subtitle_a/chapter_1/subchapter_a/part_i/§1/filing_status
  initial_credit_amount: us/26/32/a/2/A/initial_credit_amount
  credit_reduction_amount: us/26/32/a/2/B/credit_reduction_amount
}

# One variable per statutory clause
variable earned_income_credit {
  entity TaxUnit
  period Year
  dtype Money
  reference "26 USC § 32(a)(1)"

  formula {
    # Use aliased references from the references block
    return max(0, initial_credit_amount - credit_reduction_amount)
  }
}
```

### 2.1.1 References block

The `references` block maps local aliases to statute paths. This:

1. **Creates auditability**: Every variable use traces to a specific statute section
2. **Enables cross-references**: When statute says "as defined in section 62", the code literally points to `§62`
3. **Supports composition**: Complex calculations compose atomic pieces from different clauses

```cosilico
references {
  # Alias: statute_path/variable_name
  earned_income: us/26/32/c/2/A/earned_income
  filing_status: us/26/1/filing_status

  # Parameters can also be referenced
  credit_percentage: us/26/32/b/1/credit_percentage
}
```

### 2.2 Variable definitions

```cosilico
variable <name> {
  # Required metadata
  entity <EntityType>           # Person, TaxUnit, Household, etc.
  period <PeriodType>           # Year, Month, Day, Eternity
  dtype <DataType>              # Money, Rate, Count, Bool, Enum
  reference "<citation>"        # Legal citation (required)

  # Optional metadata
  label "<human readable>"
  description "<longer description>"
  unit "<unit>"                 # "USD", "GBP", "%", "people"

  # Formula (optional - inputs have no formula)
  formula {
    <expression>
  }

  # Conditional applicability (optional)
  defined_for {
    <boolean expression>
  }

  # Default value (optional, defaults to 0/false/null by dtype)
  default <value>
}
```

> **STRICT SYNTAX: No YAML pipe in formulas.**
>
> Use indented code directly after `formula:`, NOT `formula: |`:
> ```cosilico
> # CORRECT:
> formula:
>   return x + y
>
> # WRONG (will error):
> formula: |
>   return x + y
> ```
> The parser enforces this strictly. YAML multi-line string syntax (`|`, `>`) is not supported.

**Example:**

```cosilico
variable eitc {
  entity TaxUnit
  period Year
  dtype Money
  reference "26 USC § 32"
  label "Earned Income Tax Credit"
  description "Refundable credit for low-to-moderate income workers"
  unit "USD"

  formula {
    let phase_in = variable(eitc_phase_in)
    let phase_out = variable(eitc_phase_out)
    return max(0, phase_in - phase_out)
  }

  defined_for {
    variable(is_tax_filer) and variable(earned_income) > 0
  }

  default 0
}
```

### 2.3 Data types

| Type | Description | Literal Syntax | Example |
|------|-------------|----------------|---------|
| `Money` | Currency amount (cents precision) | `1234.56` | `eitc`, `income_tax` |
| `Rate` | Decimal rate (0.0 to 1.0 typical) | `0.15` | `marginal_rate` |
| `Percent` | Percentage (0 to 100) | `15%` | Display-friendly rate |
| `Count` | Non-negative integer | `3` | `num_dependents` |
| `Int` | Signed integer | `-5` | `age_difference` |
| `Bool` | Boolean | `true`, `false` | `is_eligible` |
| `Enum(T)` | Enumerated type | `single`, `married` | `filing_status` |
| `Date` | Calendar date | `2024-01-01` | `birth_date` |
| `String` | Text (limited use) | `"California"` | `state_name` |

**Type Coercion Rules:**
- `Int` → `Money`: Implicit (dollars)
- `Rate` → `Percent`: Explicit (`rate.as_percent`)
- `Count` → `Int`: Implicit
- All others: Explicit conversion required

### 2.4 Expressions

#### Arithmetic
```cosilico
a + b       # Addition
a - b       # Subtraction
a * b       # Multiplication
a / b       # Division (Money / Money = Rate, Money / Rate = Money)
a % b       # Modulo
-a          # Negation
abs(a)      # Absolute value
```

#### Comparison
```cosilico
a == b      # Equal
a != b      # Not equal
a < b       # Less than
a <= b      # Less than or equal
a > b       # Greater than
a >= b      # Greater than or equal
```

#### Logical
```cosilico
a and b     # Logical AND
a or b      # Logical OR
not a       # Logical NOT
```

#### Conditional
```cosilico
if condition then value_if_true else value_if_false

# Multi-way conditional
match {
  case condition1 => value1
  case condition2 => value2
  else => default_value
}
```

#### Clamping and rounding
```cosilico
min(a, b, ...)      # Minimum
max(a, b, ...)      # Maximum
clamp(x, lo, hi)    # Equivalent to max(lo, min(x, hi))
floor(x)            # Round down
ceil(x)             # Round up
round(x)            # Round to nearest
round(x, 2)         # Round to 2 decimal places
```

### 2.5 Variable references

```cosilico
# Same entity, same period
variable(earned_income)

# Same entity, different period
variable(earned_income, period - 1)        # Previous year
variable(earned_income, period.january)     # January of this year

# Different entity (aggregation)
person.sum(employment_income)               # Sum across all persons
person.max(age)                            # Maximum age
person.any(is_disabled)                    # True if any person is disabled
person.all(is_citizen)                     # True if all persons are citizens
person.count()                             # Number of persons
person.count(is_dependent)                 # Number of dependents

# Filtered aggregation
person.sum(employment_income, where: is_adult)
person.count(where: age < 17)

# Role-based access
person.first(where: role == head).age      # Age of head of household
spouse.employment_income                    # Spouse's income (if exists)
```

### 2.6 Parameter references

```cosilico
# Simple parameter
parameter(gov.irs.eitc.max_amount)

# Parameterized by filing status
parameter(gov.irs.income.brackets[filing_status])

# Bracket scale operations
let brackets = parameter(gov.irs.income.brackets)
brackets.marginal_rate(taxable_income)     # Tax via marginal rates
brackets.threshold_at(index: 2)            # Get 3rd bracket threshold
brackets.rate_at(income: 50000)            # Rate at $50k income
```

### 2.7 Let bindings

Local variable bindings for readability:

```cosilico
formula {
  let agi = variable(adjusted_gross_income)
  let exemptions = variable(num_exemptions) * parameter(gov.irs.exemption_amount)
  let taxable = max(0, agi - exemptions)
  return parameter(gov.irs.brackets).marginal_rate(taxable)
}
```

### 2.8 Entity operations

#### Aggregation (child → parent)
```cosilico
# From Person to TaxUnit
tax_unit.members.sum(employment_income)
tax_unit.members.max(age)
tax_unit.members.any(is_blind)
tax_unit.members.count()
tax_unit.members.count(where: age < 17)
```

#### Broadcast (parent → child)
```cosilico
# From TaxUnit to Person
tax_unit.filing_status    # Available on each person in the unit
household.state_name      # Available on each person in the household
```

### 2.9 Period operations

```cosilico
# Period arithmetic
period - 1                    # Previous year
period + 1                    # Next year
period.month(1)               # January of period's year

# Period conversion
variable(monthly_income).sum_over(period)    # Sum 12 months to year
variable(annual_income) / 12                  # Divide year to month

# Cross-period references
variable(income_tax, period - 1)              # Last year's tax
variable(avg_income, period - 3 to period - 1)  # 3-year lookback average
```

---

## 3. Built-in functions

### 3.1 Mathematical
```cosilico
abs(x)          # Absolute value
min(a, b, ...)  # Minimum of values
max(a, b, ...)  # Maximum of values
clamp(x, lo, hi) # Constrain to range
floor(x)        # Round down to integer
ceil(x)         # Round up to integer
round(x)        # Round to nearest integer
round(x, n)     # Round to n decimal places
sqrt(x)         # Square root (rarely needed)
```

### 3.2 Logical
```cosilico
if_else(cond, true_val, false_val)  # Ternary
coalesce(a, b, ...)                  # First non-null value
is_null(x)                           # Check for null/missing
```

### 3.3 Bracket scales
```cosilico
scale.marginal_rate(amount)          # Calculate tax via marginal rates
scale.average_rate(amount)           # Calculate average tax rate
scale.threshold_at(index)            # Get threshold at index
scale.rate_at(amount)                # Get marginal rate for amount
scale.tax_at(amount)                 # Get cumulative tax up to amount
```

### 3.4 Date functions
```cosilico
age_in_years(birth_date, as_of)     # Calculate age
days_between(date1, date2)           # Days between dates
year_of(date)                        # Extract year
month_of(date)                       # Extract month (1-12)
```

---

## 4. Control flow

### 4.1 Conditional expressions

```cosilico
# Simple if-else
if income > 50000 then high_rate else low_rate

# Match expression (exhaustive)
match filing_status {
  case single => 12950
  case married_filing_jointly => 25900
  case married_filing_separately => 12950
  case head_of_household => 19400
}

# Match with guards
match {
  case age >= 65 and is_blind => 3700
  case age >= 65 or is_blind => 1850
  else => 0
}
```

### 4.2 No loops

The DSL intentionally has **no loops**. Iteration is handled through:
- Entity aggregations (`person.sum(...)`)
- Period ranges (`sum_over(period - 5 to period)`)
- Recursion is not supported (all dependencies must be DAG)

This ensures:
- All computations terminate
- Dependency graph is statically analyzable
- Vectorization is straightforward

---

## 5. Modules and imports

### 5.1 Module declaration

```cosilico
# Each file declares its module path
module us.federal.irs.credits.eitc

# Module path corresponds to file path:
# rules/us/federal/irs/credits/eitc.rac
```

### 5.2 Imports

```cosilico
# Import specific variables
import us.federal.irs.income (adjusted_gross_income, earned_income)

# Import all from module
import us.federal.irs.income (*)

# Import with alias
import us.ca.ftb.credits.ca_eitc as state_eitc

# Import parameters
import parameters us.federal.irs (*)
```

### 5.3 Visibility

```cosilico
# Public (default) - visible to other modules
variable eitc { ... }

# Private - only visible within module
private variable eitc_internal_calc { ... }

# Internal - visible within jurisdiction package
internal variable eitc_phase_in { ... }
```

---

## 6. Testing

Tests live in **YAML files**, separate from rule definitions. This is the canonical test format for Cosilico.

> **Why YAML, not inline DSL tests?** The DSL supports a `test` block (see section 2.1) for documentation purposes, but YAML is the primary format for test suites. YAML tests are:
> - Easier for AI to generate (structured data, not grammar)
> - Editable by non-programmers (policy experts, IRS worksheets)
> - Scriptable for bulk updates
> - Colocated with rules by program (see directory structure in 7.13)

### 6.1 Why YAML for tests?

| Aspect | YAML tests | Inline DSL tests |
|--------|------------|------------------|
| **Separation** | Rules and test cases in separate files | Mixed in same file |
| **Editing** | Standard YAML syntax | Requires DSL knowledge |
| **AI generation** | Structured format, easy to parse | Requires DSL grammar |
| **IRS examples** | Can transcribe directly from worksheets | Requires translation to DSL |
| **Bulk updates** | Scriptable across files | Per-file changes |
| **Version control** | Clear diffs | Clear diffs |

### 6.2 Test file structure

```
tests/
├── us/
│   ├── federal/
│   │   ├── irs/
│   │   │   ├── credits/
│   │   │   │   ├── eitc.yaml           # EITC test cases
│   │   │   │   ├── ctc.yaml            # CTC test cases
│   │   │   │   └── eitc_properties.yaml # Property-based tests
│   │   │   └── income/
│   │   │       └── brackets.yaml
│   │   └── ssa/
│   │       └── social_security.yaml
│   └── states/
│       ├── ca/
│       │   └── ca_eitc.yaml
│       └── ny/
│           └── ny_eitc.yaml
└── integration/
    └── full_household.yaml
```

### 6.3 Basic test format

```yaml
# tests/us/federal/irs/credits/eitc.yaml

metadata:
  module: us.federal.irs.credits.eitc
  description: EITC test cases from IRS publications
  maintainer: cosilico-team

tests:
  - name: Single filer, no children, $8000 income
    reference: IRS Publication 596, Worksheet A
    period: 2024

    input:
      people:
        worker:
          age: 28
          employment_income: 8000

      tax_units:
        tax_unit:
          members: [worker]
          filing_status: single

      households:
        household:
          members: [worker]
          state_name: TX

    output:
      earned_income: 8000
      eitc_phase_in: 612        # 8000 * 0.0765
      eitc_max_amount: 632
      eitc_phase_out: 0
      eitc: 612

  - name: Married filing jointly, 2 children, $35000 income
    reference: IRS EITC Assistant example
    period: 2024

    input:
      people:
        parent1:
          age: 35
          employment_income: 25000
        parent2:
          age: 33
          employment_income: 10000
        child1:
          age: 8
        child2:
          age: 5

      tax_units:
        tax_unit:
          members: [parent1, parent2, child1, child2]
          filing_status: married_filing_jointly

      households:
        household:
          members: [parent1, parent2, child1, child2]
          state_name: CA

    output:
      earned_income: 35000
      num_qualifying_children_for_eitc: 2
      eitc: 5764
```

### 6.4 Shorthand syntax

For simple cases, use compact syntax:

```yaml
tests:
  # Minimal single-person test
  - name: Basic income tax
    period: 2024
    input:
      person:                    # Shorthand for single person
        age: 30
        employment_income: 50000
      state: CA                  # Shorthand for household.state_name
      filing_status: single      # Shorthand for tax_unit.filing_status

    output:
      income_tax: 4235

  # Even shorter for quick checks
  - name: Zero income, zero tax
    period: 2024
    input: { age: 30, employment_income: 0, state: TX }
    output: { income_tax: 0, eitc: 0 }
```

The test runner expands shorthand to full entity structure.

### 6.5 Multi-period tests

```yaml
tests:
  - name: Income averaging over 3 years
    reference: 26 USC § 1301 (farm income averaging)

    input:
      person:
        age: 45
        # Different income each year
        employment_income:
          2022: 30000
          2023: 35000
          2024: 150000  # Big harvest year
        is_farmer: true
      state: IA
      filing_status: single

    # Can specify expected outputs for multiple periods
    output:
      2024:
        farm_income_averaging_benefit: 12500
        income_tax: 28000  # Lower due to averaging
```

### 6.6 Reform tests

```yaml
tests:
  - name: CTC expansion impact
    description: Test household under proposed CTC expansion
    period: 2024

    reform:
      gov.irs.credits.ctc.amount.base:
        2024-01-01: 3600  # Expanded from $2000
      gov.irs.credits.ctc.phase_out.start.single:
        2024-01-01: 200000  # Raised threshold

    input:
      people:
        parent:
          age: 32
          employment_income: 45000
        child:
          age: 4
      tax_units:
        tax_unit:
          members: [parent, child]
          filing_status: single

    output:
      ctc: 3600  # Full expanded credit

    # Compare to baseline
    baseline_output:
      ctc: 2000  # Current law
```

### 6.7 Tolerance and error margins

```yaml
tests:
  - name: Complex calculation with rounding
    period: 2024

    # Absolute tolerance (default: 0.01 for Money, 0.0001 for Rate)
    absolute_error_margin: 1.00  # Allow $1 difference

    # OR relative tolerance
    relative_error_margin: 0.001  # 0.1% difference allowed

    input:
      person: { age: 55, employment_income: 123456.78 }
      state: NY

    output:
      income_tax: 24691  # Approximately

  - name: Exact match required
    period: 2024
    exact: true  # No tolerance

    input:
      person: { age: 30, employment_income: 0 }

    output:
      income_tax: 0
      eitc: 0
```

### 6.8 Test categories and tags

```yaml
metadata:
  module: us.federal.irs.credits.eitc
  tags: [credits, refundable, eitc]

tests:
  - name: Edge case - exactly at phase-out threshold
    tags: [edge-case, phase-out]
    period: 2024
    # ...

  - name: IRS example from Pub 596 page 23
    tags: [irs-official, regression]
    reference: IRS Publication 596 (2024), Example 3
    # ...

  - name: Boundary - maximum credit
    tags: [boundary, max-value]
    # ...
```

Run specific categories:
```bash
cosilico test --tag edge-case
cosilico test --tag irs-official
cosilico test --exclude-tag slow
```

### 6.9 Property-based tests

For invariants that should hold across all inputs:

```yaml
# tests/us/federal/irs/credits/eitc_properties.yaml

metadata:
  module: us.federal.irs.credits.eitc
  type: properties

properties:
  - name: EITC is non-negative
    description: Credit should never be negative
    for_all:
      variables: [eitc]
      constraint: eitc >= 0

  - name: EITC bounded by maximum
    for_all:
      variables: [eitc, eitc_max_amount]
      constraint: eitc <= eitc_max_amount

  - name: EITC phases out at high income
    for_all:
      where:
        earned_income: { min: 60000 }
        filing_status: single
        num_qualifying_children_for_eitc: 0
      constraint: eitc == 0

  - name: Tax is monotonic in income
    description: More income should never reduce tax liability
    monotonic:
      variable: income_tax
      with_respect_to: employment_income
      direction: increasing

  - name: Benefits cliff detection
    description: Net income should generally increase with gross income
    for_all:
      variables: [household_net_income, employment_income]
      # Flag violations rather than fail (cliffs exist in current law)
      warn_if: |
        delta(household_net_income) / delta(employment_income) < -0.5
```

Run property tests:
```bash
cosilico test --properties
cosilico test --properties --samples 10000  # More thorough
```

### 6.10 Parameterized tests

Generate tests from data:

```yaml
tests:
  - name: EITC by income level - ${income}
    template: true
    period: 2024

    parameters:
      - income: 0
        expected_eitc: 0
      - income: 5000
        expected_eitc: 382
      - income: 10000
        expected_eitc: 765
      - income: 15000
        expected_eitc: 1147
      - income: 20000
        expected_eitc: 632  # Capped at max
      - income: 25000
        expected_eitc: 250  # Phase-out
      - income: 30000
        expected_eitc: 0    # Fully phased out

    input:
      person:
        age: 30
        employment_income: ${income}
      state: TX
      filing_status: single

    output:
      eitc: ${expected_eitc}
```

### 6.11 Integration tests

Full household scenarios testing multiple programs:

```yaml
# tests/integration/full_household.yaml

metadata:
  type: integration
  description: Full household calculations across all programs

tests:
  - name: Low-income family - all benefits
    description: Single parent with 2 kids, $25k income, receives EITC, CTC, SNAP
    period: 2024

    input:
      people:
        parent:
          age: 28
          employment_income: 25000
        child1:
          age: 6
        child2:
          age: 3

      tax_units:
        tax_unit:
          members: [parent, child1, child2]
          filing_status: head_of_household

      spm_units:
        spm_unit:
          members: [parent, child1, child2]
          housing_cost: 1200  # Monthly rent

      households:
        household:
          members: [parent, child1, child2]
          state_name: TX

    output:
      # Federal taxes
      income_tax: -3200      # Negative = refundable credits exceed liability
      payroll_tax: 1912

      # Federal credits
      eitc: 6604
      ctc: 4000

      # Benefits
      snap: 4800             # Annual SNAP

      # Summary
      household_benefits: 15404
      household_tax: -1288   # Net refund
      household_net_income: 41692
```

### 6.12 Running tests

```bash
# Run all tests
cosilico test

# Run specific file
cosilico test tests/us/federal/irs/credits/eitc.yaml

# Run specific test by name
cosilico test --name "Single filer, no children"

# Run with verbose output
cosilico test -v

# Run with coverage
cosilico test --coverage

# Run only fast tests
cosilico test --exclude-tag slow

# Generate test report
cosilico test --report html --output test-report.html

# Update expected values (dangerous - review carefully!)
cosilico test --update-expected
```

### 6.13 Test output

```
$ cosilico test tests/us/federal/irs/credits/eitc.yaml

Running 24 tests from eitc.yaml...

✓ Single filer, no children, $8000 income (0.003s)
✓ Married filing jointly, 2 children, $35000 income (0.004s)
✓ Head of household, 1 child, $20000 income (0.003s)
✗ Edge case - exactly at phase-out threshold (0.003s)

  FAILED: eitc
    Expected: 1234
    Actual:   1235
    Difference: 1 (0.08%)

    Reference: IRS Publication 596, Example 7

    Input:
      employment_income: 21430
      filing_status: single
      num_qualifying_children_for_eitc: 1

...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Results: 23 passed, 1 failed, 0 skipped
Time: 0.089s
Coverage: eitc (100%), eitc_phase_in (100%), eitc_phase_out (87%)
```

### 6.14 Continuous integration

```yaml
# .github/workflows/test.yml

name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Cosilico
        run: pip install cosilico

      - name: Run tests
        run: cosilico test --coverage --report junit --output results.xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3

      - name: Property tests (nightly only)
        if: github.event_name == 'schedule'
        run: cosilico test --properties --samples 100000
```

---

## 7. Parameters and data versioning

Cosilico implements **full bi-temporal versioning** across all inputs: parameters, indices, forecasts, and microdata. This enables complete reproducibility of any historical simulation.

### 7.1 The reproducibility problem

A simulation depends on many inputs that change over time:

| Input Type | Example | Changes when? |
|------------|---------|---------------|
| Statutory parameters | EITC base rates | Congress passes law |
| Inflation-adjusted parameters | Tax brackets | IRS publishes annually |
| Economic indices | CPI-U | BLS publishes monthly |
| Forecasts | Projected CPI | CBO updates quarterly |
| Microdata | CPS ASEC | Census releases annually |
| Imputations | Childcare expense model | We retrain periodically |
| Calibration weights | Population targets | Updated with new Census data |

To reproduce a simulation from June 2024, you need ALL inputs as they existed in June 2024.

### 7.2 Bi-temporal model

Every value has two time dimensions:

- **Effective date**: When the value applies (e.g., "2025 tax year")
- **Knowledge date**: When we knew this value (e.g., "as of June 2024")

```
┌─────────────────────────────────────────────────────────────────┐
│                         Knowledge Date                          │
│              2024-02      2024-06      2024-11                  │
├─────────────┬────────────┬────────────┬────────────┬────────────┤
│ Effective   │            │            │            │            │
│ Date        │            │            │            │            │
├─────────────┼────────────┼────────────┼────────────┼────────────┤
│ 2024        │ Projected  │ Projected  │ Published  │ ← IRS      │
│             │ $11,850    │ $11,920    │ $11,600    │   released │
├─────────────┼────────────┼────────────┼────────────┼────────────┤
│ 2025        │ Projected  │ Projected  │ Projected  │            │
│             │ $12,100    │ $12,175    │ $12,250    │            │
├─────────────┼────────────┼────────────┼────────────┼────────────┤
│ 2026        │ Projected  │ Projected  │ Projected  │            │
│             │ $12,350    │ $12,400    │ $12,500    │            │
└─────────────┴────────────┴────────────┴────────────┴────────────┘
```

### 7.3 Parameter tiers

Parameters have a precedence hierarchy:

```
published > projected > statutory_calculation
```

1. **Published**: Official government source (IRS Rev Proc, SSA announcement)
2. **Projected**: Our calculation using statute formula + forecasts
3. **Statutory calculation**: On-the-fly from base year + inflation index

```yaml
# rules/us/federal/irs/income/brackets.yaml

gov.irs.income.brackets.single:
  description: Income tax bracket thresholds for single filers
  unit: USD

  # Statutory basis changes over time - uprating method is itself time-varying
  statute:
    # Pre-TCJA: CPI-U
    - effective: 1993-01-01
      expires: 2017-12-31
      reference: "26 USC § 1(f)(3) (pre-TCJA)"
      base_year: 1993
      base_values: [22100, 53500, 115000, 250000]  # 1993 values
      inflation_index: cpi_u
      rounding: -50

    # TCJA changed to Chained CPI and reset base year
    - effective: 2018-01-01
      expires: 2025-12-31  # TCJA sunsets
      reference: "26 USC § 1(j)(2), as amended by Pub.L. 115-97 § 11001"
      enacted: "Tax Cuts and Jobs Act of 2017"
      base_year: 2018
      base_values: [9525, 38700, 82500, 157500, 200000, 500000]
      inflation_index: chained_cpi  # TCJA switched from CPI-U
      rounding: -50

    # Post-TCJA sunset: reverts to pre-TCJA rules (unless extended)
    - effective: 2026-01-01
      reference: "26 USC § 1(f)(3) (post-sunset)"
      note: "TCJA provisions sunset; reverts to CPI-U unless Congress acts"
      base_year: 2026
      base_values: null  # Must be calculated from 2025 + reversion rules
      inflation_index: cpi_u  # Reverts to CPI-U
      rounding: -50
      sunset_of: "Pub.L. 115-97 § 11001"

  # Official published values (authoritative)
  published:
    2017-01-01:
      values: [9325, 37950, 91900, 191650, 416700, 418400]
      reference: "Rev. Proc. 2016-55"
      inflation_index_used: cpi_u  # Last year of CPI-U
    2018-01-01:
      values: [9525, 38700, 82500, 157500, 200000, 500000]
      reference: "Rev. Proc. 2017-58"
      inflation_index_used: chained_cpi  # First year of C-CPI-U
    2019-01-01:
      values: [9700, 39475, 84200, 160725, 204100, 510300]
      reference: "Rev. Proc. 2018-57"
      inflation_index_used: chained_cpi
    # ...
    2024-01-01:
      values: [11600, 47150, 100525, 191950, 243725, 609350]
      reference: "Rev. Proc. 2023-34"
      inflation_index_used: chained_cpi

  # Our projections (vintaged)
  projected:
    2024-06:
      method: statutory_inflation
      # Projection uses the inflation index that's statutory for that period
      values:
        2025-01-01:
          values: [11925, 48475, 103350, 197300, 250525, 626350]
          inflation_index_used: chained_cpi
          forecast_provider: cbo
          forecast_vintage: 2024-06
        # Post-sunset projections need both scenarios
        2026-01-01:
          scenarios:
            tcja_extended:
              values: [12175, 49500, 105550, 201500, 255950, 639900]
              inflation_index_used: chained_cpi
              assumption: "TCJA extended"
            tcja_sunset:
              values: [14200, 57800, 123200, 235500, 299200, 747900]
              inflation_index_used: cpi_u
              assumption: "TCJA sunsets, reverts to pre-TCJA structure"
```

### 7.4 Time-varying indexation rules

The inflation index used for indexation is itself a statutory parameter that changes over time.

> **Terminology:** US calls this "indexing" or "indexation"; UK calls it "uprating". We use "indexation" as the general term.

```yaml
# data/indexation/us_federal_tax.yaml

indexation_rules:
  description: Which inflation index applies to federal tax parameters
  reference: "26 USC § 1(f)"

  history:
    - effective: 1981-01-01
      expires: 2017-12-31
      index: cpi_u
      reference: "Economic Recovery Tax Act of 1981"
      description: "CPI-U (all urban consumers)"

    - effective: 2018-01-01
      expires: 2025-12-31
      index: chained_cpi
      reference: "Tax Cuts and Jobs Act of 2017, § 11002"
      description: "Chained CPI-U (C-CPI-U), ~0.25% lower annually"
      note: "Estimated to raise $134B over 10 years via slower bracket growth"

    - effective: 2026-01-01
      index: cpi_u  # Reverts unless Congress acts
      reference: "TCJA sunset provision"
      contingent_on: "tcja_extension"
      alternatives:
        tcja_extended:
          index: chained_cpi
        tcja_sunset:
          index: cpi_u

# Different programs use different indices
programs:
  income_tax_brackets:
    index_rule: indexation_rules

  standard_deduction:
    index_rule: indexation_rules

  eitc_parameters:
    index_rule: indexation_rules

  social_security_benefits:
    # SSA uses different index entirely
    index: cpi_w  # CPI for Urban Wage Earners
    reference: "42 USC § 415(i)"

  snap_thresholds:
    # SNAP uses poverty guidelines which have their own indexation
    index: poverty_guidelines
    reference: "7 USC § 2014(c)"
```

**UK example - different indices for different purposes:**

```yaml
# data/indexation/uk_benefits.yaml

indexation_rules:
  description: UK benefit uprating rules
  reference: "Social Security Administration Act 1992, s.150"

  # Most benefits use CPI since 2011 (was RPI before)
  default:
    - effective: 1987-04-01
      expires: 2011-04-05
      index: rpi
      reference: "Retail Prices Index"

    - effective: 2011-04-06
      index: cpi
      reference: "Consumer Prices Index"
      note: "Coalition switched from RPI to CPI, reducing uprating ~1% annually"

programs:
  # State pension has triple lock (highest of: CPI, earnings, 2.5%)
  state_pension:
    index: triple_lock
    reference: "Pensions Act 2014, s.9"
    components:
      - cpi
      - average_earnings
      - fixed: 0.025

  # Universal Credit uses CPI
  universal_credit:
    index: cpi
    reference: "Welfare Reform Act 2012"

  # Student loan thresholds use RPI (different from benefits)
  student_loan_threshold:
    index: rpi
    reference: "Education (Student Loans) Regulations"
    note: "Plan 2 threshold frozen 2021-2025 despite RPI increases"
    overrides:
      2021-04-01:
        freeze: true
        expires: 2025-03-31
```

**Why this matters:**

| Index | 2018-2024 Growth | Effect |
|-------|------------------|--------|
| CPI-U | +27.3% | Higher brackets |
| Chained CPI | +24.8% | Lower brackets = more tax |
| UK RPI | +32.1% | Higher thresholds |
| UK CPI | +26.8% | Lower thresholds |

The TCJA switch to chained CPI means brackets grow ~0.25% slower annually, resulting in real bracket creep and higher effective taxes over time. Similarly, the UK's 2011 switch from RPI to CPI for benefits reduced their real value.

**Engine calculation:**

```cosilico
variable projected_bracket {
  formula {
    let base = parameter(gov.irs.income.brackets.single, tier: statute)
    let base_year = base.base_year

    # Get the applicable indexation rule for this period
    let indexation = indexation_rule(gov.irs.income.brackets, period)

    # indexation.index is time-varying: cpi_u pre-2018, chained_cpi 2018-2025
    let inflation_factor = index(indexation.index).factor(from: base_year, to: period)

    return round(base.values * inflation_factor, indexation.rounding)
  }
}
```

**Handling sunset uncertainty:**

```bash
# Default: assume current law (TCJA sunsets in 2026)
cosilico sim reform.yaml --year 2027

# Assume TCJA extended
cosilico sim reform.yaml --year 2027 --assume tcja_extended

# Compare scenarios
cosilico compare reform.yaml --year 2027 \
  --scenario-a "current_law" \
  --scenario-b "tcja_extended"
```

### 7.5 Unknown and uncertain parameter values

Not all parameter values are known. The engine must explicitly represent gaps and uncertainty rather than silently interpolating or extrapolating.

**The problem:**

```yaml
# Current behavior: 2024 value persists until 2027
gov.some.parameter:
  values:
    2024-01-01: 1000
    2027-01-01: 1200

# What we actually know:
# - 2024: 1000 (published)
# - 2025: ? (not yet announced)
# - 2026: ? (not yet announced)
# - 2027: 1200 (from statute)
```

**Solution: explicit `unknown` markers**

```yaml
gov.irs.eitc.max_amount:
  published:
    2024-01-01:
      values: {0: 632, 1: 4213, 2: 6960, 3: 7830}
      reference: "Rev. Proc. 2023-34"

    2025-01-01: unknown  # IRS hasn't published yet

    2026-01-01: unknown

    # Known from statute (TCJA sunset provisions specify 2027+ structure)
    2027-01-01:
      values: {0: 649, 1: 4325, 2: 7150, 3: 8046}
      reference: "26 USC § 32(b) post-TCJA sunset"
```

**Detailed unknown status:**

```yaml
gov.state.ca.ctc.amount:
  published:
    2024-01-01:
      value: 1000
      reference: "CA Rev. & Tax Code § 17052.1"

    2025-01-01:
      status: unknown
      reason: "FTB has not published 2025 values"
      expected_by: 2024-12-15
      subscribe: true  # Flag for monitoring

    2026-01-01:
      status: unknown
      reason: "Program funding uncertain - depends on budget"
      contingent_on: "ca_2025_budget"
```

**Projected vs unknown:**

```yaml
gov.irs.income.brackets:
  published:
    2024-01-01:
      values: [11600, 47150, 100525, 191950, 243725, 609350]
      reference: "Rev. Proc. 2023-34"

    # We have a projection but it's not official
    2025-01-01:
      status: projected
      values: [11925, 48475, 103350, 197300, 250525, 626350]
      method: "chained_cpi indexation"
      confidence: high  # Statutory formula is clear
      forecast_vintage: 2024-06

    # Unknown - too far out, depends on inflation
    2028-01-01:
      status: unknown
      reason: "No reliable forecast available"

    # Unknown - depends on legislation
    2026-01-01:
      status: unknown
      reason: "TCJA sunset creates uncertainty"
      scenarios:
        tcja_extended: { status: projected, values: [...] }
        tcja_sunset: { status: projected, values: [...] }
```

**Engine behavior:**

```python
# Default: error on unknown
calculate(person, period="2025")
# → Error: Parameter gov.irs.eitc.max_amount unknown for 2025-01-01
#   Reason: IRS hasn't published yet
#   Expected by: 2024-12-15

# Allow unknown (returns null)
calculate(person, period="2025", unknown_params="null")
# → {"eitc": null, "warnings": ["eitc depends on unknown parameter"]}

# Use projections if available
calculate(person, period="2025", unknown_params="projected")
# → {"eitc": 3584, "confidence": "projected", "method": "chained_cpi indexation"}

# Extrapolate using statutory formula (last resort)
calculate(person, period="2025", unknown_params="extrapolate")
# → {"eitc": 3590, "confidence": "extrapolated", "warning": "using statutory formula"}
```

**API query for parameter status:**

```bash
# What parameters are unknown for 2025?
GET /api/v1/parameters/status?period=2025-01-01&status=unknown

{
  "unknown": [
    {
      "parameter": "gov.irs.eitc.max_amount",
      "reason": "IRS hasn't published yet",
      "expected_by": "2024-12-15",
      "has_projection": true
    },
    {
      "parameter": "gov.state.ca.ctc.amount",
      "reason": "FTB has not published 2025 values",
      "expected_by": "2024-12-15",
      "has_projection": false
    }
  ],
  "projected": [
    {
      "parameter": "gov.irs.income.brackets",
      "method": "chained_cpi indexation",
      "confidence": "high"
    }
  ]
}
```

**Validation:**

```bash
# Check what periods are fully calculable
cosilico validate coverage --jurisdiction us.federal

2024: ✓ all parameters known
2025: ⚠ 3 parameters unknown, 12 projected
2026: ⚠ 8 parameters unknown (TCJA uncertainty)
2027: ✗ 15 parameters unknown

# List unknown parameters
cosilico validate unknown --period 2025

gov.irs.eitc.max_amount
  Status: unknown
  Reason: IRS hasn't published yet
  Expected: 2024-12-15
  Projection available: yes (chained_cpi, confidence: high)
```

### 7.6 Economic indices and forecasts

Indices separate actuals from forecasts, with forecast vintages tracked:

```yaml
# data/indices/cpi_u.yaml

cpi_u:
  description: Consumer Price Index for All Urban Consumers
  source: BLS
  series_id: CUUR0000SA0
  unit: index
  base: "1982-84=100"

  actuals:
    # Monthly values from BLS
    2023-01-01: 299.170
    2023-02-01: 300.840
    # ...
    2024-10-01: 315.664
    last_updated: 2024-11-13
    update_schedule: "~15th of each month"

  forecasts:
    cbo:
      # Each vintage is a complete forecast as of that date
      2024-02:
        published: 2024-02-07
        reference: "CBO Budget and Economic Outlook, Feb 2024"
        annual_percent_change:
          2024: 2.8
          2025: 2.4
          2026: 2.2
          2027: 2.1
          2028: 2.0

      2024-06:
        published: 2024-06-18
        reference: "CBO Budget and Economic Outlook Update, June 2024"
        annual_percent_change:
          2024: 2.9
          2025: 2.3
          2026: 2.1
          2027: 2.0
          2028: 2.0

      2024-11:
        published: 2024-11-05
        reference: "CBO Monthly Budget Review, Nov 2024"
        annual_percent_change:
          2024: 2.9
          2025: 2.5
          2026: 2.3
          2027: 2.1
          2028: 2.0

    fed:
      2024-09:
        published: 2024-09-18
        reference: "FOMC Summary of Economic Projections"
        annual_percent_change:
          2024: 2.3
          2025: 2.1
          2026: 2.0

    # Custom scenarios for analysis
    custom:
      high_inflation:
        description: "Persistent inflation scenario"
        annual_percent_change:
          2024: 3.5
          2025: 4.0
          2026: 3.5
```

### 7.7 Microdata versioning

Microdata vintages capture the complete state of survey data:

```yaml
# data/microdata/cps/vintages/2024-06/manifest.yaml

vintage: 2024-06
created: 2024-06-10T14:30:00Z
description: "CPS ASEC 2024 with Q2 imputations and weight calibration"

# Source data
sources:
  cps_asec:
    description: Current Population Survey Annual Social and Economic Supplement
    survey_year: 2024
    reference_year: 2023  # Income reference year
    source: census.gov
    downloaded: 2024-04-15
    original_file: asec2024_pubuse.dat
    checksum: sha256:abc123def456...

  soi_puf:
    description: IRS Statistics of Income Public Use File
    tax_year: 2021
    source: irs.gov
    checksum: sha256:789xyz...

# Processing pipeline
processing:
  # Step 1: Imputation
  imputation:
    model_version: "2024-05"
    models:
      childcare_expense:
        method: gradient_boosting
        training_data: sipp_2023
        features: [age_youngest_child, employment_income, state, marital_status]
        r2_score: 0.73

      health_insurance_premium:
        method: quantile_regression
        training_data: meps_2022
        features: [age, family_size, state, employer_coverage]
        r2_score: 0.68

      rent_expense:
        method: random_forest
        training_data: acs_2023
        features: [state, county_fips, family_size, income]
        r2_score: 0.81

  # Step 2: Tax simulation (to get calculated variables for calibration)
  tax_simulation:
    engine_version: "1.2.3"
    rules_commit: "a1b2c3d"
    variables_calculated:
      - income_tax
      - payroll_tax
      - eitc
      - snap

  # Step 3: Weight calibration
  calibration:
    method: microcalibrate
    algorithm: l0_regularized

    targets:
      # Administrative totals
      - source: irs_soi
        vintage: 2022
        variables:
          agi_total: 14_200_000_000_000
          eitc_recipients: 31_000_000
          eitc_total: 57_000_000_000

      # Census population controls
      - source: census_population_estimates
        vintage: 2024
        variables:
          total_population: 335_000_000
          population_by_state: {...}

      # ACS economic targets
      - source: acs_1year
        vintage: 2023
        variables:
          median_household_income: 80_610
          poverty_rate: 0.114

    results:
      weight_adjustment_range: [0.31, 2.87]
      converged: true
      iterations: 23

# Output dataset stats
output:
  file: enhanced.parquet
  checksum: sha256:final789...
  records:
    households: 75_432
    tax_units: 82_156
    persons: 182_651

  variables:
    original: 412
    imputed: 8
    calculated: 156
    total: 576

# Reproducibility
reproducibility:
  git_repo: cosilico/us-data
  commit: "e4f5g6h"
  docker_image: "cosilico/data-pipeline:2024-06"
  random_seed: 42
```

### 7.8 Simulation manifests

Every simulation produces a manifest for complete reproducibility:

```yaml
# simulations/2024_q2_eitc_expansion/manifest.yaml

simulation:
  id: "sim_2024_q2_eitc_expansion"
  name: "EITC Expansion Analysis Q2 2024"
  created: 2024-06-15T14:30:00Z
  created_by: "analyst@cosilico.ai"

# Temporal coordinates
temporal:
  effective_date: 2025-01-01      # Policy year being modeled
  knowledge_date: 2024-06-15      # All inputs as of this date

# Pinned versions
versions:
  engine:
    version: "1.2.3"
    commit: "a1b2c3d"

  rules:
    repo: cosilico/us-rules
    commit: "b2c3d4e"
    branch: main

  parameters:
    projection_vintage: 2024-06
    forecast_provider: cbo
    forecast_vintage: 2024-06

  microdata:
    dataset: cps_enhanced
    vintage: 2024-06
    manifest_checksum: sha256:abc123...

# What was run
reform:
  name: "EITC Phase-in Rate Increase"
  file: reforms/eitc_expansion.yaml
  parameters_modified:
    gov.irs.eitc.phase_in_rate:
      baseline: {0: 0.0765, 1: 0.34, 2: 0.40, 3: 0.45}
      reform: {0: 0.15, 1: 0.40, 2: 0.45, 3: 0.50}

# Results summary
results:
  baseline:
    total_eitc: 57_200_000_000
    eitc_recipients: 31_450_000
    avg_eitc: 1_818

  reform:
    total_eitc: 72_800_000_000
    eitc_recipients: 34_200_000
    avg_eitc: 2_129

  impact:
    cost: 15_600_000_000
    new_recipients: 2_750_000
    avg_benefit_increase: 311

# Output files
outputs:
  summary: results/summary.json
  distributional: results/distributional.parquet
  household_impacts: results/household_impacts.parquet
  audit_log: results/audit.jsonl
```

### 7.9 DSL access to versioned data

```cosilico
# Default: latest knowledge date, uses precedence rules
let brackets = parameter(gov.irs.income.brackets.single)

# Force specific tier
let brackets_official = parameter(
  gov.irs.income.brackets.single,
  tier: published  # Only use IRS-published values
)

# Historical knowledge date
let brackets_june = parameter(
  gov.irs.income.brackets.single,
  as_of: 2024-06-15  # What we knew in June
)

# Specific projection vintage
let brackets_projected = parameter(
  gov.irs.income.brackets.single,
  tier: projected,
  vintage: 2024-06
)

# Index with forecast selection
let cpi = index(cpi_u, forecast_provider: cbo)
let cpi_high = index(cpi_u, forecast_provider: custom.high_inflation)
```

### 7.10 CLI commands

```bash
# Run with current knowledge (default)
cosilico sim reform.yaml --year 2025

# Pin to historical knowledge date
cosilico sim reform.yaml --year 2025 --knowledge-date 2024-06-15

# Specify forecast provider
cosilico sim reform.yaml --year 2025 --forecast-provider cbo --forecast-vintage 2024-06

# Pin microdata vintage
cosilico sim reform.yaml --year 2025 --microdata-vintage 2024-03

# Full reproducibility from manifest
cosilico sim --manifest simulations/2024_q2_eitc_expansion/manifest.yaml

# Compare across vintages
cosilico diff reform.yaml \
  --knowledge-date 2024-02-15 \
  --vs-knowledge-date 2024-11-15

# Compare microdata vintages
cosilico diff reform.yaml \
  --microdata-vintage 2024-03 \
  --vs-microdata-vintage 2024-06

# Show what changed between vintages
cosilico vintage-diff \
  --parameter gov.irs.income.brackets.single \
  --from 2024-02 \
  --to 2024-11

# List available vintages
cosilico vintages --microdata
cosilico vintages --forecasts cbo
cosilico vintages --parameters gov.irs.income.brackets
```

### 7.11 Audit trail

Every calculation includes full provenance:

```json
{
  "calculation": {
    "variable": "income_tax",
    "value": 8521.00,
    "effective_date": "2025-01-01",
    "knowledge_date": "2024-06-15"
  },

  "parameters_used": {
    "gov.irs.income.brackets.single": {
      "value": [11925, 48475, 103350, 197300, 250525, 626350],
      "tier": "projected",
      "projection_vintage": "2024-06",
      "method": "statutory_inflation",
      "inputs": {
        "base_values": [9525, 38700, 82500, 157500, 200000, 500000],
        "base_year": 2018,
        "index": "cpi_u",
        "forecast_provider": "cbo",
        "forecast_vintage": "2024-06"
      }
    },
    "gov.irs.income.rates": {
      "value": [0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37],
      "tier": "published",
      "reference": "26 USC § 1(j)(2)(A)"
    }
  },

  "microdata": {
    "dataset": "cps_enhanced",
    "vintage": "2024-06",
    "record_id": "h_12345",
    "weight": 1523.4
  }
}
```

### 7.12 Document archival

Government sources disappear. Websites restructure, PDFs get removed, links rot. Every citation must be backed by an archived copy.

> **Vision:** Inspired by [PolicyEngine/atlas](https://github.com/PolicyEngine/atlas) proposal - document archival and knowledge graphs should be first-class API features, not afterthoughts.

#### Tiered archival strategy

Not all sources are equal. We prioritize based on computational law needs:

**Tier 1: Statutes (comprehensive)**
```
Goal: Archive ALL federal and state statutory law
- US Code (all 54 titles)
- State codes (50 states + DC + territories)
- This is the foundation - finite, tractable, essential

Sources:
- Federal: GovInfo XML, Cornell LII
- States: Individual legislature sites (quality varies)

Why comprehensive: Statutes cross-reference extensively. EITC references
AGI, which references dozens of IRC sections. Selective archival creates
broken cross-references. Archive everything.
```

**Tier 2: Program Documents (as encoded)**
```
Goal: Archive documents for programs we implement
- IRS Publications (596, 17, etc.) - how to apply tax law
- State tax forms and instructions
- Agency manuals (SNAP handbook, SSA POMS)
- Benefits eligibility guides

These are MORE useful than regulations for implementation - they tell you
how to actually calculate, step by step.

Growth: Expands as we add program coverage
```

**Tier 3: Regulations (selective)**
```
Goal: Archive CFR/state regs we actually cite
- 26 CFR (IRS regs) - sections we reference
- 7 CFR 273 (SNAP regs) - when encoding SNAP
- State administrative codes as needed

Lower priority because:
- Often just restates statute in more words
- Program documents are more actionable
- Much larger corpus with less marginal value

Exception: Some programs are primarily regulatory (not statutory)
```

**Open Source Opportunity:**

No good open source alternative to Cornell LII exists for statutes + state codes + API access. We're building this infrastructure for our rules engine anyway. By open-sourcing the archive:

- Public good (legal information should be free)
- Others build on it (legal tech, policy orgs, researchers)
- Network effects (contributions improve coverage)
- Our business is the calculation engine, not the archive

```
cosilico/lawarchive     # Separate repo, fully open
├── federal/
│   ├── usc/           # All 54 titles
│   └── cfr/           # Selective, as needed
├── states/
│   ├── ca/
│   ├── tx/
│   └── ...
└── tools/
    ├── scraper/       # Fetch from official sources
    ├── parser/        # Convert to machine-readable
    └── api/           # Serve via REST
```

**The problem:**

```yaml
# This link will break eventually
reference: "https://www.irs.gov/pub/irs-pdf/p596.pdf"

# This CBO report URL changed when they redesigned their site
reference: "https://www.cbo.gov/publication/57061"

# State agency sites are especially unstable
reference: "https://www.dss.ca.gov/cdssweb/entres/forms/English/pub100.pdf"
```

**Solution: Archive all source documents**

```
archives/
├── index.yaml                    # Master index of all archived documents
├── us/
│   ├── federal/
│   │   ├── usc/                 # US Code sections
│   │   │   ├── 26-32.md         # IRC § 32 (EITC)
│   │   │   └── 26-32.meta.yaml  # Metadata
│   │   ├── irs/
│   │   │   ├── pub-596-2024.pdf       # IRS Publication 596
│   │   │   ├── pub-596-2024.meta.yaml
│   │   │   ├── rev-proc-2023-34.pdf   # Revenue Procedure
│   │   │   └── rev-proc-2023-34.meta.yaml
│   │   └── cbo/
│   │       ├── budget-outlook-2024-02.pdf
│   │       └── budget-outlook-2024-02.meta.yaml
│   └── states/
│       └── ca/
│           ├── ftb/
│           │   ├── form-3514-2024.pdf
│           │   └── form-3514-2024.meta.yaml
│           └── dss/
│               └── pub-100.pdf
└── uk/
    ├── legislation/
    │   ├── welfare-reform-act-2012.md
    │   └── welfare-reform-act-2012.meta.yaml
    └── hmrc/
        └── rates-thresholds-2024-25.pdf
```

**Document metadata:**

```yaml
# archives/us/federal/irs/pub-596-2024.meta.yaml

document:
  id: irs-pub-596-2024
  title: "Publication 596: Earned Income Credit (EIC)"
  type: publication

source:
  agency: IRS
  jurisdiction: us.federal

  # Original URL (may be dead)
  original_url: "https://www.irs.gov/pub/irs-pdf/p596.pdf"

  # Permanent archives
  archives:
    - type: wayback
      url: "https://web.archive.org/web/20240115/https://www.irs.gov/pub/irs-pdf/p596.pdf"
      archived_date: 2024-01-15
    - type: local
      path: "archives/us/federal/irs/pub-596-2024.pdf"
      checksum: sha256:abc123...
    - type: perma_cc
      url: "https://perma.cc/ABC1-23XY"
      archived_date: 2024-01-20

dates:
  published: 2024-01-10
  effective: 2024-01-01
  expires: 2024-12-31
  archived: 2024-01-15

supersedes: irs-pub-596-2023
superseded_by: null  # Updated when 2025 version released

content:
  format: pdf
  pages: 52
  language: en

  # Extracted text for searchability
  text_extracted: true
  text_path: "archives/us/federal/irs/pub-596-2024.txt"

  # Key sections referenced by rules
  sections:
    - id: worksheet-a
      title: "EIC Worksheet A"
      pages: [23, 24]
      referenced_by:
        - us.federal.irs.credits.eitc
    - id: table-1
      title: "Earned Income Credit Table"
      pages: [30-48]

# What rules cite this document
cited_by:
  - rule: us.federal.irs.credits.eitc
    sections: [worksheet-a, table-1]
  - parameter: gov.irs.eitc.max_amount
    sections: [worksheet-a]
```

**Reference format in rules:**

```yaml
# parameters.yaml
gov.irs.eitc.max_amount:
  reference:
    citation: "26 USC § 32(b)(2)"
    archive: usc-26-32            # Points to archived document

  published:
    2024-01-01:
      values: {0: 632, 1: 4213, 2: 6960, 3: 7830}
      reference:
        citation: "Rev. Proc. 2023-34, Section 3.07"
        archive: rev-proc-2023-34  # Points to archived PDF
        page: 7
```

```cosilico
# In DSL - reference includes archive pointer
variable eitc {
  reference {
    citation: "26 USC § 32"
    archive: usc-26-32
  }
  # ...
}
```

**Archive CLI:**

```bash
# Archive a new document
cosilico archive add https://www.irs.gov/pub/irs-pdf/p596.pdf \
  --id irs-pub-596-2024 \
  --title "Publication 596: Earned Income Credit" \
  --agency irs \
  --effective 2024-01-01

# Archive to Wayback Machine and Perma.cc
cosilico archive snapshot https://www.irs.gov/pub/irs-pdf/p596.pdf

# Check for broken links
cosilico archive check

# Find documents that need updating (new year published)
cosilico archive outdated

# Verify all references have valid archives
cosilico archive verify

# Search archived documents
cosilico archive search "phase-in rate"
```

**Automated archival pipeline:**

```yaml
# .github/workflows/archive.yml

name: Archive Documents
on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6am UTC
  workflow_dispatch:

jobs:
  archive:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check for broken links
        run: cosilico archive check --output broken-links.json

      - name: Archive broken links via Wayback
        run: |
          for url in $(jq -r '.broken[].original_url' broken-links.json); do
            cosilico archive snapshot "$url" --wayback
          done

      - name: Check for new IRS publications
        run: cosilico archive fetch-new --source irs

      - name: Check for new CBO reports
        run: cosilico archive fetch-new --source cbo

      - name: Commit new archives
        run: |
          git add archives/
          git commit -m "Archive: $(date +%Y-%m-%d) document updates" || true
          git push
```

**Versioned statute tracking:**

For statutes that change over time, archive each version:

```yaml
# archives/us/federal/usc/26-32.meta.yaml

document:
  id: usc-26-32
  title: "26 USC § 32 - Earned income"
  type: statute

versions:
  - effective: 2018-01-01
    archive: usc-26-32-tcja.md
    amended_by: "Pub.L. 115-97 (TCJA)"
    checksum: sha256:abc123...

  - effective: 2021-03-11
    archive: usc-26-32-arpa.md
    amended_by: "Pub.L. 117-2 (ARPA) - temporary 2021 expansion"
    checksum: sha256:def456...

  - effective: 2022-01-01
    archive: usc-26-32-current.md
    amended_by: "Reversion to pre-ARPA"
    checksum: sha256:ghi789...

# Track pending legislation that would amend this section
pending_amendments:
  - bill: "H.R. 1234"
    title: "Working Families Tax Relief Act"
    status: "Passed House, pending Senate"
    would_amend: [subsection_b, subsection_c]
```

**API integration - archives as first-class feature:**

```bash
# REST API endpoints for document access

# Get document by ID
GET /api/v1/archives/irs-pub-596-2024
# Returns: metadata + download URL

# Get document for a specific statute
GET /api/v1/archives/statute/26-usc-32
# Returns: current version + version history

# Get all documents cited by a rule
GET /api/v1/rules/us.federal.irs.credits.eitc/sources
# Returns: list of archived documents with sections

# Get all rules that cite a document
GET /api/v1/archives/irs-pub-596-2024/citations
# Returns: rules and parameters referencing this doc

# Search across all archived documents
GET /api/v1/archives/search?q=phase-in+rate&jurisdiction=us.federal
# Returns: matching documents with snippets

# Get document as of a specific date (for statute versioning)
GET /api/v1/archives/statute/26-usc-32?as_of=2021-06-01
# Returns: ARPA-amended version

# Knowledge graph: what affects EITC?
GET /api/v1/graph/us.federal.irs.credits.eitc
# Returns: statutes, regulations, parameters, indices, related programs
```

**Calculation responses include source links:**

```json
{
  "variable": "eitc",
  "value": 3584,
  "sources": [
    {
      "type": "statute",
      "citation": "26 USC § 32",
      "archive_id": "usc-26-32",
      "url": "/api/v1/archives/usc-26-32",
      "relevant_sections": ["(a)(1)", "(b)(2)"]
    },
    {
      "type": "parameter",
      "path": "gov.irs.eitc.max_amount",
      "citation": "Rev. Proc. 2023-34",
      "archive_id": "rev-proc-2023-34",
      "url": "/api/v1/archives/rev-proc-2023-34",
      "page": 7
    }
  ],
  "trace_url": "/api/v1/calculations/{id}/trace"
}
```

**Knowledge graph for program interconnections:**

```yaml
# Graph shows how programs connect

GET /api/v1/graph/snap

{
  "program": "snap",
  "jurisdiction": "us.federal",

  "statutes": [
    {"id": "7-usc-2011", "title": "Food and Nutrition Act of 2008"}
  ],

  "regulations": [
    {"id": "7-cfr-273", "title": "SNAP Eligibility and Benefits"}
  ],

  "parameters_from": [
    {"id": "poverty_guidelines", "source": "HHS"},
    {"id": "thrifty_food_plan", "source": "USDA"}
  ],

  "affects": [
    {"program": "medicaid", "relationship": "categorical_eligibility"},
    {"program": "school_meals", "relationship": "direct_certification"}
  ],

  "affected_by": [
    {"program": "tanf", "relationship": "income_exclusion"},
    {"program": "ssi", "relationship": "income_exclusion"}
  ],

  "state_variations": {
    "count": 50,
    "examples": ["ca_calfresh_restaurant_meals", "ny_hep"]
  }
}
```

### 7.13 Directory structure

```
cosilico/
├── rules/
│   └── us/federal/irs/
│       └── credits/
│           └── eitc/
│               ├── eitc.rac       # Rules
│               ├── parameters.yaml      # Parameters with tiers
│               └── tests.yaml           # Tests
│
├── data/
│   ├── indices/
│   │   ├── cpi_u.yaml                  # Actuals + forecast vintages
│   │   ├── chained_cpi.yaml
│   │   └── wage_index.yaml
│   │
│   ├── forecasts/
│   │   ├── cbo/
│   │   │   └── vintages/
│   │   │       ├── 2024-02.yaml
│   │   │       ├── 2024-06.yaml
│   │   │       └── 2024-11.yaml
│   │   └── custom/
│   │       └── high_inflation.yaml
│   │
│   └── microdata/
│       └── cps/
│           └── vintages/
│               ├── 2024-03/
│               │   ├── manifest.yaml
│               │   └── enhanced.parquet
│               ├── 2024-06/
│               │   ├── manifest.yaml
│               │   └── enhanced.parquet
│               └── latest -> 2024-06/
│
├── archives/                            # Archived source documents
│   ├── index.yaml                       # Master index
│   ├── us/
│   │   ├── federal/
│   │   │   ├── usc/                    # US Code sections
│   │   │   ├── irs/                    # IRS publications, forms
│   │   │   └── cbo/                    # CBO reports
│   │   └── states/
│   │       └── ca/                     # California sources
│   └── uk/
│       ├── legislation/                # UK statutes
│       └── hmrc/                       # HMRC guidance
│
└── simulations/
    └── 2024_q2_eitc_expansion/
        ├── manifest.yaml               # Full reproducibility record
        ├── reform.yaml
        └── results/
            ├── summary.json
            └── distributional.parquet
```

---

## 8. Error handling

### 8.1 Compile-time errors

The compiler catches:
- **Type errors**: `Money + Bool` is invalid
- **Period mismatches**: Monthly variable used where annual expected
- **Entity mismatches**: Person variable used in TaxUnit formula without aggregation
- **Missing citations**: Variables without `reference` field
- **Undefined references**: `variable(nonexistent)`
- **Circular dependencies**: A depends on B depends on A

```
error[E0001]: Type mismatch in formula
  --> rules/us/federal/irs/income_tax.rac:15:12
   |
15 |     return agi + is_blind
   |            ^^^^^^^^^^^^^ cannot add Money and Bool
   |
   = note: expected Money, found Bool
   = hint: did you mean to use a conditional? `if is_blind then ... else ...`
```

### 8.2 Validation warnings

```
warning[W0001]: Missing unit specification
  --> rules/us/federal/irs/credits/eitc.rac:8:3
   |
 8 |   dtype Money
   |   ^^^^^^^^^^ Money type should specify unit (USD, GBP, etc.)
   |
   = hint: add `unit "USD"` for clarity

warning[W0002]: Test case may be outdated
  --> rules/us/federal/irs/credits/eitc.rac:45:1
   |
45 | test "EITC example" {
   | ^^^^^^^^^^^^^^^^^^^ test uses 2023 parameters but current year is 2024
```

---

## 9. Tooling requirements

### 9.1 Language server protocol (LSP)

Full LSP implementation providing:
- **Completion**: Variables, parameters, keywords
- **Hover**: Type info, documentation, citations
- **Go to definition**: Jump to variable/parameter definition
- **Find references**: Where is this variable used?
- **Diagnostics**: Real-time error checking
- **Formatting**: Consistent code style
- **Rename**: Safe refactoring

### 9.2 Syntax highlighting

Tree-sitter grammar for:
- VS Code extension
- Neovim integration
- GitHub rendering
- Web-based editors

### 9.3 CLI tools

```bash
# Compile and validate
cosilico check rules/

# Run tests
cosilico test rules/

# Generate code for target
cosilico compile --target python rules/ -o dist/
cosilico compile --target javascript rules/ -o dist/
cosilico compile --target sql rules/ -o dist/

# Calculate specific variable
cosilico calc eitc --input situation.yaml

# Show dependency graph
cosilico deps income_tax --format dot | dot -Tpng > deps.png

# Find all rules citing a statute
cosilico refs "26 USC § 32"

# Diff two versions
cosilico diff v2023.1 v2024.1 --variables eitc
```

### 9.4 Web playground

Interactive browser-based environment:
- Edit DSL code
- See compiled output (Python, JS)
- Run calculations
- Visualize dependency graph
- Share via URL

---

## 10. Migration path

### 10.1 From Python (PolicyEngine/OpenFisca)

Automated migration tool:

```bash
# Convert Python variable to DSL
cosilico migrate python policyengine_us/variables/irs/credits/eitc.py

# Output:
# rules/us/federal/irs/credits/eitc.rac
```

The migrator handles:
- Decorator extraction → DSL structure
- Type inference from numpy operations
- Citation extraction from docstrings
- Test case generation from existing tests

### 10.2 Gradual adoption

Support mixed codebases during transition:

```python
# Python code can import compiled DSL
from cosilico.compiled.us import eitc_formula

# DSL can reference "foreign" Python variables (with restrictions)
foreign us.legacy.complex_calculation {
  path: "policyengine_us.variables.legacy.complex"
  # Marked as untrusted, won't compile to WASM/SQL
}
```

---

## 11. Example: complete EITC implementation

```cosilico
# rules/us/federal/irs/credits/eitc.rac

module us.federal.irs.credits.eitc
version "2024.1"
jurisdiction us

import us.federal.irs.income (earned_income, adjusted_gross_income)
import us.federal.irs.filing (filing_status, is_joint)
import us.federal.irs.dependents (num_qualifying_children_for_eitc)

# Main EITC variable
variable eitc {
  entity TaxUnit
  period Year
  dtype Money
  unit "USD"
  reference "26 USC § 32"
  label "Earned Income Tax Credit"
  description "Refundable credit for low-to-moderate income working individuals and families"

  formula {
    let phase_in = variable(eitc_phase_in)
    let phase_out = variable(eitc_phase_out)
    let max_credit = variable(eitc_max_amount)

    return max(0, min(phase_in, max_credit) - phase_out)
  }

  defined_for {
    variable(earned_income) > 0 and
    variable(adjusted_gross_income) < parameter(gov.irs.eitc.agi_limit[filing_status])
  }

  default 0
}

# Phase-in calculation
variable eitc_phase_in {
  entity TaxUnit
  period Year
  dtype Money
  unit "USD"
  reference "26 USC § 32(a)(1)"

  formula {
    let earned = variable(earned_income)
    let rate = parameter(gov.irs.eitc.phase_in_rate[num_children_category])
    return earned * rate
  }
}

# Phase-out calculation
variable eitc_phase_out {
  entity TaxUnit
  period Year
  dtype Money
  unit "USD"
  reference "26 USC § 32(a)(2)"

  formula {
    let income = max(variable(earned_income), variable(adjusted_gross_income))
    let threshold = parameter(gov.irs.eitc.phase_out_start[filing_status, num_children_category])
    let rate = parameter(gov.irs.eitc.phase_out_rate[num_children_category])

    return max(0, (income - threshold) * rate)
  }
}

# Maximum credit by family size
variable eitc_max_amount {
  entity TaxUnit
  period Year
  dtype Money
  unit "USD"
  reference "26 USC § 32(b)(2)"

  formula {
    return parameter(gov.irs.eitc.max_amount[num_children_category])
  }
}

# Category for parameter lookup
private variable num_children_category {
  entity TaxUnit
  period Year
  dtype Enum(eitc_child_category)
  reference "26 USC § 32(b)"

  formula {
    let n = variable(num_qualifying_children_for_eitc)
    match {
      case n == 0 => eitc_child_category.none
      case n == 1 => eitc_child_category.one
      case n == 2 => eitc_child_category.two
      else => eitc_child_category.three_or_more
    }
  }
}

enum eitc_child_category {
  none
  one
  two
  three_or_more
}
```

**Associated test file** (`tests/us/federal/irs/credits/eitc.yaml`):

```yaml
metadata:
  module: us.federal.irs.credits.eitc
  description: EITC test cases from IRS publications
  tags: [credits, refundable, eitc]

tests:
  - name: Single filer, no children, $8000 income
    reference: IRS Publication 596, Worksheet A
    period: 2024
    input:
      person: { age: 28, employment_income: 8000 }
      state: TX
      filing_status: single
    output:
      earned_income: 8000
      eitc_phase_in: 612
      eitc_max_amount: 632
      eitc_phase_out: 0
      eitc: 612

  - name: Married filing jointly, 2 children, $35000 income
    reference: IRS EITC Assistant example
    period: 2024
    input:
      people:
        parent1: { age: 35, employment_income: 25000 }
        parent2: { age: 33, employment_income: 10000 }
        child1: { age: 8 }
        child2: { age: 5 }
      tax_units:
        tax_unit:
          members: [parent1, parent2, child1, child2]
          filing_status: married_filing_jointly
      households:
        household:
          members: [parent1, parent2, child1, child2]
          state_name: CA
    output:
      earned_income: 35000
      num_qualifying_children_for_eitc: 2
      eitc_max_amount: 6960
      eitc: 5764

properties:
  - name: EITC is bounded by max amount
    for_all:
      variables: [eitc, eitc_max_amount]
      constraint: eitc <= eitc_max_amount

  - name: EITC is non-negative
    for_all:
      variables: [eitc]
      constraint: eitc >= 0
```

---

## 12. Future extensions

### 12.1 Literate programming mode

For law-adjacent documentation:

```cosilico-lit
# Earned Income Tax Credit

Per [26 USC § 32](https://uscode.house.gov/view.xhtml?req=26+USC+32):

> (a) Allowance of credit
> In the case of an eligible individual, there shall be allowed as a
> credit against the tax imposed by this subtitle for the taxable year
> an amount equal to the credit percentage of so much of the taxpayer's
> earned income for the taxable year as does not exceed the earned
> income amount.

This translates to:

```cosilico
variable eitc {
  formula {
    let credit_pct = parameter(gov.irs.eitc.phase_in_rate)
    let earned = variable(earned_income)
    let cap = parameter(gov.irs.eitc.earned_income_amount)
    return credit_pct * min(earned, cap)
  }
}
```

The phase-out is defined in subsection (a)(2)...
```

### 12.2 Formal verification

Integration with proof assistants:

```cosilico
# Compiler can generate Lean/Coq theorems
@verify monotonic(income_tax, with_respect_to: taxable_income)
@verify bounded(eitc, lower: 0, upper: 10000)
@verify equivalent(eitc, eitc_alternative_formula)
```

### 12.3 Probabilistic extensions

For uncertainty quantification:

```cosilico
variable childcare_cost {
  dtype Money ~ LogNormal(mu: 8.5, sigma: 0.7)  # Distribution, not point estimate
  # ...
}
```

---

## Appendix A: Grammar (EBNF)

```ebnf
file = module_decl version_decl? jurisdiction_decl? import* definition* ;

module_decl = "module" module_path ;
version_decl = "version" string ;
jurisdiction_decl = "jurisdiction" identifier ;

import = "import" module_path "(" import_list ")" ("as" identifier)? ;
import_list = "*" | identifier ("," identifier)* ;

definition = variable_def | enum_def | test_def | property_def ;

variable_def = visibility? "variable" identifier "{" variable_body "}" ;
visibility = "private" | "internal" ;

variable_body =
  "entity" entity_type
  "period" period_type
  "dtype" data_type
  "reference" string
  ("label" string)?
  ("description" string)?
  ("unit" string)?
  ("formula" "{" expression "}")?
  ("defined_for" "{" expression "}")?
  ("default" literal)?
;

expression =
  | "let" identifier "=" expression
  | "if" expression "then" expression "else" expression
  | "match" match_body
  | binary_expr
  | unary_expr
  | call_expr
  | member_expr
  | literal
  | identifier
  | "(" expression ")"
;

(* ... additional grammar rules ... *)
```

---

## Appendix B: Comparison with alternatives

Design goals comparison (not all features implemented yet):

| Feature | Cosilico DSL (goal) | Python decorators | Catala | DMN/FEEL |
|---------|---------------------|-------------------|--------|----------|
| Sandboxing | Yes (by design) | No (full Python) | Yes | Yes |
| Compilation targets | 5 planned | Python only | 2 (OCaml, Python) | Primarily Java |
| Vectorization | Built-in | Manual NumPy | Scalar only | Scalar only |
| Legal citations | Part of grammar | Comments only | Literate style | Not supported |
| IDE support | LSP planned | Python tooling | Limited | Commercial tools |
| Formal verification | Planned | Not supported | Supported | Not supported |
| Time-varying params | Built-in | Manual implementation | Not supported | Not supported |
| Entity hierarchies | Built-in | Manual implementation | Not supported | Not supported |

Sources: [Catala](https://catala-lang.org/), [DMN spec](https://www.omg.org/spec/DMN/), OpenFisca/PolicyEngine codebases.

---

## Appendix C: Implementation roadmap

Ordered by priority, not calendar. Each phase builds on the previous.

### Phase 1: Core language
- [ ] Grammar specification (EBNF)
- [ ] Tree-sitter parser
- [ ] Type system implementation
- [ ] Python code generator
- [ ] Basic CLI (`check`, `compile`)

### Phase 2: Tooling
- [ ] LSP server
- [ ] VS Code extension
- [ ] Test runner (YAML format)
- [ ] Migration tool from Python

### Phase 3: Additional targets
- [ ] JavaScript generator
- [ ] SQL generator (subset of operations)
- [ ] WASM generator (via Rust)

### Phase 4: Advanced features
- [ ] Literate programming mode
- [ ] Formal verification integration
- [ ] Web playground
- [ ] Spark generator

---

*This specification is a living document. Updates track implementation progress and community feedback.*
