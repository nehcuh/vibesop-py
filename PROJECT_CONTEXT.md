# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-05-24 00:40
**Session**: Deep review + GOALS.md alignment fixes + gstack removal + engineering charter integration + slash-orchestrate routing bug fix

**Completed**:
- Comprehensive multi-dimensional review (philosophy, architecture, design, code quality) against GOALS.md
- Fixed `feedback_loop.py` vs `retention.py` threshold inconsistency (duplicate RetentionSuggestion models with conflicting rules)
- Registered `vibe skill` (singular) CLI command group alongside existing `vibe skills` (plural)
- Integrated META v2.0 charter into `rules/behaviors.md` + `behaviors.md.j2` template (6 rules selected, Zero-Pause layer rejected)
- Removed gstack from TRUSTED_PACKS, all recommenders, cold start, featured registry, namespace priorities, quickstart, onboard — 11 source + 5 test files
- Fixed `slash-orchestrate` leaking into sub-task routing via `_MANAGEMENT_SKILL_IDS` blacklist in PlanBuilder
- Updated docs: cold-start-guide.md, install.py help/docstrings, adapter templates, slash_commands

**Key Learnings**:
- Duplicate data models across files can silently diverge — grep for class names
- Management/meta skills need explicit exclusion from domain routing (keyword matching can't distinguish "tools that manage the system" from "skills that do the work")
- META charter integration: selective adoption (6/11 rules) better than wholesale replacement for VibeSOP's route-confirm-orchestrate model

**Files Modified**: 55 files, +913/-387 lines

---

### 2026-05-23 (S2)
**Session**: Fix incomplete URL parse fix — second clone in PackInstaller still used raw web URL
**Next Steps**: Can now use `vibe install <url-with-subdir> --platform <target>`
<!-- handoff:end -->
