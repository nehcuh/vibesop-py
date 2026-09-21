#!/usr/bin/env python3
"""Reproduce gate43 echo-pair rates from a spans.jsonl (locked t7 §B.0).

Why this exists
---------------
T+7 / T+14 reports were one-shot scripts that never landed. T+21 cannot
be a third vanished notebook. This file is the ledger: same predicates,
same windows, exit 0 always (report-only).

Locked predicates (gate43-t7-echo-measure.md §B.0):
  route span  = span_kind==task AND name startswith "route:"
  is_cli      = metadata.platform=="vibe-cli" OR metadata.source=="cli"
  pair        = same task_id, (hook h, cli c), c.ts > h.ts, all combinations
  anchor      = c.ts
  echo        = h.has_match is True AND (c.ts - h.ts) <= 90s
  wide        = all pairs

Windows (UTC):
  baseline  anchor <= 2026-08-24T00:00Z   denom 30.05 d
  T+7       (T0, T+7]                     denom 7 d
  T+14 post (T+7, T+14]                   denom 7 d
  T+21 post (T+14, T+21]                  denom 7 d

T0 = 2026-08-24T10:42Z.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vibesop.core.observability._span_fields import span_timestamp  # noqa: E402
from vibesop.core.observability.tool_call_bridge import (  # noqa: E402
    _CLI_PLATFORM,
    _parse_dt,
)

T0 = datetime(2026, 8, 24, 10, 42, tzinfo=UTC)
T7 = T0 + timedelta(days=7)
T14 = T0 + timedelta(days=14)
T21 = T0 + timedelta(days=21)
BASELINE_END = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)
BASELINE_DAYS = 30.05
ECHO_DT = timedelta(seconds=90)


def _meta(record: dict[str, Any]) -> dict[str, Any]:
    meta = record.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}
    return meta if isinstance(meta, dict) else {}


def load_route_spans(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get("span_kind") != "task":
                continue
            name = rec.get("name")
            if not isinstance(name, str) or not name.startswith("route:"):
                continue
            ts = _parse_dt(span_timestamp(rec))
            if ts is None:
                continue
            task_id = rec.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                continue
            meta = _meta(rec)
            has_raw = meta.get("has_match")
            has_match = bool(has_raw) if has_raw is not None else None
            is_cli = meta.get("platform") == _CLI_PLATFORM or meta.get("source") == "cli"
            session = rec.get("session_id")
            out.append(
                {
                    "ts": ts,
                    "task_id": task_id,
                    "is_cli": bool(is_cli),
                    "has_match": has_match,
                    "session_id": session if isinstance(session, str) else None,
                    "platform": meta.get("platform"),
                }
            )
    return out


def pairs(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sp in spans:
        by_task[sp["task_id"]].append(sp)
    found: list[dict[str, Any]] = []
    for group in by_task.values():
        hooks = [s for s in group if not s["is_cli"]]
        clis = [s for s in group if s["is_cli"]]
        for h in hooks:
            for c in clis:
                if c["ts"] <= h["ts"]:
                    continue
                dt = c["ts"] - h["ts"]
                found.append(
                    {
                        "anchor": c["ts"],
                        "dt": dt,
                        "echo": h["has_match"] is True and dt <= ECHO_DT,
                        "h_match": h["has_match"],
                        "h_platform": h["platform"],
                        "c_platform": c["platform"],
                        "cross_session": (
                            h["session_id"] is not None
                            and c["session_id"] is not None
                            and h["session_id"] != c["session_id"]
                        ),
                    }
                )
    return found


def in_window(anchor: datetime, start: datetime | None, end: datetime) -> bool:
    if start is None:
        return anchor <= end
    return start < anchor <= end


def poisson_ci(k: int) -> tuple[float, float]:
    """Normal 95% interval around a Poisson count (report-only)."""
    z = 1.959963984540054
    if k == 0:
        return (0.0, 3.689)
    lo = 0.5 * (z**2) + k - z * math.sqrt(k + 0.25 * z**2)
    hi = 0.5 * (z**2) + k + z * math.sqrt(k + 0.25 * z**2)
    return (max(0.0, lo), hi)


def summarise(found: list[dict[str, Any]], start: datetime | None, end: datetime, days: float) -> dict[str, Any]:
    windowed = [p for p in found if in_window(p["anchor"], start, end)]
    echo = [p for p in windowed if p["echo"]]
    dts = sorted(p["dt"].total_seconds() for p in echo)
    p50 = dts[len(dts) // 2] if dts else None
    by_day: dict[str, int] = defaultdict(int)
    for p in echo:
        by_day[p["anchor"].date().isoformat()] += 1
    ci = poisson_ci(len(echo))
    return {
        "n_wide": len(windowed),
        "n_echo": len(echo),
        "wide_per_day": round(len(windowed) / days, 2),
        "echo_per_day": round(len(echo) / days, 2),
        "echo_p50_s": p50,
        "echo_ci95_count": [round(ci[0], 1), round(ci[1], 1)],
        "echo_ci95_per_day": [round(ci[0] / days, 2), round(ci[1] / days, 2)],
        "echo_by_day": dict(sorted(by_day.items())),
        "echo_cross_session": sum(1 for p in echo if p["cross_session"]),
        "days": days,
    }


def rails(spans: list[dict[str, Any]], start: datetime, end: datetime, days: float) -> dict[str, Any]:
    window = [s for s in spans if start < s["ts"] <= end]
    hooks = [s for s in window if not s["is_cli"]]
    clis = [s for s in window if s["is_cli"]]
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in spans:
        by_task[s["task_id"]].append(s)
    single_hooks = 0
    for h in hooks:
        clis_task = [s for s in by_task[h["task_id"]] if s["is_cli"] and s["ts"] > h["ts"]]
        if not any((c["ts"] - h["ts"]) <= ECHO_DT for c in clis_task):
            single_hooks += 1
    divergent = 0
    cli_only = 0
    slow = 0
    for c in clis:
        if c["has_match"] is not False:
            continue
        prev = [s for s in by_task[c["task_id"]] if (not s["is_cli"]) and s["ts"] < c["ts"]]
        if not prev:
            cli_only += 1
            continue
        h = max(prev, key=lambda s: s["ts"])
        dt = c["ts"] - h["ts"]
        if h["has_match"] is True and dt <= timedelta(seconds=300):
            divergent += 1
        elif dt > timedelta(seconds=300):
            slow += 1
        else:
            cli_only += 1
    return {
        "hook_per_day": round(len(hooks) / days, 1),
        "cli_per_day": round(len(clis) / days, 1),
        "hook_single_per_day": round(single_hooks / days, 1),
        "divergent": divergent,
        "cli_miss_cli_only": cli_only,
        "cli_miss_slow": slow,
        "humanish_cli_miss": cli_only + slow,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spans",
        type=Path,
        default=Path.home() / "Projects/cmspark/.vibe/observability/spans.jsonl",
    )
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if not args.spans.is_file():
        print(f"missing spans: {args.spans}", file=sys.stderr)
        return 2
    spans = load_route_spans(args.spans)
    found = pairs(spans)
    payload = {
        "spans_file": str(args.spans),
        "n_route_spans": len(spans),
        "n_pairs": len(found),
        "baseline": summarise(found, None, BASELINE_END, BASELINE_DAYS),
        "t7": summarise(found, T0, T7, 7.0),
        "t14_post": summarise(found, T7, T14, 7.0),
        "t21_post": summarise(found, T14, T21, 7.0),
        "rails_t7": rails(spans, T0, T7, 7.0),
        "rails_t14": rails(spans, T7, T14, 7.0),
        "rails_t21": rails(spans, T14, T21, 7.0),
        "t0": T0.isoformat(),
        "t21": T21.isoformat(),
    }
    text = json.dumps(payload, indent=2, default=str)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
