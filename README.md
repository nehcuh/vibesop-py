# VibeSOP - Python Edition

> **Modern Python implementation** of the battle-tested AI-assisted development workflow SOP.

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Pyright](https://img.shields.io/badge/Pyright-Strict-blue.svg)](https://github.com/microsoft/pyright)

## 🚀 Quick Start

```bash
# Clone and setup
git clone https://github.com/nehcuh/vibesop-py.git && cd vibesop-py

# Using uv (recommended - 10-100x faster than pip)
uv sync

# Or using pip
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Run CLI
vibe --help
```

## 🎯 Design Philosophy

- **Python 3.12+**: Leverages modern type system and performance improvements
- **Pydantic v2**: Runtime validation with compile-time type hints
- **uv**: Blazing fast package manager (written in Rust)
- **Type Safety**: Strict type checking with basedpyright
- **Modern Tooling**: Ruff for linting/formatting (100x faster than flake8/black)

## 🛠️ Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Type checking (requires pyright or mypy)
pyright src/vibesop
# or
mypy src/vibesop

# Linting
uv run ruff check

# Auto-fix issues
uv run ruff check --fix

# Formatting
uv run ruff format

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src/vibesop --cov-report=html

# Verify type checking (automated script)
./scripts/verify-type-checking.sh
```

See [scripts/verify-type-checking.md](scripts/verify-type-checking.md) for detailed type checking guide.

## 📦 Project Structure

```
vibesop-py/
├── src/vibesop/              # Package source
│   ├── cli/                  # CLI commands (Typer)
│   ├── core/                 # Core business logic
│   │   ├── models/           # Pydantic models
│   │   ├── routing/          # AI routing system
│   │   └── config/           # Configuration management
│   ├── llm/                  # LLM clients (OpenAI, Anthropic)
│   ├── skills/               # Skill management
│   └── utils/                # Utilities
├── tests/                    # Test suite
│   ├── unit/                 # Unit tests
│   └── integration/          # Integration tests
├── scripts/                  # Utility scripts
│   └── sync-core.sh          # Sync core YAML from Ruby version
├── pyproject.toml            # Project configuration
└── README.md                 # This file
```

## 🔄 Migration Status

This is a **complete rewrite** of the Ruby version in modern Python.

- [x] Project structure and tooling
- [x] Type system setup (Pydantic v2)
- [x] Core models (Skill, Route, Config)
- [x] CLI framework (Typer)
- [x] AI-powered routing (5-layer system)
- [x] LLM clients (Anthropic, OpenAI)
- [x] Skill management (filesystem discovery)
- [x] Memory system (conversation tracking)
- [x] Checkpoint system (work state persistence)
- [x] Preference learning (personalized routing)
- [x] **Security scanning** (Phase 1: 66 tests ✅)
- [x] **Platform adapters** (Phase 2: 83 tests ✅)
- [x] **Configuration builder** (Phase 3: 40 tests ✅)
- [x] **Hook system** (Phase 4: 32 tests ✅)
- [x] **Integration management** (Phase 5: 26 tests ✅)
- [x] **Installation system** (Phase 6: 16 tests ✅)

**Total: 263+ tests passing across all modules**

## 📚 Documentation

### v2.0 Roadmap 🚀
- **[Roadmap Index](docs/ROADMAP_INDEX.md)** - Complete roadmap documentation index
- **[Full Roadmap](docs/roadmap-2.0.md)** - Detailed v2.0 development plan
- **[Quick Reference](docs/roadmap-2.0-summary.md)** - Executive summary of v2.0 features
- **[Timeline](docs/roadmap-2.0-timeline.md)** - 12-week development schedule
- **[Project Board](docs/roadmap-2.0-board.md)** - Agile development progress board

### v1.0 Documentation
- **[Implementation Summary](docs/IMPLEMENTATION_SUMMARY.md)** - Complete implementation details
- **[CLI Reference](docs/CLI_REFERENCE.md)** - Full command reference
- **[Development Plan](docs/development-plan.md)** - Original development roadmap
- **[中文文档](README.zh.md)** - Chinese version of README

## 🎨 Key Features

### AI-Powered Skill Routing

```bash
$ vibe route "帮我评审代码"

📥 Input: 帮我评审代码
✅ Matched: /review (95% confidence)
   Source: gstack
   Layer: AI Triage
```

### Modern Type Safety

```python
from pydantic import BaseModel, Field, field_validator

class SkillRoute(BaseModel):
    """Skill routing result with runtime validation."""

    skill_id: str = Field(..., min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    layer: Literal[0, 1, 2, 3, 4]

    @field_validator('skill_id')
    @classmethod
    def validate_skill_id(cls, v: str) -> str:
        if not v.startswith('/'):
            raise ValueError('skill_id must start with /')
        return v
```

## 📝 Development Guidelines

### Type Safety First

```python
# ✅ Good: Full type annotations
def route_request(request: RoutingRequest) -> RoutingResult:
    """Route a request to the appropriate skill."""
    ...

# ❌ Bad: Missing types
def route_request(request):
    ...
```

### Use Pydantic for All Data Models

```python
from pydantic import BaseModel

class Config(BaseModel):
    """Configuration with runtime validation."""
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
```

### Async First

```python
import asyncio

async def call_llm(prompt: str) -> str:
    """Call LLM asynchronously."""
    # Use httpx for async HTTP
    async with httpx.AsyncClient() as client:
        response = await client.post(...)
        return response.json()
```

## 🤝 Contributing

This is the Python edition of VibeSOP. For the Ruby version, see [vibesop](https://github.com/nehcuh/vibesop).

## 📄 License

MIT - see [LICENSE](LICENSE) file.

## 🙏 Acknowledgments

Based on the battle-tested Ruby implementation at [vibesop](https://github.com/nehcuh/vibesop).
