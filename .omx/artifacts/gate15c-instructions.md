# Gate 15c Final Confirmation — M12 产品设计 v3

Repo: /Users/huchen/Projects/vibesop-py. Read `.omx/artifacts/m12-product-design.md` (v3, final). This is a doc-only confirmation after gate15b. Each of your gate15b items was addressed as follows — verify by reading the doc; push back only if a fix is wrong or missing.

- claude BLOCK (admission gate false implication): now conjunction — "distinct (task_key, 自然日) 对 ≥ 3 且 跨 ≥2 个不同自然日"; the false implication claim deleted; same-day/cross-day synthetic injection tests added as M2 acceptance.
- claude Nit-A: synthetic injection tests in M2. Nit-B: spans missing has_match → treated as unknown, NOT miss pool (保守). Nit-C: admission task_key reuses the span's full-text-derived task_id (unified with re-ask detection); calibration corpus based on truncated text as the pipeline sees it. Nit-D: ScanSummary layer-share instrumentation added to M4. Nit-E: cold-start expectation + backfill sentence added.
- pi N1: miss classification rule explicit (miss = has_match=False; mode="not_intercepted" excluded — 19/75 spans are mostly continuation tokens; miss pool shrinks to ~6 real spans); M0 smoke runs at a lenient threshold to validate the extraction chain, admission uses the calibrated threshold; fallback = collect-until-N real misses or synthetic injection as secondary evidence.
- pi N2: M2 exit — ≥1 real-data-admitted candidate visible in `vibe skill discover` with populated evidence card (guards the third silent-empty manifestation).
- pi N3: M1 exit — real dogfood tool_sequences output AND ≥20 bridged tool_call spans across ≥3 distinct sessions AND last-capture fresh within 7 days.
- pi N5: edit-guard mechanism specified — content hash recorded at draft generation; registration requires current draft hash ≠ generated hash, or --force (mtime rejected as gameable).
- pi minor: journey step 4 says CLI-only explicitly; kimi/pi hook availability no longer asserted as fact (spike first).

## Verdict format

End with exactly one of: `VERDICT: PASS`, `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (reasoning).
