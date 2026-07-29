# W3 Implementation Review — Merged Findings

**Reviewers**: grok + pi (parallel)
**Date**: 2026-07-29
**Brief**: `docs/decisions/_review-w3-implementation-brief.md`

## Reviewer split

| Aspect | grok | pi |
|--------|------|----|
| Severity calibration | Harsh — 3 P0, 5 P1, 4 P2 | Moderate — 2 P0, 4 P1, 2 P2 |
| Gold gate unit | **P0: span_count ≠ evidence** | P2: too strict |
| Auto-prompt default | P0: missing TTY gating | P1: add config setting |
| `workflow_node` kind | P1: overloads orchestration | Acceptable |
| OTel Link | (not mentioned) | P0: missing |
| Real InstinctLearner test | P1 missing | P1 missing |
| Silent exception | P1: bare except hides bugs | Acceptable |

Both converge on: **real InstinctLearner integration test missing** (high confidence), **per-route I/O cost** (P1), **gold precision unmeasured** (P1/P2).

## Consolidated P0 (must fix)

### P0-1: Gold size unit is wrong — counts nested spans, not distinct runs

**Source**: grok P0-3
**Files**: `src/vibesop/core/observability/recall.py:184` (`is_gold = task_info["count"] >= min_gold_span_count`)

`task_info["count"]` = total spans for task_id, including nested `llm:*` and `tool:*` children. The fixture proves the bug: cmspark has 7 spans but only **3 distinct traces**. A single chatty route with 5+ child spans meets the gold gate after one success.

**Fix**: Replace span count with **distinct trace_id count**.
- Primary gate: `distinct_trace_id_count >= 3` (3 separate executions)
- Fallback when no trace_ids in spans: `span_count >= 5` (legacy compatibility)
- Keep `success_count >= 1`

### P0-2: Auto-prompt missing TTY / non-interactive gating

**Source**: grok P0-2
**Files**: `src/vibesop/cli/main.py:_maybe_prompt_replay`

Currently `_maybe_prompt_replay` runs whenever `not no_replay and not json_output and not minimal`. In non-interactive contexts (subprocess, CI, scripts), `typer.confirm` reads from empty stdin → either errors or hangs.

**Fix**: Add `sys.stdin.isatty()` check. Skip prompt when not a TTY.

### P0-3: Panel says "Replay" / "same skill" but Y does no skill reuse

**Source**: grok P0-1
**Files**: `src/vibesop/cli/main.py:_maybe_prompt_replay` (Rich panel copy)

Panel currently shows "Last skill: X" + "Steps: ..." then asks `Replay? [Y/n]`. User expects Y → skill reused. Actual behavior: Y → emit replay span + print step list + continue normal routing. This is the D2 scope decision but the panel doesn't communicate it.

**Fix**: Reword panel to be honest about what Y does. Either:
- (a) Rename "Replay" to "Mark as gold match?" (provenance only), or
- (b) Keep "Replay" verb but add explicit "Will: emit provenance span + show prior steps. Routing continues normally."

Going with (b) to preserve user vocabulary while being honest.

## Consolidated P1 (should fix)

### P1-1: `should_replay` matrix incomplete — top_k=1 only

**Source**: grok P1-1
**Files**: `src/vibesop/core/observability/replay.py:109-117`

If rank-1 is non-gold near-miss and rank-2 is gold, user never sees a prompt. Should scan top-k for first gold match.

**Fix**: Change `top_k=1` to `top_k=3` in the internal recall call; iterate to find first gold; if none gold, return top match with `reason="not_gold"`.

### P1-2: Bare `except Exception` swallows real bugs

**Source**: grok P1-5
**Files**: `src/vibesop/cli/main.py:1915-1920` (learner construction)

Bare `except Exception: return` silently kills replay forever if `.vibe/instincts.jsonl` has a permission error or corrupt line.

**Fix**: `except Exception as exc: logger.warning("replay learner unavailable: %s", exc); return`. Already done at the outer try/except; need same treatment at the inner learner construct.

### P1-3: Real InstinctLearner integration test missing

**Source**: grok P1 + pi P1-5 (independent convergence)
**Files**: `tests/core/observability/test_recall.py`

