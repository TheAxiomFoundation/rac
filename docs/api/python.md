# Python API

## Installation

```bash
pip install cosilico rac-us
```

## Basic Usage

```python
from cosilico import Simulation

sim = Simulation(jurisdictions=["us"], year=2024)

household = {
    "people": {
        "adult": {"age": 30, "employment_income": 50000}
    },
    "tax_units": {
        "tax_unit": {"members": ["adult"], "filing_status": "single"}
    },
    "households": {
        "household": {"members": ["adult"], "state_name": "CA"}
    }
}

result = sim.calculate(household)
print(result.us.income_tax)
```

## Reforms

```python
from cosilico import Reform

reform = Reform({
    "us/irc/.../§32/(b)/(1)/credit_percentage": {
        "2024-01-01": {"no_children": 0.15}
    }
})

result = sim.calculate(household, reform=reform)
```

## Tracing

```python
trace = sim.trace(household, "us.eitc")
print(trace.to_dict())
```
