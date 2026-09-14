# VibeSOP Architecture Guide

> Refreshed 2026-09-14. This page is the navigation entry for current architecture.

VibeSOP combines skill management, workflow planning and delivery checks, execution observability, experience retrieval, recurring tasks and a separate empirical research workspace. SkillOS is the skill subsystem, not the whole project.

## Reading path

1. [Current module map and execution boundaries](../dev/architecture-overview.md).
2. [Routing system](routing-system.md): stages, matchers and no-match behavior.
3. [Verification and plan delivery](verification-contract.md): availability, blocked plans and evidence requirements.
4. [Agent integration](../agent-integration.md): hooks, generated configuration and in-process integration.
5. [Machine acceptance evidence](acceptance-evidence.md): commands, logs, exit codes and fingerprints.
6. [Skill format](../skill-format-spec-v3.md): independently versioned protocol.

[Project positioning](../POSITIONING.md) describes the product/research boundary; [project status](../PROJECT_STATUS.md) distinguishes current source from public releases. [ARCHITECTURE.md](ARCHITECTURE.md) retains detailed and historical subsystem descriptions.
