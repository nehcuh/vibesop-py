# Gate 14c Review — M11 third fix round

All claims reproduced on the working tree; nothing modified. Evidence levels tagged per behavior rules.

## 1. Stopword-zero-evidence implementation `[inspected] + [executed]`

Traced every score path in `_score_evidence` (strategies.py:165-296) against the working tree:

| Path | Stopword excluded? |
|---|---|
| anchors (`find_anchors`, idf.py) | ✅ double-filtered — `meaningful` pre-filter (strategies.py:217-221) **and** `token in ANCHOR_STOPWORDS` inside `find_anchors` |
| partial bonus | ✅ loop is `for qt in meaningful` (strategies.py:228) |
| substring bonus | ✅ `for qt in meaningful` (strategies.py:259) |
| coverage numerator AND denominator | ✅ both sum over `meaningful` only (strategies.py:243-246) |
| TF-IDF anchor gate | ✅ its `meaningful` list skips the pre-filter, but `find_anchors`' internal check covers it |

Two residual permeable paths exist and are **contained, not leaky**: `base_score` (strategies.py:207-211) still counts stopword exact matches against the Jaccard union, and `name_bonus` containment runs over all query tokens. Both are bounded by the anchorless cap (0.25 < 0.3 default matcher floor). Verified empirically `[executed]`: worst-case raw keyword score across all 239 candidates is **0.233** / **0.25** for the two junk demos — they abstain even on a hypothetical min_confidence=0.3 installation. The packet's claim (partial/substring/coverage num+den) is literally accurate; base_score was never claimed.

Graceful degradation: an all-stopword query yields `meaningful=[]` → coverage 0 (`or 1.0` guards division) → capped 0.25 → fallback_llm. Zero legitimate-query regressions: 0 OK→BAD across all 152 eval queries `[executed]`.

## 2. Superset pinning `[executed]`

Live check: `set(DEFAULT_STOP_WORDS) - set(ANCHOR_STOPWORDS) = set()` (34/34). `as`/`like`/`together`/`fully`/`today`/`despite` all present. `test_default_stop_words_are_subset` pins exactly what gate14b demanded — the superset claim now holds by construction and breaks loudly if DEFAULT_STOP_WORDS grows. This is the right pin: it closes the class, not the instances.

## 3. pi's gate14b demos, real 239-pool, warmed, default config `[executed]`

- `can you together update today before friday` → keyword layer `[]`, router → fallback_llm, has_match=False ✅
- `get this working on the new branch before the deadline` → same ✅
- `can you together update the website before friday` → keyword layer `[]` at the 0.6 threshold, raw 0.408 vs oneshot-web-spec ✅ (exact reproduction of the claimed number)

Notably `can` (w=0.786) and `together` (w=0.893) both clear the 0.78 IDF bar and both exactly hit candidate tokens — the stopword exclusion is load-bearing, not decorative.

**`website` residual judgment: I concur it is defensible, not a leak.** The anchor is a content word literally present in the skill's curated keywords; the query's subject IS the website; the 0.408 score sits below every default routing threshold so the router correctly abstains to fallback_llm. Even in a lowered-threshold deployment, routing a website-update request to a web-spec skill is semantically adjacent, not function-word junk. One fragility note (nit below): w(`website`)=0.786 is 0.006 above the anchor bar.

## 4. Nothing new broken `[executed]`

- New tests: 33/33 pass (test_idf, test_evidence_scoring, test_matcher_rewarm).
- Full suite: **5628 passed / 14 skipped / 0 failed** (packet said "5626+3"; actual is 5626+2 — an arithmetic slip in the packet, not a code issue).
- Evals fresh-run: base 31/34, oneshot 10/11, extended 98/107 — identical to claims.
- Per-query: vs /tmp/m11-baseline.json **17 error→OK, 0 OK→BAD**, 9 unchanged residual errors (3 scenario / 4 recall / 2 semantic-index — matches CHANGELOG); vs orchestrator's /tmp/m11c-*.json **0 outcome diffs** across 152 queries.
- Diff scope matches the packet exactly (11 files); ruff clean on all changed files (the one ARG002 error is in `context_mixin.py`, untouched by this diff — pre-existing on HEAD, out of scope).
- Nit fixes verified in tree: substring_bonus loose-by-design comment (strategies.py:252-254), de-tautologized rewarm assertion, `TFIDFMatcher.warm_up([])` reset (strategies.py:561-566).

## Nits

1. **Stopword narrative overstatement**: "stopwords contribute ZERO score evidence" doesn't hold for `base_score`/`name_bonus`. Contained today (anchor cap 0.25), but if anyone raises `keyword_anchor_cap` above 0.3, stopword Jaccard mass becomes live again. Worth one sentence in the routing-system doc's M11 section.
2. **Boundary token**: `website` anchors at w=0.786 vs bar 0.78 — 0.006 margin. Pool-drift sensitive; already covered by the config's "re-run evals after major pool changes" guidance, flagged here for the record.

The gate14b blocker is closed at mechanism level with pinned tests; demos, evals, and suite all reproduce cleanly.

VERDICT: PASS_WITH_NITS
