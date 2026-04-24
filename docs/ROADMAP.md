# VibeSOP Roadmap

> **Version**: 4.3.0
> **Last Updated**: 2026-04-24 (Phase 3 complete)
> **Status**: Active Development

---

## Current State (v4.3.0)

### ✅ Completed

- [x] Core routing engine with 7-layer pipeline
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
- [x] **Context-aware routing** (v4.3.0)
- [x] **Agent Runtime layer** (v4.3.0)
- [x] **Badge system** (v4.3.0)

### 📊 Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Code Lines | ~49,000 | ~15,000 | ⚠️ 3× over (feature growth) |
| Test Count | 1,951 | 2,000+ | ⚠️ On track |
| Test Coverage | 74% (full run) | >75% | ⚠️ 1% below target |
| Routing P95 | 354ms | <100ms | ⚠️ In progress (v4.4.0) |
| Skills Supported | 45+ | 45+ | ✅ |
| Lint Errors | 114 | 0 | ⚠️ Reduced from 185 |
| Quick Commands | 7 | 7 | ⚠️ CLI ready, platform-dependent |
| Service Layer | 4 services | 4 services | ✅ |

---

## v4.1.0 — AI Triage Production ✅ (Released 2026-04)

### Goals
Make AI Triage (Layer 2) production-ready with real LLM integration.

### Features

- [x] **Real LLM Integration**
  - Anthropic Claude API
  - OpenAI GPT API
  - Local model support (Ollama)

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

## v4.3.0 — Context-Aware Routing + Slash Commands ✅ (Released 2026-04-24)

### Goals
Improve routing accuracy with context awareness, multi-turn conversations, direct Agent integration, and explicit slash commands.

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

## v4.4.0 — SkillMarket + Feedback Loop (2026-Q2)

### Goals
Complete the skill ecosystem with discovery, community, and self-improvement.

### Features

#### SkillMarket (Highest Priority)
- [ ] **Skill Discovery**
  - Search skills by keywords, tags, project type
  - Browse trending/popular skills
  - GitHub topic-based skill crawling
  - Custom registry URLs support

- [ ] **Skill Metadata**
  - Rating and reviews system
  - Download statistics
  - Compatibility matrix (platform × version)
  - Author profiles and trust scores

- [ ] **Smart Recommendations**
  - Project-type-based recommendations
  - "Users who installed X also installed Y"
  - Missing skill detection for current project

- [ ] **CLI Integration**
  - `vibe market search <query>`
  - `vibe market recommend`
  - `vibe market info <skill>`
  - `vibe market install --popular`

#### Autoresearch Feedback Loop
- [ ] **Automatic Skill Improvement**
  - Analyze routing success/failure patterns
  - Suggest keyword additions based on missed queries
  - Auto-generate A/B test variants
  - Skill quality regression detection

- [ ] **Skill Evolution**
  - Track skill effectiveness over time
  - Auto-deprecate low-quality skills
  - Suggest skill splits (too broad) or merges (too narrow)

#### Performance Optimization
- [ ] **Latency Reduction**
  - Current P95: 354ms, Target: <100ms
  - Router hot-path optimization
  - Lazy loading for heavy dependencies
  - Connection pooling for LLM clients

- [ ] **Quality Gates**
  - Fix 185 lint errors → 0
  - Increase coverage from 74% → 80%
  - Add performance regression CI

### Success Metrics

- SkillMarket: 50+ discoverable skill packs
- Routing P95 latency: <100ms
- Test coverage: >80%
- Lint errors: 0

---

## v5.0.0 — SkillRuntime: Scope + Lifecycle (2026-Q2/Q3)

> **ADR**: [docs/version_05.md](docs/version_05.md) (Plan: VibeSOP Skill Ecosystem Evolution, approved 2026-04-21)

### Goals
Introduce scope isolation, skill enable/disable, and lifecycle state management.

### Features

- [ ] **SkillRuntime Core**
  - Scope system: project-level vs global skills
  - Skill enable/disable toggle (`vibe skill enable/disable <id>`)
  - SkillLifecycleState machine (DRAFT → ACTIVE → DEPRECATED → ARCHIVED)
  - Scope-aware config resolution (project `.vibe/` overrides global `~/.vibe/`)

- [ ] **Data Pre-burial for v5.1**
  - SkillConfig gains `usage_stats` field (call count, success rate, last used)
  - SkillConfig gains `version_history` field (semver tracking)
  - SkillConfig gains `evaluation_context` extension slot

- [ ] **CLI Commands**
  - `vibe skill enable <id>` / `vibe skill disable <id>`
  - `vibe skill scope <id> --project` / `vibe skill scope <id> --global`
  - `vibe skill lifecycle <id> --set deprecated`

### Success Metrics

- Skill scope isolation: 100% (project skills invisible outside project root)
- Toggle latency: <50ms
- Lifecycle states: 4 (draft/active/deprecated/archived)
- Backward compatibility: v4.x users smooth migration via config

---

## v5.1.0 — SkillMarket + Feedback Loop (2026-Q3/Q4)

### Goals
Complete the skill ecosystem with discovery, community, and self-improvement.

### Features

- [ ] **SkillMarket MVP**
  - `vibe market search <query>` — keyword + tag search
  - `vibe market info <skill>` — ratings, downloads, compatibility
  - `vibe market install` — one-click from discovered skills
  - GitHub topic crawling (`topic:vibesop-skill`)

- [ ] **Autoresearch Feedback Loop**
  - Analyze routing success/failure patterns
  - Suggest keyword additions for missed queries
  - Skill quality regression detection
  - Auto-deprecate skills below quality threshold

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
| v4.0.0 | 2026-04-06 | ✅ Core routing engine |
| v4.1.0 | 2026-04 | ✅ AI Triage production |
| v4.2.0 | 2026-04 | ✅ Skill health monitoring |
| v4.3.0 | 2026-04-24 | ✅ Context-aware routing + Agent Runtime |
| v5.0.0 | 2026-Q2/Q3 | ⏳ SkillRuntime: Scope + Lifecycle |
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

*Last updated: 2026-04-24 (v5.x Roadmap aligned with ADR)*
