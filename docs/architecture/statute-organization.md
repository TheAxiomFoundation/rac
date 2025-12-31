# Statute-Organized Code

Cosilico's defining architectural choice: **code structure mirrors legal structure**.

## Repository Architecture

The Cosilico ecosystem consists of multiple repositories:

```
rac/          # Core engine (this repo)
├── src/cosilico/         # Parser, executor, RL training, indexing
├── statute/              # Example rules for testing/development
└── data/                 # Index data (CPI values, forecasts)

rac-us/              # US federal tax/benefit rules
├── statute/26/           # Title 26 (Internal Revenue Code)
├── statute/42/           # Title 42 (Social Security, Medicare)
├── regs/                 # Treasury regulations (26 CFR)
└── guidance/             # IRS notices, Revenue Procedures

rac-us-ca/           # California state rules
├── statute/rtc/          # Revenue and Taxation Code
└── regs/                 # FTB regulations

cosilico-uk/              # UK tax/benefit rules
├── statute/FA2024/       # Finance Act 2024
├── statute/ITA2007/      # Income Tax Act 2007
└── regs/                 # HMRC regulations
```

Each jurisdiction repo uses the same structure:
- `statute/` - Primary law (USC, Acts of Parliament, etc.)
- `regs/` - Implementing regulations
- `guidance/` - Agency guidance

## The Core Insight

Traditional tax software organizes by calculation type:
```
calculations/
├── credits/
│   ├── eitc.py
│   └── ctc.py
├── deductions/
│   └── standard_deduction.py
└── income/
    └── agi.py
```

Cosilico organizes by statutory citation:
```
statute/26/32/                                   # §32 - EITC
├── a/1/earned_income_credit.rac           # §32(a)(1)
├── a/2/A/initial_credit_amount.rac        # §32(a)(2)(A)
├── a/2/B/credit_reduction_amount.rac      # §32(a)(2)(B)
├── b/1/credit_percentage.yaml                  # §32(b)(1) parameters
├── b/2/A/amounts.yaml                          # §32(b)(2)(A) indexed amounts
├── c/2/A/earned_income.rac                # §32(c)(2)(A) definition
├── i/1/disqualified_income_limit.yaml          # §32(i)(1) parameter
├── j/1/indexing_rule.yaml                      # §32(j)(1) indexing
└── j/2/rounding_rules.yaml                     # §32(j)(2) rounding
```

**The path IS the legal citation.** `statute/26/32/a/1/` maps to "26 USC §32(a)(1)".

Section numbers are unique within a title, so we don't need the full subtitle/chapter/subchapter hierarchy.

## Why This Matters

### 1. Citation is Path

```python
# Variable at:
# statute/26/32/a/1/earned_income_credit

# Maps directly to:
# 26 USC §32(a)(1)
```

Legal citation and code location are one and the same.

### 2. Auditability

When a regulator asks "where does this calculation come from?", the answer is the folder name. No documentation lookup required.

### 3. Legal Diff = Code Diff

When Congress amends §32(b)(2), the git diff shows exactly what changed:
```diff
- statute/26/32/b/2/amounts.yaml
+ statute/26/32/b/2/amounts.yaml
```

### 4. AI Training Signal

The encoder learns that statute structure maps to code structure. The path becomes training metadata for free.

## One Variable Per Clause

Each statutory clause gets exactly one variable. Complex provisions become compositions of atomic pieces.

### Example: EITC (26 USC §32)

**§32(a)(1)** - "there shall be allowed as a credit..."
```
statute/26/32/a/1/earned_income_credit.rac
```

**§32(a)(2)(A)** - "credit percentage of earned income..."
```
statute/26/32/a/2/A/initial_credit_amount.rac
```

**§32(a)(2)(B)** - "the greater of AGI or earned income..."
```
statute/26/32/a/2/B/credit_reduction_amount.rac
```

**§32(b)(1)** - Credit percentages (parameter, not formula)
```
statute/26/32/b/1/credit_percentage.yaml
```

