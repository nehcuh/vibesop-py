# VibeSOP Documentation Index

> **Last Updated**: 2026-04-28
> **Version**: 5.3.0

This document serves as the central index for all VibeSOP documentation, organized by purpose and audience.

## 📚 Documentation Structure

### Root Directory (Essential Files)

These files remain in the project root for discoverability and tool integration:

- **[README.md](../README.md)** - Main project entry point and overview
- **[README.zh-CN.md](../README.zh-CN.md)** - Chinese language overview
- **[LICENSE](../LICENSE)** - License information
- **[CHANGELOG.md](../CHANGELOG.md)** - Version history and changes

---

## 📖 Core Documentation

### Getting Started

- **🆕 [Skills Ecosystem Guide](SKILLS_GUIDE.md)** - Complete guide to the VibeSOP skills ecosystem
  - 50+ skills explained (builtin, superpowers, gstack, omx)
  - 10-layer routing system详解
  - Priority decision mechanism
  - How to switch between skills
  - Scenario-based selection guide
- **[Quick Start - Users](QUICKSTART_USERS.md)** - User-facing installation and basic usage
- **[Quick Start - Developers](QUICKSTART_DEVELOPERS.md)** - Developer setup and contribution workflow
- **[Cold Start Guide](cold-start-guide.md)** - First-time configuration guide

### Project Overview

- **[Project Context](PROJECT_CONTEXT.md)** - Project background, goals, and scope
- **[Project Status](PROJECT_STATUS.md)** - Current development status and milestones
- **[Philosophy](PHILOSOPHY.md)** - Design principles and core philosophy
- **[Roadmap](ROADMAP.md)** - Future development plans and timeline

### Governance

- **[Code of Conduct](CODE_OF_CONDUCT.md)** - Community guidelines
- **[Security](SECURITY.md)** - Security policy and vulnerability reporting

---

## 🏗️ Architecture & Design

- **[Architecture](architecture/ARCHITECTURE.md)** - System architecture and technical design
  - Component structure
  - Data flow
  - Design patterns

---

## 👥 User Documentation

### Guides & References

- **[CLI Reference](user/CLI_REFERENCE.md)** - Complete command-line interface reference
  - All commands and options
  - Usage examples
  - Best practices

### External Skills

- **🆕 [Skills Ecosystem Guide](SKILLS_GUIDE.md)** - Complete guide to all 50+ skills
  - Builtin, Superpowers, GStack, OMX skills explained
  - 10-layer routing system详解
  - Priority decision mechanism
  - How to switch between skills manually
  - Scenario-based selection guide with decision tree
- **🆕 [Kimi CLI Setup Guide](KIMI_CLI_SETUP.md)** - Complete guide to VibeSOP's Kimi CLI adapter
  - Configuration generation (config.toml, skills/)
  - Provider and model setup
  - Troubleshooting common issues
  - 44 skills deployment
- **[OMX Guide](OMX_GUIDE.md)** - Complete guide to oh-my-codex (OMX) skill pack
  - deep-interview, ralph, ralplan, team, ultrawork, autopilot, ultraqa
  - Usage scenarios and best practices
  - Comparison with other skill packs
- **[External Skills Guide](EXTERNAL_SKILLS_GUIDE.md)** - Creating and integrating custom skills
- **[External Skills Examples](EXTERNAL_SKILLS_EXAMPLES.md)** - Sample implementations

---

## 🔧 Developer Documentation

### Development Workflow

- **[Contributing Guide](dev/CONTRIBUTING.md)** - How to contribute to VibeSOP
  - Development setup
  - Code style
  - Pull request process

### Technical Planning

- **[CLI Optimization Plan](dev/CLI_OPTIMIZATION_PLAN.md)** - Performance improvement initiatives
- **[Production Readiness Review](dev/PRODUCTION_READINESS_REVIEW.md)** - Production readiness assessment

### Deep Dives

- **[Semantic Routing](semantic/)** - AI-powered skill routing system
- **[Triggers](triggers/)** - Automatic skill invocation system

---

## 📂 Directory Structure

```
docs/
├── architecture/          # Architecture and design docs
│   └── ARCHITECTURE.md
├── dev/                   # Developer-facing documentation
│   ├── CONTRIBUTING.md
│   ├── CLI_OPTIMIZATION_PLAN.md
│   └── PRODUCTION_READINESS_REVIEW.md
├── user/                  # User-facing documentation
│   └── CLI_REFERENCE.md
├── semantic/              # Semantic routing system docs
├── triggers/              # Trigger system documentation
├── INDEX.md               # This file
├── QUICKSTART_USERS.md
├── QUICKSTART_DEVELOPERS.md
├── cold-start-guide.md
├── EXTERNAL_SKILLS_GUIDE.md
├── EXTERNAL_SKILLS_EXAMPLES.md
├── PROJECT_CONTEXT.md
├── PROJECT_STATUS.md
├── PHILOSOPHY.md
├── ROADMAP.md
├── CODE_OF_CONDUCT.md
└── SECURITY.md
```

---

## 🎯 Quick Navigation by Role

### For Users

1. Start with [Quick Start - Users](QUICKSTART_USERS.md)
2. Reference [CLI Reference](user/CLI_REFERENCE.md) for commands
3. Explore [External Skills Guide](EXTERNAL_SKILLS_GUIDE.md) for customization

### For Developers

1. Start with [Quick Start - Developers](QUICKSTART_DEVELOPERS.md)
2. Read [Contributing Guide](dev/CONTRIBUTING.md) for workflow
3. Study [Architecture](architecture/ARCHITECTURE.md) for system design
4. Check [Project Status](PROJECT_STATUS.md) for current priorities

### For Contributors

1. Review [Code of Conduct](CODE_OF_CONDUCT.md)
2. Read [Contributing Guide](dev/CONTRIBUTING.md)
3. Check [Roadmap](ROADMAP.md) for planned features
4. Review [Project Context](PROJECT_CONTEXT.md) for background

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

### Review Schedule

- **Monthly**: Review and update quickstart guides
- **Quarterly**: Review and update architecture docs
- **Per Release**: Update project status and roadmap

---

## 🔗 External Resources

- **GitHub Repository**: [https://github.com/nehcuh/vibesop-py](https://github.com/nehcuh/vibesop-py)
- **Issue Tracker**: [GitHub Issues](https://github.com/nehcuh/vibesop-py/issues)
- **Documentation Website**: (Coming soon)

---

*For questions or suggestions about documentation, please open an issue or pull request.*
