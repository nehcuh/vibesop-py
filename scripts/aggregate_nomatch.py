#!/usr/bin/env python3
"""Aggregate the production no-match rate over route spans (8.4.0 compat facade).

Thin shim over :mod:`vibesop.core.observability.route_observe`. The parsing,
scoring, Wilson interval, byte-level decode, BOM/CRLF handling, and fail-soft
file errors now live in the library; this script keeps the exact 8.4.0 CLI
contract so existing docs, cron jobs, and tests keep working:

- missing spans file -> exit 0 + ``{"error": "missing_spans", "n_route": 0}``
- unreadable spans path -> exit 0 + ``{"error": "unreadable_spans", "n_route": 0}``
- invalid ``--since`` -> argparse exit 2 (validated before the file is read)
- corrupt lines are ``n_corrupt``, never a ``UnicodeDecodeError``

Usage:
    uv run python scripts/aggregate_nomatch.py [--spans PATH] [--since ISO8601] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from vibesop.core.observability.route_observe import (  # noqa: E402
    _human_line,
    aggregate,
    wilson_interval,
)

__all__ = ["aggregate", "main", "wilson_interval"]


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
