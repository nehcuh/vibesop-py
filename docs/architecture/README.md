# VibeSOP Architecture Documentation

> **Version**: 4.0.0
> **Last Updated**: 2026-04-06

This directory contains comprehensive architecture documentation for VibeSOP.

## Documents

### [overview.md](overview.md)
**Start Here** - High-level system architecture

- System purpose and design principles
- Key components and their interactions
- Data flow diagrams
- Performance characteristics
- Extension points

### [three-layers.md](three-layers.md)
**Architecture** - Three-layer architectural pattern

- Presentation Layer (CLI)
- Application Layer (Core Logic)
- Infrastructure Layer (Utilities)
- Layer boundaries and communication rules
- Module placement guide

### [routing-system.md](routing-system.md)
**Core Component** - Routing system deep dive

- UnifiedRouter interface
- 7-layer routing pipeline
- Layer-by-layer breakdown
- Performance optimization
- Caching strategies
- Extending the router

### [external-integrations.md](external-integrations.md)
**Integration** - External tool and skill package integration

- Platform adapters (Claude Code, OpenCode)
- Skill package installation flow
- Health monitoring
- Platform-specific features

## Quick Navigation

**By Topic**:
- Want to understand the system? → [overview.md](overview.md)
- Implementing a feature? → [three-layers.md](three-layers.md)
- Debugging routing? → [routing-system.md](routing-system.md)
- Adding integration? → [external-integrations.md](external-integrations.md)

**By Role**:
- **Contributors**: Start with [three-layers.md](three-layers.md)
- **Users**: Read [overview.md](overview.md)
- **Architects**: Review all documents

## Architecture Diagrams

### High-Level View

```
┌─────────────────┐
│  CLI Commands   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  UnifiedRouter  │ ← 7-Layer Pipeline
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Skill Match    │
└─────────────────┘
```

### Detailed View

See [overview.md](overview.md) for complete diagrams.

## Design Principles

1. **Discovery > Execution**: VibeSOP routes, doesn't execute
2. **Single Responsibility**: Each component has one clear purpose
3. **Dependency Inversion**: High-level modules don't depend on low-level details
4. **Open/Closed**: Open for extension (new skills), closed for modification

## Performance Targets

| Operation | Target | Actual |
|-----------|--------|--------|
| Route query | <50ms | <1ms |
| Discover skills | <100ms | ~50ms |
| Install package | <1s | ~500ms |

## Contributing

When making architectural changes:

1. Update relevant documentation
2. Add diagrams for new components
3. Update performance characteristics
4. Review layer boundaries

---

*For project positioning, see [../POSITIONING.md](../POSITIONING.md)*
*For core principles, see [../PRINCIPLES.md](../PRINCIPLES.md)*
