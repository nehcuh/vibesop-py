# Pi Review Brief — Product Evolution Final + Sprint 1 Go/No-Go

**Date:** 2026-07-31  
**Reviewer target:** pi (`pi -p`, may use read tools)  
**Docs:**
- `docs/decisions/2026-07-31-product-evolution-adversarial.md` (**Binding** evolution)
- `docs/decisions/2026-07-31-positioning-vs-llm-space.md` (positioning; execution order superseded)

**Code areas to spot-check for Sprint 1 feasibility:**
- `src/vibesop/core/instinct/learner.py` — `record_outcome`, `record_outcome_for_query`
- `src/vibesop/core/observability/replay.py` + `src/vibesop/cli/main.py` `_maybe_prompt_replay`
- `src/vibesop/cli/commands/skills_commands/_discovery.py` — suggestions pending/dismiss
- `src/vibesop/cli/commands/loop_cmd.py` — instinct presets
- `src/vibesop/core/skills/` feedback / suggestion collectors if present

---

## What to review

You are **pi**, external adversarial reviewer (UX + product + implementation realism).

### Part A — Evolution final (strategy)

Verdict on `2026-07-31-product-evolution-adversarial.md`:

1. Is the **aha north star** correct for solo-dev persona?
2. Is demoting meta-auditor (route-auditor as default) and elevating **correction write-back + replay** sound?
3. Any **internal contradiction** with shipped code reality (memory ~shipped, METRIC unwired)?
4. Any **P0 blocker** that should stop Sprint 1 entirely?
5. Missing kill criteria or safety gate?

### Part B — Sprint 1 Go/No-Go (implementation)

Sprint 1 scope (from evolution final §3 Sprint 1):

| # | Deliverable | Kill if |
|---|-------------|---------|
| 1.1 | Pending human-readable suggestions (CLI): low-confidence route / correction / high-freq miss → ≤3/day Chinese | |
| 1.2 | accept / dismiss → write-back affects next route | |
| 1.3 | Replay hot-path usable (prompt after route) | |
| 1.4 | outcome density clear (`record_outcome` when written) | |
| Kill | 14 days real use: 0 accept/dismiss AND 0 replay Y → stop expanding analyzer | |

**Questions:**

B1. What **already exists** vs must be built for 1.1–1.4?  
B2. Dangerous reuse mistakes (e.g. conflating skill-suggestions with routing instincts)?  
B3. Minimal file-level implementation plan (≤8 steps) if GO.  
B4. Verdict: **SHIP SPRINT 1** | **CONDITIONAL** (list mandatory fixes) | **BLOCK**.

---

## Output format (strict)

```markdown
# Pi Review: Product Evolution + Sprint 1

## Verdict: SHIP SPRINT 1 | CONDITIONAL | BLOCK

## Part A — Strategy findings
### A1 … (P0/P1/P2)
…

## Part B — Sprint 1 findings  
### B1 Existing vs gap
### B2 Hazards
### B3 Minimal plan (if GO/CONDITIONAL)
### B4 Acceptance tests (executable)

## Must-fix before code (if any)
- [ ] …

## Explicit non-blockers (things NOT required for Sprint 1)
- …
```

Be ruthless, evidence-oriented, cite file paths when claiming code state. Chinese OK for findings; keep Verdict line in English enum above.
