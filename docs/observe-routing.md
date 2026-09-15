# Online Routing Evidence Operations (`vibe observe routing`)

> **Applies to**: source candidate 8.5.0 (the [`vibesop.observe.routing`](../src/vibesop/core/observability/route_observe.py) v1 contract).
> **Status**: report-only operator tooling. Public release 8.4.1 does not contain it; 8.5.0 is not published until it is tagged and pushed.
> **Last updated**: 2026-09-15

`vibe observe routing` turns local routing telemetry into three operational
signals and one versioned machine report:

| Signal | Question it answers |
|---|---|
| `no_match` | How often do route spans end in no-match, over the scorable slice? |
| `near_miss` | How often does the hermetic eval inject a skill on a near-miss negative? (optional) |
| `decision_source` | How often is `metadata.layer` missing or outside the `RoutingLayer` enum? |
| `coverage` | How much of the scanned route traffic is actually scorable? |

The command is **report-only**. It never writes the routing registry, the eval
dataset, thresholds, skill files, or any policy. See
[No automatic policy mutation](#no-automatic-policy-mutation).

---

## 1. Inputs and producers

| Input | Produced by | Default |
|---|---|---|
| `--spans PATH` | `vibe route` appends route spans to `.vibe/observability/spans.jsonl`. The observer reads any JSONL file of `Span.to_dict()` (or `SpanWriter` JSON-string `metadata`) records. | `<cwd>/.vibe/observability/spans.jsonl` |
| `--eval-json PATH` | `uv run python scripts/eval_routing.py --hermetic --json --json-out FILE` (or `--json` on stdout). | none → `near_miss` state is `not_requested` |

The eval producer's `--json` and `--json-out` payloads carry the provenance keys
the observer requires: `dataset`, `hermetic`, and `generated_at`. Older payloads
without them are rejected fail-closed (see [Eval provenance](#7-eval-provenance)).

### Runnable example

```sh
# 1. Produce a fresh hermetic eval payload (near-miss over-injection evidence).
uv run python scripts/eval_routing.py --hermetic --json --json-out /tmp/eval-routing.json

# 2. Observe local route spans against it. Reads `.vibe/observability/spans.jsonl`
#    in the current project by default. Report-only: it never edits the eval
#    dataset, thresholds, or routing policy.
uv run vibe observe routing \
  --eval-json /tmp/eval-routing.json --json
```

Exit `4` on the first run is expected: the default minimum is 100 scorable route
spans (see [Sample and coverage gates](#5-sample-and-coverage-gates)).

### Which spans count

A record is scanned only when its `name` is a string starting with `route:`
(the CLI/hook task span). Everything else in the JSONL is ignored. For each
route span the observer decodes `metadata` (dict or JSON string), then scores
no-match **field-first**, first readable slot wins:

1. `metadata.has_match` (bool) → no-match iff `has_match is False`;
2. `metadata.skill_id` (str) → no-match iff `skill_id == ""`;
3. `metadata.primary` (str) → no-match iff `primary == ""`;
4. `metadata.layer` (non-empty str) → no-match iff `layer == "fallback_llm"`.

If none of those slots is readable the span is **unscored** (not a silent hit).
A present-but-undecodable `metadata` (non-dict, bad JSON, or JSON non-object)
counts as `n_unparsed_metadata` and forces `no_match` to `insufficient_data`.

Counts partition as:

```
n_route   = n_hit + n_nomatch + n_unscored
n_scored  = n_hit + n_nomatch          # n_scored <= n_route
n_unparsed_metadata <= n_unscored      # subset; also inside n_route
n_no_ts, n_corrupt                     # outside n_route
```

An unparsed `metadata` payload is both `n_unparsed_metadata` and `n_unscored`,
so it counts once inside `n_route`; only dropped window spans (`n_no_ts`) and
corrupt JSONL lines (`n_corrupt`) are outside `n_route`.

---

## 2. Metric numerators and denominators

| Metric | Numerator (`n`) | Denominator (`d`) | Rate | Notes |
|---|---|---|---|---|
| `no_match` | `n_nomatch` (scored route spans judged no-match) | `n_scored` = `n_hit + n_nomatch` | `n / d` | Wilson 95% interval reported for `(n, d)`; `null` when `d == 0`. |
| `near_miss` | `near_miss_over_inject` from the eval payload | `n_near_miss` from the eval payload | `n / d` | `not_requested` when no `--eval-json`; `insufficient_data` when `n_near_miss < 10`. |
| `decision_source` | `n_unknown_scored` (scored spans with `layer` missing or non-enum) | `n_scored` | `n / d` | `unknown_share_of_route = n_unknown / n_route` is also reported but does **not** drive the verdict. |
| `coverage` | `n_scored` | `n_route` | `n / d` | `scoring_coverage`; a thin scorable slice is not evidence. |

`decision_source` classifies `metadata.layer`:
- a valid `RoutingLayer` value (`explicit`, `scenario`, `semantic_index`,
  `ai_triage`, `keyword`, `tfidf`, `embedding`, `levenshtein`, `custom`,
  `no_match`, `fallback_llm`) → known;
- any other non-empty string → `unknown` bucket and listed under `non_enum_layers` (top 20);
- absent or empty → `missing` bucket. `missing` and `unknown` both count as unknown.

Zero denominators render `null` ratios, never `0%`. `fallback_llm` is both a
known layer and the router's no-match sentinel.

---

## 3. Default thresholds and exact comparisons

All comparisons use the raw (unrounded) ratio. Fractional thresholds accept
`[0, 1]`; `warn` must be `<= crit`.

| Flag | Default | Comparison | State |
|---|---|---|---|
| `--min-samples` | `100` | `d < min_samples` | `insufficient_data` (`below_min_samples`) |
| `--min-samples-near-miss` | `10` | `n_near_miss < min_samples_near_miss` | `insufficient_data` (`eval_rows_below_min`) |
| `--min-coverage` | `0.80` | `scoring_coverage < min_coverage` | `insufficient_data` (`below_min_coverage`) |
| `--nomatch-warn` | `0.40` | `rate >= nomatch_warn` | `warn` |
| `--nomatch-crit` | `0.60` | `rate >= nomatch_crit` | `critical` |
| `--near-miss-warn` | `0.15` | `rate >= near_miss_warn` | `warn` |
| `--near-miss-crit` | `0.30` | `rate >= near_miss_crit` | `critical` |
| `--unknown-warn` | `0.05` | `unknown_share >= unknown_warn` | `warn` |
| `--unknown-crit` | `0.10` | `unknown_share >= unknown_crit` | `critical` |
| `--max-corrupt` | `0` | `n_corrupt > max_corrupt` | floors the overall verdict at `warn` (`corrupt_payloads`) |
| `--max-eval-age-hours` | `24.0` | `(now - generated_at) > 24h` | `invalid_eval_provenance` fault |

**Exact inclusive boundaries.** A ratio exactly equal to a warn/crit threshold
takes that state (for example `n=40, d=100` is `warn` at `0.40` and `critical`
at `0.60`). Exactly `min_samples` (100) and exactly `min_samples_near_miss` (10)
are sufficient. `scoring_coverage == 0.80` is healthy. An eval generated exactly
24h ago is accepted; exactly 5 minutes in the future is accepted.

---

## 4. States

| State | Meaning |
|---|---|
| `healthy` | Every participating metric is healthy. |
| `warn` | Worst participating state is warn, or at least one corrupt line exceeded `--max-corrupt`. |
| `critical` | Worst participating state is critical. |
| `insufficient_data` | Worst participating state is insufficient (thin sample, low coverage, missing input). |
| `fault` | The observer could not honor a requested input (unreadable spans, invalid eval payload/provenance, `--require-inputs`, `--strict-payloads`). |

`insufficient_data` is **not** "worse than warn"; these are labels, not a
severity ordering. Treat any non-zero exit as not-green and map explicitly.
`near_miss` participates in the rollup only when `--eval-json` is supplied.

**Corruption behavior.** The file is read byte-by-byte and each line decoded as
UTF-8; a truncated multibyte append or invalid UTF-8 is `n_corrupt`, never a
crash. A UTF-8 BOM is stripped from the first line only; a mid-file U+FEFF is
corrupt. Invalid JSON and non-object JSON lines are corrupt. Empty/whitespace
lines are skipped without counting. By default any corrupt line floors the
overall verdict at `warn`; `--max-corrupt N` tolerates `N`, and
`--strict-payloads` turns any corruption or unparsed metadata into a fault.

---

## 5. Sample and coverage gates

A high no-match rate on a tiny readable slice is not evidence, so `no_match`
requires **both** gates before it can be warn/critical:

1. `scoring_coverage = n_scored / n_route >= 0.80`;
2. `n_scored >= 100`.

`decision_source` requires `n_scored >= 100` but does not apply the coverage
gate. `near_miss` requires `n_near_miss >= 10`. The coverage gate exists to
block false-green reports such as 5,000 route spans where only 30 are scorable.

---

## 6. Window, project filter, and eval freshness

- `--since ISO8601` is an **inclusive** lower bound on the span timestamp.
- `--until ISO8601` is an **exclusive** upper bound, so the window is
  `[since, until)`. An empty window (`since >= until`) or an unparseable bound
  is a usage error (exit 2) raised **before** the spans file is touched.
- Span timestamps come from `started_at` first, then the legacy `timestamp`
  field. Naive values are read as UTC. A windowed span with no parseable
  timestamp is `n_no_ts` and dropped. With no window active, timestamps are not
  required.
- `--project-id ID` keeps only records whose `project_id` exactly equals `ID`.
- **Freshness is independent of the window.** `--since`/`--until` filter spans;
  the eval payload's freshness is measured against the observer clock. A fresh
  eval is accepted even when the span window excludes every span, and a stale
  eval is rejected even for a wide span window. The eval is a separate
  static-dataset run, not a stream filtered by the same window.

---

## 7. Eval provenance

A supplied `--eval-json` is validated **fail-closed** before its counts are
used. Any of the following is an `invalid_eval_provenance` fault (exit 3):

- missing or wrong-typed `dataset` / `hermetic` / `generated_at`, or empty `dataset`;
- `generated_at` that is not timezone-aware ISO8601 (a naive value is rejected, not guessed UTC);
- `hermetic` that is not exactly `true`;
- `dataset` that does not match `--expected-eval-dataset` (default
  `tests/benchmark/routing_eval.yaml`) after separator/leading-`./` normalization
  — exact full-string match, never a basename match;
- `generated_at` more than **5 minutes** in the future;
- `generated_at` older than `--max-eval-age-hours` (default **24h**).

The expected dataset identity is the repo-relative POSIX path when the dataset
lives under the repo root (`tests/benchmark/routing_eval.yaml`); an external
dataset resolves to an absolute path. Use `--expected-eval-dataset` only when
you intentionally point at another dataset, and pass the same value.

Invalid counts are also faults: `n_near_miss` / `near_miss_over_inject` must be
non-negative integers with `over <= n_near_miss`; if `n_neg` is present it must
be an integer `>= over`.

A provenance fault is **never** suppressed by `--report-only`.

---

## 8. Exit codes and flags

| Exit | Name | Meaning |
|---|---|---|
| `0` | healthy | Every participating metric is healthy (or a verdict suppressed by `--report-only`). |
| `1` | warn | Worst participating state is warn, or a corrupt-payload floor applied. |
| `2` | usage | Invalid window or threshold. Click/Typer convention; a usage error is never masked by a missing spans file. |
| `3` | critical-or-fault | Worst participating state is critical, or any fault (unreadable spans, invalid eval payload/provenance, `--require-inputs`, `--strict-payloads`). |
| `4` | insufficient_data | Worst participating state is insufficient (missing input, no route spans, no scorable spans, unparsed metadata, below coverage or min-samples). |

> **Not Nagios-compatible.** Nagios reads `2=CRITICAL`, `3=UNKNOWN`; this
> command reads `2=usage` and `3=critical/fault`. Map exits explicitly in any
> monitoring wrapper.

| Flag | Effect |
|---|---|
| `--report-only` | Forces exit `0` for **verdicts** only. Usage (`2`) and faults (`3`) are unchanged. A `critical` report still prints `overall_state: critical` and exits `0`; a provenance fault still exits `3`. |
| `--require-inputs` | Escalates a missing spans file or missing eval file from `insufficient_data` (`4`) to a fault (`3`). Use in automated gates where absence must be loud. |
| `--strict-payloads` | Turns any corrupt line or unparsed metadata payload into a fault (`3`). |
| `--json` / `-j` | Emits the versioned machine JSON on stdout instead of the human block. |
| `--expected-eval-dataset` | Overrides the exact dataset identity to match. |
| `--max-eval-age-hours`, `--min-samples`, `--min-samples-near-miss`, `--min-coverage`, `--nomatch-warn/-crit`, `--near-miss-warn/-crit`, `--unknown-warn/-crit`, `--max-corrupt` | Override the default thresholds in section 3. |

---

## 9. JSON contract (`vibesop.observe.routing` v1)

`--json` prints a single JSON object. Important fields:

| Field | Type | Notes |
|---|---|---|
| `schema` | string | Always `vibesop.observe.routing`. |
| `schema_version` | int | Always `1`. |
| `generated_at` | string | Observer clock, UTC ISO8601. |
| `overall_state` | string | `healthy` \| `warn` \| `critical` \| `insufficient_data` \| `fault`. |
| `exit_code` | int | The process exit the report maps to. |
| `outcome` | object | `{kind: "verdict"\|"fault", reason: string\|null}`. |
| `window` | object | `{active, since, until, timezone}`; bounds are normalized to UTC. |
| `filters` | object | `{project_id}`. |
| `inputs` | object | `spans_path`, `spans_mtime`, `eval_json_path`, `eval_json_mtime`, `expected_eval_dataset`, `future_skew_tolerance_seconds`, `registry_path` (always `null`). |
| `counts` | object | `n_route`, `n_hit`, `n_nomatch`, `n_scored`, `n_unscored`, `n_no_ts`, `n_corrupt`, `n_unparsed_metadata`. |
| `coverage` | object | `{scoring_coverage, min_coverage, state}`. |
| `metrics` | object | `{no_match, near_miss, decision_source}` (section 2). |
| `registry` | null | Reserved; the observer never reads or writes the routing registry. |
| `thresholds` | object | The effective threshold values for this run. |
| `recommendations` | string[] | Deterministic, human-readable next steps. |
| `error` | object | Present only on a fault or missing input: `{kind, path, message}`. |
| `errors` | object[] | Optional additive detail: present only when more than one requested input is missing under `--require-inputs`; lists every missing input path in a fixed order (spans first, then eval). The primary `error` is unchanged. |

The report is deterministic for a fixed clock and input. It never includes raw
query text, skill ids, or span metadata at the top level.

---

## 10. Cron and CI wrappers

Both wrappers map **every** documented exit explicitly. Do not treat exit `2`
as healthy.

### Cron / systemd wrapper

```sh
#!/bin/sh
# observe-routing-cron.sh — append the machine report, page on critical/fault.
set -eu
cd /srv/vibesop
OUT=/var/log/vibesop/observe-routing-$(date -u +%Y%m%dT%H%M%SZ).json
uv run vibe observe routing \
  --spans /srv/vibesop/.vibe/observability/spans.jsonl \
  --eval-json /srv/vibesop/.vibe/eval-routing.json \
  --require-inputs --json > "$OUT" || rc=$?
rc=${rc:-0}
case "$rc" in
  0)  logger -t vibe-observe "healthy" ;;
  1)  logger -t vibe-observe "WARN: see $OUT" ;;
  2)  logger -t vibe-observe "USAGE ERROR: bad window/threshold — fix the invocation"; exit 2 ;;
  3)  logger -t vibe-observe "CRITICAL/FAULT: see $OUT"; exit 3 ;;
  4)  logger -t vibe-observe "INSUFFICIENT DATA (collect more spans or provide eval): see $OUT" ;;
  *)  logger -t vibe-observe "unexpected exit $rc"; exit 3 ;;
esac
```

### CI step (report artifact, no automatic gate)

```yaml
- name: Observe routing evidence (report-only)
  run: |
    set -eu
    uv run python scripts/eval_routing.py --hermetic --json --json-out eval-routing.json
    uv run vibe observe routing \
      --eval-json eval-routing.json \
      --report-only --json > observe-routing.json || {
        rc=$?
        # --report-only never suppresses faults (3) or usage (2).
        echo "observe routing fault/usage (exit $rc)"; cat observe-routing.json; exit "$rc"
      }
    # Informational only: no routing policy or dataset is changed here.
```

If you *do* want the step to fail the build, drop `--report-only` and map
`1/3/4` yourself; the command still will not mutate anything.

---

## 11. First run and missing data

- **No spans file** → `insufficient_data` (`4`) with `error.kind: missing_input`,
  `metrics.no_match.reason: missing_input`, and `no_match.rate: null`. Exit `4`
  is the expected first-run result, not an error.
- **Spans path exists but cannot be read** (for example a directory, or an I/O
  error) → `fault` (`3`) with `error.kind: unreadable_input`; both
  `metrics.no_match.reason` and `metrics.decision_source.reason` carry
  `unreadable_input`, never a generic `missing_input`.
- **`--require-inputs`** → the same missing file becomes a fault (`3`), so an
  automated pipeline cannot mistake "no data yet" for green. When the spans
  file and a supplied `--eval-json` are **both** missing, the report adds an
  `errors` array naming both paths in a fixed order (`[spans, eval]`) while the
  primary `error` field still points at the spans file.
- **Spans file exists but has no `route:` spans** → `insufficient_data`
  (`no_route_spans`).
- **Route spans exist but none are scorable** → `insufficient_data`
  (`no_scored_spans`).
- **`--eval-json` supplied but the file is missing** → `insufficient_data`
  (`4`); add `--require-inputs` for a fault.
- **`--eval-json` not supplied** → `near_miss` is `not_requested`, not
  false-green.

---

## 12. Legacy spans and unknown layers

- Spans written before `metadata.layer` existed have no `layer` key. They land
  in the `missing` bucket and count toward `decision_source` unknown share once
  they are scorable. This is expected for historical data; it is still producer
  contract drift worth fixing going forward.
- A present but non-enum value (for example `builtin` or `semantic`) lands in
  the `unknown` bucket and its raw value is listed in `non_enum_layers` (top 20
  by count). This usually means a producer changed the layer vocabulary without
  updating consumers.
- `decision_source` is gated on the scored denominator, so a handful of legacy
  rows cannot flip a small sample to warn/critical.

---

## 13. Append/rotation limitation

The observer reads the file once, from the beginning. There is no tail and no
rotation handling: `--since`/`--until` is a filter over the scanned file, not an
index, and a rotated/renamed file is invisible unless `--spans` points at it.
Writers append; the file is never compacted. This is deliberate for a
report-only tool, but it means:

- a window query still reads the whole file (I/O is O(file size));
- if the writer rotates between runs, spans in the rotated file are not seen by
  a later run unless you point `--spans` at that file (or concatenate);
- a truncated append is counted as corrupt (see section 4), not silently lost.

For long-running projects, keep the active spans file bounded by the writer's
rotation policy and archive rotated files with explicit `--spans` paths.

---

## 14. No automatic policy mutation

`vibe observe routing` and `scripts/aggregate_nomatch.py` are **read-only over
the evidence and the policy surface**. In particular the command never:

- writes the routing registry (`registry` is always `null`);
- edits the eval dataset or its baseline;
- changes thresholds or routing configuration;
- promotes skills, edits `SKILL.md`, or touches CI gates.

Exit `0`/`1`/`3`/`4` are labels, not instructions. Changing a threshold or the
dataset is a separate, reviewed change with its own evidence.

---

## 15. How evidence informs dataset and threshold decisions

Use the report as input to a human-reviewed decision, never as an automatic
trigger:

1. **Confirm coverage and sample first.** If `coverage.state` is
   `insufficient_data`, collect more spans or fix the producers before reading
   any rate.
2. **Investigate before tuning.** For `no_match` warn/critical, inspect the
   `fallback_llm` route spans (`counts.n_nomatch`, `metrics.no_match`). For
   `decision_source` warn/critical, inspect `non_enum_layers` and missing-layer
   producers. Decide whether the fix is the producer, the dataset, or a
   threshold — in that order.
3. **Update the eval dataset deliberately.** If the evidence shows a new class
   of query that should route, add labeled rows to
   `tests/benchmark/routing_eval.yaml`, regenerate the hermetic baseline with
   `scripts/eval_routing.py --hermetic --update-baseline`, and review the
   resulting diff. Near-miss negatives are reported separately and are not
   folded into `must_not_inject`.
4. **Change thresholds only with a reason and a review.** Threshold flags are
   configuration, not evidence. A threshold change should cite the report that
   motivated it and land with its own tests; the observer's defaults stay
   conservative until then.
5. **Keep the hermetic `--check` gate independent.** The eval's `--check` exit
   codes are the routing-quality gate; this observer is report-only and must
   not be wired into that gate or used to relax it.

---

## Related documents

- [`scripts/eval_routing.py`](../scripts/eval_routing.py) — hermetic eval producer and baseline gate.
- [`scripts/aggregate_nomatch.py`](../scripts/aggregate_nomatch.py) — 8.4.0-compatible no-match facade.
- [`src/vibesop/core/observability/route_observe.py`](../src/vibesop/core/observability/route_observe.py) — observer implementation and machine contract.
- [CLI Reference](user/CLI_REFERENCE.md) — `vibe observe routing` flag list.
- [Roadmap](ROADMAP.md) — the operational-evidence slice and later milestones.
