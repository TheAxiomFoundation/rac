# Cosilico

**AI that reads law and writes code.**

Cosilico is building AI agents that encode tax and benefit legislation directly from statutory text. We're not translating existing implementations or assisting human engineers - we're training AI to read legislation and produce executable, auditable code.

## How It Works

```
┌─────────────────┐                              ┌─────────────────┐
│   Statute       │                              │   Executable    │
│   26 USC § 32   │────────▶  AI Agent  ────────▶│   Code          │
│   (EITC)        │                              │   (Cosilico DSL)│
└─────────────────┘                              └─────────────────┘
                                                          │
                        ┌──────────────────┐              │
                        │  Reward Signal   │◀─────────────┘
                        │  (Oracle Stack)  │
                        │  PE, TAXSIM, IRS │
                        └──────────────────┘
```

Existing implementations like PolicyEngine and TAXSIM become **verification oracles**. They provide the reward signal that trains the AI - ground truth for whether generated code is correct.

This is reinforcement learning from implementation feedback. The AI iterates until its code matches oracle outputs across thousands of test scenarios.

## What Makes This Different

**Traditional:** Lawyers read statute → Engineers write code → QA validates

**Cosilico:** AI reads statute → AI writes code → Oracles validate → AI improves

Humans shift from implementation to oversight - reviewing edge cases, resolving oracle disagreements, and handling genuine statutory ambiguity.

## Key Concepts

### Statute-Organized Code

Code structure mirrors legal structure. The path IS the citation:

```
rac-us/
└── irc/
    └── subtitle_a/.../§32/
        ├── (a)/(1)/earned_income_credit.rac
        ├── (a)/(2)/(A)/initial_credit_amount.rac
        └── (b)/(1)/credit_percentage.yaml
```

`us/irc/.../§32/(a)/(1)/earned_income_credit` maps directly to "26 USC §32(a)(1)".

### References System

Variables declare dependencies through named references with optional vintage pinning:

```python
references:
  federal_agi: us/irc/.../§62/(a)/adjusted_gross_income
  prior_year_agi: us/irc/.../§62/(a)/adjusted_gross_income@year-1
  credit_percentage: us/irc/.../§32/(b)/(1)/credit_percentage

def earned_income_credit() -> Money:
    ...
```

### Multi-Jurisdiction

Each jurisdiction in its own repository:

- `rac-us` - US federal
- `rac-us-ca` - California
- `rac-us-ny` - New York
- `cosilico-uk` - United Kingdom

The engine coordinates cross-jurisdiction calculations (federal AGI → state returns, SALT deduction).

## The Moat

The moat isn't the encoded rules - those are open source. The moat is the **training data factory**:

1. **Oracle stack** - Unified interface to PolicyEngine, TAXSIM, IRS examples
2. **Test case generator** - Boundary, edge, adversarial scenarios
3. **Curriculum** - Progressive complexity from simple rules to full tax liability
4. **Feedback loop** - Every human correction improves the system

Each jurisdiction makes the next faster. Each edge case trains better judgment.

## Learn More

- {doc}`ai-encoding/overview` - The AI rules engine
- {doc}`architecture/statute-organization` - Code mirrors law
- {doc}`architecture/references` - Dependency system
- {doc}`architecture/jurisdictions` - Multi-repo architecture
