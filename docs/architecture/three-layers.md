# Three-Layer Architecture

> **Version**: 4.0.0
> **Last Updated**: 2026-04-06

## Overview

VibeSOP is organized into three distinct layers, each with clear responsibilities and boundaries.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Presentation Layer                       │
│  (CLI, User Interface, Output Formatting)                      │
├─────────────────────────────────────────────────────────────────┤
│                        Application Layer                        │
│  (Routing Logic, Skill Management, Configuration)              │
├─────────────────────────────────────────────────────────────────┤
│                        Infrastructure Layer                     │
│  (File I/O, Caching, Security, Storage)                        │
└─────────────────────────────────────────────────────────────────┘
```

## Layer 1: Presentation Layer

**Purpose**: User interaction and output formatting

**Components**:
```
vibesop/cli/
├── main.py                 # CLI entry point
├── interactive.py          # Interactive mode
└── commands/
    ├── route_commands.py   # Routing commands
    ├── skills_cmd.py       # Skill management
    ├── install.py          # Installation
    └── ...
```

**Responsibilities**:
- Parse command-line arguments
- Display results to user
- Handle interactive input
- Format output (JSON, tables, panels)

**Dependencies**: Only depends on Application Layer

**Should NOT**:
- Contain business logic
- Access filesystem directly
- Implement routing algorithms

## Layer 2: Application Layer

**Purpose**: Core business logic and domain operations

**Components**:
```
vibesop/core/
├── routing/
│   ├── unified.py         # UnifiedRouter
│   └── ...                # Routing pipeline
├── matching/
│   ├── base.py            # IMatcher interface
│   └── ...                # Matcher implementations
├── skills/
│   ├── loader.py          # SkillLoader
│   ├── manager.py         # SkillManager
│   └── ...
├── config/
│   └── manager.py         # ConfigManager
└── algorithms/
    └── ...                # Reusable algorithms
```

**Responsibilities**:
- Route queries to skills
- Manage skill lifecycle
- Apply preference learning
- Coordinate between components

**Dependencies**:
- Can use Infrastructure Layer
- Can use other Application Layer modules
- MUST NOT depend on Presentation Layer

**Should NOT**:
- Format output for display
- Handle user input
- Know about CLI flags

## Layer 3: Infrastructure Layer

**Purpose**: Low-level services and cross-cutting concerns

**Components**:
```
vibesop/
├── security/              # Security scanning
│   ├── scanner.py
│   └── skill_auditor.py
├── utils/                 # Utility functions
│   ├── atomic_writer.py
│   └── helpers.py
└── llm/                   # LLM integration
    └── factory.py
```

**Responsibilities**:
- File I/O operations
- Security scanning
- Caching
- LLM communication
- Path validation

**Dependencies**:
- No dependencies on upper layers
- Can use standard library and external packages

## Layer Boundaries

### Allowed Communication

```
Presentation ──► Application ──► Infrastructure
     ▲                ▲               ▲
     └────────────────┴───────────────┘
           (lower layers only)
```

### Examples

**✅ Correct**:
- CLI calls `UnifiedRouter.route()` (Presentation → Application)
- `UnifiedRouter` uses `SkillLoader` (Application → Infrastructure)
- `ConfigManager` uses `atomic_writer` (Application → Infrastructure)

**❌ Incorrect**:
- `UnifiedRouter` formats table output (Application → Presentation)
- CLI directly parses SKILL.md files (Presentation → Infrastructure)
- `SkillLoader` knows about CLI flags (Infrastructure → Presentation)

## Benefits

1. **Testability**: Each layer can be tested in isolation
2. **Maintainability**: Changes in one layer don't cascade
3. **Reusability**: Infrastructure can be used by different applications
4. **Clarity**: Clear separation of concerns

## Module Placement Guide

| Feature | Layer | Location |
|---------|-------|----------|
| Routing algorithm | Application | `core/routing/` |
| CLI command | Presentation | `cli/commands/` |
| File writing | Infrastructure | `utils/atomic_writer.py` |
| Security check | Infrastructure | `security/` |
| Output formatting | Presentation | `cli/` (rich panels) |
| Skill discovery | Application | `core/skills/loader.py` |

## Dependency Rules

1. **Upper layers can depend on lower layers**
2. **Lower layers MUST NOT depend on upper layers**
3. **Modules within the same layer should minimize dependencies**
4. **Shared utilities go in Infrastructure Layer**

---

*For system overview, see [overview.md](overview.md)*
*For routing details, see [routing-system.md](routing-system.md)*
