# Gate 15b Confirmation Review — M12 产品设计 v2

You reviewed the M12 product design at gate15. The v2 revision at `.omx/artifacts/m12-product-design.md` (repo: /Users/huchen/Projects/vibesop-py) responds to your findings. Re-read it fully. Verify against the code where needed. DO NOT modify anything.

## What changed v1 → v2

- claude BLOCK-1 (clustering premise falsified: `_extract_query` reads only `input_data`; 75 real route spans yield 0 extractable queries, 0 clusters — orchestrator reproduced): new **M0 milestone** (metadata fallback in `_extract_query` + real-span smoke; M2 exit requires scan on this repo's real spans.jsonl producing >0 clusters including miss clusters).
- claude BLOCK-2 (claude-code capture channel live in code but zero data in dogfood — `.vibe/tool_sequences.jsonl` doesn't exist; hook swallows failures — orchestrator reproduced): M1 exit criterion now requires real dogfood tool_sequences output + capture-liveness signal (last-capture timestamp); silent swallow fix in scope.
- pi join-key defect (route hook doesn't forward session_id; fresh UUID per CLI invocation): M1 now includes route-hook session_id forwarding, or fallback time-window join with ambiguity rejection. Claude's counter-evidence (agent-path spans carry real platform session UUIDs) is noted; CLI path excluded from join.
- pi miss-source ambiguity: resolved — route span metadata carries has_match (excludes fallback_llm), so miss filtering reads spans directly; no MissCounter hash join.
- pi `--activate` contradiction: now requires "draft materially edited since generation" or explicit `--force`; dashboard is READ-ONLY, mutations CLI-only (adopts pi's recommendation).
- pi: spans.jsonl rotation (50MB) added; 200-vs-500 truncation corrected; cold-start expectations; [XP]-or-force required for global promote; evaluation method added (calibration with 30-50 labeled dogfood misses, `--history` precision metric promoted/(promoted+dismissed), post-promote route-hit≥5 closed-loop check).
- claude nits: gold-gate wording corrected (unstable bucket, not "never a candidate"); cursor contention resolved (single-reader fanout); re-ask detection keyed on span task_id (not truncated-query hashes); privacy wording corrected ("tool names only"); knobs NOT in RoutingConfig (module constants + CLI flags, future DiscoveryConfig); admission unit = distinct (task_key, natural-day) pairs ≥3; 0.82 marked as to-be-calibrated; 14-day cooldown restored; M11 miss-pool composition shift acknowledged.
- pi's "lost from A" items restored: --history, evidence_score ordering, 14-day cooldown, --mute.

## Your job

1. Verify your own gate15 findings are each addressed (or push back where v2's resolution is wrong).
2. Check v2 for NEW contradictions or gaps introduced by the revision.
3. Pay special attention: is the M0/M1 exit-criteria framing sufficient to prevent the "silently empty feature" failure mode? Is anything still asserted as "works" that hasn't been verified on real data?

## Verdict format

End with exactly one of: `VERDICT: PASS`, `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (list blocking issues with reasoning).
