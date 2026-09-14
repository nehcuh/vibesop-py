# Task independence and difficulty review (pre-freeze)

This is a **controlled small-CLI benchmark**: requirement → workspace files → isolated Docker CLI. It is **not** evidence about whole-repository multi-file engineering. READY_FOR_REVIEW must keep that scope. Each task is not a data permutation of another, and none is a clone of the three historical calibration tasks.

## Distribution

| Category | Tasks | What is independently tested |
|---|---|---|
| Routing (local rules) | route-lifecycle-v1, route-nomatch-contract-v1, route-priority-table-v1, route-plan-dag-v1 | State machine; three-way no-match/fallback/blocked; dynamic priority table; serial/parallel DAG planning |
| Config / cross-layer | config-render-resolve-v1, config-adapter-vs-entry-v1, config-home-isolation-v1, config-param-passthrough-v1 | Manifest path recording vs guessed layout; **two process entries sharing a binding map**; HOME isolation with persistence across containers; typed param round-trip |
| Quant / splittable | match-vwap-window-v1, match-lot-calendar-v1, etl-join-aggregate-v1, window-dedup-late-v1 | Real volume-weighted VWAP lookback; trading-calendar next session; inner join + aggregate; watermark/dedup/late |

Historical calibration (intent / config-path / next-bar) remains read-only and is **not** in this twelve.

## Why they are not permutations

- Lifecycle vs no-match vs priority vs DAG: different input schemas and decision procedures (state, catalog/blocked, dynamic table, text segmentation).
- Render/resolve vs adapter/entry vs home vs params: different stores (manifest vs bindings.json vs $VIBE_HOME vs hooks/*.json) and different failure taxonomies.
- VWAP vs calendar vs ETL vs stream: lookback volume weighting vs calendar sessions vs join/group vs event-time watermark. VWAP is not an arithmetic mean of closes.

## Coupling vs small controls

- **Meaningful coupling:** T6 bind from `adapter.py` must be visible to a later `app.py` lookup in a fresh process (and the reverse). Hidden tests seed a non-guessable mapped path. T5 resolve must read the recorded dest, not `skills/<id>/SKILL.md`. T7 state lives in VIBE_HOME across separate containers, not cwd.
- **Splittable + integration:** T11 join vs aggregate; T12 dedup vs watermark; T9 window vs order loop; T10 calendar vs fill records. E workers get disjoint file lists; overlapping files are a pre-registered run failure (`ownership_conflict`), not a footnote on a passing score.
- **Small control preserved inside T6:** `ping` only checks the via marker. Informal calibration tasks (`cal-harness-*`) are additional tiny harness controls and are excluded from the 360.

## Difficulty (qualitative, pre-results)

Easier: T6 ping, T1 defaults, T7 init. Medium: T2/T3/T5/T8. Harder: T4 unresolved/DAG, T9 rounding+volume, T10 calendar, T12 late-vs-dup order. Difficulty is mixed on purpose; independence matters more than equal hardness.

## Spec variants

Full spec contains the complete contract. Brief omits some operational details. Every arm may call `ask_clarification` with id `contract` to retrieve the **entire** full spec (metered). Spec-variant comparison therefore measures retrieval/clarification behavior and overhead as well as initial completeness. Hidden tests are identical. No hidden preference is scored unless it is in the full spec / Q&A.

## T4 dependency order (frozen)

`depends_on` for group k is the list of skills of group k-1 **in emission order** (left-to-right as those steps were appended from the source segment). It is not lexicographically sorted. Hidden case `mixed` expects `depends_on: ["build", "lint"]`.
