# VibeSOP Architecture

> **Version**: 6.2.0
> **Last Updated**: 2026-06-05

## Three-Pillar Architecture (v6.2.0)

VibeSOP v6.2.0 introduces a 3-pillar architecture that defines the AI-assisted
development skill protocol standard:

```
┌─────────────────────────────────────────────────────────────────┐
│                    VibeSOP Skill Protocol                       │
├───────────────────┬───────────────────┬─────────────────────────┤
│   The Spec        │  The Reference     │  The Conformance Suite │
│                   │                    │                        │
│  SKILL.md v3.0    │  3 Integration    │  tests/conformance/    │
│  Canonical Model  │  Patterns         │  85 compliance tests   │
│  29 Fields        │  File/Hook/SDK    │  CLI: vibe spec conf.  │
├───────────────────┼───────────────────┼─────────────────────────┤
│  spec/models.py   │  adapters/        │  test_spec_compliance  │
│  spec/validator.py│   file_based.py   │  test_platform_adapters│
│  spec/version.py  │   hook_based.py   │  test_agent_runtime    │
│                   │   sdk_based.py    │                        │
└───────────────────┴───────────────────┴─────────────────────────┘
```

**Pillar 1 — The Spec**: A single, unambiguous, versioned SKILL.md format
specification. `SkillSpec` captures all 29 frontmatter fields including the
12 that were previously discarded by the parser.

**Pillar 2 — The Reference**: Three clean reference implementation patterns:
- **File-based** (`FileBasedAdapter`): AGENTS.md + docs/ + skills/ symlinks
- **Hook-based** (`HookBasedAdapter`): CLAUDE.md + Jinja2 rules/ + settings.json hook
- **SDK-based** (`SdkBasedAdapter`): TypeScript extensions + prompt templates

**Pillar 3 — The Conformance Suite**: Any platform can run the suite to verify
compliance. `vibe spec conformance --all` runs all 85 tests.

---

## Overview

VibeSOP is a **Skill Operating System (SkillOS)** that manages the full lifecycle of AI development skills. It sits as a middleware layer between AI agents (Claude Code, OpenCode, etc.) and skill ecosystems.

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
│  │ vibe route  │──│ 10-Layer    │──│ Discovery → Security    │  │
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

User-facing commands that interact with the SkillOS engine.

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

### 2. Agent Runtime Layer (`src/vibesop/agent/`) ✨ v6.2.0

Fully wired entry point connecting all runtime components. Platform adapters use
`AgentRuntime.handle_query()` instead of shelling out to `vibe route` via a
subprocess.

```python
from vibesop.agent.runtime import AgentRuntime

# One-call entry point for platform hooks
runtime = AgentRuntime()
result = runtime.handle_query("review my code", platform="claude-code")

# Or get platform-specific hook response JSON
hook_json = runtime.handle_query_for_hook(
    "review my code",
    platform="claude-code",
    hook_event_name="UserPromptSubmit",
)
```

**Wired Pipeline** (7 stages):
1. Slash command detection → `SlashCommandExecutor`
2. Intent interception → `IntentInterceptor.should_intercept()`
3. Route query → `AgentRouter.route()`
4. Present decision → `DecisionPresenter` (with `--explain`)
5. Extract match details → `AgentRuntimeResult`
6. Inject skill content → `SkillInjector.inject_single_skill()`
7. Format hook response → `AgentRuntimeResult.to_hook_response()`

**Key Components**:
- `AgentRuntime` — Unified entry point (wires 7 components)
- `AgentRuntimeResult` — Structured result with `to_hook_json()` and `to_hook_response()`
- `IntentInterceptor` — Decides whether to trigger routing (short query skip, meta-query skip, explicit override, slash command detection)
- `SkillInjector` — Loads skill content for platform context injection
- `DecisionPresenter` — Transparent routing explanation (why this skill, alternatives, rejected near-misses)
- `SlashCommandExecutor` — Execute built-in `/vibe-*` commands
- `PlanExecutor` — Guide agents through multi-step orchestration
- `StepContextInjector` — Inject step dependencies and context into agent
- `ExecutionProtocol` — Serialize/deserialize execution plans

