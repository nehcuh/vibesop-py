# VibeSOP Roadmap

> **Version**: 4.4.0
> **Last Updated**: 2026-04-26
> **Status**: Active Development

---

## Current State (v4.4.0)

### ✅ Completed

- [x] Core SkillOS engine with 10-layer pipeline
- [x] Unified skill management (builtin + external + custom)
- [x] Security auditing for external skills
- [x] Preference learning system
- [x] CLI with route/install/skills commands
- [x] Performance optimization (candidate caching, <50ms P95)
- [x] Architecture cleanup (65% code reduction)
- [x] Documentation overhaul
- [x] AI Triage production readiness (v4.1.0)
- [x] Skill health monitoring (v4.2.0)
- [x] Skill-level LLM configuration system
- [x] One-click smart skill installation
- [x] Context-aware routing (v4.3.0)
- [x] Agent Runtime layer (v4.3.0)
- [x] Badge system (v4.3.0)
- [x] Multi-intent detection + task decomposition + execution planning (v4.4.0)
- [x] Skill lifecycle management (DRAFT → ACTIVE → DEPRECATED → ARCHIVED) (v4.4.0)
- [x] Scope system (project-level vs global skill isolation) (v4.4.0)
- [x] Feedback loop (usage analytics + satisfaction tracking) (v4.4.0)

### 📊 Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Code Lines | ~49,000 | ~15,000 | ⚠️ 3× over (feature growth) |
| Test Count | 2,044 | 2,000+ | ✅ |
| Test Coverage | 74% (full run) | >75% | ⚠️ 1% below target |
| Routing P95 | 225ms | <100ms | ⚠️ In progress |
| Skills Supported | 45+ | 45+ | ✅ |
| Lint Errors | 22 | 0 | ⚠️ |
| Quick Commands | 7 | 7 | ✅ |
| Service Layer | 4 services | 4 services | ✅ |

---

## v4.1.0 — AI Triage Production ✅ (Released 2026-04)

### Goals
Make AI Triage (Layer 2) production-ready with real LLM integration.

### Features

- [x] **Real LLM Integration**
  - Anthropic Claude API
  - OpenAI GPT API
  - Local model support (Ollama, default provider in v4.4.0+)

- [x] **Cost Management**
  - Token usage tracking
  - Cost per query estimation
  - Budget alerts and limits

- [x] **Caching Improvements**
  - Semantic cache (similar queries)
  - Persistent cache across sessions
  - Cache warming for common queries

- [x] **Fallback Strategy**
  - Graceful degradation when LLM unavailable
  - Automatic fallback to keyword matching
  - Circuit breaker pattern

### Success Metrics

- AI Triage hit rate > 30%
- Average cost per query < $0.005
- Cache hit rate > 50%
- Zero downtime for LLM failures

---

## v4.2.0 — Skill Health Monitoring ✅ (Released 2026-04)

### Goals
Monitor the health and quality of external skill packs.

### Features

- [x] **Health Dashboard**
  - `vibe skills health` command
  - Visual status indicators
  - Detailed health reports

- [x] **Health Metrics**
  - Last update time
  - Open issues count
  - Version compatibility
  - Security audit status

- [x] **Alerts**
  - Outdated skill packs
  - Security vulnerabilities
  - Breaking changes

- [x] **Auto-Update**
  - Check for updates
  - Security patch auto-install
  - Changelog integration

### Success Metrics

- Health check coverage: 100% of installed packs
- Alert response time: < 24 hours
- Security patch adoption: > 90% within 7 days

---

## v4.3.0 — Context-Aware Routing + Quick Commands ✅ (Released 2026-04-24)

### Goals
Improve routing accuracy with context awareness, multi-turn conversations, direct Agent integration, and CLI quick commands.

### Features

- [x] **Context-Aware Routing**
  - Project type detection (15+ types: python, rust, js, ts, go, java, etc.)
  - Technology stack inference (13+ stacks: django, fastapi, react, docker, k8s, etc.)
  - Project context boost (+0.02~0.04 confidence)

- [x] **Multi-Turn Support**
  - Conversation context tracking
  - Follow-up query detection (continuation/retry/alternative/clarification/refinement)
  - Chinese + English pronoun reference detection

- [x] **Agent Runtime Layer**
  - Direct Python API for AI Agents (no external API key needed)
  - Agent LLM injection (`router.set_llm(agent_llm)`)
  - Platform adaptation (Claude Code, Cursor, Continue.dev)

- [x] **Router Refactoring**
  - 8 Mixin extraction from 1210-line God Class → 506 lines (-58%)
  - Cleaner separation of concerns
  - Better testability

- [x] **Badge System**
  - 4 badge types: first_feedback, skill_champion, quality_master, ecosystem_guardian
  - Integrated into skills feedback, health check, and routing

- [x] **Routing Transparency**
  - `--explain` flag shows full routing decision tree
  - `--validate` mode with rejected candidate display
  - Per-layer diagnostics with timing and reasoning

- [x] **Central Storage Architecture**
  - Skill packs installed to `~/.config/skills/<pack>/`
  - Platform directories receive symlinks (`~/.claude/skills/<pack>` → central)
  - Unified management across all AI tools

