# VibeSOP Roadmap

> **Version**: 4.0.0
> **Last Updated**: 2026-04-06
> **Status**: Active Development

---

## Current State (v4.0.0)

### ✅ Completed

- [x] Core routing engine with 7-layer pipeline
- [x] Unified skill management (builtin + external + custom)
- [x] Security auditing for external skills
- [x] Preference learning system
- [x] CLI with route/install/skills commands
- [x] Performance optimization (candidate caching, <50ms P95)
- [x] Architecture cleanup (65% code reduction)
- [x] Documentation overhaul

### 📊 Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Code Lines | ~13,000 | ~13,000 ✅ |
| Test Coverage | ~80% | >75% ✅ |
| Routing P95 | ~45ms | <50ms ✅ |
| Skills Supported | 44+ | 40+ ✅ |

---

## v4.1.0 — AI Triage Production (Q2 2026)

### Goals
Make AI Triage (Layer 2) production-ready with real LLM integration.

### Features

- [ ] **Real LLM Integration**
  - Anthropic Claude API
  - OpenAI GPT API
  - Local model support (Ollama)

- [ ] **Cost Management**
  - Token usage tracking
  - Cost per query estimation
  - Budget alerts and limits

- [ ] **Caching Improvements**
  - Semantic cache (similar queries)
  - Persistent cache across sessions
  - Cache warming for common queries

- [ ] **Fallback Strategy**
  - Graceful degradation when LLM unavailable
  - Automatic fallback to keyword matching
  - Circuit breaker pattern

### Success Metrics

- AI Triage hit rate > 30%
- Average cost per query < $0.005
- Cache hit rate > 50%
- Zero downtime for LLM failures

---

## v4.2.0 — Skill Health Monitoring (Q3 2026)

### Goals
Monitor the health and quality of external skill packs.

### Features

- [ ] **Health Dashboard**
  - `vibe skills health` command
  - Visual status indicators
  - Detailed health reports

- [ ] **Health Metrics**
  - Last update time
  - Open issues count
  - Version compatibility
  - Security audit status

- [ ] **Alerts**
  - Outdated skill packs
  - Security vulnerabilities
  - Breaking changes

- [ ] **Auto-Update**
  - Check for updates
  - Security patch auto-install
  - Changelog integration

### Success Metrics

- Health check coverage: 100% of installed packs
- Alert response time: < 24 hours
- Security patch adoption: > 90% within 7 days

---

## v4.3.0 — Advanced Routing (Q4 2026)

### Goals
Improve routing accuracy with context awareness and multi-turn conversations.

### Features

- [ ] **Context-Aware Routing**
  - Project type detection
  - Technology stack inference
  - Previous query history

- [ ] **Multi-Turn Support**
  - Conversation context
  - Follow-up query handling
  - Intent clarification

- [ ] **Custom Matchers**
  - Plugin system for custom matchers
  - Community matcher marketplace
  - Matcher performance analytics

- [ ] **A/B Testing Framework**
  - Route variant testing
  - Performance comparison
  - Automatic winner selection

### Success Metrics

- Routing accuracy improvement: +10%
- Multi-turn query support: 100%
- Custom matcher API stability: v1.0

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
| v4.1.0 | 2026-06-01 | 🚧 AI Triage production |
| v4.2.0 | 2026-09-01 | ⏳ Skill health monitoring |
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
