# Gate 15 Design Review — M12 产品设计：对话中语义洞察 → 技能发现

You are reviewing a PRODUCT DESIGN (not code) for the VibeSOP repo at /Users/huchen/Projects/vibesop-py. Read these files (all in repo):

1. `.omx/artifacts/m12-product-design.md` — THE DESIGN UNDER REVIEW (synthesized)
2. `.omx/artifacts/m12-exploration.md` — verified facts about the current codebase
3. `.omx/artifacts/m12-design-a.md` — adversarial sub-design A (user-value view)
4. `.omx/artifacts/m12-design-b.md` — adversarial sub-design B (architecture view)

The user's requirement: during conversations, semantically detect when similar user queries repeatedly fail to route to a skill BUT the coding agent handles them in a similar way; consolidate into a standalone workflow; record as a project skill; surface the discovery on a dashboard; support one-click promotion to a global skill.

You may read any source file to verify feasibility claims. DO NOT modify anything.

## Review focus

1. **Correctness of adjudication**: the synthesis ruled behavior collection is core (rejecting A's "v1 without behavior data"), citing the structural fact that `scan_candidates` requires gold_rate≥0.60 so pure-miss clusters can never become candidates, and that claude-code PostToolUse capture already exists (adapters/claude_code.py:655 → .vibe/tool_sequences.jsonl). Verify both claims against the code. Is the ruling sound? Did the synthesis lose anything valuable from A or B?
2. **Feasibility of the data flow**: the M1 assembly bridge (join tool events to route spans by session_id + time window, emit tool_call spans), outcome signals (re-ask = strong negative etc.), the behavior-consistency gate (tool-sequence bigram-Jaccard). Check against actual span/store code — is the join feasible? Are the claimed consumers (dashboard/aggregator/dag_rebuilder) real?
3. **Threshold philosophy**: ≥3 misses across ≥2 natural days, embedding cosine ≥0.82, bigram-Jaccard ≥0.5. Are these defensible starting points? Any interaction with M11's evidence-based scoring (e.g. fallback_llm queries now more common after M11's stricter abstention — does that flood the miss pool)?
4. **Privacy**: is the privacy design consistent with the repo's existing conventions? Any leak path missed?
5. **Scope**: is the v1 cut right? What's the most likely way this milestone set fails or balloons?
6. **Missing pieces**: anything the design needs but doesn't mention (e.g. evaluation method — how do we measure the discovery quality?; migration/compat; cost of embedding at scan time)?

## Verdict format

End with exactly one of: `VERDICT: PASS`, `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (list blocking issues with reasoning).
