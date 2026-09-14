# Architecture Overview

> Refreshed 2026-09-14 for the current source tree. Package and publication status: [PROJECT_STATUS.md](../PROJECT_STATUS.md).

## Scope

VibeSOP provides workflow tools for AI-assisted development and a repository for empirical research. SkillOS names the skill-management part of that system. The source repository also uses its own tooling for development and experiments; there is no rule that its own skills must remain uninstalled.

The package and the research workspace have different boundaries: `src/vibesop/` and bundled `core/` resources provide the installable tooling; experiment branches, raw runs and research protocols are not automatically included in a wheel.

## Main components

| Component | Responsibility | Source |
|---|---|---|
| CLI | Routing, plans, skills, traces, recall, recurring tasks and diagnostics | [cli/](../../src/vibesop/cli/) |
| Skill management | Discovery, installation, scopes, metadata, lifecycle | [core/skills/](../../src/vibesop/core/skills/), [installer/](../../src/vibesop/installer/) |
| Routing | Explicit selection, scenario/semantic selection, LLM triage and matching; no-match is a valid outcome | [core/routing/](../../src/vibesop/core/routing/) |
| Plans and verification | Dependencies, state, events, availability annotation and delivery contracts | [core/orchestration/](../../src/vibesop/core/orchestration/) |
| Agent integration | Intent interception, context injection, presentation and execution guidance | [agent/runtime/](../../src/vibesop/agent/runtime/) |
| Platform configuration | Agent-specific files, hooks, plugins and templates | [adapters/](../../src/vibesop/adapters/), [builder/](../../src/vibesop/builder/) |
| Observability and memory | Trace storage, replay, clustering, recall and feedback | [core/observability/](../../src/vibesop/core/observability/), [core/instinct/](../../src/vibesop/core/instinct/) |
| Recurring tasks | Specifications, scheduling, execution and persisted run state | [core/loop/](../../src/vibesop/core/loop/) |
| Research | Protocols, reports and versioned evidence outside the package boundary | [research/](../research/README.md), [experiments/](../experiments/README.md) |

## Routing and execution are separate decisions

Routing uses a four-stage cascade with query-dependent branches and multiple matchers. Historical “ten-layer” diagrams count internal handlers and fallback cases differently; use the [routing guide](../architecture/routing-system.md) and current code for behavior.

A match does not imply a deliverable plan. Availability and content checks annotate or reject plans; consumers must respect `execution_ready` and the [verification contract](../architecture/verification-contract.md).

On the hook path, the host agent executes after receiving context. Explicit runtime, loop and validation paths can run configured work themselves. A generated adapter does not establish that every host's tool execution, authorization or completion detection is identical.

## Development and integration

- Install a skill pack with `vibe install <pack>`; generate agent configuration with `vibe build <platform> --output <directory>`.
- Use `vibe route --verbose` for routing diagnostics; `--validate` checks routing configuration.
- Inspect the [Agent Integration Guide](../agent-integration.md) for in-process LLM injection and platform contracts.
- Read [positioning](../POSITIONING.md) and [project status](../PROJECT_STATUS.md) before describing implementation details as shipped capabilities or proven research outcomes.

Skill format and conformance remain independently versioned: [SKILL.md v3.0](../skill-format-spec-v3.md). Historical implementation detail remains in [ARCHITECTURE.md](../architecture/ARCHITECTURE.md).
