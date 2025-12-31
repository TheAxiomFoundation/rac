# Jurisdiction Repositories

Each jurisdiction gets its own repository. This is granular - not just countries, but states and localities too.

## Repository Structure

```
rac/           # Core DSL, compiler, runtime, encoder
rac-us/               # US federal
rac-us-ca/            # California
rac-us-ny/            # New York
rac-us-ny-nyc/        # NYC local
cosilico-uk/               # UK (unitary, one repo)
cosilico-ca-federal/       # Canada federal
cosilico-ca-on/            # Ontario
...
```

## Why Separate Repositories?

### 1. Different Legal Domains

US tax law experts don't need UK benefits code in their working tree. Separation focuses each repo on its domain.

### 2. Independent Release Cycles

US can ship fixes without touching UK. California updates don't require New York changes.

### 3. Regulatory Compliance

Some jurisdictions may have data/code residency requirements. Separate repos enable compliance.

### 4. Contributor Segmentation

A UK policy researcher can clone just `cosilico-uk`. A California tax specialist focuses on `rac-us-ca`.

### 5. CI Efficiency

US tests don't run when UK changes. Each repo has focused, fast CI.

## Package Structure

Users install what they need:

```bash
pip install rac rac-us rac-us-ca
```

Engine discovers installed jurisdictions:

```python
from cosilico import Simulation

sim = Simulation(
    jurisdictions=["us", "us-ca"],
    year=2024
)
result = sim.calculate(household)

# Access results by jurisdiction
result.us.income_tax
result.us_ca.income_tax
```

## Cross-Jurisdiction Dependencies

The engine coordinates calculations that span jurisdictions.

### Federal → State Flow

Most state tax calculations depend on federal:

```python
# us-ca/rtc/.../§17041/(a)/variables/ca_taxable_income.rac

references:
  federal_agi: us/irc/.../§62/(a)/adjusted_gross_income
  ca_additions: us-ca/rtc/.../§17220/additions
  ca_subtractions: us-ca/rtc/.../§17250/subtractions

def ca_taxable_income() -> Money:
    return federal_agi + ca_additions - ca_subtractions
```

California imports `federal_agi` from the federal repo. The engine resolves this cross-repo reference.

### State → Federal Flow (SALT)

The State and Local Tax (SALT) deduction creates a reverse dependency:

```python
# us/irc/.../§164/(a)/variables/salt_deduction.rac

references:
  state_income_taxes: aggregate(us-*/tax_liability)  # All installed state repos
  local_property_taxes: aggregate(us-*/local/property_tax)
  salt_cap: us/irc/.../§164/(b)/(6)/salt_cap

def salt_deduction() -> Money:
    return min(state_income_taxes + local_property_taxes, salt_cap)
```

### Circular Dependencies

SALT creates a potential loop:
1. Federal AGI → State taxable income
2. State tax → Federal SALT deduction
3. Federal taxable income → Federal tax

The engine handles this through:
- **Iterative solving** - Converge to fixed point
- **Algebraic resolution** - When mathematically tractable
- **Ordering rules** - Some jurisdictions define explicit ordering

## Engine Responsibilities

### 1. Dependency Resolution

Topological sort across jurisdictions:

```
federal AGI
    ↓
state taxable income
    ↓
state tax
    ↓
federal SALT deduction
    ↓
federal taxable income
```

### 2. Version Pinning

State 2024 might couple to federal 2023 AGI (prior-year references):

```python
references:
  # California 2024 uses federal 2023 AGI for some calculations
  prior_federal_agi: us/irc/.../§62/(a)/adjusted_gross_income@year-1
```

### 3. Import System

Cross-repo imports work seamlessly:

```python
from cosilico_us.irc.subtitle_a.chapter_1.subchapter_b.part_1.§62 import adjusted_gross_income
```

### 4. Unified Simulation

User passes one household, engine coordinates all jurisdictions:

```python
household = {
    "people": [...],
    "tax_units": [...],
    "state": "CA"
}

# Engine runs:
# 1. Federal calculations
# 2. State calculations (using federal results)
# 3. Local calculations (using state results)
# 4. Resolves any circular dependencies

result = sim.calculate(household)
```

## Encoder and Jurisdictions

The AI encoder in `rac` generates rules for jurisdiction repos:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  26 USC § 32    │────▶│  rac │────▶│  rac-us/   │
│  (EITC statute) │     │  /encoder        │     │  irc/.../§32/   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │  PolicyEngine-US │
                        │  (oracle)        │
                        └──────────────────┘
```

The encoder is jurisdiction-agnostic infrastructure. It produces artifacts that get committed to specific jurisdiction repos.

## Trade-offs vs Monorepo

| Aspect | Per-Jurisdiction Repos | Monorepo |
|--------|------------------------|----------|
| **Focus** | Each repo is focused | Everything together |
| **CI** | Fast, scoped | Slow, comprehensive |
| **Releases** | Independent | Coordinated |
| **Cross-repo changes** | Multiple PRs | Single PR |
| **Discoverability** | Must know repo exists | All in one place |
| **Ownership** | Clear boundaries | Shared |

We chose per-jurisdiction repos because:
1. Legal domains are genuinely separate
2. Contributors specialize by jurisdiction
3. Release cadences differ by jurisdiction
4. Regulatory requirements may mandate separation

## Local Development

For development spanning multiple jurisdictions:

```bash
# Clone all needed repos
git clone https://github.com/cosilico/rac
git clone https://github.com/cosilico/rac-us
git clone https://github.com/cosilico/rac-us-ca

# Install in editable mode
pip install -e rac
pip install -e rac-us
pip install -e rac-us-ca

# Now cross-repo changes work locally
```

Or use a workspace tool that handles multi-repo development.
