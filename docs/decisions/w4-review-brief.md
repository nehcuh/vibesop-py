# W4 Skill Promote — Review Brief

**Spec**: `docs/decisions/2026-07-29-task-memory-product-design.md:116-122`
**Plan**: `/Users/huchen/.claude/plans/ethereal-prancing-kay.md`
**Kill-switch**: §5 row "W4 末 — gold cluster 数 ≥5 / 候选池积压 <10 — else freeze"

## Review status

**Round 1**: grok + pi reviews landed 12 findings (3 P0, 8 P1, rest P2).
**Round 1 fixes applied**: all 3 P0s + 8 P1s addressing data correctness,
UX, and the architectural merge blocker (drafts were on auto-discovered
path). 11 new regression tests added. Test count: 44 → 55.

## What shipped

| # | Scope | Tests |
|---|-------|-------|
| W4.A | `ClusterCandidate` dataclass + `ClusterCandidateStore` (TTL=30d, hard cap=50, terminal sticky, admit-only-if-better) | 13 |
| W4.B | `label_step_frequency` (core ≥70% / common 30–70% / optional <30%) | 9 |
| W4.C | `scan_candidates` orchestrator + `ScanSummary` (stable / unstable / neutral zone) | 8 |
| W4.D | 4 CLI commands: `scan-candidates`, `candidates`, `promote`, `dismiss` (+ arg bounds) | 15 |
| W4.E | `materialize_candidate` writes SKILL.md draft OUTSIDE discovery paths | 6 |
| W4.F | Kill-switch smoke + this brief | 3 |
| **Total** | | **55** |

Files:
- `src/vibesop/core/observability/skill_promote.py` (~510 LOC, NEW)
- `src/vibesop/cli/commands/skill_commands.py` (+280 LOC, EDIT — 4 commands appended)
- 5 new test files
- 1 fixture: `tests/fixtures/w4_gold_clusters_spans.jsonl`

## Round 1 review findings + fixes

### P0-1 (grok): Drafts were on auto-discovered path → ARCHITECTURAL BREAK

**Finding**: `materialize_candidate` wrote to `.vibe/skills/<id>/SKILL.md`.
`CandidateManager._build_search_paths` (candidate_manager.py:240) includes
`.vibe/skills/` — every drafted skill was auto-discovered by the next
`get_candidates()` call, no `register` needed. The "未审不注入" guarantee
was architecturally false.

**Fix**: Drafts now land at `.vibe/observability/skill_drafts/<id>/SKILL.md`.
That path is NOT in `_build_search_paths`. Verified end-to-end: after
`materialize_candidate`, `CandidateManager.get_candidates()` returns 248
skills (unchanged) — drafted skill NOT among them.

### P0-2 (grok): "未审不注入" test was vacuous

**Finding**: Test patched `CandidateManager` and asserted it was never
*constructed*. Promote never touches CandidateManager regardless — the
assertion passed while the guarantee was broken.

**Fix**: New test builds a REAL `CandidateManager(project_root=tmp_path)`
after promote and asserts the drafted `skill_id` is NOT in discovered
candidates. Catches the actual guarantee.

### P0-3 (pi): Hard cap silent eviction violated spirit

**Finding**: At MAX_PENDING, eviction was silent (INFO log). Cron-scheduled
scans would lose candidates without audit trail.

**Fix**: Bumped to WARNING log level + admit-only-if-better policy (next).

### P1-1 (grok+pi): Hard cap admit logic was wrong

**Finding**: Always evicted lowest then appended — an unstable new arrival
(rate≈0.15) could displace a stable pending row (rate≈0.65).

**Fix**: Admit-only-if-better. New row admitted iff its `gold_rate` exceeds
current minimum; otherwise rejected with WARNING log. Test added:
`test_hard_cap_rejects_new_row_below_min`.

### P1-2 (grok+pi): Default candidates list included unstable

