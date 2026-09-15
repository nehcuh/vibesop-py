"""Online routing-evidence observer (8.5).

Single home for the shipped ``scripts/aggregate_nomatch.py`` parsing/scoring
implementation plus the ``vibesop.observe.routing`` v1 machine contract used
by ``vibe observe routing``.

Report-only by design: the observer never writes the routing registry, the
eval dataset, thresholds, or any policy file. It turns
``.vibe/observability/spans.jsonl`` into three operational signals:

- ``no_match`` — production no-match rate over scorable route spans, with a
  Wilson 95% interval and a scoring-coverage gate (a high rate on a tiny
  readable slice is not evidence).
- ``near_miss`` — optional ``--eval-json`` from ``scripts/eval_routing.py``;
  ``not_requested`` when the operator did not supply it, never false-green.
- ``decision_source`` — ``metadata.layer`` vs the :class:`RoutingLayer`
  enum, with unknown/non-enum share gated only on the scored denominator.

Reused verbatim from 8.4.0 (do not fork the predicate):

- lens: JSON object whose ``name`` is a ``str`` starting with ``route:``;
- scoring is field-first (``has_match`` -> ``skill_id`` -> ``primary`` ->
  ``layer``), first readable slot wins;
- ``metadata`` may be a dict (``Span.to_dict``) or a JSON string
  (``SpanWriter``);
- byte-level read + per-line UTF-8 decode; a truncated multibyte append is
  ``n_corrupt``, never a ``UnicodeDecodeError`` into argparse exit 2;
- a UTF-8 BOM is stripped from the first line only; a mid-file U+FEFF is
  corrupt;
- ``--since`` inclusive, ``--until`` exclusive, naive values read as UTC,
  ``started_at`` first then legacy ``timestamp``; a windowed span with no
  parseable timestamp is ``n_no_ts`` and dropped;
- zero denominator -> ``null`` ratios, never ``0%``.

Exit codes (labels, not a severity ordering):

    0 healthy    — every participating metric healthy
    1 warn       — worst participating state is warn
    2 usage      — bad window/thresholds (Click/Typer convention)
    3 fail       — worst participating state is critical, or any fault
    4 insufficient_data — worst participating state is insufficient_data

``4`` is not "worse than" ``1``; treat any non-zero as not-green and map
explicitly. Not Nagios-compatible (Nagios reads 2=CRITICAL, 3=UNKNOWN).
``--report-only`` forces exit 0 for verdicts only; usage (2) and faults (3)
are unchanged. ``--strict-payloads`` turns corrupt/unparsed payloads into a
fault.

Usage:
    from vibesop.core.observability.route_observe import observe_routing
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import NormalDist
from typing import Any

from vibesop.core.models import RoutingLayer

MISSING_SPANS_ERROR = "missing_spans"
UNREADABLE_SPANS_ERROR = "unreadable_spans"
#: Layer bucket for spans that carry no ``layer`` key (gate18 convention).
UNKNOWN_LAYER = "unknown"
#: Layer bucket for a present-but-non-enum ``layer`` value (folded into unknown).
MISSING_LAYER = "missing"
#: The router's no-match sentinel layer.
FALLBACK_LLM_LAYER = "fallback_llm"

SCHEMA = "vibesop.observe.routing"
SCHEMA_VERSION = 1

HEALTHY = "healthy"
WARN = "warn"
CRITICAL = "critical"
INSUFFICIENT = "insufficient_data"
NOT_REQUESTED = "not_requested"

#: Known routing-layer values (``RoutingLayer`` members) in canonical order.
ROUTING_LAYER_VALUES: tuple[str, ...] = tuple(layer.value for layer in RoutingLayer)
_ROUTING_LAYER_SET: frozenset[str] = frozenset(ROUTING_LAYER_VALUES)

_SEVERITY: dict[str, int] = {HEALTHY: 0, INSUFFICIENT: 1, WARN: 2, CRITICAL: 3}

#: Canonical portable identity of the default eval dataset (see
#: ``scripts/eval_routing.py``).
DEFAULT_EVAL_DATASET = "tests/benchmark/routing_eval.yaml"
#: An eval payload may sit at most this far ahead of the observer clock.
FUTURE_SKEW_TOLERANCE = timedelta(minutes=5)
FUTURE_SKEW_TOLERANCE_SECONDS = 300


@dataclass(frozen=True)
class ObserveThresholds:
    """Report-only verdict thresholds (all comparisons on raw, unrounded ratios)."""

    min_samples: int = 100
    min_samples_near_miss: int = 10
    min_coverage: float = 0.80
    nomatch_warn: float = 0.40
    nomatch_crit: float = 0.60
    near_miss_warn: float = 0.15
    near_miss_crit: float = 0.30
    unknown_warn: float = 0.05
    unknown_crit: float = 0.10
    max_corrupt: int = 0
    #: Eval provenance freshness bound, in hours, relative to the injected now.
    max_eval_age_hours: float = 24.0


@dataclass(frozen=True)
class ObserveError:
    """A fail-closed fault: the observer could not honor a requested input."""

    kind: str
    path: str
    message: str


@dataclass(frozen=True)
class ObserveResult:
    """Machine report plus the process exit code it maps to."""

    report: dict[str, Any]
    exit_code: int
    fault: bool


@dataclass
class _ScanResult:
    """Internal tally over one spans file. Counts partitions:

    - ``n_route == n_hit + n_nomatch + n_unscored``
    - ``n_scored == n_hit + n_nomatch``
    - ``n_no_ts`` / ``n_corrupt`` / ``n_unparsed_metadata`` are outside both.
    """

    spans_path: str
    error: str | None = None
    error_kind: str | None = None
    n_route: int = 0
    n_hit: int = 0
    n_nomatch: int = 0
    n_unscored: int = 0
    n_no_ts: int = 0
    n_corrupt: int = 0
    n_unparsed_metadata: int = 0
    n_known: int = 0
    n_unknown: int = 0
    n_unknown_scored: int = 0
    nomatch_by_layer: Counter[str] = field(default_factory=Counter)
    layer_buckets: Counter[str] = field(default_factory=Counter)
    non_enum_layers: Counter[str] = field(default_factory=Counter)

    @property
    def n_scored(self) -> int:
        return self.n_nomatch + self.n_hit


# ---------------------------------------------------------------------------
# Parsing / scoring primitives (shipped predicate, do not fork)
# ---------------------------------------------------------------------------


def _parse_ts(value: Any) -> datetime | None:
    """Parse an ISO8601 timestamp; naive values are read as UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _span_ts(record: dict[str, Any]) -> datetime | None:
    """``started_at`` first, legacy ``timestamp`` fallback."""
    return _parse_ts(record.get("started_at")) or _parse_ts(record.get("timestamp"))


