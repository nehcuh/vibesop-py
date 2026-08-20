# Gate 13 Review — M10 (pack arbitration + suite hermeticization)

All verification executed live on the working tree: extended eval re-run (81/107, confusion-pair count = 26 errors, git-master positive retained), base 31/34, oneshot 10/11, touched files 150 passed in 0.34s, tests/core+tests/unit 3227 passed in 40s, ruff clean on all 9 changed files.

```
VERDICT: PASS_WITH_NITS
BLOCKS:
- (none)
NITS:
- src/vibesop/core/routing/_layers.py:497-499 — the abstain justification says the trusted
  runner-up's "sim is below the match floor — promoting it would route on evidence we
  already rejected", but the measured cluster tops at 0.502 > 0.45: for that upper band the
  trusted profile CLEARED the hard-match floor and merely lost the argmax. Abstaining is
  still the right policy (contested evidence → AI triage, same landing as the margin gate),
  but the stated reason is wrong for part of the cluster it was calibrated on. Say "loses
  the argmax to the pack" instead of "below the match floor".
- src/vibesop/core/routing/_layers.py:492 — comment quotes eval query "commit 三批改动"
  verbatim (yaml line 100). Zero runtime coupling (code branches on namespace + sims only,
  never query text) and M9 set the precedent (the guarded-skill comment quotes eval query
  "似乎有其他进程…"), but eval-query text in production comments rots when labels change —
  paraphrase in future calibration notes.
- src/vibesop/core/config/manager.py:272-274 — "an index rebuild can flip it" overstates:
  re-embedding the same profile text with the same model is near-deterministic; the real
  mover is pack profile TEXT drift (pack skill updates). The recalibrate mandate is right;
  naming the actual trigger would make it actionable.
- tests/unit/core/routing/test_triage_recall.py:84, tests/core/matching/test_strategies.py:229,
  tests/core/routing/test_index_layer.py:322, tests/core/skills/test_indexer.py:1634 — local
  patch.dict(None) stubs now duplicate the conftest autouse stub; harmless (idempotent) but
  candidate cleanup.
NOTES:
- Track A trace [executed]: arbitration at _layers.py:504-522 runs AFTER the threshold
  (0.45) and margin gates, BEFORE candidate lookup/guard check — it arbitrates a would-be
  winner, correct placement. Fires only when winner_ns ∉ trusted set; trusted winner passes
  untouched (test_trusted_winner_not_arbitrated). Empty/no-installed ranking is caught
  earlier by `not best_skill_id` at the threshold gate; `best_skill_id or ""` is
  dead-defensive. Namespace provenance is sound: candidate_manager.py:164 always sets it;
  the dict-comp pattern matches pre-existing line 623.
- Floor ordering is coherent [inspected]: 0.25 (recall noise ceiling) < 0.35
  (trusted-evidence floor) < 0.45 (hard match) forms a monotone evidence ladder; the
  docstring's cross-reference to ai_triage_recall_min_similarity is apt.
- Fragility opinion (Q2): keep 0.35, don't lower. The binding constraint is the keep-side
  positive (git-master trusted-best 0.274 → 0.076 headroom; losing it = eval regression);
  the abstain-side razor (0.352 vs floor) failing soft (one generic-query misroute returns,
  caught by the next eval run). 0.32 halves keep-headroom to 0.046 for 0.032 abstake-side
  gain — both within drift noise. Docstring warning + recalibrate mandate is adequate.
- False-abstain landing (Q1e) [inspected]: a genuine pack-intent query whose trusted-best
  lands in [0.35, 0.45) abstains → layer miss → AI triage still sees the pack skill in
  candidates. That's contested-evidence escalation, consistent with the M9 margin-gate
  precedent — defensible, at the cost of one LLM call. The eval confirms the one measured
  pack positive survives (trusted-best 0.274).
- Track B fidelity [executed]: every test that ASSERTS embedding behavior already uses an
  inner patch.dict fake which correctly overrides the conftest None stub (patch.dict
  saves/restores the surrounding value); nothing whose purpose was embedding behavior got
  blanket-stubbed. The monkeypatch.setitem-vs-patch.dict rationale (sys.modules key-delete
  → stale parent attr → dead-module patching) is a real CPython gotcha; same-instance
  monkeypatch LIFO makes the OSError-test override correct.
- Conftest blast radius [executed]: benchmark-only exemption is correctly scoped — pytest
  tests under tests/benchmark stay live, and CI deselects them via `-m "not benchmark and
  not slow"` anyway. Trade-off worth stating: sentence-transformers is a core dep, so CI
  previously smoke-tested the real model path incidentally (network download); the default
  suite no longer does — real-model coverage is now local-benchmark-only. Acceptable.
- Memory-test warmup [executed]: intent (router-object leak measurement) preserved; the
  comment honestly flags path dependence; imports present; 8/8 pass in 17.4s.
- Overfit check (Q5) [executed]: no eval-query-keyed logic anywhere in src/; new tests use
  non-eval gibberish queries ("zq wv xk") and synthetic ids. Residual 26 extended errors
  are keyword-layer pack matches (mattpocock/ui-ux/kimi-gated-fix clusters) — genuinely
  out of M10's semantic-index scope, honest boundary.
- Layering story: M7 recall floor / M9 margin + external token bar / M10 namespace
  arbitration each target a distinct measured failure mode; doc section (routing-system.md
  :129-138, :326) matches implementation. Not heuristic stacking.
```

Bottom line: both tracks do what they claim, with all numbers reproduced independently. The two substantive nits are comment-level inaccuracies in the abstain justification (argmax-loss vs below-floor) — worth fixing before commit since that comment is the rule's calibration record, but neither affects behavior.
