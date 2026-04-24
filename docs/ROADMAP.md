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

## v5.0.0 — Plugin Ecosystem (2026-Q3)

### Goals
Transform VibeSOP into a platform with a thriving plugin ecosystem.

### Features

- [ ] **Plugin System**
  - Matcher plugins (custom routing logic)
  - Adapter plugins (new AI platforms)
  - Hook system (pre/post routing events)
  - Plugin sandbox for security

- [ ] **Marketplace v2**
  - Plugin registry alongside skill registry
  - One-command plugin install
  - Plugin versioning and updates

- [ ] **Developer SDK**
  - `vibesop-dev` CLI for plugin development
  - Local testing harness
  - Auto-generated documentation
  - Plugin template generator

- [ ] **Enterprise Features**
  - Private skill registries
  - Team skill sharing and governance
  - Audit logging and compliance
  - SSO integration

### Success Metrics

- Plugin ecosystem: 50+ plugins
- Marketplace adoption: 1000+ users
- Enterprise customers: 5+

---

## Backlog

### Nice to Have

- [ ] Web UI for skill management
- [ ] IDE integrations (VS Code, JetBrains)
- [ ] Mobile app for skill discovery
- [ ] Voice command support
- [ ] Real-time collaboration
- [ ] Skill execution (not just routing)

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
| v5.0.0 | 2027-Q2 | ⏳ Plugin ecosystem |

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

*Last updated: 2026-04-24 (v5 Quality Sprint — Phase 1-3 complete)*
