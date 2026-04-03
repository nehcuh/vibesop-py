# Contributing to VibeSOP Python Edition

Thank you for your interest in contributing to VibeSOP! This document provides guidelines and instructions for contributing to the project.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12 or higher
- Git
- GitHub account

### Setup Development Environment

```bash
# Fork and clone the repository
git clone https://github.com/your-username/vibesop-py.git
cd vibesop-py

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"

# Verify installation
vibe --help
pytest tests/ -v
```

---

## 📋 Development Workflow

### 1. Branch Strategy

```bash
# Main branch - stable releases
main

# Feature branches - new features
feature/your-feature-name

# Bugfix branches - bug fixes
bugfix/your-bugfix-name

# Documentation branches - docs only
docs/your-doc-update
```

### 2. Making Changes

```bash
# Create a new branch
git checkout -b feature/your-feature-name

# Make your changes
# ... edit files ...

# Run tests
pytest tests/ -v

# Run linting
ruff check src/
ruff format src/

# Run type checking
pyright src/
```

### 3. Commit Messages

Follow conventional commits format:

```
<type>: <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat: add support for new platform

Implement support for VS Code adapter with
full configuration generation and hook installation.

Closes #123
```

```
fix: resolve path traversal vulnerability

Add proper path validation to prevent directory
traversal attacks in file operations.

Security: CVE-2024-XXXX
```

### 4. Submitting Changes

```bash
# Push your branch
git push origin feature/your-feature-name

# Create pull request on GitHub
# Fill in the PR template
# Wait for review
```

---

## 🧪 Testing

### Test Structure

```
tests/
├── security/          # Security module tests
├── adapters/          # Platform adapter tests
├── builder/           # Configuration builder tests
├── hooks/             # Hook system tests
├── integrations/      # Integration management tests
└── installer/         # Installation system tests
```

### Writing Tests

```python
"""Tests for your module."""

import pytest
from pathlib import Path
from vibesop.your_module import YourClass


class TestYourClass:
    """Test YourClass functionality."""

    def test_create_instance(self) -> None:
        """Test creating an instance."""
        obj = YourClass()
        assert obj is not None

    def test_your_method(self) -> None:
        """Test your_method."""
        obj = YourClass()
        result = obj.your_method()
        assert result == expected_value
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific module
pytest tests/security/ -v

# Run with coverage
pytest tests/ --cov=src/vibesop --cov-report=html

# Run specific test
pytest tests/security/test_scanner.py::test_scan -v
```

### Test Guidelines

1. **Test coverage**: Maintain 85%+ coverage
2. **Test naming**: Use descriptive names (`test_<what>_<condition>_<result>`)
3. **Fixtures**: Use pytest fixtures for common setup
4. **Mocking**: Mock external dependencies (API calls, file system)
5. **Assertions**: Use specific assertions with clear messages

---

## 📝 Code Style

### Formatting

We use **Ruff** for formatting and linting:

```bash
# Format code
ruff format src/

# Check linting
ruff check src/

# Auto-fix issues
ruff check --fix src/
```

### Type Hints

All code must have type hints:

```python
from typing import List, Optional

def process_items(
    items: List[str],
    count: Optional[int] = None,
) -> dict[str, int]:
    """Process items and return counts.

    Args:
        items: List of items to process
        count: Optional maximum count

    Returns:
        Dictionary with item counts
    """
    # Implementation
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two integers.

    Args:
        a: First integer
        b: Second integer

    Returns:
        Sum of a and b

    Raises:
        TypeError: If arguments are not integers

    Example:
        >>> calculate_sum(1, 2)
        3
    """
    return a + b
```

---

## 🏗️ Architecture Guidelines

### Module Structure

```python
# __init__.py - Public API
from vibesop.module.submodule import PublicClass

__all__ = [
    "PublicClass",
]

# submodule.py - Implementation
class _InternalClass:
    """Internal class - not exported."""
    pass

class PublicClass:
    """Public class - exported."""
    pass
```

### Error Handling

```python
from vibesop.security.exceptions import SecurityError

def process_input(user_input: str) -> None:
    """Process user input with proper error handling."""
    try:
        # Validate input
        if not user_input:
            raise ValueError("Input cannot be empty")

        # Process input
        result = do_something(user_input)

    except SecurityError as e:
        # Handle security errors
        logger.error(f"Security error: {e}")
        raise

    except Exception as e:
        # Handle unexpected errors
        logger.exception(f"Unexpected error: {e}")
        raise
```

### Security Considerations

1. **Always scan user input**:
   ```python
   from vibesop.security import SecurityScanner

   scanner = SecurityScanner()
   result = scanner.scan(user_input)
   if result.has_threats:
       raise UnsafeContentError("Threats detected")
   ```

