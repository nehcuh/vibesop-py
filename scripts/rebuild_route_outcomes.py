#!/usr/bin/env python3
"""One-shot remediation (gate41 item 4): rebuild route_outcomes.jsonl.

Background: ``route_outcomes.jsonl`` is write-once — tool_call_bridge never
revises a recorded row. Historical double-hook registration (gate41 F-B)
wrote two route spans per prompt, so the outcomes derived from them are
~70% phantom reask rows. This script rebuilds the outcomes file from a
deduplicated copy of the route spans by calling the bridge's OWN derivation
functions (``_derive_outcomes`` / ``_derive_hit_outcomes``,
tool_call_bridge.py:460/:516) on the filtered material.

Hard boundaries (gate41 §3 frozen assets):
- tool_call_bridge.py is IMPORTED, never modified; ``run_bridge`` is never
  run (replayed tool events would re-emit tool_call spans into spans.jsonl).
- ``tool_call_bridge_state.json`` is never read or written.
- No discover/scan is triggered; spans.jsonl is opened read-only.
- The ONLY write target is ``route_outcomes.jsonl`` itself, and only under
  ``--apply`` (the existing file is renamed to ``.bak`` first).

Dedup/exclusion signatures (input material only — they change NO bridge
predicate and must not leak into fire-count or write-side surfaces):
- S1 (double hook / parallel fan-out): same task_id, different session_id,
  both agent=claude-code, Δt∈[0,10]s, time-cluster size=2 → keep the first.
- S2 (SESSION_ID double-forward shape): same agent=claude-code, same
  session_id, same task_id, Δt<15s, size=2 → keep the first.
- S3 (hollow ONEOFF): a route span whose session appears exactly once in
  the WHOLE spans file is excluded. session_id "default" (or missing) does
  not identify a session (grok NIT-9): such spans never join a "same
  session" judgement and are treated as once-only → excluded. This trade-off
  also drops legitimate single-query sessions (pi NIT-5, accepted: moved_on
  is impossible from a once-session span, so S3 only shrinks the reask
  numerator / expired bucket, never the moved_on denominator).
- grok×claude cross-platform same-task pairs are KEPT (legitimate
  cross-agent concurrency, product decision).

RMW WARNING (gate16b claude N3): the bridge's outcome append is
read-modify-write without a cross-process lock. Run this script during an
IDLE period (no live agent sessions, no assembly fan-out running),
otherwise a concurrent bridge run may append to the outcomes file across
the .bak swap and lose or duplicate rows.

Usage:
    uv run python scripts/rebuild_route_outcomes.py [--project-root PATH]
    uv run python scripts/rebuild_route_outcomes.py --project-root PATH --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vibesop.core.observability.tool_call_bridge import (  # noqa: E402
    OUTCOMES_FILENAME,
    BridgeStats,
    _RouteSpan,
    _derive_hit_outcomes,
    _derive_outcomes,
    _load_route_spans,
)
from vibesop.utils.atomic_writer import write_text  # noqa: E402

#: S1 window: double-hook pairs land 0.5-10.5s apart (gate41 F-B measurement);
#: Δt≈0 pairs are parallel fan-out — physically not a user re-ask.
S1_MAX_SECONDS = 10.0  # inclusive (Δt∈[0,10]s)
#: S2 window: same-session double-forward shape (Δt<15s, strict).
S2_MAX_SECONDS = 15.0  # exclusive
#: --apply is refused when the projected reask:moved_on ratio exceeds this.
RATIO_THRESHOLD = 10.0

#: Agent covered by the double-hook signatures (grok×claude pairs are kept).
_HOOK_AGENT = "claude-code"
#: session_id values that do not identify a real session (grok NIT-9).
_NON_SESSION_IDS = frozenset({"default"})

REASK_REASONS = ("reask_same_task_id", "hit_reask_same_task_id")
MOVED_ON_REASONS = ("session_continued_without_reask", "hit_session_moved_on")
# gate41 pi N4: `vibe skill outcomes` reads hit-side rows only
# (skill_outcomes.py:66-68), so the projection is reported — and the --apply
# gate enforced — on BOTH the pooled and the hit-only cuts.
HIT_REASK_REASONS = ("hit_reask_same_task_id",)
HIT_MOVED_ON_REASONS = ("hit_session_moved_on",)

QUERY_PREFIX_CHARS = 60


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild route_outcomes.jsonl from deduplicated route spans "
        "(gate41 item 4). Dry-run by default; --apply writes."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project whose .vibe/observability data is rebuilt (default: cwd).",
    )
    parser.add_argument(
        "--spans-file",
        type=Path,
        default=None,
        help="Override spans file (default: <project-root>/.vibe/observability/spans.jsonl).",
    )
    parser.add_argument(
        "--outcomes-file",
        type=Path,
        default=None,
        help="Override outcomes file "
        "(default: <project-root>/.vibe/observability/route_outcomes.jsonl).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rename the existing outcomes file to .bak and write the rebuilt one. "
        "Refused when the projected reask:moved_on ratio exceeds 10:1.",
    )
    return parser.parse_args(argv)


def _load_all_session_counts(spans_path: Path) -> Counter[str]:
    """Count session_id occurrences across ALL spans in the file.

    S3 is specified against the whole spans file (gate41: "session 在全
    spans 文件仅出现 1 次"), not only route spans — a real single-query
    session still records tool_call/child spans under the same session.
    Fault-tolerant per project JSONL convention: corrupt lines are skipped
    (same read semantics as tool_call_bridge._load_route_spans).
    """
    counts: Counter[str] = Counter()
    if not spans_path.exists():
        return counts
    with spans_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            session_id = record.get("session_id")
            if isinstance(session_id, str) and session_id:
                counts[session_id] += 1
    return counts


def _time_clusters(group: list[_RouteSpan], max_gap: float, *, inclusive: bool):
    """Yield chain-clusters of time-sorted spans: consecutive spans join one
    cluster while their gap is within ``max_gap`` seconds."""
    cluster = [group[0]]
    for span in group[1:]:
        gap = (span.started_at - cluster[-1].started_at).total_seconds()
        if gap < max_gap or (inclusive and gap == max_gap):
            cluster.append(span)
        else:
            yield cluster
            cluster = [span]
    yield cluster


def _s1_duplicates(spans: list[_RouteSpan]) -> dict[str, str]:
    """S1: same task_id, different session_id, both claude-code, Δt∈[0,10]s,
    size=2 → keep the first. Returns {dropped span_id: kept span_id}."""
    by_task: dict[str, list[_RouteSpan]] = defaultdict(list)
    for span in spans:
        if span.task_id and span.agent_id == _HOOK_AGENT and span.started_at is not None:
            by_task[span.task_id].append(span)
    drops: dict[str, str] = {}
    for group in by_task.values():
        group.sort(key=lambda s: s.started_at)
        for cluster in _time_clusters(group, S1_MAX_SECONDS, inclusive=True):
            if len(cluster) != 2:
                continue  # size=2 guard: 3+ fan-out groups are kept whole
            first, second = cluster
            # gate41 claude NIT-1: "default"/missing ids are non-identifying
            # — a "default"×real pair is NOT a proven double-hook pair, and
            # dropping the real-session leg would let S3 take the survivor.
            if (
                first.session_id
                and second.session_id
                and first.session_id not in _NON_SESSION_IDS
                and second.session_id not in _NON_SESSION_IDS
                and first.session_id != second.session_id
            ):
                drops[second.id] = first.id
    return drops


def _s2_duplicates(spans: list[_RouteSpan], already_dropped: set[str]) -> dict[str, str]:
    """S2: same claude-code agent, same session_id, same task_id, Δt<15s,
    size=2 → keep the first. Returns {dropped span_id: kept span_id}.

    session_id "default"/missing does not join the "same session" judgement
    (grok NIT-9). Historical count is zero — this guards the future
    SESSION_ID-aligned shape.
    """
    by_key: dict[tuple[str, str], list[_RouteSpan]] = defaultdict(list)
    for span in spans:
        if (
            span.task_id
            and span.agent_id == _HOOK_AGENT
            and span.started_at is not None
            and span.session_id
            and span.session_id not in _NON_SESSION_IDS
            and span.id not in already_dropped
        ):
            by_key[(span.task_id, span.session_id)].append(span)
    drops: dict[str, str] = {}
    for group in by_key.values():
        group.sort(key=lambda s: s.started_at)
        for cluster in _time_clusters(group, S2_MAX_SECONDS, inclusive=False):
            if len(cluster) == 2:
                drops[cluster[1].id] = cluster[0].id
    return drops


def _is_once_session(span: _RouteSpan, session_counts: Counter[str]) -> bool:
    """S3: the span's session appears exactly once in the whole spans file.
    "default"/missing session ids are non-identifying → once-only."""
    session_id = span.session_id
    if not session_id or session_id in _NON_SESSION_IDS:
        return True
    return session_counts.get(session_id, 0) == 1


def _filter_spans(
    spans: list[_RouteSpan], session_counts: Counter[str]
) -> tuple[list[_RouteSpan], list[tuple[str, _RouteSpan]]]:
    """Apply S1 → S2 → S3 in order. Returns (kept, [(signature, dropped span)])."""
    s1 = _s1_duplicates(spans)
    s2 = _s2_duplicates(spans, set(s1))
    kept: list[_RouteSpan] = []
    dropped: list[tuple[str, _RouteSpan]] = []
    for span in spans:
        if span.id in s1:
            dropped.append(("S1", span))
        elif span.id in s2:
            dropped.append(("S2", span))
        elif _is_once_session(span, session_counts):
            dropped.append(("S3", span))
        else:
            kept.append(span)
    return kept, dropped


def _rebuild_outcomes(route_spans: list[_RouteSpan], source_root: Path, work_root: Path):
    """Run the bridge's own derivation on the filtered copy, inside a scratch
    root (so even dry-run never writes the real project). The miss side needs
    ``.vibe/instincts/routing_pending.jsonl`` for the explicit-accept channel;
    it is copied read-only into the scratch root. Returns (lines, stats)."""
    pending = source_root / ".vibe" / "instincts" / "routing_pending.jsonl"
    if pending.exists():
        dst = work_root / ".vibe" / "instincts" / "routing_pending.jsonl"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pending, dst)
    stats = BridgeStats()
    _derive_outcomes(route_spans, work_root, stats)
    _derive_hit_outcomes(route_spans, work_root, stats)
    outcomes_path = work_root / ".vibe" / "observability" / OUTCOMES_FILENAME
    lines = outcomes_path.read_text(encoding="utf-8").splitlines() if outcomes_path.exists() else []
    return lines, stats


def _reason_counts(lines: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            reason = data.get("reason")
            counts[str(reason) if reason else "<missing>"] += 1
    return counts


def _ratio(
    counts: Counter[str],
    reask_reasons: tuple[str, ...] = REASK_REASONS,
    moved_on_reasons: tuple[str, ...] = MOVED_ON_REASONS,
) -> tuple[int, int, float]:
    """reask:moved_on projection. moved_on=0 with reask>0 is infinite (refused)."""
    reask = sum(counts[r] for r in reask_reasons)
    moved_on = sum(counts[r] for r in moved_on_reasons)
    if reask == 0:
        return reask, moved_on, 0.0
    if moved_on == 0:
        return reask, moved_on, float("inf")
    return reask, moved_on, reask / moved_on


def _print_report(
    spans_path: Path,
    outcomes_path: Path,
    spans: list[_RouteSpan],
    kept: list[_RouteSpan],
    dropped: list[tuple[str, _RouteSpan]],
    old_counts: Counter[str],
    new_counts: Counter[str],
) -> float:
    print("=== rebuild_route_outcomes (gate41 item 4) ===")
    print(f"spans file:    {spans_path}")
    print(f"outcomes file: {outcomes_path}")
    sig_counts = Counter(sig for sig, _ in dropped)
    print(f"route spans loaded: {len(spans)}")
    print(
        f"kept: {len(kept)}  dropped: {len(dropped)} "
        f"(S1={sig_counts.get('S1', 0)} S2={sig_counts.get('S2', 0)} S3={sig_counts.get('S3', 0)})"
    )

    print("\n-- dropped spans (signature, span id, query prefix) --")
    for sig, span in sorted(
        dropped,
        key=lambda d: (d[0], d[1].started_at.isoformat() if d[1].started_at else "", d[1].id),
    ):
        prefix = span.query[:QUERY_PREFIX_CHARS].replace("\n", " ")
        ts = span.started_at.isoformat() if span.started_at else "-"
        print(f"{sig}  {span.id}  {ts}  {prefix}")

    print("\n-- outcome reason counts (old -> new) --")
    print(f"{'reason':<36} {'old':>8} {'new':>8}")
    for reason in sorted(set(old_counts) | set(new_counts)):
        print(f"{reason:<36} {old_counts.get(reason, 0):>8} {new_counts.get(reason, 0):>8}")

    old_reask, old_moved, old_ratio = _ratio(old_counts)
    new_reask, new_moved, new_ratio = _ratio(new_counts)
    print(f"\ncurrent  reask:moved_on = {old_reask}:{old_moved} = {old_ratio:.2f}:1 (pooled)")
    print(f"projected reask:moved_on = {new_reask}:{new_moved} = {new_ratio:.2f}:1 (pooled)")
    old_hit = _ratio(old_counts, HIT_REASK_REASONS, HIT_MOVED_ON_REASONS)
    new_hit = _ratio(new_counts, HIT_REASK_REASONS, HIT_MOVED_ON_REASONS)
    print(f"current  reask:moved_on = {old_hit[0]}:{old_hit[1]} = {old_hit[2]:.2f}:1 (hit-only)")
    print(f"projected reask:moved_on = {new_hit[0]}:{new_hit[1]} = {new_hit[2]:.2f}:1 (hit-only)")
    worst = max(new_ratio, new_hit[2])
    verdict = "PASS" if worst <= RATIO_THRESHOLD else "FAIL"
    print(f"projection ≤ {RATIO_THRESHOLD:.0f}:1 gate (both cuts): {verdict}")
    return worst


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.project_root.resolve()
    spans_path = args.spans_file or root / ".vibe" / "observability" / "spans.jsonl"
    outcomes_path = args.outcomes_file or root / ".vibe" / "observability" / OUTCOMES_FILENAME

    if not spans_path.exists():
        print(f"no spans file at {spans_path}; nothing to rebuild")
        return 0

    spans = _load_route_spans(spans_path)
    session_counts = _load_all_session_counts(spans_path)
    kept, dropped = _filter_spans(spans, session_counts)

    old_lines = (
        outcomes_path.read_text(encoding="utf-8").splitlines() if outcomes_path.exists() else []
    )
    old_counts = _reason_counts(old_lines)

    with tempfile.TemporaryDirectory(prefix="rebuild-route-outcomes-") as tmp:
        new_lines, stats = _rebuild_outcomes(kept, root, Path(tmp))
    new_counts = _reason_counts(new_lines)

    new_ratio = _print_report(
        spans_path, outcomes_path, spans, kept, dropped, old_counts, new_counts
    )
    print(
        f"\nderivation recorded: miss={stats.outcomes_recorded} hit={stats.hit_outcomes_recorded} "
        f"({len(new_lines)} lines)"
    )

    if not args.apply:
        print("\ndry-run only; re-run with --apply (during an IDLE period) to write.")
        return 0

    if new_ratio > RATIO_THRESHOLD:
        print(
            f"\n--apply REFUSED: projected reask:moved_on {new_ratio:.2f}:1 exceeds "
            f"{RATIO_THRESHOLD:.0f}:1. Investigate the residual reask rows before rebuilding."
        )
        return 1

    # gate41 pi N5: never replace a non-empty outcomes file with an empty
    # rebuild (e.g. every span once-session → S3 excludes all) — that is a
    # data-destroying edge, not a remediation.
    if old_lines and not new_lines:
        print(
            "\n--apply REFUSED: rebuild produced 0 rows from a non-empty outcomes file. "
            "All route spans were excluded by the signatures; investigate before rebuilding."
        )
        return 1

    if outcomes_path.exists():
        backup = outcomes_path.with_name(outcomes_path.name + ".bak")
        # gate41 claude NIT-3: a second --apply must not silently destroy the
        # first backup.
        if backup.exists():
            print(
                f"\n--apply REFUSED: backup already exists at {backup}. "
                "Move or remove it before rebuilding again."
            )
            return 1
        outcomes_path.replace(backup)
        print(f"backed up: {backup}")
    outcomes_path.parent.mkdir(parents=True, exist_ok=True)
    write_text(outcomes_path, "".join(line + "\n" for line in new_lines))
    print(f"wrote {len(new_lines)} outcome rows: {outcomes_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