def _parse_aware_ts(value: Any) -> datetime | None:
    """Parse ISO8601 that *must* carry a timezone offset.

    Distinct from :func:`_parse_ts` (spans window, where a naive value is
    read as UTC): an eval ``generated_at`` without an offset is
    unverifiable provenance and is rejected rather than guessed.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return None if dt.tzinfo is None else dt


def _normalize_dataset_identity(value: str) -> str:
    """Canonical comparison form for a dataset identity.

    ``\\`` separators become ``/`` and a leading ``./`` is dropped. This is
    a full-string normalization used for exact matching only — never a
    basename match.
    """
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _decode_metadata(record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Best-effort metadata dict plus whether it was a well-formed object.

    ``True`` when the key is absent/``None`` (shipped fail-soft behavior),
    a dict, or a JSON string that decodes to a dict. ``False`` when a
    present value is a non-dict, an undecodable string, or a JSON
    non-object — evidence loss that must stay visible.
    """
    raw = record.get("metadata")
    if raw is None:
        return {}, True
    if isinstance(raw, dict):
        return raw, True
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}, False
        if isinstance(decoded, dict):
            return decoded, True
        return {}, False
    return {}, False


def _parse_metadata(record: dict[str, Any]) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
    """Shipped helper preserved for compatibility: dict passes through,
    JSON string is decoded, anything else (or undecodable) is empty."""
    return _decode_metadata(record)[0]


def _score_no_match(meta: dict[str, Any]) -> bool | None:
    """Field-first no-match verdict: True=no-match, False=hit, None=unscored."""
    has_match = meta.get("has_match")
    if isinstance(has_match, bool):
        return not has_match
    skill_id = meta.get("skill_id")
    if isinstance(skill_id, str):
        return skill_id == ""
    primary = meta.get("primary")
    if isinstance(primary, str):
        return primary == ""
    layer = meta.get("layer")
    if isinstance(layer, str) and layer:
        return layer == FALLBACK_LLM_LAYER
    return None


