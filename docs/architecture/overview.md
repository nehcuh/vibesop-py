# VibeSOP Architecture Overview

> **Version**: 4.0.0
> **Last Updated**: 2026-04-06

## System Purpose

VibeSOP is a **Skill Operating System (SkillOS)** for AI-assisted development. It manages the full lifecycle of skills — discovering, routing, orchestrating, and evaluating — without executing skill code itself.

**Key Principle**: Discovery > Execution. VibeSOP manages, AI Agents execute.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                               │
│  vibe route / vibe skills / vibe install / vibe analyze        │
├─────────────────────────────────────────────────────────────────┤
│                      Routing Engine                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐   │
│  │ UnifiedRouter   │  │ Layer Pipeline  │  │ Optimization │   │
│  │ (Single Entry)  │  │ (10-Layer Match)│  │ (Pref/Learn) │   │
│  └─────────────────┘  └─────────────────┘  └──────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                    Core Services                                │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────────┐    │
│  │ SkillLoader  │  │ ConfigManager │  │ SecurityScanner │    │
│  │ (Discovery)  │  │ (Multi-Source)│  │ (Skill Audit)   │    │
│  └──────────────┘  └───────────────┘  └─────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│                    Integration Layer                            │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────────┐    │
│  │ SmartInstall │  │ HealthMonitor │  │ AdapterFactory  │    │
│  │ (Auto-Setup) │  │ (Status Check)│  │ (Platform Out)  │    │
│  └──────────────┘  └───────────────┘  └─────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│                      Storage Layer                               │
│  SKILL.md Files │ YAML Registry │ Preference DB │ Cache       │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. UnifiedRouter
**Purpose**: Single entry point for all routing operations

**Responsibilities**:
- Coordinate 10-layer matching pipeline
- Apply preference learning
- Return routing results with confidence scores

**Performance**: P95 < 1ms (with candidate cache)

### 2. Matching Infrastructure
**Purpose**: Provide multiple matching strategies

**Layers** (tried in priority order):
1. **AI Triage** (optional): LLM-based semantic classification
2. **Explicit Override**: `/skill` or `use skill` patterns
3. **Scenario Patterns**: Predefined situation mappings
4. **Keyword/TF-IDF**: Fast lexical and semantic matching
5. **Fuzzy Fallback**: Levenshtein distance for typos

### 3. Skill Management
**Purpose**: Discover, load, and manage skills

**Key Classes**:
- `SkillLoader`: Discover skills from filesystem
- `SkillManager`: High-level API for skill operations
- `SkillStorage`: Centralized skill storage with symlinks

### 4. Configuration System
**Purpose**: Multi-source configuration with clear priority

**Priority Order**:
1. CLI flags (highest)
2. Project config (`.vibe/config.yaml`)
3. User config (`~/.config/vibe/config.yaml`)
4. Defaults (lowest)

### 5. Integration Layer
**Purpose**: Bridge VibeSOP with external tools

**Components**:
- **SmartInstaller**: Auto-analyze and install skill packages
- **HealthMonitor**: Check skill package status
- **Adapter Factory**: Generate platform-specific configs

## Data Flow

```
User Query
    │
    ▼
┌─────────────┐
│ CLI Command │ (vibe route "debug this")
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│   UnifiedRouter     │
├─────────────────────┤
│ 1. Load Candidates  │ ← Cached after first call
│ 2. Try Layer 0      │ ← Explicit override
│ 3. Try Layer 1      │ ← Scenario patterns
│ 4. Try Layer 2      │ ← AI Triage (optional)
│ 5. Try Layer 3      │ ← Keyword/TF-IDF
│ 6. Try Layer 4      │ ← Fuzzy fallback
│ 7. Apply Boost      │ ← Preference learning
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  RoutingResult      │
│  - primary          │ ← Best match
│  - alternatives     │ ← Other options
│  - confidence       │ ← 0.0-1.0
│  - routing_path     │ ← Layers tried
└──────┬──────────────┘
       │
       ▼
    User / AI Agent
```

## Design Principles

1. **Single Responsibility**: Each component has one clear purpose
2. **Dependency Inversion**: High-level modules don't depend on low-level details
3. **Open/Closed**: Open for extension (new skills), closed for modification
4. **Interface Segregation**: Small, focused interfaces

## Performance Characteristics

| Operation | Latency (P95) | Throughput |
|-----------|---------------|------------|
| Route query | <1ms | >1000 QPS |
| Discover skills | ~50ms | ~20 QPS |
| Install skill package | ~500ms | ~2 QPS |
| Generate config | ~10ms | ~100 QPS |

## Security Model

1. **Path Safety**: All paths validated against traversal attacks
2. **Skill Auditing**: External skills scanned before loading
3. **Sandboxed Execution**: Skills run in AI Agent, not VibeSOP
4. **No Network**: Core routing doesn't require external calls

## Extension Points

1. **Custom Matchers**: Implement `IMatcher` interface
2. **Skill Packages**: Drop-in SKILL.md files
3. **Platform Adapters**: Implement adapter protocol
4. **Preference Learning**: Custom weight functions

---

*For detailed diagrams, see [three-layers.md](three-layers.md)*
*For routing details, see [routing-system.md](routing-system.md)*
