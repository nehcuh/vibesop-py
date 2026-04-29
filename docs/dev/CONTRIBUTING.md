# Contributing to VibeSOP

Thank you for your interest in contributing to VibeSOP! This guide will help you get started.

## Quick Start

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/vibesop-py.git
cd vibesop-py

# Setup environment
uv sync  # or: pip install -e ".[dev]"

# Verify
uv run pytest
uv run ruff check .
```

## Development Workflow

1. **Create a branch**: `git checkout -b feature/your-feature`
2. **Make changes**: Edit code following our guidelines
3. **Run checks**: 
   ```bash
   uv run ruff check .        # Lint
   uv run ruff format .       # Format
   uv run pyright             # Type check
   make test-fast             # Test (fast, parallel, ~30s)
   uv run pytest              # Test (full suite with coverage)
   ```
4. **Commit**: Follow conventional commits (see below)
5. **Push and PR**: Create pull request with description

## Architecture Guidelines

### Core Principles

Before contributing, read [docs/PHILOSOPHY.md](../PHILOSOPHY.md). Key points:

- **Discovery > Execution**: SkillOS manages, AI agents execute
- **Matching > Guessing**: Use multi-layer matching
- **Memory > Intelligence**: Leverage preference learning
- **Open > Closed**: Support any SKILL.md skill
- **Production-First**: All code must be production-ready
- **Portable > Specific**: Keep `core/` platform-agnostic

### Module Boundaries

| Module | Purpose | Keep Out |
|--------|---------|----------|
| `core/` | Routing logic | Platform-specific code |
| `cli/` | User interface | Business logic |
| `adapters/` | Platform adapters | Routing logic |
| `installer/` | Skill installation | Core routing |
| `security/` | Security auditing | Other concerns |

### What NOT to Do

- ❌ Add skill execution logic to `core/`
- ❌ Skip tests for new features
- ❌ Break backward compatibility (minor versions)
- ❌ Ignore security implications
- ❌ Add platform-specific code to `core/`

## Testing

```bash
# Fast parallel test (~30s, recommended for development)
make test-fast

# Full test suite with coverage (~4 min, CI use)
uv run pytest

# With coverage report
uv run pytest --cov

# Specific file
uv run pytest tests/core/test_routing.py

# Performance tests
uv run pytest tests/benchmark/ -v
```

**Requirements**:
- Minimum coverage: 75% (current: ~74%)
- All tests must pass
- New features need tests

## Code Style

We use:
- **Ruff**: Linting and formatting
- **Pyright**: Type checking (strict mode)
- **Conventional Commits**: Commit messages

```bash
# Auto-fix issues
uv run ruff check --fix .
uv run ruff format .
```

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style
- `refactor`: Refactoring
- `test`: Tests
- `chore`: Maintenance

**Examples**:
```bash
feat(routing): add embedding matcher

Add semantic matching using sentence-transformers.
Improves accuracy by 15% for ambiguous queries.

Closes #123

fix(security): prevent path traversal

Add validation to prevent directory traversal.

Security: CVE-2024-XXXX
```

## Pull Request Process

1. **Update docs**: If changing behavior
2. **Run checks**: All must pass
3. **Fill template**:
   - What changed
   - Why it changed
   - How to test
4. **Wait for review**: At least one approval
5. **Address feedback**: Update PR as needed

### PR Checklist

- [ ] Tests pass
- [ ] Code follows style
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
- [ ] Security considered

## Getting Help

- **GitHub Issues**: Bugs and features
- **GitHub Discussions**: Questions
- **Docs**: [docs/architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md), [docs/PHILOSOPHY.md](../PHILOSOPHY.md)

## License

By contributing, you agree to license your work under MIT License.

---

**Thank you for making VibeSOP better!**
