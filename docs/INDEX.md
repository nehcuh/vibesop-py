# VibeSOP Documentation Index

> **Last Updated**: 2026-07-18
> **Version**: 8.1.2

This document serves as the central index for all VibeSOP documentation, organized by purpose and audience.

---

## 📂 Root Directory (Essential Files)

These files remain in the project root for discoverability and tool integration:

- **[README.md](../README.md)** — Main project entry point, vision, quick start (English)
- **[README.zh-CN.md](../README.zh-CN.md)** — Chinese edition of the README
- **[AGENTS.md](../AGENTS.md)** — Agent configuration and routing protocol
- **[GOALS.md](../GOALS.md)** — Project goals and objective checklist
- **[CLAUDE.md](../CLAUDE.md)** — Claude Code specific integration notes
- **[CHANGELOG.md](../CHANGELOG.md)** — Version history and changes
- **[LICENSE](../LICENSE)** — MIT License
- **[CONTRIBUTING.md](../CONTRIBUTING.md)** — Contribution guidelines (mirrors dev/CONTRIBUTING.md)

---

## 📖 Core Documentation

### Getting Started

- **[Skills Ecosystem Guide](SKILLS_GUIDE.md)** — Complete guide to the VibeSOP skills ecosystem
  - 18 built-in skills + community packs explained (superpowers, gstack, omx)
  - 4-stage routing cascade详解
  - Priority decision mechanism and scenario-based selection
- **[Quick Start - Users](QUICKSTART_USERS.md)** — User-facing installation and basic usage
- **[Quick Start - Developers](QUICKSTART_DEVELOPERS.md)** — Developer setup and contribution workflow
- **[Cold Start Guide](cold-start-guide.md)** — First-time configuration guide

### Project Overview

