# Gate 14c Confirmation Review — M11 third fix round

Repo: /Users/huchen/Projects/vibesop-py. The appended diff is the FULL current diff vs HEAD. History: gate14 (pi BLOCK: incomplete ANCHOR_STOPWORDS — fixed), gate14b (pi BLOCK: stopword list still incomplete — `as`/like/together/fully missing, superset claim false — and a demonstrated 0.623/0.706 mis-fire; claude PASS_WITH_NITS with 3 nits). This round closes gate14b. Your job: verify the gate14b blocker is genuinely closed and this round introduced nothing new. DO NOT modify anything.

## What this round changed (all verified by orchestrator reproduction)

1. **ANCHOR_STOPWORDS completed** (src/vibesop/core/matching/idf.py): added the missing function-word classes — `as` (was in tokenizer DEFAULT_STOP_WORDS but missing here), `like`, `together`, `fully`, plus time/degree/place adverbs and connectives (today/tomorrow/yesterday/nearly/almost/barely/despite/toward(s)/accordingly/thereby/…). New tests pin: `set(DEFAULT_STOP_WORDS) <= set(ANCHOR_STOPWORDS)` and that as/like/together/fully/today/despite never anchor (tests/core/matching/test_idf.py).
2. **Stopwords now contribute ZERO score evidence** (strategies.py `_score_evidence`): excluded not only from anchors but from partial bonus, substring bonus, and the coverage numerator AND denominator. Rationale: pi's gate14b demo rode stopword prefix hits ("can"⊂"canvas") to saturate the coverage gate. This is a mechanism-level closure of the function-word class, not list-whack-a-mole.
3. gate14b claude nits: substring_bonus site comment (loose-by-design), rewarm test assertion de-tautologized (`assert km._idf is not None` — builtin skills guarantee a non-empty reloaded pool), TFIDFMatcher.warm_up([]) now explicitly resets `_fitted`/`_idf` (symmetric with KeywordMatcher).

## Post-fix verified results (reproduce what you can)

- pi's gate14b demos, real 239-pool, warmed, default MatcherConfig:
  - `can you together update today before friday` → keyword layer returns NOTHING (abstains). ✅
  - `get this working on the new branch before the deadline` → NOTHING. ✅
  - `can you together update the website before friday` → 0.706 → **0.408** vs oneshot-web-spec. The residual is anchored by the content word `website`, which is literally in that skill's curated keywords AND is what the query asks to update — orchestrator judges this defensible/semantic-adjacent rather than function-word leakage. Challenge this judgment if you disagree.
- Evals re-run on production code: base 31/34, oneshot 10/11, extended 98/107; per-query diff vs /tmp/m11-baseline.json: 17 error→OK, 0 OK→BAD (third consecutive round with identical fix/regression counts). After-state: /tmp/m11c-{base,oneshot,ext}.json.
- Full pytest was running at packet time; verify `uv run pytest tests/ -q` shows 0 failures (5626+3 new expected).

## Review focus

1. Is the stopword-zero-evidence change correctly implemented (no path where a stopword still feeds partial/substring/coverage)? Any side effect on legitimate queries (e.g. queries whose meaningful tokens are mostly stopwords — do they now degrade gracefully)?
2. The superset pinning test — does it actually pin what gate14b demanded?
3. The `website` residual judgment (above): defensible or still a leak?
4. Anything new broken by this round.

## Verdict format

End with exactly one of: `VERDICT: PASS`, `VERDICT: PASS_WITH_NITS` (list nits), `VERDICT: BLOCK` (file:line + reasoning).