- [x] **Quick Commands (CLI)**
  - 7 built-in commands: `/vibe-route`, `/vibe-install`, `/vibe-analyze`, `/vibe-evaluate`, `/vibe-orchestrate`, `/vibe-list`, `/vibe-help`
  - CLI direct execution via `vibe route --slash "/vibe-help"`
  - Platform hook scripts for best-effort AI Agent integration
  - Shared service layer (RoutingService, InstallService, AnalysisService, EvaluationService)

- [x] **Orchestration Interaction**
  - `--strategy=sequential|parallel|auto` for multi-skill execution
  - Interactive step editing (move/remove/reorder)
  - Data dependency visualization

### Success Metrics

- ✅ Routing accuracy improvement: +5% (with project context)
- ✅ Multi-turn query support: 100%
- ✅ Agent Runtime API stability: v1.0
- ✅ Quick command coverage: 7 commands, CLI + hook integration
- ✅ Service layer: 4 services, zero duplication with CLI
- ✅ Test count: 1751+ (+64 from v4.2.0)

---

## v4.4.0 — SkillOS: Orchestration + Lifecycle + Feedback ✅ (Released 2026-04-26)

### Goals
Transform VibeSOP from a routing tool into a complete Skill Operating System.

### Features

#### Orchestration (Default Mode)
- [x] **Multi-Intent Detection**
  - Automatic detection of complex queries with multiple intents
  - Heuristic + LLM-based detection with zero-cost fast path
  - Intent domain boundary detection

- [x] **Task Decomposition**
  - LLM-based query decomposition into sub-tasks
  - Fallback rule-based decomposition when LLM unavailable
  - Guardrails to prevent over-decomposition

- [x] **Execution Planning**
  - Automatic serial/parallel strategy detection
  - Dependency inference between steps
  - Interactive plan editing (move/remove/reorder)

- [x] **Streaming Progress**
  - Real-time orchestration progress display
  - Phase-by-phase callbacks (routing → detection → decomposition → planning)
  - Error recovery strategies (skip/retry/abort)

#### Skill Lifecycle Management
- [x] **SkillLifecycle State Machine**
  - States: DRAFT → ACTIVE → DEPRECATED → ARCHIVED
  - Valid transition enforcement
  - Routability checks (archived/draft skills excluded)

- [x] **Scope System**
  - Project-level vs global skills
  - Scope-aware routing (project skills invisible outside project)
  - `.vibe/skills/` project-local override

- [x] **CLI Commands**
  - `vibe skill list` — List skills with lifecycle state
  - `vibe skill enable <id>` / `vibe skill disable <id>`
  - `vibe skill status <id>` — Show skill details and valid transitions

#### Feedback Loop
- [x] **Usage Analytics**
  - Execution record storage (`.vibe/analytics.jsonl`)
  - Skill usage statistics (satisfaction rate, modification rate)
  - Low-quality skill detection

- [x] **User Feedback Collection**
  - Post-execution satisfaction prompt
  - Automatic deviation recording suggestion
  - Feedback-driven routing improvement

#### SkillMarket (Partial)
- [x] **GitHub Topic Crawling**
  - `vibe market search <query>` — Search by keywords
  - `vibe market install <skill>` — Install from discovery

#### Performance Optimization
- [ ] **Latency Reduction** (Ongoing)
  - Current P95: 225ms, Target: <100ms
  - Router hot-path optimization
  - Lazy loading for heavy dependencies

- [ ] **Quality Gates** (Ongoing)
  - Fix remaining lint errors → 0
  - Increase coverage from 74% → 80%

### Success Metrics

- ✅ Orchestration: Multi-intent detection + task decomposition + execution planning
- ✅ SkillLifecycle: 4 states with transition validation
- ✅ Scope system: Project-level skill isolation
- ✅ Feedback loop: Usage analytics + user satisfaction tracking
- ⚠️ Routing P95 latency: 225ms (target <100ms)
- ⚠️ Lint errors: 22 (target 0)
- ⚠️ Test coverage: 74% (target >80%)

---

## v5.0.0 — SkillRuntime: Scope + Lifecycle (2026-Q2) ✅ IN PROGRESS

> **ADR**: [docs/version_05.md](docs/version_05.md) (Plan: VibeSOP Skill Ecosystem Evolution, approved 2026-04-21)

### Goals
Introduce scope isolation, skill enable/disable, and lifecycle state management.

### Features

- [~] **SkillRuntime Core** (In Progress)
  - Scope system: project-level vs global skills
  - Skill enable/disable toggle (`vibe skill enable/disable <id>`)
  - SkillLifecycleState machine (DRAFT → ACTIVE → DEPRECATED → ARCHIVED)
  - Scope-aware config resolution (project `.vibe/` overrides global `~/.vibe/`)

- [~] **Data Pre-burial for v5.1** (In Progress)
  - SkillConfig gains `usage_stats` field (call count, success rate, last used)
  - SkillConfig gains `version_history` field (semver tracking)
  - SkillConfig gains `evaluation_context` extension slot

