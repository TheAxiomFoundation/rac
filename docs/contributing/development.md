# Development Setup

## Prerequisites

- Python 3.10+
- Node.js 18+ (for JS targets)
- Git

## Clone and Install

```bash
git clone https://github.com/cosilico/rac
cd rac
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/
```

## Building Documentation

```bash
cd docs
jupyter-book build .
```

## Code Style

- Python: Black, isort, flake8
- TypeScript: Prettier, ESLint

```bash
make format
make lint
```