- **[Project Context](../PROJECT_CONTEXT.md)** — Project background, goals, and scope（根目录，持续更新）
- **[Project Status](PROJECT_STATUS.md)** — Current development status and milestones
- **[Philosophy](PHILOSOPHY.md)** — Design principles and core philosophy (Discovery > Execution, Matching > Guessing, Memory > Intelligence, Open > Closed)
- **[Roadmap](ROADMAP.md)** — Future development plans and timeline (v4.x → v8.0)
- **[v8.0 Roadmap: Autonomous Loop System](ROADMAP.md#v800--autonomous-loop-system)** — 自主循环任务路线图
- **[Loop Setup Guide](loop-setup-guide.md)** — Phase 1 实测部署指南（cron/systemd/launchd 配置 + 24h 观察指标）
- **[Use Cases Guide](USE_CASES.md)** — 12 个具体场景的"痛点→方案→命令"手册（日常开发/编排/跨平台/自主监控/生命周期）
- **[Use Cases Guide (EN)](USE_CASES.en.md)** — 12 concrete scenarios with pain → approach → commands

### Governance

- **[Code of Conduct](CODE_OF_CONDUCT.md)** — Community guidelines
- **[Security](SECURITY.md)** — Security policy and vulnerability reporting

---

## 🏗️ Architecture & Design

- **[Architecture Overview](architecture/ARCHITECTURE.md)** — System architecture and technical design
  - 3-Pillar architecture (Spec / Reference / Conformance)
  - 4-stage routing cascade
  - Agent Runtime layer
  - Component structure and data flow
- **[Architecture Guide (overview)](architecture/overview.md)** — 架构导览与阅读路径
- **[Three Layers](architecture/three-layers.md)** — 三层模型详解
- **[Routing System](architecture/routing-system.md)** — 路由系统设计与决策机制
- **[Skill Runtime Interface](architecture/skill-runtime-interface.md)** — SkillRuntime contract and lifecycle state machine
- **[Workflow Engine](architecture/ARCHITECTURE.md#dynamic-workflow-engine-v60v62)** — Dynamic workflow engine: 6 patterns, platform compatibility, CLI flags
- **[Cross-Platform Support](architecture/cross-platform-support.md)** — Windows / macOS / Linux 兼容设计
- **[External Integrations](architecture/external-integrations.md)** — 外部技能包（superpowers/gstack/omx）集成架构

---

## 👥 User Documentation

### Guides & References

- **[CLI Reference](user/CLI_REFERENCE.md)** — Complete command-line interface reference
- **[Getting Started](user/getting-started.md)** — Step-by-step first-time user guide
- **[Session Intelligent Routing](user/session-intelligent-routing.md)** — Multi-turn conversation and context-aware routing
- **[Workflows](user/workflows.md)** — Cross-cutting workflow definitions and usage
- **[Troubleshooting](user/troubleshooting.md)** — Common issues and solutions

### External Skills

- **[External Skills Guide](EXTERNAL_SKILLS_GUIDE.md)** — Creating and integrating custom skills
- **[External Skills Examples](EXTERNAL_SKILLS_EXAMPLES.md)** — Sample implementations
- **[SKILL.md Format Spec v3](skill-format-spec-v3.md)** — Canonical SKILL.md frontmatter specification (29 fields)
- **[SKILL.md Format Spec v2](skill-format-spec-v2.md)** — Legacy v2 specification (for migration reference)
- **[SKILL.md Format Spec v1](skill-format-spec.md)** — Original specification (for migration reference)

### Platform & Configuration

- **[Kimi CLI Setup Guide](KIMI_CLI_SETUP.md)** — VibeSOP's Kimi CLI adapter configuration
- **[SKILL LLM Config Guide](SKILL_LLM_CONFIG_GUIDE.md)** — LLM provider setup for VibeSOP CLI subprocess mode
- **[Agent Integration](agent-integration.md)** — Integrating VibeSOP with AI agents

### Skill Pack Guides

- **[OMX Guide](OMX_GUIDE.md)** — oh-my-codex (OMX) skill pack complete guide
  - deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa

---

## 🔧 Developer Documentation

### Development Workflow

- **[Contributing Guide](dev/CONTRIBUTING.md)** — How to contribute to VibeSOP
- **[Agent Scenario Validation SOP](dev/agent-scenario-validation-sop.md)** — 多 Agent 场景化验证标准流程（场景库/指标/模型分层）
- **[Agent Scenario Validation Report](dev/agent-scenario-validation-2026-07-19.md)** — Claude Code/Kimi Code/Grok Build × vibesop 两轮验证（含部署坑与模型调研）
- **[Releasing](dev/releasing.md)** — Release process and versioning
- **[Testing](dev/testing.md)** — Testing strategies and conventions

### Technical Planning (archive)

- **[CLI Optimization Plan](archive/CLI_OPTIMIZATION_PLAN.md)** — Performance improvement initiatives
- **[Production Readiness Review](archive/PRODUCTION_READINESS_REVIEW.md)** — Production readiness assessment
- **[Roadmap Index](archive/roadmap-index.md)** — Detailed roadmap breakdown

### Deep Dives

- **[Architecture Overview](dev/architecture-overview.md)** — Developer-facing architecture summary
- **[Architecture Deep Dive](dev/architecture.md)** — In-depth technical architecture
- **[API Reference](dev/api-reference.md)** — Auto-generated API documentation
- **[Hooks Guide](dev/hooks-guide.md)** — Platform hook development

---

## 🧠 Specialized Systems

- **[Semantic Routing](semantic/)** — AI-powered semantic matching system (Sentence Transformers, embeddings, score fusion)
- **[Trigger System](triggers/)** — Automatic skill invocation system (keywords, regex, semantic triggers)

---

## 📋 Proposals & ADRs

### Architecture Decision Records

- **[adr/README.md](adr/README.md)** — ADR index
- **[ADR 001](adr/001-skill-ecosystem-evolution.md)** — Skill Ecosystem Evolution (v5.x Roadmap)
- **[ADR 002](adr/002-optimization-roadmap-v55.md)** — v5.4 → v5.5 Quality Convergence Roadmap
- **[ADR 003](adr/003-plan-completion-criteria.md)** — Plan Completion Criteria
- **[ADR 004](adr/004-deprecated-types-cleanup.md)** — Deprecated Types Cleanup（3 phases，已落地）

### Proposals

- **[proposals/](proposals/)** — Design proposals for upcoming features
- **[Skill 商店重构与智能建议反馈环](proposals/skill-market-search-and-feedback-loop.md)** — 商店改造（公共生态搜索+信任三级+双作用域安装）、未命中追踪、任务蒸馏、Langfuse 决议（2026-07-18，已评审）

---

## 📂 Archive

- **[archive/README.md](archive/README.md)** — Archive index
- **[archive/](archive/)** — Historical documents, delivery summaries, and superseded plans

---

## 🌐 Community & Articles

- **[Discussion Summary](archive/DISCUSSION_SUMMARY.md)** — Community discussion summaries
- **[Vibe Coding Article](vibe-coding-article.md)** — Article on vibe coding philosophy
- **[Version 0.5 ADR](archive/version_05.md)** — v5.x architecture decision record (detailed)

---

## 📊 Key Metrics (v7.0.0+)

| Metric | Value |
|--------|-------|
| **Version** | 8.1.0 |
| **Tests** | 4,066+ pytest passing |
| **Coverage** | ~73% (target: 75%) |
| **Skills Supported** | 18 builtin + 43 community via packs (mattpocock + superpowers; omx/gstack optional) |
| **Platforms** | Claude Code, Kimi CLI, Pi Agent, OpenCode, Grok Build, Cursor |
| **Cross-Cutting Workflows** | `prompt-chain-validator` (v7.0) |
| **Routing Model** | 4-Stage Cascade |
| **Workflow Patterns** | 6 (SEQUENTIAL, PARALLEL, FAN_OUT, ADVERSARIAL, LOOP_UNTIL_DRY, TOURNAMENT) |
| **Spec Version** | SKILL.md v3.0 (29 fields) |

---

## 📝 Maintenance Guidelines

### Adding New Documentation

1. **Choose the right location** based on audience and purpose
2. **Update this index** to include the new document
3. **Cross-reference** related documents
4. **Follow naming conventions**: UPPERCASE_WITH_UNDERSCORES for key docs

### Document Standards

- **Markdown format** for all documentation
- **Include table of contents** for documents > 500 lines
- **Add "Last Updated" timestamp** for frequently changed docs
- **Use relative paths** for internal links
- **Maintain version consistency** — all docs should reference the current release version

### Review Schedule

- **Monthly**: Review and update quickstart guides
- **Quarterly**: Review and update architecture docs
- **Per Release**: Update project status, roadmap, and this index

---

## 🔗 External Resources

- **GitHub Repository**: [https://github.com/nehcuh/vibesop-py](https://github.com/nehcuh/vibesop-py)
- **Issue Tracker**: [GitHub Issues](https://github.com/nehcuh/vibesop-py/issues)
- **Changelog**: [../CHANGELOG.md](../CHANGELOG.md)

---

*For questions or suggestions about documentation, please open an issue or pull request.*