**Shell Hook Elimination**: The `vibesop-route.sh` hook was reduced from 221→46
lines. All routing logic now lives in Python's `AgentRuntime` — the shell script
is a thin wrapper that calls `handle_query_for_hook()`. This eliminates logic
duplication between bash and Python.

**HookPoint.ROUTE_INTERCEPTOR**: Wired in `HOOK_DEFINITIONS` for all 4 platforms
(claude-code, kimi-cli, opencode, pi). Each entry maps to the Python
`AgentRuntime` class.

---

### 3. Routing Engine (`src/vibesop/core/routing/`)

The heart of VibeSOP — routes queries to skills using a 10-layer pipeline.

#### UnifiedRouter

```python
from vibesop.core.routing import UnifiedRouter

router = UnifiedRouter()
result = router.route("debug this error")

# result.primary.skill_id = "systematic-debugging"
# result.primary.confidence = 0.95
# result.routing_path = [RoutingLayer.KEYWORD]
```

**10-Layer Matching Pipeline**:

| Layer | Strategy | Speed | When Used |
|-------|----------|-------|-----------|
| 0 | Explicit Override | <1ms | Direct commands like `/review` |
| 1 | Scenario Pattern | <1ms | Predefined scenarios |
| 2 | AI Triage | ~100ms | Complex semantic queries, long queries (>5 chars by default) |
| 3 | Keyword Matching | <1ms | Direct keyword hits (short queries) |
| 4 | TF-IDF | ~5ms | Semantic similarity |
| 5 | Embedding | ~20ms | Deep semantic (optional) |
| 6 | Fuzzy Matching (Levenshtein) | ~10ms | Typo tolerance |
| 7 | Custom Plugins | varies | User-defined matchers |
| 8 | No Match | N/A | No confident match found |
| 9 | Fallback LLM | ~100ms | Last-resort routing |

**3 Optimization Mechanisms**:

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
3. Project config (`.vibe/config.toml`)
4. Global config (`~/.vibe/config.toml`)
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
│ UnifiedRouter   │  → 10-layer matching pipeline
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
- ✅ Dynamic Workflow orchestration

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

**Coverage**: ~29% (measured 2026-05-01, target: 75%)

---

## Design Decisions

### Why Separate Management from Execution?

1. **Lifecycle Management** — SkillOS manages full lifecycle, AI agents execute
2. **Tool Agnostic** — Works with any AI agent
3. **Security** — No arbitrary code execution in management layer
4. **Testability** — Management logic easily testable

### Why SKILL.md?

1. **Declarative** — Skills define themselves
2. **Version Controlled** — Skills in git
3. **Portable** — Works across AI tools
4. **Human Readable** — Easy to understand

### Why 10-Layer Pipeline?

1. **Accuracy** — Multiple strategies catch different patterns
2. **Performance** — Fast layers first, slow layers as fallback
3. **Flexibility** — Easy to add new matchers
4. **Observability** — Clear routing path for debugging

---

## Dynamic Workflow Engine (v6.0–v6.2)

The Dynamic Workflow Engine provides intelligent multi-step orchestration that goes beyond
single-skill routing. It classifies user intent, selects an execution pattern, and
optionally re-orchestrates the plan at runtime based on intermediate results.

### Architecture

```
User Query (multi-intent or complex)
    │
    ▼
┌─────────────────┐
│  ClassifierAgent │  ← Pattern selection (keyword fast-path + LLM semantic)
└────────┬────────┘
         │ WorkflowPattern
         ▼
┌─────────────────┐
│   PlanBuilder    │  ← Build ExecutionPlan with pattern-aware step layout
└────────┬────────┘
         │ ExecutionPlan
         ▼
┌─────────────────────────────────────────────────┐
│               WorkflowEngine                     │
│                                                  │
│  Static patterns: SEQUENTIAL, PARALLEL, FAN_OUT  │
│  → ParallelScheduler (topological batch exec)    │
│                                                  │
│  Dynamic patterns: LOOP_UNTIL_DRY, TOURNAMENT    │
│  → Reorchestrator (runtime plan mutation)        │
│  → TournamentRunner (pairwise comparison)        │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  VerifierAgent   │  ← Optional adversarial verification (adversarial pattern)
│  TrustLevel:     │     TRUSTED / QUARANTINE / SANDBOX
└─────────────────┘
```

