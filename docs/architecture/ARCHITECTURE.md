# VibeSOP Architecture

> **Version**: 4.3.0
> **Last Updated**: 2026-04-24

---

## Overview

VibeSOP is a **routing engine** that connects natural language queries to the appropriate skills. It operates as a middleware layer between AI agents (like Claude Code or OpenCode) and skill ecosystems.

```
┌─────────────────────────────────────────────────────────────────┐
│                         AI Agent                                │
│              (Claude Code / OpenCode / etc.)                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │ Executes skill
┌───────────────────────────▼─────────────────────────────────────┐
│                      VibeSOP Router                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ CLI Layer   │  │ UnifiedRouter│  │ Skill Management       │  │
│  │             │  │             │  │                         │  │
│  │ vibe route  │──│ 7-Layer     │──│ Discovery → Security    │  │
│  │ vibe execute│  │ Pipeline    │  │ Audit → Metadata        │  │
│  │ vibe install│  │             │  │                         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼───────┐  ┌────────▼────────┐  ┌──────▼──────┐
│   Built-in    │  │  External Packs │  │   Custom    │
│    Skills     │  │ superpowers     │  │   Skills    │
│               │  │ gstack          │  │             │
│ core/skills/  │  │ omx             │  │ .vibe/      │
└───────────────┘  └─────────────────┘  └─────────────┘
```

---

## Core Components

### 1. CLI Layer (`src/vibesop/cli/`)

User-facing commands that interact with the routing engine.

```python
# Entry points
vibe route "debug this"           → UnifiedRouter.route()
vibe skills available             → SkillManager.list_skills()
vibe install <url>                → SkillInstaller.install()
vibe analyze session              → SessionAnalyzer.analyze()
```

**Key Files**:
- `main.py` — Main CLI entry point with core commands (route, doctor, version, etc.)
- `subcommands/__init__.py` — Subcommand registration
- `commands/skills_cmd.py` — `vibe skills` subcommands (list, available, info, install, link, etc.)
- `commands/analyze.py` — Unified `vibe analyze` command (session, security, integrations)
- `commands/quickstart.py` — Interactive setup wizard
- `commands/install.py` — Skill pack installation
- `executor.py` — Internal skill execution utility (not exposed as CLI command)

---

### 2. Agent Runtime Layer (`src/vibesop/agent/`) ✨ v4.3.0

Direct Python API for AI Agents to use VibeSOP routing with their internal LLM, without requiring external API key configuration.

```python
# Entry point for AI Agents
from vibesop.agent import AgentRouter, SimpleLLM, SimpleResponse

# Wrap Agent's internal LLM
class AgentLLM(SimpleLLM):
    def call(self, prompt, max_tokens=100, temperature=0.1):
        # Use Agent's internal LLM here
        response = agent_internal_llm(prompt)
        return SimpleResponse(content=response)

# Route with Agent's LLM
router = AgentRouter()
router.set_llm(AgentLLM())
result = router.route("帮我审查代码质量")
print(result.primary.skill_id)  # gstack/review
```

**Key Components**:
- `AgentRouter` — UnifiedRouter wrapper for Agent integration
- `SimpleLLM` — Base class for LLM wrapper
- `SimpleResponse` — Response object matching TriageService interface

**Runtime Services** (`runtime/`):
- `skill_injector.py` — Inject skill definitions into Agent context
- `decision_presenter.py` — Present routing decisions to Agent
- `plan_executor.py` — Execute multi-step plans within Agent
- `intent_interceptor.py` — Intercept and interpret complex intents

