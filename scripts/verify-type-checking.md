# Type Checking Verification Guide

This document explains how to verify type checking for VibeSOP-Py v1.0.0.

## Installation

First, install development dependencies:

```bash
# Using pip
pip install -e ".[dev]"

# Using uv (recommended)
uv pip install -e ".[dev]"
```

## Running Type Checks

### Option 1: Pyright (Recommended)

Pyright is the primary type checker configured for this project.

```bash
# Check all source code
pyright src/vibesop

# Check with verbose output
pyright src/vibesop --verbose

# Check specific module
pyright src/vibesop/core/routing

# Generate type coverage report
pyright src/vibesop --outputjson
```

### Option 2: MyPy

Mypy is also configured as an alternative type checker.

```bash
# Check all source code
mypy src/vibesop

# Check with strict mode
mypy src/vibesop --strict

# Check specific module
mypy src/vibesop/core/routing/engine.py
```

## Type Checking Configuration

The type checking rules are defined in `pyproject.toml`:

```toml
[tool.pyright]
typeCheckingMode = "strict"
pythonVersion = "3.12"

# All unknown types are errors
reportUnknownMemberType = "error"
reportUnknownVariableType = "error"
reportUnknownArgumentType = "error"
reportUnknownParameterType = "error"

# Missing type annotations are errors
reportMissingParameterType = "error"
reportMissingReturnType = "error"
reportMissingTypeArgument = "error"
```

## Common Type Issues and Fixes

### 1. Missing Type Annotations

**Issue:**
```python
def calculate_score(items):
    return len(items)
```

**Fix:**
```python
def calculate_score(items: list[str]) -> int:
    return len(items)
```

### 2. Unknown Types

**Issue:**
```python
from some_module import SomeClass  # type: ignore

def process(item: SomeClass):  # Unknown type
    pass
```

**Fix:**
```python
from some_module import SomeClass

def process(item: SomeClass) -> None:
    pass
```

### 3. Unused Imports

**Issue:**
```python
from typing import List, Dict  # Dict is unused
```

**Fix:**
```python
from typing import List
```

## Pre-commit Type Checking

To automatically run type checks before commits:

```bash
# Install pre-commit hooks
pre-commit install

# Run type checks manually
pre-commit run pyright --all-files
```

## CI/CD Integration

Type checks should run in CI/CD pipeline:

```yaml
# .github/workflows/type-check.yml
name: Type Check

on: [push, pull_request]

jobs:
  pyright:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run Pyright
        run: pyright src/vibesop
```

## Type Coverage Goals

For v1.0.0 release:
- ✅ All new code must have complete type annotations
- ✅ Zero type errors in `pyproject.toml` configured checks
- ✅ Type coverage > 95%

## Troubleshooting

### Pyright Not Found

```bash
# Install pyright
npm install -g pyright

# Or install basedpyright (Python wrapper)
pip install basedpyright
```

### Type Checking Too Slow

```bash
# Use pyright's daemon mode for faster checks
pyright src/vibesop --watch
```

### False Positives

If you believe a type error is a false positive:

1. Check if the type is correctly defined
2. Add `# type: ignore` only as last resort
3. Document why the ignore is necessary

## Verification Checklist

Before v1.0.0 release:

- [ ] Install dev dependencies
- [ ] Run `pyright src/vibesop` - zero errors
- [ ] Run `mypy src/vibesop` - zero errors (if using mypy)
- [ ] Check type coverage > 95%
- [ ] Verify all `# type: ignore` comments are documented