- [~] **CLI Commands** (In Progress)
  - `vibe skill enable <id>` / `vibe skill disable <id>`
  - `vibe skill scope <id> --project` / `vibe skill scope <id> --global`
  - `vibe skill lifecycle <id> --set deprecated`

### Success Metrics

- Skill scope isolation: 100% (project skills invisible outside project root)
- Toggle latency: <50ms
- Lifecycle states: 4 (draft/active/deprecated/archived)
- Backward compatibility: v4.x users smooth migration via config

---

## v5.1.0 — SkillMarket + Feedback Loop (2026-Q2/Q3) ✅ IN PROGRESS

### Goals
Complete the skill ecosystem with discovery, community, and self-improvement.

### Features

- [~] **SkillMarket MVP** (In Progress)
  - `vibe market search <query>` — keyword + tag search
  - `vibe market info <skill>` — ratings, downloads, compatibility
  - `vibe market install` — one-click from discovered skills
  - GitHub topic crawling (`topic:vibesop-skill`)

- [~] **Autoresearch Feedback Loop** (In Progress)
  - Analyze routing success/failure patterns
  - Suggest keyword additions for missed queries
  - Skill quality regression detection
  - Auto-deprecate skills below quality threshold
  - User satisfaction tracking (`AnalyticsStore`)
  - Interactive feedback collection after execution

- [ ] **Skill Evaluation**
  - Rating and reviews system
  - Usage statistics (downloads, active users)
  - Compatibility matrix (platform × version)
  - Author trust scores

### Success Metrics

- SkillMarket: 50+ discoverable skill packs
- Feedback loop: automatic keyword additions for 80%+ missed queries
- Evaluation coverage: 100% of installed skills
- Deprecation accuracy: <5% false positives

---

## v5.2.0 — Intelligent Ecosystem (2026-Q4/2027-Q1)

### Goals
Proactive skill recommendations, transparent fallback, active discovery.

### Features

- [ ] **Smart Recommendations**
  - Project-type-based recommendations ("Python project → suggest tdd, review")
  - "Users who installed X also installed Y"
  - Missing skill detection for current project

- [ ] **Transparent Auto-Degradation**
  - When no skill matches, show: "I found no matching skill. Falling back to raw LLM."
  - Route result includes `layer: FALLBACK_LLM` for visibility
  - Config: `fallback.always_ask true` to require user confirmation

- [ ] **Active Discovery**
  - Periodically scan for new skills matching project tech stack
  - Proactive suggestion with explicit opt-in
  - One-command install from suggestion

### Success Metrics

- Recommendation click-through: >30%
- Fallback awareness: 100% of fallbacks transparent to user
- Active discovery: <5% false positive suggestions

---

## Backlog

### Nice to Have

- [ ] Web UI for skill management → **Deferred: post-v5.2 evaluation**
- [ ] IDE integrations (VS Code, JetBrains) → **Deferred: post-v5.2 evaluation**
- [ ] Mobile app for skill discovery → **Deferred: post-v5.2 evaluation**
- [ ] Voice command support → **Deferred: post-v5.2 evaluation**
- [ ] Real-time collaboration → **Deferred: post-v5.2 evaluation**
- [ ] Skill execution (not just routing) → **Deferred: post-v5.2 evaluation**

### Technical Debt

- [ ] Documentation translation (CN, JP, DE)
- [ ] API stability guarantees (semver)
- [ ] Migration guide for breaking changes
- [ ] Benchmark suite and performance dashboard

---

## Release Schedule

| Version | Date | Focus |
|---------|------|-------|
| v4.0.0 | 2026-04-06 | ✅ Core SkillOS engine |
| v4.1.0 | 2026-04 | ✅ AI Triage production |
| v4.2.0 | 2026-04 | ✅ Skill health monitoring |
| v4.3.0 | 2026-04-24 | ✅ Context-aware routing + Agent Runtime |
| v4.4.0 | 2026-04-26 | ✅ SkillOS: Orchestration + Lifecycle + Feedback |
| v5.0.0 | 2026-Q2/Q3 | 📋 SkillRuntime: Scope + Lifecycle (refined) |
| v5.1.0 | 2026-Q3/Q4 | 📋 SkillMarket + Feedback Loop |
| v5.2.0 | 2026-Q4/2027-Q1 | 📋 Intelligent Ecosystem |

---

## Contributing

See something missing? Want to accelerate a feature?

1. Check [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines
2. Open an issue to discuss the feature
3. Submit a PR referencing the roadmap item

---

## Changelog

### v4.0.0 (2026-04-06)
- Initial stable release
- 7-layer routing pipeline
- Unified architecture
- Security auditing
- Performance optimization

---

### v4.3.1 (2026-04-24)
- Roadmap revised: v5.x unified with version_05.md ADR (layered evolution plan)
- v5.0.0 redefined as SkillRuntime (scope + lifecycle), not Plugin Ecosystem
- Added v5.1.0 (SkillMarket + Feedback Loop) and v5.2.0 (Intelligent Ecosystem)
- Pre-v6.0 ideas deferred to post-v5.2 evaluation

---

*Last updated: 2026-04-26 (v4.4.0 released; v5.x Roadmap aligned with ADR)*
