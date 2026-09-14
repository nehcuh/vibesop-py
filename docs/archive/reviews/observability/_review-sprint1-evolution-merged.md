# Sprint 1 Go/No-Go — Pi Review Merged

**Date:** 2026-07-31  
**Reviewer:** pi (`pi -p`)  
**Verdict:** **CONDITIONAL → GO after absorbing must-fix into Sprint 1**

Full pi report: [`_review-sprint1-evolution-pi.md`](_review-sprint1-evolution-pi.md)

## Must-fix absorbed (become Sprint 1 scope, not blockers)

| ID | Fix | Implementation choice |
|----|-----|------------------------|
| FIX-1 | Replay Y injects prior skill | `_maybe_prompt_replay` returns skill_id; set `RoutingContext.current_skill` + habit_boost; learn+outcome |
| FIX-2 | Route hot-path outcome signal | **Do not** auto-success every hit (Wilson poison). Low-conf/no-match → pending; accept/dismiss → `record_outcome` |
| FIX-3 | Low-conf produces pending | `RoutingPendingStore` (separate from `SkillSuggestionCollector` — H1) |
| FIX-4 | Don't pretend feedback-collect = interactive accept | New CLI: `vibe instinct pending/accept/dismiss` |

## Extra pi guidance absorbed

- Kill addendum: if 14d outcome density = 0 → stop expanding analyzer, fix signal first  
- H1: routing pending ≠ skill-sequence suggestions  
- Replay stats: optional counter on emit  

## GO criteria for this session

Ship: store + enqueue + CLI + replay inject + unit tests. Real 14d kill is post-ship observation.
