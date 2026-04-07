# VibeSOP Architecture

## Overview

VibeSOP is a multi-platform workflow SOP system for AI-assisted development.

## Core Components

```
┌─────────────────────────────────────────────────────────┐
│                        CLI Layer                         │
│  Typer-based commands (30+ commands, grouped)            │
├─────────────────────────────────────────────────────────┤
│                    Business Logic                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Routing  │  │ Workflow │  │ Skills   │              │
│  │ Engine   │  │ Pipeline │  │ Manager  │              │
│  └──────────┘  └──────────┘  └──────────┘              │
├─────────────────────────────────────────────────────────┤
│                   Platform Layer                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Adapters │  │ Builder  │  │ Installer│              │
│  └──────────┘  └──────────┘  └──────────┘              │
├─────────────────────────────────────────────────────────┤
│                   Infrastructure                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Security │  │ Memory   │  │ Checkpoint│             │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
```

## 7-Layer Routing Engine

| Layer | Mechanism | Accuracy | Use Case |
|-------|-----------|----------|----------|
| 0 | LLM Semantic Triage | 95% | Complex, ambiguous queries |
| 1 | Explicit Overrides | 100% | Direct invocation (`/review`) |
| 2 | Scenario Patterns | 80% | Common keywords (debug, test) |
| 3 | Keyword Matching | 75% | Exact token matches |
| 4 | TF-IDF Semantic | 70% | Bilingual similarity |
| 5 | Embedding-Based | 85% | Semantic understanding |
| 6 | Fuzzy Matching | 60% | Typo tolerance |

## Key Design Patterns

- **Adapter**: Platform-agnostic config generation
- **Strategy**: Pluggable routing algorithms and workflow strategies
- **Chain of Responsibility**: 7-layer routing fallback
- **Facade**: ConfigRenderer and SkillManager simplify complex operations
- **Template Method**: Shared utilities with platform-specific rendering

## Data Models

All data models use Pydantic v2 for runtime validation:
- `SkillRoute`: Routing result
- `RoutingRequest`: User query + context
- `SkillDefinition`: Skill metadata
- `WorkflowDefinition`: Workflow structure
- `AppSettings`: Environment configuration