All tests use MagicMock for learner. Real `InstinctLearner` normalization (representative_query → instinct_id) drift could break production path silently.

**Fix**: Add integration test that writes real instincts.jsonl to tmp_path, loads real `InstinctLearner(storage_path=...)`, calls `recall_similar(learner=learner)`.

### P1-4: Y-path CLI test missing

**Source**: grok P1-4 (test gap)
**Files**: `tests/cli/test_route_replay_cli.py`

Module docstring claims "Y confirm emits replay span + prints step_sequence" but no test exercises this. Currently only `input="n\n"` paths are tested.

**Fix**: Add test with `input="y\n"` that asserts replay span is written to span file.

### P1-5: Non-TTY CLI test missing

**Source**: grok P1-4
**Files**: `tests/cli/test_route_replay_cli.py`

No test verifies that non-TTY context skips prompt. After P0-2 fix, this becomes a contract.

**Fix**: Add test that monkeypatches `sys.stdin.isatty()` to False and asserts no prompt.

## Consolidated P2 (defer with comment)

### P2-1: `default=True` on confirm risky given weak gold

**Source**: grok P2-1 + pi concern

Until gold precision is measured, default Y could inflate false replay metrics. **Defer** — fix in W4 once telemetry exists.

### P2-2: Hot-path I/O — full file scan per route

**Source**: grok P2-2 + pi P1-4

`SpanWriter.query_recent(limit=500)` reads entire spans.jsonl, then `[-500:]`. With `InstinctLearner()` also reading full file. Becomes slow at 10k+ spans.

**Defer** to post-MVP. Add index by task_id later.

### P2-3: Permanent disable config

**Source**: pi P1-3

`vibe config set replay.enabled false` would let users permanently opt out. Reasonable product decision but config schema not yet defined.

**Defer** to W4 or post-MVP when config schema lands.

### P2-4: `workflow_node` kind overloads orchestration semantics

**Source**: grok P1-3

Grok prefers dedicated `kind="replay"` or `metadata.event_type="replay"`. Pi was OK with `workflow_node`. Adding new SpanKind is cheap (Literal update) but requires updating all match/case sites.

**Defer** — current `name.startswith("replay:")` + metadata works for MVP. Revisit when dashboard aggregation complains.

## Out of scope (rejected)

### OTel Span Link (pi P0-2)

Pi wants proper distributed tracing `Link` to prior trace. VibeSOP uses custom `SpanWriter` JSONL storage, not OTel SDK. The `metadata.replay_of` field is the equivalent provenance link in our model. Adding OTel SDK just for this would be architectural overreach.

**Verdict**: Won't fix. `metadata.replay_of` is sufficient for our dashboard.

### Below-threshold reason code (pi P0-1)

Pi wants `reason="below_threshold"` distinct from `reason="no_recall"`. The brief's matrix treats both as "no match above threshold" which is semantically correct. Splitting them adds telemetry surface area without actionable signal.

**Verdict**: Won't fix. Single `no_recall` reason is fine.

## Implementation plan (P0 + P1)

| # | Task | Estimate |
|---|------|----------|
| Fix-1 | P0-1: Replace span_count with distinct_trace_id_count in recall.py grouping | 30 min |
| Fix-2 | P0-2: Add `sys.stdin.isatty()` check in `_maybe_prompt_replay` | 10 min |
| Fix-3 | P0-3: Reword Rich panel to be honest about Y behavior | 15 min |
| Fix-4 | P1-1: should_replay scans top-3 for first gold | 20 min |
| Fix-5 | P1-2: Replace bare except with logger.warning | 5 min |
| Fix-6 | P1-3: Add real InstinctLearner integration test | 30 min |
| Fix-7 | P1-4: Add Y-path CLI test | 20 min |
| Fix-8 | P1-5: Add non-TTY CLI test | 15 min |
| Fix-9 | Update fixture: bump cmspark to 5 distinct traces | 10 min |
| Fix-10 | Re-run full W3 regression + 5-iteration flake check | 15 min |

Total: ~2.5 hours. Then commit W3 and proceed to W4 (Skill Promote).
