#!/usr/bin/env python3
"""Aggregate the production no-match rate over route spans (evo lane D2b).

Report-only observer (direction D item 3): turns ``.vibe/observability/
spans.jsonl`` into a windowed no-match rate with a Wilson 95% CI, so
"no match is a success" becomes a number instead of a slogan. Fail-soft
by design — a missing spans file is exit 0 + ``{"error": "missing_spans"}``,
never a red light.

Selection lens (same as behavior_consistency.py:120-131): spans whose
``name`` starts with ``route:``. No span_kind / mode filtering — spans
from non-routing paths (``slash_command``, ``not_intercepted``) carry no
scoring fields and fall out as ``unscored`` on their own.

Scoring is field-first ("use what's readable"), matching producer
semantics (agent_runtime.py step 6 / cli/main.py span block):

1. ``metadata.has_match`` is a bool → no-match iff False. Covers both
   true no-match and all-fallback routing (gold_detection.py:114-116).
2. else ``metadata.skill_id`` (fallback key: ``primary``) is a str →
   no-match iff empty (producers write "" on miss).
3. else ``metadata.layer`` is a non-empty str → no-match iff
   ``fallback_llm`` (no skill survived; any real layer means a primary
   existed).
4. else the span is skipped and counted as ``unscored``.

``metadata`` may be a dict or a JSON string (SpanWriter serialises it —
verified against real spans.jsonl). Corrupt lines are skipped silently
(same convention as tool_call_bridge._load_route_spans).

Windowing: ``--since`` ISO8601 compares against ``started_at`` (legacy
``timestamp`` fallback); naive values are read as UTC. A span with no
usable timestamp cannot be proven inside the window and is dropped
(counted as ``n_no_ts``); without ``--since`` every route span counts.

Usage:
    uv run python scripts/aggregate_nomatch.py [--spans PATH] [--since ISO8601] [--json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any

MISSING_SPANS_ERROR = "missing_spans"
#: Layer bucket for no-match spans that carry no ``layer`` key (gate18
#: convention: ScanSummary.miss_share_by_layer buckets missing as "unknown").
UNKNOWN_LAYER = "unknown"
#: The router's no-match sentinel layer (unified with the D3 yaml-gate
#: vocabulary: primary empty / fallback_llm both mean "no real skill").
FALLBACK_LLM_LAYER = "fallback_llm"


def _parse_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Best-effort metadata dict: dict passes through, JSON string is
    decoded, anything else (or undecodable) is empty."""
    meta = record.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            return {}
    return meta if isinstance(meta, dict) else {}


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
    """``started_at`` first, legacy ``timestamp`` fallback (_span_fields
    convention)."""
    return _parse_ts(record.get("started_at")) or _parse_ts(record.get("timestamp"))


def _score_no_match(meta: dict[str, Any]) -> bool | None:
    """Field-first no-match verdict: True=no-match, False=hit, None=unscored."""
    has_match = meta.get("has_match")
    if isinstance(has_match, bool):
        return not has_match
    primary = meta["skill_id"] if "skill_id" in meta else meta.get("primary")
    if isinstance(primary, str):
        return primary == ""
    layer = meta.get("layer")
    if isinstance(layer, str) and layer:
        return layer == FALLBACK_LLM_LAYER
    return None


def wilson_interval(k: int, n: int, z: float | None = None) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials (95% by default).

    Pure stdlib (NormalDist.inv_cdf); returns (0.0, 0.0) for n == 0.
    """
    if n <= 0:
        return 0.0, 0.0
    if z is None:
        z = NormalDist().inv_cdf(0.975)
    p = k / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return (max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom))


def aggregate(
    spans_path: Path,
    since: str | None = None,
) -> dict[str, Any]:
    """Read spans.jsonl and return the windowed no-match report dict.

    Never raises on missing/unreadable files or corrupt lines (fail-soft
    observer); a missing file is reported as ``{"error": ...}``.
    """
    if not spans_path.exists():
        return {"error": MISSING_SPANS_ERROR, "n_route": 0}

    since_dt = _parse_ts(since) if since else None
    if since and since_dt is None:
        raise ValueError(f"--since is not a valid ISO8601 timestamp: {since!r}")

    n_route = n_nomatch = n_hit = n_unscored = n_no_ts = n_corrupt = 0
    nomatch_by_layer: Counter[str] = Counter()
    try:
        with spans_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
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
                if since_dt is not None:
                    ts = _span_ts(record)
                    if ts is None:
                        n_no_ts += 1
                        continue
                    if ts < since_dt:
                        continue
                n_route += 1
                meta = _parse_metadata(record)
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
    except OSError:
        return {"error": "unreadable_spans", "n_route": 0}

    n_scored = n_nomatch + n_hit
    rate = n_nomatch / n_route if n_route else 0.0
    rate_scored = n_nomatch / n_scored if n_scored else 0.0
    low, high = wilson_interval(n_nomatch, n_route)
    return {
        "spans_path": str(spans_path),
        "since": since,
        "n_route": n_route,
        "n_hit": n_hit,
        "n_nomatch": n_nomatch,
        "n_scored": n_scored,
        "n_unscored": n_unscored,
        "n_no_ts": n_no_ts,
        "n_corrupt": n_corrupt,
        "rate": round(rate, 4),
        "rate_scored": round(rate_scored, 4),
        "wilson95_low": round(low, 4),
        "wilson95_high": round(high, 4),
        "nomatch_by_layer": dict(nomatch_by_layer),
    }


def _human_line(report: dict[str, Any]) -> str:
    if "error" in report:
        return (
            f"spans unavailable ({report['error']}); n_route={report.get('n_route', 0)} "
            "(fail-soft, nothing to aggregate)"
        )
    window = report.get("since") or "all"
    return (
        f"spans={report['spans_path']} window={window} "
        f"n_route={report['n_route']} n_nomatch={report['n_nomatch']} "
        f"rate={report['rate']:.4f} wilson95=[{report['wilson95_low']:.4f}, "
        f"{report['wilson95_high']:.4f}] "
        f"(n_hit={report['n_hit']} unscored={report['n_unscored']} "
        f"rate_scored={report['rate_scored']:.4f})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate the windowed no-match rate over production route spans "
        "(fail-soft, report-only)."
    )
    parser.add_argument(
        "--spans",
        type=Path,
        default=Path.cwd() / ".vibe" / "observability" / "spans.jsonl",
        help="spans file (default: <cwd>/.vibe/observability/spans.jsonl).",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="ISO8601 lower bound on span started_at (default: whole file).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the full report as JSON (default: one human-readable line).",
    )
    args = parser.parse_args(argv)

    try:
        report = aggregate(args.spans, since=args.since)
    except ValueError as exc:
        parser.error(str(exc))
        return 2  # unreachable — parser.error exits

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(_human_line(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
