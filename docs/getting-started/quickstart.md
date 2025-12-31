# Quickstart

Get up and running with Cosilico in minutes.

## Installation

```bash
pip install cosilico rac-us
```

## Your First Calculation

```python
from cosilico import Simulation

# Create a simulation
sim = Simulation(jurisdictions=["us"], year=2024)

# Define a household
household = {
    "people": {
        "adult": {
            "age": 30,
            "employment_income": 50000
        }
    },
    "tax_units": {
        "tax_unit": {
            "members": ["adult"],
            "filing_status": "single"
        }
    },
    "households": {
        "household": {
            "members": ["adult"],
            "state_name": "CA"
        }
    }
}

# Calculate
result = sim.calculate(household)

print(f"Federal income tax: ${result.us.income_tax:,.2f}")
print(f"EITC: ${result.us.eitc:,.2f}")
```

## Adding State Calculations

```bash
pip install rac-us-ca
```

```python
sim = Simulation(jurisdictions=["us", "us-ca"], year=2024)
result = sim.calculate(household)

print(f"Federal tax: ${result.us.income_tax:,.2f}")
print(f"CA state tax: ${result.us_ca.income_tax:,.2f}")
```

## Next Steps

- {doc}`installation` - Detailed installation options
- {doc}`first-calculation` - Understanding the calculation model
- {doc}`../architecture/overview` - How Cosilico works
