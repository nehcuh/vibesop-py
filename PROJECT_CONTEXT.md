# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-06-05 (S14) v6.2-doc-sync-and-workflow-documentation
**Session**: Version bump + comprehensive documentation sync + Workflow Engine docs
**Completed**:
- Bumped pyproject.toml 5.5.0 → 6.2.0 (CLI now reports VibeSOP v6.2.0)
- Batch updated 20+ docs: version 5.5.0 → 6.2.0, dates to 2026-06-05
- Added Dynamic Workflow Engine section to ARCHITECTURE.md (architecture diagram, 6 patterns, components table, CLI flags, platform compatibility matrix)
- Updated README.md integrations (4 platforms) + Workflow section with pattern table + platform matrix
- Added CHANGELOG.md entries for v6.0.0, v6.1.0, v6.2.0
- Fixed ROADMAP.md: v6.0.0 marked COMPLETED, release dates corrected
- Updated INDEX.md: Workflow Engine entry, platform list, metrics
- Updated 5 adapter templates/sources with Workflow Patterns (routing-protocol.md.j2 × 2, vibe-orchestrate.md.j2, kimi_cli.py, opencode.py)
- Fixed 2 pre-existing test bugs (hook template assertions, _Skill.get() AttributeError)
**Key Insight**: Claude Code has native sub-agent parallelism; other platforms execute workflow steps serially
**Commit**: b6daa4d docs(v6.2): bump version + Workflow docs + test fixes (29 files)
**Branch**: refactor/router-orchestrator-split
**Next**: Create PR to main, verify all docs render correctly

### 2026-06-05 (S13) v6.x-dynamic-workflow-engine-complete
**Session**: Full Dynamic Workflow Engine v6.0-v6.2 implemented, reviewed, and fixed
**Completed**: ClassifierAgent, VerifierAgent, VerificationLoop, WorkflowEngine, Reorchestrator, TournamentRunner

<!-- handoff:end -->