### 6 Workflow Patterns

| Pattern | Type | Use Case | Example |
|---------|------|----------|---------|
| `SEQUENTIAL` | Static | Linear dependency chain | Analyze → Fix → Verify |
| `PARALLEL` | Static | Independent concurrent tasks | Lint + Type-check + Test |
| `FAN_OUT` | Static | One-to-many distribution | Review across 3 dimensions |
| `ADVERSARIAL` | Static | Verify via independent critic | Generate → Verify → Accept |
| `LOOP_UNTIL_DRY` | Dynamic | Iterative until no new findings | Bug hunting, exhaustive audit |
| `TOURNAMENT` | Dynamic | Best-of-N via pairwise judge | Design selection, approach comparison |

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| ClassifierAgent | `core/orchestration/classifier.py` | Two-phase classification: keyword rules (85% fast-path) + LLM semantic |
| PlanBuilder | `core/orchestration/plan_builder.py` | Convert sub-tasks into pattern-aware ExecutionPlan |
| WorkflowEngine | `core/orchestration/workflow_engine.py` | Route static vs dynamic execution, manage engine lifecycle |
| VerifierAgent | `core/orchestration/verifier.py` | Independent verification with isolated context window |
| VerificationLoop | `core/orchestration/verification_loop.py` | Retry loop with feedback aggregation |
| Reorchestrator | `core/orchestration/reorchestrator.py` | Post-step analysis: CONTINUE / APPEND / LOOP_BACK / ESCALATE / TERMINATE |
| TournamentRunner | `core/orchestration/tournament.py` | Pairwise comparison with isolated judge |
| StepRunner | `agent/step_runner.py` | Execute plans; routes dynamic plans to WorkflowEngine |

### CLI Flags

```bash
# Force a specific workflow pattern
vibe route --pattern fan_out "analyze architecture and performance"

# Enable adversarial verification
vibe route --verify "refactor the auth module"

# Configure verifier strictness (lenient / standard / strict)
vibe route --verify --strictness strict "security audit this code"
```

### Platform Compatibility

The Workflow Engine runs inside VibeSOP's process and is platform-independent.
However, **execution model** varies based on each platform's native capabilities:

| Platform | VibeSOP Workflow | Native Sub-Agent | Execution Model | Auto-Trigger |
|----------|-----------------|-------------------|-----------------|-------------|
| **Claude Code** | ✅ Full | ✅ `parallel()`, `pipeline()` | Parallel sub-agents | Shell hooks |
| **Kimi CLI** | ✅ Full | ❌ | Serial (single agent) | Config hooks |
| **Pi Agent** | ✅ Full | ❌ | Serial (single agent) | TS extensions |
| **OpenCode** | ✅ Full | ❌ | Serial (single agent) | Manual `source` |

**What this means in practice:**

- On **Claude Code**: The platform can spawn real sub-agents for `PARALLEL` and `FAN_OUT`.
  `LOOP_UNTIL_DRY` and `TOURNAMENT` leverage the native `Workflow` tool for true
  concurrent execution.
- On **Kimi CLI / Pi / OpenCode**: VibeSOP generates the full execution plan, but the
  platform's single agent executes steps sequentially. Dynamic patterns (`LOOP_UNTIL_DRY`,
  `TOURNAMENT`) still work — the engine loops within a single agent session, but without
  true parallelism.

**All patterns produce the same structured output** (`DynamicExecutionResult`) regardless
of platform. The difference is purely in execution concurrency.

---

## v5.x Feature Overview

### v5.0.0 — SkillRuntime: Scope + Lifecycle ✅
- Scope isolation (project-level vs global skills)
- Skill enable/disable with lifecycle state machine
- DRAFT → ACTIVE → DEPRECATED → ARCHIVED transitions
- Data pre-burial: usage_stats, version_history, evaluation_context

### v5.1.0 — SkillMarket + Quality ✅
- Skill marketplace: search (`vibe market search`), install (`vibe market install`)
- Publish via GitHub Issues (`vibe market publish`)
- 5-dimension quality evaluation (routing accuracy, user satisfaction, execution success, usage frequency, health score)
- Automated retention/deprecation with FeedbackLoop

