# Routing Eval Set — Append Workflow (gate37)

How real production queries (with real human verdicts) enter
`tests/benchmark/routing_eval.yaml`. CI hard-gating on the eval set is
deliberately rejected (gate37 裁决 4); this document covers the
append-only sample flow.

## Files

- `tests/benchmark/routing_eval.yaml` — the scored main set. **Never
  hand-edit this file.** Appends go through the script only.
- `tests/benchmark/routing_eval_extended.yaml` — the review queue. Human
  editing happens HERE (it is an in-flow action, not a violation).
- `tests/benchmark/routing_eval_retention.yaml` — insight-mining pool for
  dismissed samples. Not scored by the eval harness.
- `scripts/build_eval_from_logs.py` — the only write path.

## Flow

1. **Export** candidates from a project's logs:

   ```bash
   uv run python scripts/build_eval_from_logs.py \
       --analytics /path/.vibe/analytics.jsonl \
       --triage /path/.vibe/ai_triage_log.jsonl
   ```

   Entries are written to the extended file with `needs_review: true`.
   Every query is forced through `redact_sensitive()` before it lands on
   disk — upstream exports carry no redaction guarantee.

2. **Human review** in the extended file: fix `expect` to the correct
   skill id list, then flip `needs_review: false`.
   - Confirmed positive: `expect: [namespace/skill-id]`
   - Scored no-match assertion: `expect: []` with NO marker (plus an
     optional `note:`) — the eval harness scores these; they are NOT
     dismissals and `--merge` leaves them in the extended flow.
   - Dismissed (no routing ground truth): `expect: []` + `needs_review:
     false` + an **explicit dismissal marker** — either `dismissed: true`
     or a `retention_reason:` field. The marker is mandatory: without it
     the entry is read as a scored no-match assertion. When the export
     carries pre-adjudicated dismiss verdicts (e.g. cmspark), they must
     enter the extended file with this marker already attached.

3. **Merge**:

   ```bash
   uv run python scripts/build_eval_from_logs.py --merge
   ```

   - `needs_review: false` + non-empty `expect` → appended to the main
     set (dedup by normalized redacted query; `needs_review`/`weak_label`
     keys stripped).
   - `needs_review: false` + empty `expect` + explicit dismissal marker →
     moved to the retention pool. The moved entry keeps `needs_review:
     false` and always carries `retention_reason` (defaulting to a
     dismissal note when only `dismissed: true` was given); the
     `dismissed` marker key itself is consumed.
   - Unmarked `expect: []` entries (scored no-match assertions) are left
     untouched — a first `--merge` over the pre-gate37 extended file is a
     zero migration of the negative-expect entries.
   - Merge re-redacts every persisted query BEFORE dedup, so two raw
     queries that redact to the same text cannot both land. Human edits
     are in-flow, so sanitisation is enforced at the write boundary, not
     assumed.
   - Anything still `needs_review: true` stays in the extended file.

4. **Smoke-run the harness** after appending to prove the set still
   parses and runs:

   ```bash
   uv run python scripts/eval_routing.py --json
   ```

## Discipline

- The main yaml is append-only via the script; hand edits to it bypass
  dedup and redaction and are treated as process violations.
- Retention entries are NOT ground truth. The pre-existing pool entries'
  `expect` values are the ORIGINAL weak labels, kept for provenance only;
  gate37 dismiss entries always have `expect: []` (a human rejected the
  weak label, so there is no label to preserve) plus a `retention_reason`
  explaining the dismissal.
- Real queries in git are a one-time leak surface (same shape as F-06):
  if a query should not be public, do not merge it — redaction is
  conservative, not exhaustive.