**Finding**: `list_pending()` returned stable + unstable. Docstring claimed
stable-only. CLI default view polluted with diagnosis rows.

**Fix**: `list_pending(include_unstable=False)` defaults to stable-only.
Same for `pending_count()`. CLI adds `--include-unstable` for the combined
view. Kill-switch now counts stable-only (matches spec intent).

### P1-3 (pi): Opaque cluster_id[:12] bad UX

**Finding**: User scanning the candidates table saw `abc123def456` with no
semantic anchor.

**Fix**: Added "Representative query" column showing the first query
truncated to 40 chars. Shortened cluster_id display to [:8].

### P1-4 (pi): _slugify collision risk

**Finding**: Two clusters sharing a first query (e.g. both starting "auth
login") would slug to the same `custom/auth-login`. Second promote silently
no-op'd via idempotent materialize.

**Fix**: `skill_id = custom/{slugified_query}-{cluster_id[:8]}`. Test added:
`test_promote_skill_id_includes_cluster_id_prefix`.

### P1-5 (grok): YAML frontmatter injection

**Finding**: Raw query text interpolated into unquoted `name:`/`description:`
fields. Multi-line / colon-bearing queries broke ruamel.yaml parsing when
the drafted skill was later loaded.

**Fix**: New `_sanitize_yaml_value` helper: collapses whitespace, escapes
backslashes/quotes, wraps in double quotes. Test added:
`test_promote_sanitizes_yaml_frontmatter` (uses `"setup: config\nthen deploy"`
as a hostile query).

### P1-6 (grok): CLI threshold args unbounded

**Finding**: `--min-cluster-size 0`, `--min-gold-rate 1.5`, `--limit -3`
all silently accepted. `min_cluster_size=0` + `min_gold_rate=0` floods the
pool; rates >1 silently yield zero candidates.

**Fix**: Bounds checked at CLI entry: `min_cluster_size>=1`,
`0<=min_gold_rate<=1.0`, `limit>=1`. Exit 1 with clear message. 5 tests
added under `TestCliArgBounds`.

### P1-7 (grok): tz-naive ttl_expires_at crashed prune

**Finding**: Hand-edited JSONL with naive ISO strings → TypeError comparing
aware vs naive in `prune_expired`. One bad line crashed the whole scan.

**Fix**: `from_dict` attaches UTC to naive datetimes. Tests added:
`test_from_dict_attaches_utc_to_naive_datetimes`,
`test_prune_expired_does_not_crash_on_naive_ttl`.

## Design decisions (call-outs for reviewers)

### 1. Trigger thresholds (size≥3, gold_rate≥0.60, unstable<0.30)

`min_cluster_size=3` is intentionally **below** W1's `is_gold` threshold of 5.
W4 surfaces *reviewable candidates*, not confirmed gold.

**Q1 status**: grok flagged as P2 (defensible with caveats). Fix shipped:
size=3 is OK because drafts are now isolated from discovery (P0-1 fix).
Tightening to size=5 deferred until production data shows noise.

### 2. Step-frequency thresholds (core 70% / common 30%)

Not in v3 spec. Module-level constants.

**Q3 status**: grok/pi concur 70/30 is defensible workflow-mining convention.
Common-step visibility in SKILL.md draft (pi P2) deferred.

### 3. TTL=30d, hard cap=50

TTL=30d matches `ReflectionStore`. Hard cap=50 from instinct auto-promote
`growth_cap` analogy. Admit-only-if-better + WARNING log address pi P0.

**Q4 status**: hybrid shipped — silent eviction replaced with admit-only-if-better
+ WARNING log. Block-scan alternative (hard error) deferred.

### 4. "未审不注入" guarantee — P0 FIXED

Drafts now land outside `_build_search_paths`. Two-layer guard:
- Layer 1: SKILL.md draft sits at `.vibe/observability/skill_drafts/` —
  CandidateManager does not search this path.
- Layer 2: store row stays `status=promoted` so re-scans don't re-suggest.

### 5. Unstable bucket (persisted with `is_unstable=True` flag)

**Q2 status**: grok+pi agreed current design is OK now that kill-switch counts
stable-only. Unstable still queryable via `--unstable` and `--include-unstable`.

### 6. Kill-switch numbers (smoke fixture)

Fixture: 15 spans, 5 clusters × 3 task_ids. Tests verify ≥5 stable candidates
and <10 backlog (stable-only count). Production freeze logic itself is
deferred (current behavior: surface backlog count, no enforcement).

## CLI surface

```bash
# Scan recent spans → populate pool (idempotent, prunes TTL-expired)
vibe skill scan-candidates [--dry-run] [--min-cluster-size N] [--min-gold-rate R] [--limit N]

# List pending (stable by default; --unstable for diagnosis; --include-unstable for both)
vibe skill candidates [--unstable] [--include-unstable] [--json]

# Promote → writes SKILL.md draft OUTSIDE discovery paths
vibe skill promote <cluster_id>

# Dismiss with optional reason (status is sticky)
vibe skill dismiss <cluster_id> [--reason TEXT]

# After promote, manual injection:
cp -r .vibe/observability/skill_drafts/custom/<slug> .vibe/skills/
vibe skill add .vibe/skills/custom/<slug>
```

## Defer list (NOT in W4 — Round 2 candidates)

- Cross-project promotion (v3 §6 cut; post-MVP)
- launchd/cron preset for `scan-candidates` (suggest: `0 */6 * * *`)
- Auto-injection of promoted skills into routing (by design — 未审不注入)
- Timeline/DAG visualization of candidate pool
- Market-search integration with SkillSuggestion (stays on pattern-based collector)
- TTL config knob (30d hardcoded)
- Step-frequency normalization by span_kind (route:/llm:/tool: counted equally)
- Unstable bucket gradation (binary at 30% only)
- Block-scan alternative to hard cap (currently admit-only-if-better)
- Common-step visibility in SKILL.md draft (pi P2)
- `vibe skill candidate <id>` detail view (pi P1; defer until usage data)
- `vibe skill unpromote` (pi P1; deferred — promote→dismiss asymmetric)
- Inode-rename race on AtomicWriter (grok P2, inherited from ReflectionStore)

## Verification

```bash
# All W4 unit + smoke tests
uv run pytest tests/core/observability/test_skill_promote_store.py \
              tests/core/observability/test_step_frequency.py \
              tests/core/observability/test_scan_candidates.py \
              tests/cli/test_skill_promote_cli.py \
              tests/cli/test_w4_kill_switch_smoke.py -v

# W3 regression (must not break)
uv run pytest tests/core/observability/test_recall.py \
              tests/cli/test_route_replay_cli.py \
              tests/cli/test_recall_cli.py -v

# Lint + types
uv run ruff check src/vibesop/core/observability/skill_promote.py \
                  src/vibesop/cli/commands/skill_commands.py
uv run ruff format --check src/vibesop/core/observability/skill_promote.py
uv run basedpyright src/vibesop/core/observability/skill_promote.py

# 5-iteration flake check (memory: feedback_test_embedding_determinism)
for i in 1 2 3 4 5; do
  uv run pytest tests/core/observability/test_skill_promote_store.py \
                tests/core/observability/test_step_frequency.py \
                tests/cli/test_skill_promote_cli.py -q --tb=no
done
```

## Round 1 reviewer questions — final disposition

- **Q1** (`min_cluster_size=3`): P2 deferred — defensible after P0-1 fix.
- **Q2** (unstable pooled vs transient): Keep pooled, count stable-only.
- **Q3** (70/30 thresholds): Defensible. No benchmark to override.
- **Q4** (hard cap policy): Hybrid shipped — admit-only-if-better + WARNING.
- **Q5** (cross-project leakage): No fix needed — pool is per-project
  (`.vibe/observability/cluster_candidates.jsonl`).
