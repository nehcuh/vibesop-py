# VibeSOP - Python Edition

> **Modern Python implementation** of the battle-tested AI-assisted development workflow SOP.
> **v2.1.0** - Now with true semantic understanding powered by Sentence Transformers!

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Pyright](https://img.shields.io/badge/Pyright-Strict-blue.svg)](https://github.com/microsoft/pyright)
[![Version](https://img.shields.io/badge/Version-2.1.0-green.svg)](https://github.com/nehcuh/vibesop-py/releases/tag/v2.1.0)

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

## ✨ What's New in v2.1.0

### 🧠 Semantic Recognition (NEW!)

**True semantic understanding** using Sentence Transformers - not just keyword matching!

```bash
# Enable semantic matching
vibe auto "帮我检查代码安全问题" --semantic

# Understands synonyms and varied phrasing
vibe auto "scan vulnerabilities" --semantic
vibe auto "check for security issues" --semantic
vibe auto "analyze security" --semantic
# All match to: security/scan ✨

# Multilingual support
vibe auto "扫描漏洞" --semantic  # Chinese
vibe auto "scan vulnerabilities" --semantic  # English
# Both work perfectly ✨
```

**Key Improvements**:
- 🎯 **Accuracy**: 70% → 89% (+27% overall)
- 🔄 **Synonyms**: 45% → 87% (+93% improvement)
- 🌍 **Multilingual**: 30% → 82% (+173% improvement)
- ⚡ **Fast**: < 20ms per query (vs 2.3ms traditional)
- ✅ **Backward Compatible**: Opt-in, no breaking changes

**Installation**:
```bash
# Basic (traditional matching only)
pip install vibesop

# With semantic features
pip install vibesop[semantic]
```

### 🎯 Intelligent Trigger System (v2.0)

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

**Traditional Matching** (v2.0):
- **Detection Speed**: 2.3ms (4x faster than target)
- **Throughput**: 427 queries/second
- **Memory Usage**: Minimal (50MB)

**Semantic Matching** (v2.1.0):
- **Detection Speed**: 12.4ms average (< 20ms target)
- **Throughput**: 81 queries/second
- **Memory Overhead**: +200MB (with models loaded)
- **Accuracy**: 89% (vs 70% traditional)

**Key Metrics**:
| Feature | v2.0 | v2.1 Semantic | Improvement |
|---------|------|--------------|-------------|
| Overall Accuracy | 70% | 89% | +27% |
| Synonym Detection | 45% | 87% | +93% |
| Multilingual | 30% | 82% | +173% |
| Varied Phrasing | 55% | 84% | +53% |

**Optimization Features**:
- ✅ Lazy loading (no startup cost)
- ✅ Vector caching (95%+ hit rate)
- ✅ Batch processing (500+ texts/sec)
- ✅ Half precision FP16 (40% memory reduction)
- ✅ Model caching (global cache)
- ✅ Disk persistence (survives restarts)

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

# Verify type checking
uv run pyright
```

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
│   ├── semantic/             # Semantic recognition (v2.1.0) ⭐ NEW
│   │   ├── encoder.py        # Text encoder
│   │   ├── similarity.py     # Similarity calculator
│   │   ├── cache.py          # Vector cache
│   │   ├── models.py         # Data models
│   │   └── strategies.py     # Matching strategies
│   ├── skills/               # Skill management
│   ├── triggers/             # Trigger detection system
│   └── utils/                # Utilities
├── tests/                    # Test suite
│   ├── semantic/             # Semantic tests (v2.1.0) ⭐ NEW
│   │   ├── test_encoder.py   # Encoder tests
│   │   ├── test_similarity.py # Similarity tests
│   │   ├── test_cache.py     # Cache tests
│   │   ├── test_strategies.py # Strategy tests
│   │   ├── test_e2e.py       # E2E tests
│   │   └── benchmarks.py     # Performance benchmarks
│   ├── unit/                 # Unit tests
│   └── integration/          # Integration tests
├── scripts/                  # Utility scripts
│   └── sync-core.sh          # Sync core YAML from Ruby version
├── docs/                     # Documentation
│   └── semantic/            # Semantic docs (v2.1.0) ⭐ NEW
│       ├── guide.md         # User guide
│       └── api.md           # API reference
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

For complete documentation, see the [docs/](docs/) directory.

**User Guides**:
- **[CLI Reference](docs/CLI_REFERENCE.md)** — Full command reference
- **[Trigger User Guide](docs/triggers/guide.md)** — Intent detection with examples
- **[Trigger API](docs/triggers/api.md)** — API documentation
- **[Trigger Patterns](docs/triggers/patterns.md)** — All 30 predefined patterns
- **[Semantic Guide](docs/semantic/guide.md)** — Semantic recognition setup
- **[Semantic API](docs/semantic/api.md)** — Semantic matching API

**Developer Docs**:
- **[Roadmap Index](docs/ROADMAP_INDEX.md)** — Project roadmap
- **[Contributing](CONTRIBUTING.md)** — How to contribute

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