### v5.2.0 — Intelligent Ecosystem ✅
- Per-skill recommendation engine (SkillRecommender)
- 4-level confidence-gated degradation (DegradationManager)
- Proactive discovery of unused skills matching current workflow
- Auto-deprecation enabled by default

---

## Hook Reliability + Multi-Agent Squad (v7.0)

### Hook Path Hardening

The shell hook wrapper (`vibesop-route.sh`, generated from
`adapters/templates/shared/vibesop-route.sh.j2`) is the integration
point Claude Code / Kimi CLI / OpenCode actually invoke. v7.0 hardens
it for non-interactive shells:

- `export PATH` adds `~/.local/bin` / `~/.cargo/bin` / `/opt/homebrew/bin`
  so the hook can find `uv` regardless of how the parent process was
  launched.
- The script walks up from `${BASH_SOURCE[0]}` looking for
  `pyproject.toml` with `name = "vibesop"`, falling back to
  `$CLAUDE_PROJECT_DIR` / `$PWD` / `$VIBESOP_PROJECT_ROOT`.
- Once the project root is located, `uv run python` is invoked from
  there so the project venv is used.

### AgentRouter ↔ AgentRuntime API

`AgentRouter.orchestrate(query, callbacks=None, context=None)` is the
single entry point for both CLI and hook paths. v7.0 added `callbacks`
and `context` parameters (both default None for backward compatibility):

- `callbacks` is reserved for future live-progress hooks; currently
  unused but accepts the same `LiveOrchestrationCallbacks` shape as
  `UnifiedRouter.orchestrate`.
- `context` carries `metadata["intent_analysis"]` (a serialized
  `IntentAnalysis`) from `IntentInterceptor._build_quick_squad_analysis`
  through to `PlanBuilder._build_squad_steps`.

### Multi-Agent Squad Pipeline

```
   User query
       │
       ▼
   IntentInterceptor.should_intercept
       │
       │  (≥ 2 distinct ROLE_KEYWORDS hit)
       ▼
   MULTI_AGENT_SQUAD + IntentAnalysis{
       suggested_roles, collaboration_protocol,
       per_agent_skills (via SkillComposer.infer_skills_for_role)
   }
       │
       ▼
   AgentRuntime.handle_query
       │  (builds RoutingContext.metadata["intent_analysis"])
       ▼
   AgentRouter.orchestrate(query, context=ctx)
       │
       ▼
   build_plan(query, plan_metadata=ctx.metadata)
       │  (picks AGENT_SQUAD / DEBATE / RED_TEAM from protocol)
       ▼
   PlanBuilder._build_squad_steps(analysis)
       │
       ▼
   AgentSquadComposer.compose(analysis)
       │  (creates AgentRole + SquadStep per role,
       │   wires input_from dependencies per protocol)
       ▼
   SkillComposer.compose_for_squad(squad, global_skills)
       │  (assigns per-role skill allowlists via priority + relevance)
       ▼
   ExecutionPlan{steps: [per-role ExecutionStep], metadata: {agent_squad}}
```

CLI output renders the squad summary via
`_format_squad_summary(squad, analysis)` (Rich table with role icons
🏗️ architect / 💻 implementer / 👁️ reviewer / 🛡️ red_team / ⚡ debater).
Hook output attaches the plan as `hookSpecificOutput.additionalContext`
so the host agent receives the squad plan as context.

### Cross-Cutting Skill: prompt-chain-validator

`.vibe/skills/cross-cutting/prompt-chain-validator.skill/SKILL.md`
encodes the dynamic-workflow + container-validation pattern as a
discoverable `type: cross-cutting` skill. `CrossCuttingDiscovery`
picks it up automatically — `vibe workflows list-workflows` shows it
without any extra registration. The matching CLI `vibe prompt-chain`
is implemented in `cli/commands/prompt_chain_cmd.py` and backed by
`core/prompt_chain/{generator,validator}.py`.

---

## References

- [Principles](docs/PRINCIPLES.md)
- [Contributing Guide](CONTRIBUTING.md)
- [API Documentation](docs/api/)
