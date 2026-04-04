# VibeSOP - Python Edition

> **Modern Python implementation** of the battle-tested AI-assisted development workflow SOP.
> **v2.0.0** - Now with intelligent trigger system and workflow orchestration!

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Pyright](https://img.shields.io/badge/Pyright-Strict-blue.svg)](https://github.com/microsoft/pyright)
[![Version](https://img.shields.io/badge/Version-2.0.0-green.svg)](https://github.com/nehcuh/vibesop-py/releases/tag/v2.0.0)

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

## ✨ What's New in v2.0

### 🎯 Intelligent Trigger System

Just describe what you want in plain language - VibeSOP automatically detects your intent and executes the right skill:

```bash
# English
vibe auto "scan for security vulnerabilities"
vibe auto "deploy configuration to production"
vibe auto "run tests"

# Chinese
vibe auto "扫描安全漏洞"
vibe auto "部署配置"
vibe auto "运行测试"

# Mixed
vibe auto "帮我 scan security issues"
```

**30 Predefined Patterns** across 5 categories:
- 🔒 **Security** (5): scan, analyze, audit, fix, report
- ⚙️ **Config** (5): deploy, validate, render, diff, backup
- 🛠️ **Dev** (8): build, test, debug, refactor, lint, format, install, clean
- 📚 **Docs** (6): generate, update, format, readme, api, changelog
- 📁 **Project** (6): init, migrate, audit, upgrade, clean, status

### 🔄 Workflow Orchestration

Define and execute multi-stage workflows with dependency management:

```bash
# List workflows
vibe workflow list

# Execute workflow
vibe workflow run .vibe/workflows/security-review.yaml

# Resume interrupted workflow
vibe workflow resume <workflow-id>
```

### ⚡ Performance

- **Detection Speed**: 2.3ms (4x faster than target)
- **Test Coverage**: 94-100% on core modules
- **Bilingual Support**: Full English + Chinese queries
- **Multi-Strategy**: Keywords (40%), Regex (30%), Semantic (30%)

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

## 🔄 v2.0 Features

### Phase 1: Workflow Orchestration Engine ✅
- [x] WorkflowPipeline with state management
- [x] 3 execution strategies (sequential, parallel, pipeline)
- [x] Dependency resolution and validation
- [x] State persistence and recovery
- [x] CLI workflow commands
- [x] 120+ tests

### Phase 2: Intelligent Trigger System ✅
- [x] 30 predefined patterns across 5 categories
- [x] Multi-strategy detection (keywords, regex, semantic)
- [x] Bilingual support (English + Chinese)
- [x] `vibe auto` command for automatic execution
- [x] 195 new tests (315 total)
- [x] 2,100+ lines documentation

**Total: 315 tests, 94-100% coverage on core modules**

## 🔄 v1.0 Foundation

All v1.0 features remain fully supported:

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

## 📚 Documentation

### v2.0 Documentation 🚀

**Quick Links**:
- **[v2.0 Release Summary](V2_RELEASE_COMPLETE.md)** - Complete v2.0 overview and migration guide
- **[Deployment Summary](DEPLOYMENT_COMPLETE.md)** - Deployment verification and installation
- **[Complete Development Summary](COMPLETE.md)** - Full development lifecycle documentation

**Trigger System**:
- **[User Guide](docs/triggers/guide.md)** - Complete usage instructions with examples
- **[API Reference](docs/triggers/api.md)** - Full API documentation for developers
- **[Pattern Reference](docs/triggers/patterns.md)** - All 30 predefined patterns documented

**Workflow System**:
- **[Workflow Guide](docs/workflows/guide.md)** - Workflow orchestration documentation (coming soon)
- **[Workflow API](docs/workflows/api.md)** - Workflow management API (coming soon)

### v1.0 Documentation

**Development**:
- **[Implementation Summary](docs/IMPLEMENTATION_SUMMARY.md)** - Complete implementation details
- **[CLI Reference](docs/CLI_REFERENCE.md)** - Full command reference
- **[中文文档](README.zh.md)** - Chinese version of README

**Roadmap**:
- **[Roadmap Index](docs/ROADMAP_INDEX.md)** - Complete roadmap documentation index
- **[Full Roadmap](docs/roadmap-2.0.md)** - Detailed v2.0 development plan
- **[Quick Reference](docs/roadmap-2.0-summary.md)** - Executive summary of v2.0 features

## 🎨 Key Features

### Intelligent Intent Detection

```bash
# Automatic intent detection (NEW in v2.0)
$ vibe auto "scan for security vulnerabilities"

🔍 Detecting intent...
✅ Matched: security/scan (87% confidence)
📊 Strategy: keywords (40%), regex (30%), semantic (30%)
🚀 Executing: /security/scan skill

# Works in Chinese too!
$ vibe auto "扫描安全漏洞"

🔍 检测意图...
✅ 匹配: security/scan (82% confidence)
🚀 执行: /security/scan skill
```

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
