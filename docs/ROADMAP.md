# VibeSOP Roadmap

> **Version**: 4.3.0
> **Last Updated**: 2026-04-24
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

| Metric | Current | Target |
|--------|---------|--------|
| Code Lines | ~15,000 | ~15,000 ✅ |
| Test Coverage | ~80% | >75% ✅ |
| Routing P95 | ~45ms | <50ms ✅ |
| Skills Supported | 45+ | 45+ ✅ |

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

## v4.3.0 — Context-Aware Routing ✅ (Released 2026-04-22)

### Goals
Improve routing accuracy with context awareness, multi-turn conversations, and direct Agent integration.

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

### Success Metrics

- ✅ Routing accuracy improvement: +5% (with project context)
- ✅ Multi-turn query support: 100%
- ✅ Agent Runtime API stability: v1.0
- ✅ Test count: 1751 (+64 from v4.2.0)

---

## v5.0.0 — Plugin Ecosystem (2027)

### Goals
Transform VibeSOP into a platform with a thriving plugin ecosystem.

### Features

- [ ] **Plugin System**
  - Matcher plugins
  - Adapter plugins
  - Hook system

- [ ] **Marketplace**
  - Skill pack registry
  - Plugin registry
  - Rating and reviews

- [ ] **Developer Tools**
  - SDK for plugin development
  - Local testing tools
  - Documentation generator

- [ ] **Enterprise Features**
  - Private skill registries
  - Team skill sharing
  - Audit logging

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

### Technical Debt

- [ ] Increase test coverage to 80%
- [ ] Performance benchmarks CI
- [ ] Documentation translation (CN, JP)
- [ ] API stability guarantees

---

## Release Schedule

| Version | Date | Focus |
|---------|------|-------|
| v4.0.0 | 2026-04-06 | ✅ Core routing engine |
| v4.1.0 | 2026-04 | ✅ AI Triage production |
| v4.2.0 | 2026-04 | ✅ Skill health monitoring |
| v4.3.0 | 2026-12-01 | ⏳ Advanced routing |
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

*Last updated: 2026-04-06*