def wilson_interval(k: int, n: int, z: float | None = None) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials (95% by default).

    Pure stdlib (NormalDist.inv_cdf); returns (0.0, 0.0) for n == 0.
    k=0 / k=n are forced to exact endpoints so float noise cannot yield
    ~1e-17 instead of 0.0.
    """
    if n <= 0:
        return 0.0, 0.0
    if z is None:
        z = NormalDist().inv_cdf(0.975)
    p = k / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    lo = max(0.0, (centre - margin) / denom)
    hi = min(1.0, (centre + margin) / denom)
    if k <= 0:
        lo = 0.0
    if k >= n:
        hi = 1.0
    return (lo, hi)


def _ratio(numerator: int, denominator: int) -> float | None:
    """``numerator / denominator``, or ``None`` when the denominator is 0."""
    if denominator <= 0:
        return None
    return numerator / denominator


def _round4(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


# ---------------------------------------------------------------------------
# Window / scan
# ---------------------------------------------------------------------------


def parse_window(since: str | None, until: str | None) -> tuple[datetime | None, datetime | None]:
    """Validate and parse window bounds before any file is touched.

    ``--since`` is inclusive, ``--until`` exclusive. Naive values are UTC.
    Raises ``ValueError`` for an unparseable bound or ``since >= until``
    (usage error, exit 2 — never masked by a missing spans file).
    """
    since_dt = _parse_ts(since) if since else None
    if since and since_dt is None:
        raise ValueError(f"--since is not a valid ISO8601 timestamp: {since!r}")
    until_dt = _parse_ts(until) if until else None
    if until and until_dt is None:
        raise ValueError(f"--until is not a valid ISO8601 timestamp: {until!r}")
    if since_dt is not None and until_dt is not None and since_dt >= until_dt:
        raise ValueError("--since must be strictly earlier than --until (empty window)")
    return since_dt, until_dt


def _scan(
    spans_path: Path,
    *,
    since_dt: datetime | None,
    until_dt: datetime | None,
    project_id: str | None,
) -> _ScanResult:
    """Stream the spans JSONL and tally the routing-evidence universe."""
    result = _ScanResult(spans_path=str(spans_path))
    try:
        exists = spans_path.exists()
    except OSError:  # pragma: no cover - defensive
        result.error = UNREADABLE_SPANS_ERROR
        result.error_kind = "io_error"
        return result
    if not exists:
        result.error = MISSING_SPANS_ERROR
        result.error_kind = "missing_input"
        return result

    n_route = n_hit = n_nomatch = n_unscored = n_no_ts = n_corrupt = 0
    n_unparsed = n_known = n_unknown = n_unknown_scored = 0
    nomatch_by_layer: Counter[str] = Counter()
    layer_buckets: Counter[str] = Counter()
    non_enum_layers: Counter[str] = Counter()
    try:
        with spans_path.open("rb") as f:
            first_line = True
            for raw_line in f:
                try:
                    decoded = raw_line.decode("utf-8")
                except UnicodeDecodeError:
                    n_corrupt += 1
                    first_line = False
                    continue
                if first_line:
                    if decoded.startswith("\ufeff"):
                        decoded = decoded[1:]
                    first_line = False
                line = decoded.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    n_corrupt += 1
                    continue
                if not isinstance(record, dict):
                    n_corrupt += 1
                    continue
                name = record.get("name")
                if not isinstance(name, str) or not name.startswith("route:"):
                    continue
                if since_dt is not None or until_dt is not None:
                    ts = _span_ts(record)
                    if ts is None:
                        n_no_ts += 1
                        continue
                    if since_dt is not None and ts < since_dt:
                        continue
                    if until_dt is not None and ts >= until_dt:
                        continue
                if project_id is not None and record.get("project_id") != project_id:
                    continue
                n_route += 1
                meta, parsed_ok = _decode_metadata(record)
                if not parsed_ok:
                    n_unparsed += 1
                verdict = _score_no_match(meta)
                if verdict is None:
                    n_unscored += 1
                elif verdict:
                    n_nomatch += 1
                    layer = meta.get("layer")
                    bucket = layer if isinstance(layer, str) and layer else UNKNOWN_LAYER
                    nomatch_by_layer[bucket] += 1
                else:
                    n_hit += 1
                # decision_source: classify metadata.layer against the enum.
                layer_value = meta.get("layer")
                if isinstance(layer_value, str) and layer_value:
                    if layer_value in _ROUTING_LAYER_SET:
                        layer_buckets[layer_value] += 1
                        n_known += 1
                    else:
                        layer_buckets[UNKNOWN_LAYER] += 1
                        non_enum_layers[layer_value] += 1
                        n_unknown += 1
                        if verdict is not None:
                            n_unknown_scored += 1
                else:
                    layer_buckets[MISSING_LAYER] += 1
                    n_unknown += 1
                    if verdict is not None:
                        n_unknown_scored += 1
    except OSError:
        result.error = UNREADABLE_SPANS_ERROR
        result.error_kind = "unreadable_input"
        return result

    result.n_route = n_route
    result.n_hit = n_hit
    result.n_nomatch = n_nomatch
    result.n_unscored = n_unscored
    result.n_no_ts = n_no_ts
    result.n_corrupt = n_corrupt
    result.n_unparsed_metadata = n_unparsed
    result.n_known = n_known
    result.n_unknown = n_unknown
    result.n_unknown_scored = n_unknown_scored
    result.nomatch_by_layer = nomatch_by_layer
    result.layer_buckets = layer_buckets
    result.non_enum_layers = non_enum_layers
    return result


# ---------------------------------------------------------------------------
# Legacy aggregate projection (scripts/aggregate_nomatch.py compat)
# ---------------------------------------------------------------------------


def aggregate(
    spans_path: Path,
    since: str | None = None,
    until: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """8.4.0-compatible report dict (fail-soft errors, legacy key set).

    ``until``/``project_id`` are additive and unused by the compat script.
    """
    since_dt, until_dt = parse_window(since, until)
    result = _scan(spans_path, since_dt=since_dt, until_dt=until_dt, project_id=project_id)
    if result.error is not None:
        return {"error": result.error, "n_route": 0}
    n_scored = result.n_scored
    rate = _ratio(result.n_nomatch, n_scored)
    if n_scored > 0:
        low, high = wilson_interval(result.n_nomatch, n_scored)
    else:
        low, high = None, None
    return {
        "spans_path": result.spans_path,
        "since": since,
        "n_route": result.n_route,
        "n_hit": result.n_hit,
        "n_nomatch": result.n_nomatch,
        "n_scored": n_scored,
        "n_unscored": result.n_unscored,
        "n_no_ts": result.n_no_ts,
        "n_corrupt": result.n_corrupt,
        "rate": _round4(rate),
        "scoring_coverage": _round4(_ratio(n_scored, result.n_route)),
        "nomatch_share_of_route": _round4(_ratio(result.n_nomatch, result.n_route)),
        "wilson95_low": _round4(low),
        "wilson95_high": _round4(high),
        "nomatch_by_layer": dict(result.nomatch_by_layer),
    }


def _fmt_ratio(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.4f}"


def _human_line(report: dict[str, Any]) -> str:  # pyright: ignore[reportUnusedFunction]
    if "error" in report:
        return (
            f"spans unavailable ({report['error']}); n_route={report.get('n_route', 0)} "
            "(fail-soft, nothing to aggregate)"
        )
    window = report.get("since") or "all"
    rate = report["rate"]
    if rate is None:
        rate_part = "rate unavailable"
        wilson_part = "wilson95=unavailable"
    else:
        rate_part = f"rate={rate:.4f}"
        wilson_part = f"wilson95=[{report['wilson95_low']:.4f}, {report['wilson95_high']:.4f}]"
    return (
        f"spans={report['spans_path']} window={window} "
        f"n_route={report['n_route']} n_nomatch={report['n_nomatch']} "
        f"{rate_part} {wilson_part} "
        f"(n_hit={report['n_hit']} n_scored={report['n_scored']} "
        f"unscored={report['n_unscored']} corrupt={report['n_corrupt']} "
        f"scoring_coverage={_fmt_ratio(report['scoring_coverage'])})"
    )


# ---------------------------------------------------------------------------
# Observe report
# ---------------------------------------------------------------------------


def validate_thresholds(thresholds: ObserveThresholds) -> None:
    """Raise ``ValueError`` (usage, exit 2) for invalid threshold config."""
    for name in (
        "min_coverage",
        "nomatch_warn",
        "nomatch_crit",
        "near_miss_warn",
        "near_miss_crit",
        "unknown_warn",
        "unknown_crit",
    ):
        value = getattr(thresholds, name)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"--{name.replace('_', '-')} must be within [0, 1] (got {value})")
    for warn_name, crit_name in (
        ("nomatch_warn", "nomatch_crit"),
        ("near_miss_warn", "near_miss_crit"),
        ("unknown_warn", "unknown_crit"),
    ):
        warn = getattr(thresholds, warn_name)
        crit = getattr(thresholds, crit_name)
        if warn > crit:
            raise ValueError(
                f"--{warn_name.replace('_', '-')} must be <= --{crit_name.replace('_', '-')}"
            )
    if thresholds.min_samples < 1:
        raise ValueError("--min-samples must be >= 1")
    if thresholds.min_samples_near_miss < 1:
        raise ValueError("--min-samples-near-miss must be >= 1")
    if thresholds.max_corrupt < 0:
        raise ValueError("--max-corrupt must be >= 0")
    max_age = thresholds.max_eval_age_hours
    if not math.isfinite(max_age) or max_age <= 0:
        raise ValueError("--max-eval-age-hours must be a finite value > 0")


def _file_mtime(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _no_match_metric(scan: _ScanResult, thresholds: ObserveThresholds) -> dict[str, Any]:
    n = scan.n_nomatch
    d = scan.n_scored
    rate = _ratio(n, d)
    if d > 0:
        lo, hi = wilson_interval(n, d)
        low: float | None = _round4(lo)
        high: float | None = _round4(hi)
    else:
        low = high = None
    coverage = _ratio(d, scan.n_route)
    state = HEALTHY
    reason: str | None = None
    if scan.error is not None:
        state, reason = INSUFFICIENT, "missing_input"
    elif scan.n_route == 0:
        state, reason = INSUFFICIENT, "no_route_spans"
    elif d == 0:
        state, reason = INSUFFICIENT, "no_scored_spans"
    elif scan.n_unparsed_metadata > 0:
        state, reason = INSUFFICIENT, "unparsed_metadata"
    elif coverage is not None and coverage < thresholds.min_coverage:
        state, reason = INSUFFICIENT, "below_min_coverage"
    elif d < thresholds.min_samples:
        state, reason = INSUFFICIENT, "below_min_samples"
    elif rate is not None and rate >= thresholds.nomatch_crit:
        state, reason = CRITICAL, "nomatch_critical"
    elif rate is not None and rate >= thresholds.nomatch_warn:
        state, reason = WARN, "nomatch_warn"
    return {
        "n": n,
        "d": d,
        "rate": _round4(rate),
        "wilson95_low": low,
        "wilson95_high": high,
        "state": state,
        "reason": reason,
    }


def _decision_source_metric(scan: _ScanResult, thresholds: ObserveThresholds) -> dict[str, Any]:
    d = scan.n_scored
    unknown_share = _ratio(scan.n_unknown_scored, d)
    unknown_share_of_route = _ratio(scan.n_unknown, scan.n_route)
    layer_coverage = _ratio(scan.n_known, scan.n_route)
    by_layer: dict[str, int] = dict.fromkeys(ROUTING_LAYER_VALUES, 0)
    by_layer[UNKNOWN_LAYER] = 0
    by_layer[MISSING_LAYER] = 0
    for key, count in scan.layer_buckets.items():
        by_layer[key] = by_layer.get(key, 0) + count
    by_layer = dict(sorted(by_layer.items()))
    non_enum_sorted = dict(
        sorted(scan.non_enum_layers.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    )
    state = HEALTHY
    reason: str | None = None
    if scan.error is not None:
        state, reason = INSUFFICIENT, "missing_input"
    elif scan.n_route == 0:
        state, reason = INSUFFICIENT, "no_route_spans"
    elif d == 0:
        state, reason = INSUFFICIENT, "no_scored_spans"
    elif d < thresholds.min_samples:
        state, reason = INSUFFICIENT, "below_min_samples"
    elif unknown_share is not None and unknown_share >= thresholds.unknown_crit:
        state, reason = CRITICAL, "unknown_layer_critical"
    elif unknown_share is not None and unknown_share >= thresholds.unknown_warn:
        state, reason = WARN, "unknown_layer_warn"
    return {
        "n_unknown": scan.n_unknown,
        "n_unknown_scored": scan.n_unknown_scored,
        "unknown_share": _round4(unknown_share),
        "unknown_share_of_route": _round4(unknown_share_of_route),
        "layer_coverage": _round4(layer_coverage),
        "by_layer": by_layer,
        "non_enum_layers": non_enum_sorted,
        "known_values": list(ROUTING_LAYER_VALUES),
        "state": state,
        "reason": reason,
    }


def _eval_provenance(
    payload: dict[str, Any],
    *,
    eval_path: str,
    expected_dataset: str,
    max_age_hours: float,
    now: datetime,
) -> tuple[dict[str, Any], ObserveError | None]:
    """Validate an eval payload's provenance and build its machine block.

    Fail-closed: a missing/wrong-typed key, empty dataset, naive or
    non-ISO8601 ``generated_at``, non-hermetic run, dataset-identity
    mismatch, a timestamp more than 5 minutes in the future, or one older
    than ``max_age_hours`` is an :data:`invalid_eval_provenance` fault.

    The returned provenance dict is always populated with the expected
    identity, the max age, and the observed future skew so even a fault
    report stays diagnosable. Freshness is computed against the injected
    ``now`` and is deliberately independent of the ``--since``/``--until``
    span window: the eval payload is a separate static-dataset run.
    """
    prov: dict[str, Any] = {
        "dataset": payload.get("dataset"),
        "expected_dataset": expected_dataset,
        "dataset_matches": None,
        "hermetic": payload.get("hermetic"),
        "generated_at": payload.get("generated_at"),
        "age_seconds": None,
        "future_skew_seconds": None,
        "max_age_hours": max_age_hours,
        "future_skew_tolerance_seconds": FUTURE_SKEW_TOLERANCE_SECONDS,
    }

    def _err(message: str) -> ObserveError:
        return ObserveError(kind="invalid_eval_provenance", path=eval_path, message=message)

    for key, expected_type in (("dataset", str), ("hermetic", bool), ("generated_at", str)):
        if key not in payload:
            return prov, _err(f"eval payload is missing required provenance key {key!r}")
        if not isinstance(payload[key], expected_type):
            return prov, _err(f"eval payload provenance key {key!r} has wrong type")
    if not payload["dataset"]:
        return prov, _err("eval payload provenance key 'dataset' is empty")

    generated = _parse_aware_ts(payload["generated_at"])
    if generated is None:
        return prov, _err(
            "eval payload provenance key 'generated_at' must be timezone-aware ISO8601"
        )
    prov["dataset_matches"] = _normalize_dataset_identity(
        payload["dataset"]
    ) == _normalize_dataset_identity(expected_dataset)
    prov["age_seconds"] = round((now - generated).total_seconds(), 3)
    prov["future_skew_seconds"] = round(max(0.0, (generated - now).total_seconds()), 3)

    if payload["hermetic"] is not True:
        return prov, _err("eval payload is not hermetic (hermetic must be exactly true)")
    if not prov["dataset_matches"]:
        return prov, _err(
            f"eval payload dataset {payload['dataset']!r} does not match expected "
            f"{expected_dataset!r} after separator/leading-./ normalization"
        )
    if (generated - now) > FUTURE_SKEW_TOLERANCE:
        return prov, _err(
            "eval payload generated_at is more than 5 minutes in the future "
            f"(future_skew_seconds={prov['future_skew_seconds']})"
        )
    if (now - generated) > timedelta(hours=max_age_hours):
        return prov, _err(
            "eval payload generated_at is older than max age "
            f"({max_age_hours} hours; age_seconds={prov['age_seconds']})"
        )
    return prov, None


def _near_miss_metric(
    eval_json: Path | None,
    thresholds: ObserveThresholds,
    *,
    expected_eval_dataset: str,
    now: datetime,
) -> tuple[dict[str, Any], ObserveError | None]:
    """Build the near_miss metric, returning a fault when a payload is invalid."""
    if eval_json is None:
        return (
            {
                "n": None,
                "d": None,
                "over_inject": None,
                "rate": None,
                "state": NOT_REQUESTED,
                "reason": "not_supplied",
                "source": None,
                "provenance": None,
            },
            None,
        )
    if not eval_json.exists():
        return (
            {
                "n": None,
                "d": None,
                "over_inject": None,
                "rate": None,
                "state": INSUFFICIENT,
                "reason": "missing_input",
                "source": None,
                "provenance": None,
            },
            ObserveError(
                kind="missing_input",
                path=str(eval_json),
                message="eval JSON path does not exist",
            ),
        )
    try:
        payload: Any = json.loads(eval_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return (
            {
                "n": None,
                "d": None,
                "over_inject": None,
                "rate": None,
                "state": INSUFFICIENT,
                "reason": "invalid_eval_payload",
                "source": None,
                "provenance": None,
            },
            ObserveError(kind="invalid_eval_payload", path=str(eval_json), message=str(exc)),
        )
    if not isinstance(payload, dict):
        return (
            {
                "n": None,
                "d": None,
                "over_inject": None,
                "rate": None,
                "state": INSUFFICIENT,
                "reason": "invalid_eval_payload",
                "source": None,
                "provenance": None,
            },
            ObserveError(
                kind="invalid_eval_payload",
                path=str(eval_json),
                message="eval JSON root is not an object",
            ),
        )
    provenance, prov_error = _eval_provenance(
        payload,
        eval_path=str(eval_json),
        expected_dataset=expected_eval_dataset,
        max_age_hours=thresholds.max_eval_age_hours,
        now=now,
    )
    if prov_error is not None:
        return (
            {
                "n": None,
                "d": None,
                "over_inject": None,
                "rate": None,
                "state": INSUFFICIENT,
                "reason": "invalid_eval_provenance",
                "source": None,
                "provenance": provenance,
            },
            prov_error,
        )
    n_near = payload.get("n_near_miss")
    over = payload.get("near_miss_over_inject")
    if (
        not isinstance(n_near, int)
        or isinstance(n_near, bool)
        or not isinstance(over, int)
        or isinstance(over, bool)
        or n_near < 0
        or over < 0
        or over > n_near
    ):
        return (
            {
                "n": None,
                "d": None,
                "over_inject": None,
                "rate": None,
                "state": INSUFFICIENT,
                "reason": "invalid_eval_payload",
                "source": None,
                "provenance": provenance,
            },
            ObserveError(
                kind="invalid_eval_payload",
                path=str(eval_json),
                message="near_miss counts missing, non-int, negative, or inconsistent",
            ),
        )
    n_neg = payload.get("n_neg")
    if n_neg is not None and (
        not isinstance(n_neg, int) or isinstance(n_neg, bool) or over > n_neg
    ):
        return (
            {
                "n": None,
                "d": None,
                "over_inject": None,
                "rate": None,
                "state": INSUFFICIENT,
                "reason": "invalid_eval_payload",
                "source": None,
                "provenance": provenance,
            },
            ObserveError(
                kind="invalid_eval_payload",
                path=str(eval_json),
                message="near_miss_over_inject exceeds n_neg or n_neg has wrong type",
            ),
        )
    rate = _ratio(over, n_near)
    state = HEALTHY
    reason: str | None = None
    if n_near == 0 or n_near < thresholds.min_samples_near_miss:
        state, reason = INSUFFICIENT, "eval_rows_below_min"
    elif rate is not None and rate >= thresholds.near_miss_crit:
        state, reason = CRITICAL, "near_miss_critical"
    elif rate is not None and rate >= thresholds.near_miss_warn:
        state, reason = WARN, "near_miss_warn"
    metric = {
        "n": over,
        "d": n_near,
        "over_inject": over,
        "rate": _round4(rate),
        "state": state,
        "reason": reason,
        "source": "eval_json",
        "provenance": provenance,
    }
    return metric, None


def _worst(states: list[tuple[str, str | None]]) -> tuple[str, str | None]:
    best: tuple[str, str | None] = (HEALTHY, None)
    for state, reason in states:
        if _SEVERITY[state] > _SEVERITY[best[0]]:
            best = (state, reason)
    return best


def _recommendations(
    scan: _ScanResult,
    no_match: dict[str, Any],
    decision_source: dict[str, Any],
    near_miss: dict[str, Any],
    thresholds: ObserveThresholds,
) -> list[str]:
    recs: list[str] = []
    if scan.n_corrupt > thresholds.max_corrupt:
        recs.append(
            f"repair or rotate the spans JSONL: {scan.n_corrupt} corrupt line(s) were skipped"
        )
    if scan.n_unparsed_metadata > 0:
        recs.append(
            f"fix span producers: {scan.n_unparsed_metadata} metadata payload(s) were unparseable"
        )
    if decision_source["state"] in (WARN, CRITICAL):
        recs.append(
            "inspect route spans whose metadata.layer is missing or non-enum (producer contract drift)"
        )
    if no_match["state"] in (WARN, CRITICAL):
        recs.append("inspect fallback_llm route spans before changing routing thresholds")
    if near_miss["state"] == NOT_REQUESTED:
        recs.append(
            "supply --eval-json from scripts/eval_routing.py --hermetic --json "
            "to evaluate near-miss over-injection"
        )
    elif near_miss.get("provenance") and near_miss["provenance"].get("hermetic") is False:
        recs.append(
            "re-run scripts/eval_routing.py with --hermetic; non-hermetic evidence "
            "is rejected as invalid_eval_provenance"
        )
    recs.append(
        "this report is report-only: do not change hermetic --check exit codes or routing policy from it alone"
    )
    return recs


def observe_routing(
    spans_path: Path,
    *,
    since: str | None = None,
    until: str | None = None,
    project_id: str | None = None,
    eval_json: Path | None = None,
    expected_eval_dataset: str = DEFAULT_EVAL_DATASET,
    thresholds: ObserveThresholds | None = None,
    strict_payloads: bool = False,
    require_inputs: bool = False,
    report_only: bool = False,
    now: datetime | None = None,
) -> ObserveResult:
    """Read the requested evidence and return the v1 report plus exit code.

    Raises ``ValueError`` for usage errors (bad window/thresholds); callers
    map that to exit 2. Missing inputs are ``insufficient_data`` (exit 4)
    unless ``--require-inputs`` escalates to a fault (exit 3). Unreadable or
    contract-violating inputs are faults.
    """
    resolved = thresholds or ObserveThresholds()
    validate_thresholds(resolved)
    since_dt, until_dt = parse_window(since, until)
    generated_at = (now or datetime.now(UTC)).astimezone(UTC)

    scan = _scan(spans_path, since_dt=since_dt, until_dt=until_dt, project_id=project_id)
    # Freshness is evaluated against the injected ``now`` and is intentionally
    # independent of the --since/--until span window: the eval payload is a
    # separate static-dataset run, not a stream filtered by that window.
    near_miss, eval_error = _near_miss_metric(
        eval_json,
        resolved,
        expected_eval_dataset=expected_eval_dataset,
        now=generated_at,
    )

    fault: ObserveError | None = None
    if scan.error_kind in ("unreadable_input", "io_error"):
        fault = ObserveError(
            kind=scan.error_kind,
            path=str(spans_path),
            message="spans file exists but could not be read",
        )
    elif eval_error is not None and eval_error.kind in (
        "invalid_eval_payload",
        "invalid_eval_provenance",
        "io_error",
    ):
        fault = eval_error
    elif require_inputs and ((scan.error_kind == "missing_input") or (eval_error is not None)):
        missing_path = (
            str(spans_path)
            if scan.error_kind == "missing_input"
            else (eval_error.path if eval_error is not None else str(spans_path))
        )
        fault = ObserveError(
            kind="missing_input",
            path=missing_path,
            message="--require-inputs: a requested input is missing",
        )
    if strict_payloads and fault is None and (scan.n_corrupt > 0 or scan.n_unparsed_metadata > 0):
        fault = ObserveError(
            kind="payload_rejected",
            path=str(spans_path),
            message=(
                f"--strict-payloads: {scan.n_corrupt} corrupt and "
                f"{scan.n_unparsed_metadata} unparsed metadata payload(s)"
            ),
        )

    no_match = _no_match_metric(scan, resolved)
    decision_source = _decision_source_metric(scan, resolved)

    participating: list[tuple[str, str | None]] = [
        (no_match["state"], no_match["reason"]),
        (decision_source["state"], decision_source["reason"]),
    ]
    if eval_json is not None:
        participating.append((near_miss["state"], near_miss["reason"]))
    # Corrupt lines are a participating warn signal so they floor the rollup
    # at warn ("at least warn") while never overriding a critical metric.
    if scan.n_corrupt > resolved.max_corrupt:
        participating.append((WARN, "corrupt_payloads"))
    overall_state, overall_reason = _worst(participating)

    coverage = _ratio(scan.n_scored, scan.n_route)
    coverage_state = (
        HEALTHY if coverage is not None and coverage >= resolved.min_coverage else INSUFFICIENT
    )

    if fault is not None:
        overall_state = "fault"
        overall_reason = fault.kind

    exit_code = 0
    if fault is not None or overall_state == CRITICAL:
        exit_code = 3
    elif overall_state == WARN:
        exit_code = 1
    elif overall_state == INSUFFICIENT:
        exit_code = 4
    if report_only and fault is None:
        exit_code = 0

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "overall_state": overall_state,
        "exit_code": exit_code,
        "outcome": {
            "kind": "fault" if fault is not None else "verdict",
            "reason": overall_reason,
        },
        "window": {
            "active": since_dt is not None or until_dt is not None,
            "since": since_dt.isoformat() if since_dt is not None else None,
            "until": until_dt.isoformat() if until_dt is not None else None,
            "timezone": "UTC",
        },
        "filters": {"project_id": project_id},
        "inputs": {
            "spans_path": str(spans_path),
            "spans_mtime": _file_mtime(spans_path),
            "eval_json_path": str(eval_json) if eval_json is not None else None,
            "eval_json_mtime": _file_mtime(eval_json),
            "expected_eval_dataset": expected_eval_dataset,
            "future_skew_tolerance_seconds": FUTURE_SKEW_TOLERANCE_SECONDS,
            "registry_path": None,
        },
        "counts": {
            "n_route": scan.n_route,
            "n_hit": scan.n_hit,
            "n_nomatch": scan.n_nomatch,
            "n_scored": scan.n_scored,
            "n_unscored": scan.n_unscored,
            "n_no_ts": scan.n_no_ts,
            "n_corrupt": scan.n_corrupt,
            "n_unparsed_metadata": scan.n_unparsed_metadata,
        },
        "coverage": {
            "scoring_coverage": _round4(coverage),
            "min_coverage": resolved.min_coverage,
            "state": coverage_state,
        },
        "metrics": {
            "no_match": no_match,
            "near_miss": near_miss,
            "decision_source": decision_source,
        },
        "registry": None,
        "thresholds": {
            "min_samples": resolved.min_samples,
            "min_samples_near_miss": resolved.min_samples_near_miss,
            "min_coverage": resolved.min_coverage,
            "nomatch_warn": resolved.nomatch_warn,
            "nomatch_crit": resolved.nomatch_crit,
            "near_miss_warn": resolved.near_miss_warn,
            "near_miss_crit": resolved.near_miss_crit,
            "unknown_warn": resolved.unknown_warn,
            "unknown_crit": resolved.unknown_crit,
            "max_corrupt": resolved.max_corrupt,
            "max_eval_age_hours": resolved.max_eval_age_hours,
        },
        "recommendations": _recommendations(scan, no_match, decision_source, near_miss, resolved),
    }
    if fault is not None:
        report_error: ObserveError | None = fault
    elif scan.error_kind == "missing_input":
        report_error = ObserveError(
            kind="missing_input",
            path=str(spans_path),
            message="spans file does not exist",
        )
    else:
        report_error = eval_error
    if report_error is not None:
        report["error"] = {
            "kind": report_error.kind,
            "path": report_error.path,
            "message": report_error.message,
        }
    return ObserveResult(report=report, exit_code=exit_code, fault=fault is not None)


def render_human(report: dict[str, Any]) -> str:
    """Deterministic multi-line human block (no ANSI, no Rich markup)."""
    lines: list[str] = []
    lines.append(f"routing observation ({SCHEMA} v{SCHEMA_VERSION})")
    lines.append(f"generated_at: {report['generated_at']}")
    window = report["window"]
    lines.append(
        "window: active={active} since={since} until={until} timezone={timezone}".format(**window)
    )
    lines.append(f"overall_state: {report['overall_state']} (exit {report['exit_code']})")
    if "error" in report:
        err = report["error"]
        lines.append(f"error: {err['kind']} path={err['path']} message={err['message']}")
    counts = report["counts"]
    lines.append("counts: " + " ".join(f"{key}={value}" for key, value in counts.items()))
    coverage = report["coverage"]
    lines.append(
        "coverage: scoring_coverage={scoring_coverage} min_coverage={min_coverage} "
        "state={state}".format(**coverage)
    )
    nm = report["metrics"]["no_match"]
    lines.append(
        "no_match: n={n} d={d} rate={rate} wilson95=[{wilson95_low}, {wilson95_high}] "
        "state={state} reason={reason}".format(**nm)
    )
    near = report["metrics"]["near_miss"]
    lines.append(
        "near_miss: n={n} d={d} rate={rate} state={state} reason={reason} source={source}".format(
            **near
        )
    )
    ds = report["metrics"]["decision_source"]
    lines.append(
        "decision_source: unknown_share={unknown_share} "
        "unknown_share_of_route={unknown_share_of_route} layer_coverage={layer_coverage} "
        "state={state} reason={reason}".format(**ds)
    )
    lines.append(f"by_layer: {json.dumps(ds['by_layer'], ensure_ascii=False, sort_keys=True)}")
    lines.append("recommendations:")
    for rec in report["recommendations"]:
        lines.append(f"  - {rec}")
    return "\n".join(lines)
