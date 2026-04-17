# VibeSOP

> **AI-Native Workflow Router for Developer Tools**
>
> Understand what you want, route to the right skill — no memorization required.

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Coverage](https://img.shields.io/badge/Coverage-80%25-green.svg)]()
[![Version](https://img.shields.io/badge/Version-4.0.0-green.svg)](https://github.com/nehcuh/vibesop-py)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## What is VibeSOP?

**VibeSOP is a routing engine for AI-powered developer tools.** It understands what you want to do and routes your intent to the right skill or workflow.

### The Problem

AI coding tools (Claude Code, Cursor, Continue.dev, Aider) have powerful capabilities, but:

- **"What command do I use for code review?"** → You have to remember
- **"How do I debug this error?"** → You search through docs
- **"Is there a skill for refactoring?"** → You don't know what's available

**Current solution**: Memorize commands, search documentation, or guess.

### The VibeSOP Solution

```bash
# Just say what you want
vibe route "debug this database error"
# → Routes to: systematic-debugging (95% confidence)

vibe route "帮我扫描安全漏洞"
# → Routes to: gstack/cso (88% confidence)

vibe route "review my PR"
# → Routes to: gstack/review (92% confidence)
```

VibeSOP:
1. **Understands your intent** in natural language (English + Chinese)
2. **Finds the right skill** from 45+ available skills
3. **Learns your preferences** — routes better the more you use it
4. **Works with any AI tool** — Claude Code, Cursor, Continue.dev, Aider, etc.

### What VibeSOP is NOT

| ❌ NOT | ✅ Instead |
|--------|------------|
| An AI coding tool | Works alongside AI tools |
| A skill executor | Routes to skills, doesn't execute them |
| A prompt library | Manages skills defined as SKILL.md |
| Tied to one platform | Works across Claude Code, Cursor, etc. |

---

## Inspiration & References

VibeSOP draws from several excellent projects and concepts:

### Open Source Projects

| Project | What We Borrowed |
|---------|------------------|
| **[gstack](https://github.com/anthropics/gstack)** | 19 engineering skills (code review, debugging, QA, browser automation) |
| **[superpowers](https://github.com/obra/superpowers)** | 7 foundational development skills (TDD, brainstorm, refactor, architect) |
| **[oh-my-codex](https://github.com/mill173/omx)** | Interview techniques, slop detection, verification workflows |
| **[Claude Code](https://github.com/anthropics/claude-code)** | SKILL.md specification, tool calling patterns |

### Academic & Industry Concepts

- **Information Retrieval**: TF-IDF, embedding-based semantic search, fuzzy matching
- **Preference Learning**: Implicit feedback loops, collaborative filtering
- **Multi-Armed Bandits**: Exploration vs exploitation in skill selection
- **Intent Classification**: Multi-stage routing pipeline (7 layers)

### How VibeSOP Differs

```
┌─────────────────────────────────────────────────────┐
│                  User Intent                        │
│              "Help me debug this bug"                │
└────────────────────┬────────────────────────────────┘
                     │
           ┌─────────▼──────────┐
           │     VibeSOP        │ ← We're here
           │  Routing Engine    │
           │                    │
           │  • Understands     │
           │  • Matches Skills  │
           │  • Learns          │
           │  • Cross-Platform  │
           └─────────┬──────────┘
                     │
      ┌──────────────┼──────────────┐
      │              │              │
┌─────▼─────┐  ┌────▼─────┐  ┌────▼─────┐
│Claude Code│  │  Cursor  │  │ Continue │
│(executes) │  │(executes)│  │(executes)│
└─────┬─────┘  └────┬─────┘  └────┬─────┘
      │              │              │
      └──────────────┼──────────────┘
                     │
          ┌──────────▼──────────┐
          │   Skill Ecosystem   │
          │                     │
          │ builtin │ gstack │  │
          │  (12)    │  (19)   │  │
          └─────────────────────┘
```

---

## Comparison with Alternatives

| Feature | VibeSOP | Cursor | Continue.dev | Aider |
|---------|---------|--------|--------------|-------|
| **Routing** | 7-layer intelligent routing | Built-in commands | Extension-based | CLI flags |
| **Skills** | 45+ cross-platform skills | Built-in features | Community extensions | Built-in workflows |
| **Learning** | Preference learning | Fixed | No | No |
| **Cross-Platform** | ✅ Works with any AI tool | ❌ Cursor only | ❌ Continue only | ❌ Aider only |
| **Open Ecosystem** | ✅ Any SKILL.md | ❌ Closed | ⚠️ Extension API | ❌ Closed |
| **Security Audit** | ✅ Before loading skills | N/A | ⚠️ User discretion | N/A |

### Why Choose VibeSOP?

1. **Not tied to one tool** — Switch from Cursor to Claude Code? Your skills come with you
2. **Discovers skills you didn't know existed** — "What can I do?" → `vibe skills list`
3. **Gets smarter over time** — Remembers what worked for you
4. **Open & extensible** — Create your own skills with a simple markdown file

---

## Installation

### Prerequisites

- **Python 3.12+** — VibeSOP uses modern Python features
- **Git** — For cloning skill repositories
- **Optional: API Key** — For AI-powered routing (Anthropic/OpenAI)

### Quick Install

```bash
# Clone the repository
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py

# Install with uv (recommended - 10-100x faster than pip)
uv sync

# Or with pip
pip install -e .
```

### Verify Installation

```bash
$ vibe --help
VibeSOP - AI-powered workflow SOP

$ vibe doctor
✅ Python version: 3.12
✅ Dependencies installed
✅ Configuration found
✅ LLM Provider: Anthropic (API key found)
```

### Optional: AI-Powered Routing

For best routing accuracy, set up an LLM provider:

```bash
# Anthropic Claude (recommended)
export ANTHROPIC_API_KEY="sk-ant-..."

# Or OpenAI
export OPENAI_API_KEY="sk-..."

# VibeSOP will automatically use AI routing
```

**Without an API key**, VibeSOP still works with keyword/TF-IDF matching (just slightly less accurate).

---

## Quick Start

### 1. Route Your First Query

```bash
$ vibe route "help me debug this error"

📥 Query: help me debug this error
✅ Matched: systematic-debugging
   Confidence: 95%
   Layer: scenario
   Source: builtin

💡 Alternatives:
   • gstack/investigate (82%)
   • superpowers/debug (75%)
```

### 2. List Available Skills

```bash
$ vibe skills available

📚 Available Skills (45 total)

builtin (12 skills)
  • systematic-debugging - Find root cause before attempting fixes
  • verification-before-completion - Require verification before claiming done
  • planning-with-files - Use persistent files for complex tasks
  ...

gstack (19 skills)
  • gstack/review - Pre-landing PR review
  • gstack/qa - Systematically QA test and fix bugs
  • gstack/browse - Fast headless browser for QA testing
  ...

superpowers (7 skills)
  • tdd - Test-driven development workflow
  • brainstorm - Structured brainstorming sessions
  • refactor - Systematic code refactoring
  ...
```

### 3. Get Skill Details

```bash
$ vibe skills info systematic-debugging

╭──────────────────────────────────────────────╮
│ Systematic Debugging                          │
├──────────────────────────────────────────────┤
│ ID: systematic-debugging                      │
│ Type: prompt                                  │
│ Namespace: builtin                            │
│                                                │
│ Description                                   │
│ Find root cause before attempting fixes.     │
│ Prevents jumping to solutions without        │
│ proper diagnosis.                             │
│                                                │
│ Intent                                        │
│ Use when:                                     │
│ - Error messages appear                       │
│ - Tests fail                                  │
│ - "Something broke"                           │
│ - Need root cause analysis                    │
╰──────────────────────────────────────────────╯
```

### 4. Install External Skills

```bash
# Install gstack skills
vibe install https://github.com/anthropics/gstack

📦 Found skill pack: gstack
   Skills discovered: 19
   Install target: ~/.config/skills/gstack/
   Continue? [Y/n]

✅ gstack installed successfully
   Run 'vibe skills available --namespace gstack' to see skills
```

---

## CLI Reference

### Core Commands

| Command | Description | Example |
|---------|-------------|---------|
| `vibe route <query>` | Route query to best skill | `vibe route "debug this error"` |
| `vibe skills available` | List all available skills | `vibe skills available -v` |
| `vibe skills info <id>` | Show skill details | `vibe skills info gstack/review` |
| `vibe install <url>` | Install skill pack | `vibe install gstack` |
| `vibe doctor` | Check environment | `vibe doctor` |

### Skills Management

```bash
# List installed skills
vibe skills list

# List all available skills (including builtin and installed packs)
vibe skills available

# Show detailed skill information
vibe skills info <skill-id>

# Install from URL or name
vibe install gstack
vibe install https://github.com/user/skills

# Link skill to platform
vibe skills link <skill-id> claude-code

# Sync project skills to platform
vibe skills sync claude-code
```

### Project Setup

```bash
# Initialize project
vibe init

# Build configuration for platform
vibe build claude-code

# Interactive quickstart
vibe quickstart
```

### Analysis Commands

```bash
# Analyze session for patterns
vibe analyze session

# Security scan
vibe analyze security .

# Detect integrations
vibe analyze integrations
```

### Preference Learning

```bash
# Show preference statistics
vibe preferences

# Record skill selection feedback
vibe record <skill-id> <query> --helpful

# Show top preferred skills
vibe top-skills
```

See [CLI_REFERENCE.md](CLI_REFERENCE.md) for complete documentation.

---

## How It Works

### 7-Layer Routing Pipeline

VibeSOP tries multiple matching strategies, fastest first:

| Layer | Strategy | Speed | Accuracy | Use Case |
|-------|----------|-------|----------|----------|
| 0 | Explicit Override | <1ms | 100% | Direct commands like `/review` |
| 1 | Scenario Pattern | <1ms | 90% | Predefined scenarios (debug, test, review) |
| 2 | AI Triage | ~100ms | 95% | Complex queries, semantic understanding |
| 3 | Keyword Matching | <1ms | 70% | Direct keyword hits |
| 4 | TF-IDF | ~5ms | 75% | Semantic similarity |
| 5 | Embedding | ~20ms | 85% | Deep semantic matching (optional) |
| 6 | Fuzzy Matching | ~10ms | 60% | Typo tolerance |

**Result**: P95 latency < 50ms with caching.

### Preference Learning

VibeSOP remembers what works:

```bash
# First time you ask about debugging
$ vibe route "debug this"
→ Matches: systematic-debugging (85%)

# You use it and it works
$ vibe record systematic-debugging "debug this" --helpful

# Next time, it ranks higher
$ vibe route "debug this"
→ Matches: systematic-debugging (92%) ← Boosted!
```

### Skill Discovery Sources

Skills are discovered from multiple locations, in priority order:

```
Priority  Source                              Path
────────  ─────────────────────────────────  ──────────────────────────────
1         Project-specific skills            .vibe/skills/
2         Shared project skills              skills/
3         Claude Code native skills          ~/.claude/skills/
4         External skill packs               ~/.config/skills/{pack}/
5         VibeSOP global skills              ~/.vibe/skills/
6         VibeSOP builtin skills             (included in code)
```

---

## Usage Examples

### Debugging Errors

```bash
$ vibe route "database connection failed after deployment"

✅ Matched: systematic-debugging
   Rationale: Error detected → Use debugging workflow

# Read the skill
cat ~/.claude/skills/systematic-debugging/SKILL.md

# Follow the systematic debugging process
1. Gather information
2. Identify patterns
3. Form hypotheses
4. Test hypotheses
5. Fix root cause
```

### Code Review

```bash
$ vibe route "review my changes before pushing"

✅ Matched: gstack/review
   Confidence: 93%

# Or use the explicit command
$ vibe route "/review"
✅ Matched: gstack/review (Layer 1: explicit override)
```

### Chinese Queries

```bash
$ vibe route "帮我重构这个函数"

✅ Matched: superpowers/refactor
   Confidence: 89%

$ vibe route "代码覆盖率太低怎么办"

✅ Matched: superpowers/tdd
   Confidence: 91%
```

### Brainstorming

```bash
$ vibe route "I need ideas for a new feature"

✅ Matched: gstack/office-hours
   Confidence: 87%
   Rationale: "ideas" + "new feature" → design thinking
```

---

## Configuration

### Project-Level Config

Create `.vibe/config.yaml` in your project:

```yaml
# .vibe/config.yaml
platform: claude-code

routing:
  min_confidence: 0.6
  enable_ai_triage: false
  enable_embedding: false
  max_candidates: 3

security:
  threat_level: medium
  scan_external: true

skills:
  namespaces:
    - builtin
    - gstack
    - superpowers
```

### Global Config

Create `~/.vibe/config.yaml`:

```yaml
# ~/.vibe/config.yaml
default_platform: claude-code
llm_provider: anthropic  # or openai

routing:
  enable_ai_triage: true
  use_cache: true

preferences:
  learning_enabled: true
```

---

## Integrations

### With Claude Code

```bash
# Build and deploy to Claude Code
vibe build claude-code --output ~/.claude

# Claude Code will now use VibeSOP for routing
```

### With Cursor

```bash
# Build for Cursor
vibe build cursor --output ~/.cursor

# Skills available in Cursor sessions
```

### With Continue.dev

```bash
# Build for Continue
vibe build opencode --output ~/.continue

# Use in Continue.dev configurations
```

---

## Security

Every external skill is **audited before loading**:

- ✅ Prompt injection detection
- ✅ Command injection detection
- ✅ Role hijacking detection
- ✅ Privilege escalation detection
- ✅ Path traversal protection

```bash
$ vibe install https://github.com/suspicious/skills

⚠️  Security audit failed:
   • Prompt injection detected in skills/evil/SKILL.md
   • Unsafe path traversal attempt

Installation blocked for your safety.
```

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    CLI Layer                    │
│  vibe route │ vibe skills │ vibe install        │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                 UnifiedRouter                   │
│  AI Triage → Explicit → Scenario → Keyword      │
│                    ↓                            │
│  [Optimization: Prefilter → Preference → Cluster]│
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              Skill Management                   │
│  Discovery → Loading → Audit → Metadata         │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│            Integration Layer                    │
│  Superpowers │ GStack │ OMX │ Custom Packs      │
└─────────────────────────────────────────────────┘
```

---

## Documentation

- [Architecture Overview](docs/architecture/README.md) - System design and components
- [Routing System](docs/architecture/routing-system.md) - 7-layer pipeline deep dive
- [Positioning & Philosophy](docs/POSITIONING.md) - Why VibeSOP exists
- [Contributing Guide](CONTRIBUTING.md) - How to contribute

---

## Philosophy

### Discovery > Execution

Knowing which skill to use is more valuable than being able to execute it. VibeSOP focuses on **routing**, not execution.

### Matching > Guessing

7-layer matching pipeline ensures accurate routing. No more "Did you mean...?"

### Memory > Intelligence

Remembering what worked is more valuable than being smart. Preference learning improves routing over time.

### Open > Closed

Any skill following the [SKILL.md](docs/SKILL_SPEC.md) specification can integrate. No vendor lock-in.

---

## Development

```bash
# Type checking
uv run basedpyright

# Linting
uv run ruff check

# Formatting
uv run ruff format

# Testing
uv run pytest

# Test coverage
uv run pytest --cov=src/vibesop --cov-report=html
```

---

## Roadmap

- [x] v4.0.0: Core routing engine with 7-layer pipeline
- [ ] v4.1.0: AI Triage production readiness
- [ ] v4.2.0: Skill health monitoring
- [ ] v5.0.0: Plugin system for custom matchers

---

## License

MIT License - see [LICENSE](LICENSE) file.

---

## Acknowledgments

VibeSOP stands on the shoulders of giants:

- **[gstack](https://github.com/anthropics/gstack)** - Engineering skills and browser automation
- **[superpowers](https://github.com/obra/superpowers)** - Foundational development workflows
- **[oh-my-codex](https://github.com/mill173/omx)** - Interview techniques and verification
- **[Claude Code](https://github.com/anthropics/claude-code)** - SKILL.md specification

VibeSOP is an independent implementation with:
- Clean architecture (65% code reduction vs Ruby version)
- Unified routing pipeline
- Production-ready security auditing
- Preference learning system

---

**Built with ❤️ for AI-native developer workflows**

[GitHub](https://github.com/nehcuh/vibesop-py) • [Issues](https://github.com/nehcuh/vibesop-py/issues) • [Discussions](https://github.com/nehcuh/vibesop-py/discussions)
