# Installation

## Requirements

- Python 3.10+
- pip or conda

## Basic Installation

```bash
pip install cosilico
```

## Installing Jurisdictions

Install only the jurisdictions you need:

```bash
# US Federal
pip install rac-us

# US States
pip install rac-us-ca  # California
pip install rac-us-ny  # New York

# UK
pip install cosilico-uk
```

## Development Installation

For contributing or local development:

```bash
git clone https://github.com/cosilico/rac
cd rac
pip install -e ".[dev]"
```

## Verifying Installation

```python
import cosilico
print(cosilico.__version__)

# List installed jurisdictions
from cosilico import list_jurisdictions
print(list_jurisdictions())
```