**Why Agent Runtime?**
- ✅ No external API key needed (uses Agent's internal LLM)
- ✅ Direct Python API (no subprocess overhead)
- ✅ Deep integration with Agent's session state
- ✅ Platform adaptation (Claude Code, Cursor, Continue.dev)

---

### 3. Routing Engine (`src/vibesop/core/routing/`)

The heart of VibeSOP — routes queries to skills using a 7-layer pipeline.

#### UnifiedRouter

```python
from vibesop.core.routing import UnifiedRouter

router = UnifiedRouter()
result = router.route("debug this error")

# result.primary.skill_id = "systematic-debugging"
# result.primary.confidence = 0.95
# result.routing_path = [RoutingLayer.KEYWORD]
```

**7-Layer Matching Pipeline**:

| Layer | Strategy | Speed | When Used |
|-------|----------|-------|-----------|
| 0 | Explicit Override | <1ms | Direct commands like `/review` |
| 1 | Scenario Pattern | <1ms | Predefined scenarios |
| 2 | AI Triage | ~100ms | Complex semantic queries |
| 3 | Keyword Matching | <1ms | Direct keyword hits |
| 4 | TF-IDF | ~5ms | Semantic similarity |
| 5 | Embedding | ~20ms | Deep semantic (optional) |
| 6 | Fuzzy Matching | ~10ms | Typo tolerance |

**3 Optimization Layers**:

1. **Candidate Prefilter** — Reduces search space
2. **Preference Boost** — Learns from user history
3. **Cluster Conflict Resolution** — Handles similar skills

**Key Files**:
- `unified.py` — UnifiedRouter implementation
- `explicit_layer.py` — Direct command handling
- `scenario_layer.py` — Scenario pattern matching
- `cache.py` — Result caching for performance

---

### 4. Matching Infrastructure (`src/vibesop/core/matching/`)

Reusable matching algorithms used by the routing pipeline.

```python
from vibesop.core.matching import KeywordMatcher, TFIDFMatcher

matcher = TFIDFMatcher(config)
matches = matcher.match("debug error", candidates, top_k=3)
```

**Components**:
- `KeywordMatcher` — Fast keyword matching
- `TFIDFMatcher` — Term frequency-inverse document frequency
- `EmbeddingMatcher` — Semantic embeddings (optional)
- `LevenshteinMatcher` — Fuzzy string matching
- `SimilarityCalculator` — Cosine similarity utilities

---

### 5. Skill Management (`src/vibesop/core/skills/`)

Discovers, loads, and manages skills from multiple sources.

```python
from vibesop.core.skills import SkillManager

manager = SkillManager()
skills = manager.list_skills()
info = manager.get_skill_info("systematic-debugging")
```

**Discovery Sources** (in priority order):

1. Built-in: `core/skills/`
2. Project: `.vibe/skills/`
3. User: `~/.config/skills/`
4. Installed packs: Registry

**Key Files**:
- `manager.py` — High-level skill management API
- `loader.py` — Skill discovery and loading
- `parser.py` — SKILL.md parsing
- `storage.py` — Skill metadata storage
- `external_loader.py` — External skill pack loading

---

### 6. Security (`src/vibesop/security/`)

Audits external skills before loading to prevent malicious code.

```python
from vibesop.security import SkillSecurityAuditor

auditor = SkillSecurityAuditor()
result = auditor.audit_skill(skill_path)
# result.safe = True/False
# result.threats = [...]
```

**Threat Detection**:
- Prompt injection
- Command injection
- Role hijacking
- Privilege escalation
- Data exfiltration
- Information disclosure

**Key Files**:
- `skill_auditor.py` — Main security auditor
- `scanner.py` — Threat pattern scanning
- `rules.py` — Security rules engine
- `path_safety.py` — Path traversal protection

---

### 7. Configuration (`src/vibesop/core/config/`)

Multi-source configuration with clear priority.

```python
from vibesop.core.config import ConfigManager

config = ConfigManager()
routing_config = config.get_routing_config()
```

**Priority** (highest to lowest):
1. CLI overrides
2. Environment variables
3. Project config (`.vibe/config.yaml`)
4. Global config (`~/.config/vibesop/config.yaml`)
5. Default values

---

## Data Flow

### Routing Flow

```
User Query
    │
    ▼
┌─────────────────┐
│   CLI Layer     │  → Parse command, extract query
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ UnifiedRouter   │  → 7-layer matching pipeline
│   .route()      │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│Matching│ │Skill   │
│Pipeline│ │Discovery│
└────┬───┘ └────┬───┘
     │          │
     └────┬─────┘
          ▼
┌─────────────────┐
│ RoutingResult   │  → skill_id, confidence, alternatives
└─────────────────┘
          │
          ▼
    AI Agent executes skill
```

### Skill Installation Flow

```
vibe install <url>
    │
    ▼
┌─────────────────┐
│ SkillInstaller  │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│Clone   │ │Analyze │
│Repository│ │Structure│
└────┬───┘ └────┬───┘
     │          │
     └────┬─────┘
          ▼
┌─────────────────┐
│ Security Audit  │  → Scan for threats
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Install Skills  │  → Copy to ~/.config/skills/
└─────────────────┘
         │
         ▼
    Update registry
```

---

## Module Boundaries

### What's in Core?

**Core** (`src/vibesop/core/`) contains platform-agnostic routing logic:

- ✅ Routing algorithms
- ✅ Skill management
- ✅ Security auditing
- ✅ Configuration
- ✅ Matching infrastructure

### What's NOT in Core?

- ❌ AI tool specific code → `adapters/`
- ❌ CLI interface → `cli/`
- ❌ Installation logic → `installer/`
- ❌ Skill execution → `cli/executor.py`

---

## Performance Characteristics

### Routing Performance

| Metric | Target | Actual |
|--------|--------|--------|
| P50 Latency | < 20ms | ~15ms |
| P95 Latency | < 50ms | ~45ms |
| P99 Latency | < 100ms | ~85ms |
| Throughput | > 1000 req/s | ~1500 req/s |

### Optimization Strategies

1. **Candidate Caching** — Pre-loaded on router init
2. **Result Caching** — 1-hour TTL for AI triage
3. **Lazy Loading** — Matchers initialized on demand
4. **Early Exit** — Stop at first confident match

---

## Extension Points

### Custom Matchers

```python
from vibesop.core.matching import IMatcher, MatchResult

class CustomMatcher(IMatcher):
    def match(self, query, candidates, context, top_k=3):
        # Your matching logic
        return [MatchResult(skill_id="...", confidence=0.9)]
```

### Custom Skills

Create a `SKILL.md` file:

```markdown
# My Custom Skill

## Trigger
- debug error
- fix bug
- troubleshoot

## Intent
Help debug errors in code

## Execution
```python
# Skill implementation
```
```

---

## Testing Architecture

```
tests/
├── unit/              # Unit tests
│   ├── core/routing/  # Router tests
│   ├── core/skills/   # Skill management tests
│   └── matching/      # Matcher tests
├── integration/       # Integration tests
├── e2e/              # End-to-end tests
├── benchmark/        # Performance tests
└── security/         # Security tests
```

**Coverage**: ~80%

---

## Design Decisions

### Why Separate Routing from Execution?

1. **Single Responsibility** — VibeSOP routes, AI agents execute
2. **Tool Agnostic** — Works with any AI agent
3. **Security** — No arbitrary code execution in core
4. **Testability** — Routing logic easily testable

### Why SKILL.md?

1. **Declarative** — Skills define themselves
2. **Version Controlled** — Skills in git
3. **Portable** — Works across AI tools
4. **Human Readable** — Easy to understand

### Why 7-Layer Pipeline?

1. **Accuracy** — Multiple strategies catch different patterns
2. **Performance** — Fast layers first, slow layers as fallback
3. **Flexibility** — Easy to add new matchers
4. **Observability** — Clear routing path for debugging

---

## Future Directions

### v4.1 — AI Triage Production
- Real LLM integration
- Token usage optimization
- Cost tracking

### v4.2 — Skill Health
- Health monitoring for external packs
- Version compatibility checking
- Automatic updates

### v5.0 — Plugin System
- Custom matcher plugins
- Hook system for extensions
- Community marketplace

---

## References

- [Principles](docs/PRINCIPLES.md)
- [Contributing Guide](CONTRIBUTING.md)
- [API Documentation](docs/api/)
