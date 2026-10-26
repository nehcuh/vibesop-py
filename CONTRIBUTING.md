# Contributing to VibeSOP

Thank you for your interest in contributing to VibeSOP! This guide will help you get started.

## Quick Start

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/vibesop-py.git
cd vibesop-py

# Setup environment (dev tooling lives in the `dev` extra)
uv sync --extra dev

# Verify
make test-fast             # Fast test suite (~30s)
uv run pytest              # Full test suite (no coverage unless asked)
```

## Development Workflow

1. **Create a branch**: `git checkout -b feature/your-feature`
2. **Make changes**: Edit code following our guidelines
3. **Run checks**:
   ```bash
   uv run ruff check .        # Lint
   uv run ruff format .       # Format
   make test-fast             # Fast test suite
   ```
4. **Commit**: Follow conventional commits (`feat:`, `fix:`, `docs:`, etc.)
5. **Open PR**: Describe changes and link issues

## Guidelines

- **Tests**: Add tests for new features; keep coverage at or above the 73% gate (branch coverage enabled, same as CI)
- **Code style**: Follow PEP 8; run `ruff format` before committing
- **Type hints**: Use type annotations for public APIs
- **Documentation**: Update docs for user-facing changes

## Full Guide

See [docs/dev/CONTRIBUTING.md](docs/dev/CONTRIBUTING.md) for detailed guidelines, architecture overview, and release procedures.