2. **Use PathSafety for file operations**:
   ```python
   from vibesop.security import PathSafety

   path_safety = PathSafety()
   if not path_safety.check_traversal(user_path, base_dir):
       raise PathTraversalError("Unsafe path")
   ```

3. **Validate all external data**:
   ```python
   from pydantic import BaseModel, validator

   class ExternalData(BaseModel):
       value: str

       @validator('value')
       def validate_length(cls, v):
           if len(v) > 1000:
               raise ValueError('Value too long')
           return v
   ```

---

## 📚 Documentation

### Code Documentation

1. **Docstrings**: All public functions/classes must have docstrings
2. **Type hints**: Required for all function parameters and returns
3. **Comments**: Explain "why", not "what"
4. **Examples**: Provide usage examples in docstrings

### Documentation Files

- **README.md**: Project overview and quick start
- **CHANGELOG.md**: Version history and changes
- **docs/**: Detailed documentation
- **CONTRIBUTING.md**: This file

### Updating Documentation

```bash
# Build documentation (if using Sphinx/docs tools)
cd docs/
make html

# View documentation
open _build/html/index.html
```

---

## 🐛 Bug Reports

### Before Creating a Bug Report

1. **Search existing issues**: Check if the bug is already reported
2. **Verify it's a bug**: Make sure it's not a feature request or user error
3. **Gather information**: Collect details about the bug

### Bug Report Template

```markdown
### Description
Brief description of the bug

### Steps to Reproduce
1. Step one
2. Step two
3. Step three

### Expected Behavior
What should happen

### Actual Behavior
What actually happens

### Environment
- OS: [e.g., Ubuntu 22.04]
- Python version: [e.g., 3.12.0]
- VibeSOP version: [e.g., 1.0.0]

### Logs
Error messages, stack traces, etc.

### Additional Context
Any other relevant information
```

---

## ✨ Feature Requests

### Before Requesting a Feature

1. **Search existing issues**: Check if the feature is already requested
2. **Check if it fits**: Does it align with project goals?
3. **Consider implementation**: Is it feasible?

### Feature Request Template

```markdown
### Description
Clear description of the feature

### Problem Statement
What problem does this solve?

### Proposed Solution
How should it work?

### Alternatives Considered
What other approaches did you consider?

### Additional Context
Examples, mockups, etc.
```

---

## 🤝 Pull Request Guidelines

### Before Submitting a PR

1. **Tests**: All tests pass
2. **Linting**: Code is formatted and passes linting
3. **Type checking**: No type errors
4. **Documentation**: Updated if needed
5. **Changelog**: Added entry if applicable

### Pull Request Template

```markdown
### Description
Brief description of changes

### Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

### Testing
- [ ] Tests added/updated
- [ ] All tests pass

### Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Changelog updated
- [ ] No new warnings generated

### Related Issues
Fixes #123
Related to #456
```

### Review Process

1. **Automated checks**: CI must pass
2. **Code review**: At least one maintainer approval
3. **Testing**: Tests must pass
4. **Documentation**: Must be complete
5. **Merge**: Maintainer merges

---

## 🎯 Development Priorities

### High Priority
- Bug fixes
- Security issues
- Performance problems
- Test failures

### Medium Priority
- New features
- Documentation improvements
- Code refactoring
- Test coverage improvements

### Low Priority
- Nice-to-have features
- Minor optimizations
- Cosmetic changes

---

## 📞 Getting Help

### Communication Channels

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and discussions
- **Documentation**: Check docs/ first

### Asking Questions

1. **Search first**: Check existing issues and discussions
2. **Be specific**: Provide details about your problem
3. **Show effort**: Explain what you've already tried
4. **Use code blocks**: Format code properly

---

## 🏅 Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md file
- Release notes
- Project documentation

---

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

## 🎓 Resources

### Python Best Practices
- [PEP 8](https://peps.python.org/pep-0008/) - Style Guide
- [PEP 257](https://peps.python.org/pep-0257/) - Docstring Conventions
- [PEP 484](https://peps.python.org/pep-0484/) - Type Hints

### Tools
- [Pytest](https://docs.pytest.org/) - Testing framework
- [Ruff](https://docs.astral.sh/ruff/) - Linter and formatter
- [Pyright](https://github.com/microsoft/pyright) - Type checker

### Project-Specific
- [IMPLEMENTATION_SUMMARY.md](docs/IMPLEMENTATION_SUMMARY.md) - Technical details
- [CLI_REFERENCE.md](docs/CLI_REFERENCE.md) - Command reference
- [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) - Current status

---

## 🙏 Thank You

Thank you for contributing to VibeSOP! Your contributions help make this project better for everyone.

---

*Last Updated: 2026-04-02*