**§32(c)(1)(A)(i)** - "has qualifying child"
```
statute/26/32/c/1/A/i/is_eligible_individual.rac
```

### The Final Credit Composes Everything

```cosilico
# statute/26/32/a/1/earned_income_credit.rac
#
# 26 USC §32(a)(1)
#
# "In the case of an eligible individual, there shall be allowed as a
# credit against the tax imposed by this subtitle for the taxable year
# an amount equal to the credit percentage of so much of the taxpayer's
# earned income for the taxable year as does not exceed the earned
# income amount, over [the phaseout reduction]."

module statute.26.32.a.1
version "2024.1"

references {
  # Eligibility from §32(c)(1)
  is_eligible_individual: statute/26/32/c/1/A/i/is_eligible_individual

  # Credit components from §32(a)(2)
  initial_credit_amount: statute/26/32/a/2/A/initial_credit_amount
  credit_reduction_amount: statute/26/32/a/2/B/credit_reduction_amount
}

variable earned_income_credit {
  entity TaxUnit
  period Year
  dtype Money
  unit "USD"
  reference "26 USC § 32(a)(1)"
  label "Earned Income Tax Credit"

  formula {
    if not is_eligible_individual then
      return 0

    return max(0, initial_credit_amount - credit_reduction_amount)
  }
}
```

## Handling Non-Statute Sources

Not everything comes from statute. Regulations, agency guidance, and case law also define rules.

### Regulations

```
rac-us/
├── statute/                       # Primary law
│   └── 26/32/...
│
└── regs/                          # Code of Federal Regulations
    └── 26/1.32-1/                 # Reg interpreting §32
        └── qualifying_child_tiebreaker.rac
```

The path `regs/26/1.32-1` maps to "26 CFR §1.32-1".

### Agency Guidance

```
rac-us/
└── guidance/
    └── irs/
        └── rev_proc_2023_34/
            └── indexed_amounts.yaml
```

### Hierarchy of Authority

When sources conflict, statute wins:
```
statute > regs > guidance > case_law
```

The engine resolves by source authority.

## Cross-References Between Repos

When a state references federal law, use fully-qualified paths:

```cosilico
# In rac-us-ca/statute/rtc/17041/a/ca_taxable_income.rac

module statute.rtc.17041.a
version "2024.1"

references {
  # "as defined in section 62" becomes a reference to federal §62
  federal_agi: rac-us://statute/26/62/a/adjusted_gross_income

  # California additions from state law
  ca_additions: statute/rtc/17220/additions
  ca_subtractions: statute/rtc/17250/subtractions
}

variable ca_taxable_income {
  entity TaxUnit
  period Year
  dtype Money

  formula {
    return federal_agi + ca_additions - ca_subtractions
  }
}
```

When statute says "as defined in section 62", the code literally points to that section.

## Depth Guidelines

How deep to go in the hierarchy?

- **Leaf nodes are sections** - The smallest citable unit (§32, §62, etc.)
- **Subsections become folders** when they define distinct concepts
- **Single-clause sections** have one variable
- **Multi-clause sections** (like §32) get folder trees

### Example: Simple vs Complex

**Simple section (§63(c)(2) - Standard Deduction Amount)**
```
statute/26/63/c/2/standard_deduction_amount.yaml
```
One parameter, one file.

**Complex section (§32 - EITC)**
```
statute/26/32/
├── a/1/...
├── a/2/A/...
├── a/2/B/...
├── b/1/...
├── b/2/...
├── c/1/A/i/...
├── c/1/A/ii/...
├── c/2/A/...
├── i/1/...
└── j/1/...
```
Full tree mirroring statute structure.

## Benefits Summary

| Benefit | How It Works |
|---------|--------------|
| **Traceability** | Path = citation |
| **Auditability** | Folder name answers "where does this come from?" |
| **Legal diffs** | Amendment = file change |
| **AI training** | Structure is metadata |
| **Debugging** | Trace clause-by-clause |
| **No mapping** | Filesystem IS the citation system |
| **Cross-jurisdiction** | Same structure works for US, UK, states |
