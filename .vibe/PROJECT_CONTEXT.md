# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-04-28 — VibeSOP v5.2.0 Full Delivery

**Summary**: Completed the v5.x roadmap (scope, toggle, evaluation, market, recommendation, degradation). Bumped version from 4.4.0 to 5.2.0. All 6 core problems from version_05.md closed.

**Key deliveries**:
- `DegradationManager`: 4-level confidence-gated fallback (AUTO/SUGGEST/DEGRADE/FALLBACK)
- `SkillRecommender`: per-skill pattern-based recommendation + proactive discovery
- Market publish: GitHub Issues-based `vibe market publish`
- `auto_deprecate` now defaults to `True` (autonomous lifecycle)
- `orchestrate()` as default CLI entry (not `route()`)
- OMX skills moved to external pack (like gstack/superpowers)
- `keyword_match_max_chars=5`: short queries use keyword routing, long queries use LLM

**Architecture decisions**:
- GitHub Issues as lightweight registry for skill market (no extra infra)
- Confidence thresholds configurable via `.vibe/config.yaml`
- Degradation skips EXPLICIT and CUSTOM layers (user-specified skills)

**Next steps**:
- Run `vibe build` to regenerate CLAUDE.md with fresh adapter templates
- Test `vibe market publish` with GITHUB_TOKEN set
- Consider community ratings aggregation for market listings
<!-- handoff:end -->
