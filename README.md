# VibeSOP

> **AI-Native Workflow Router for Developer Tools**
> 
> Route natural language to the right skill. No more "How do I...?" — just say what you want.

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Coverage](https://img.shields.io/badge/Coverage-65.8%25-green.svg)]()
[![Version](https://img.shields.io/badge/Version-4.0.0-green.svg)](https://github.com/nehcuh/vibesop-py)

## The Problem

You're using AI-powered developer tools (Claude Code, OpenCode, etc.) and you want to:

- "Debug this error" → Which debugging skill should I use?
- "Review my code" → Where's the code review skill?
- "Deploy to production" → What's the deployment workflow?

**Current state**: You memorize commands, search docs, or guess.

**With VibeSOP**: Just say what you want. VibeSOP routes your intent to the right skill.

```bash
# Instead of memorizing commands
vibe route "debug this database error"
# → Routes to: systematic-debugging

vibe route "帮我扫描安全漏洞"
# → Routes to: gstack/cso

vibe route "review my PR"
# → Routes to: gstack/review
```

## What is VibeSOP?

VibeSOP is a **routing engine** that:

1. **Understands intent** — Natural language → skill matching
2. **Manages skills** — Discovery, installation, security auditing
3. **Learns preferences** — Routes better the more you use it

**VibeSOP is NOT:**
- ❌ An AI tool itself (it works with Claude Code, OpenCode, etc.)
- ❌ A skill executor (it tells you which skill to use)
- ❌ A prompt library (skills define their own prompts)

## Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e ".[dev]"
```

### Basic Usage

```bash
# Route a query
vibe route "debug this error"
vibe route "扫描安全漏洞"

# Execute a skill directly
vibe execute systematic-debugging "database connection failed"

# List available skills
vibe skills list

# Install external skill packs
vibe install https://github.com/gstack/gstack-skills
```

### In Your Project

```python
from vibesop.core.routing import UnifiedRouter

router = UnifiedRouter()

# Route natural language to skill
result = router.route("debug this error")
print(result.primary.skill_id)  # "systematic-debugging"
print(result.primary.confidence)  # 0.95

# Get skill information
from vibesop.core.skills import SkillManager

manager = SkillManager()
skills = manager.list_skills()
info = manager.get_skill_info("systematic-debugging")
```

## How It Works

### 7-Layer Routing Pipeline

VibeSOP tries multiple matching strategies in order:

| Layer | Strategy | Speed | Use Case |
|-------|----------|-------|----------|
| 0 | AI Triage | ~100ms | Complex queries, semantic understanding |
| 1 | Explicit Override | <1ms | Direct commands like `/review` |
| 2 | Scenario Pattern | <1ms | Predefined scenarios (debug, test, review) |
| 3 | Keyword Matching | <1ms | Direct keyword hits |
| 4 | TF-IDF | ~5ms | Semantic similarity |
| 5 | Embedding | ~20ms | Deep semantic matching (optional) |
| 6 | Fuzzy Matching | ~10ms | Typo tolerance |

**Performance**: P95 latency < 50ms (with caching)

### Skill Discovery

VibeSOP discovers skills from multiple sources:

1. **Built-in skills** — Core routing and utility skills
2. **External packs** — Installable skill collections
3. **Project skills** — Project-specific `.vibe/skills/`
4. **User skills** — Personal `~/.config/skills/`

### Security

Every external skill is audited before loading:

- Prompt injection detection
- Command injection detection
- Role hijacking detection
- Privilege escalation detection

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Layer                             │
│  vibe route │ vibe execute │ vibe install │ vibe skills  │
└─────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────┐
│                UnifiedRouter                             │
│  AI Triage → Explicit → Scenario → Keyword → TF-IDF    │
│                    ↓                                    │
│  [Optimization: Prefilter → Preference Boost → Cluster] │
└─────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────┐
│              Skill Management                            │
│  Discovery → Loading → Security Audit → Metadata        │
└─────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────┐
│              Integration Layer                           │
│  Superpowers │ GStack │ OMX │ Custom Skill Packs       │
└─────────────────────────────────────────────────────────┘
```

## Documentation

- [Architecture Overview](docs/architecture/README.md)
- [Routing System](docs/architecture/routing-system.md)
- [Positioning & Philosophy](docs/POSITIONING.md)
- [Contributing Guide](CONTRIBUTING.md)

## Philosophy

### Discovery > Execution

Knowing which skill to use is more valuable than being able to execute it. VibeSOP focuses on routing, not execution.

### Matching > Guessing

7-layer matching pipeline ensures accurate routing. No more "Did you mean...?"

### Memory > Intelligence

Remembering what worked is more valuable than being smart. Preference learning improves routing over time.

### Open > Closed

Any skill following the SKILL.md specification can integrate. No vendor lock-in.

## Roadmap

- [x] v4.0.0: Core routing engine with 7-layer pipeline
- [ ] v4.1.0: AI Triage production readiness
- [ ] v4.2.0: Skill health monitoring
- [ ] v5.0.0: Plugin system for custom matchers

## License

MIT License - see [LICENSE](LICENSE) file.

## Acknowledgments

VibeSOP is inspired by the gstack project, but is an independent implementation with:
- Clean architecture (65% code reduction)
- Unified routing pipeline
- Production-ready security auditing
- Preference learning system

---

**Built with ❤️ for AI-native developer workflows**
