"""M12 M4 — read-model assembly for the dashboard Discoveries page.

Read-only by design (``.omx/artifacts/m12-product-design.md`` v3, M4:
变更操作 promote/dismiss/mute 只在 CLI，看板不写——保人审闸门单入口).
This module only READS the candidate pool and signal stores; it exposes
no mutation helpers and the endpoint performs no writes (``build_queue``
is called with ``observe=False`` so even cooling bookkeeping is skipped).

Data sources (same stores the ``vibe skill discover`` CLI reads):

- ``ClusterCandidateStore`` — pending candidates (stable + unstable, all
  admission sources), from BOTH scopes: project
  (``<project_root>/.vibe/observability``) and global
  (``~/.vibe/observability``). Same cluster_id in both scopes is deduped
  preferring the more heterogeneous record (same rule as the CLI's
  ``_gather_scoped_candidates``).
- ``DiscoverySignalStore`` — sticky negative list + active mutes. The
  union of BOTH scopes' signals applies to every card (a fingerprint
  dismissed once is dismissed everywhere — CLI parity).
- ``DiscoveryObservationStore`` — cooling detection only (read).

Aggregate header stats cover counts derived from the cards themselves
(status / scope / source / cooling). Scan-level stats
(``ScanSummary.embedding_degraded`` / miss-pool sizes) are deliberately
OMITTED: ``scan_candidates`` prints the summary to the console but never
persists it, so there is no honest on-disk source — and running a scan
from a GET endpoint is out of the question (expensive + mutating).

Fresh-project tolerance: every store read is guarded by a file-existence
check. The stores create their storage dir on construction, so an
unguarded construction would make this "read-only" endpoint create
``.vibe/observability/`` in a fresh project. With the guards, missing
stores yield empty lists, never 500 and never new directories.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from vibesop.core.observability.discovery import (
    DiscoveryObservationStore,
    DiscoveryRow,
    DiscoverySignalStore,
    build_queue,
)
from vibesop.core.observability.skill_promote import (
    ClusterCandidate,
    ClusterCandidateStore,
    dedupe_project_distribution,
    sanitize_body_text,
)
from vibesop.utils.redaction import redact_sensitive

__all__ = ["CLI_HINT", "build_discoveries_payload"]

Scope = Literal["project", "global"]

_SCOPES: tuple[Scope, ...] = ("project", "global")

# Read-only contract made explicit on every card (and in the UI banner).
CLI_HINT = (
    "看板只读 —— 变更操作请使用 CLI：`vibe skill discover` 查看队列 · "
    "`vibe skill promote <id>` 起草 SKILL.md · `vibe skill discover dismiss <id>` 否决 · "
    "`vibe skill discover --mute <id>` 静音"
)

_MAX_EXAMPLES = 3  # example queries per card
_MAX_TOP_STEPS = 5  # step labels per card
_PATTERN_MAX_LEN = 120  # pattern summary truncation


def _display_text(text: str, max_len: int = 200) -> str:
    """Redact + single-line collapse + truncate for card display.

    Queries are already redacted at the write side (集中脱敏); this is the
    display-side second pass so a hand-edited store file cannot leak
    secrets into the browser (same defence as the CLI's ``_redact_query``,
    built on ``skill_promote.sanitize_body_text``).
    """
    return sanitize_body_text(redact_sensitive(str(text)), max_len=max_len)


def _scope_dirs(project_root: Path) -> dict[Scope, Path]:
    """Observability dirs per scope (mirrors the CLI's store scoping)."""
    return {
        "project": project_root / ".vibe" / "observability",
        "global": Path.home() / ".vibe" / "observability",
    }


def _load_scoped_candidates(
    scope_dirs: dict[Scope, Path],
) -> dict[str, tuple[Scope, ClusterCandidate]]:
    """Pending candidates from both scopes, deduped by cluster_id.

    Dedup prefers the more heterogeneous record (larger
    ``project_distribution``); on a tie the project scope wins (``_SCOPES``
    iterates project-first and only a strictly larger distribution
    replaces). This rule MUST stay in lockstep with its CLI counterpart
    ``_gather_scoped_candidates`` in
    ``vibesop.cli.commands.skill_commands`` (which points back here) —
    if one side drifts, the board and ``vibe skill discover`` disagree
    on which record a duplicated cluster_id shows.
    """
    by_id: dict[str, tuple[Scope, ClusterCandidate]] = {}
    for scope in _SCOPES:
        obs_dir = scope_dirs[scope]
        # Guard keeps the endpoint read-only: ClusterCandidateStore
        # mkdirs its storage dir on construction.
        if not (obs_dir / ClusterCandidateStore.FILENAME).exists():
            continue
        for candidate in ClusterCandidateStore(obs_dir).list_pending(include_unstable=True):
            existing = by_id.get(candidate.cluster_id)
            if existing is None or len(candidate.project_distribution) > len(
                existing[1].project_distribution
            ):
                by_id[candidate.cluster_id] = (scope, candidate)
    return by_id


def _load_signal_unions(
    scope_dirs: dict[Scope, Path], now: datetime
) -> tuple[set[str], dict[str, datetime]]:
    """Union of both scopes' dismissed fingerprints + active mutes.

    Cross-scope wiring matches the CLI (gate17 claude nit 1 / pi nit 3):
    a fingerprint dismissed/muted in either scope's store applies
    everywhere — same fingerprint, one dismissal.
    """
    dismissed: set[str] = set()
    mutes: dict[str, datetime] = {}
    for scope in _SCOPES:
        obs_dir = scope_dirs[scope]
        if not (obs_dir / DiscoverySignalStore.FILENAME).exists():
            continue
        store = DiscoverySignalStore(obs_dir)
        dismissed |= store.dismissed_fingerprints()
        mutes.update(store.active_mutes(now))
    return dismissed, mutes


def _row_to_card(scope: Scope, row: DiscoveryRow) -> dict[str, Any]:
    """Serialize one DiscoveryRow to the JSON card shape."""
    candidate = row.candidate
    examples = [_display_text(q) for q in candidate.queries if str(q).strip()]
    top_steps = [
        {"name": _display_text(name, max_len=80), "label": label}
        for name, label in sorted(
            candidate.step_labels.items(),
            key=lambda kv: (-candidate.step_freq.get(kv[0], 0), kv[0]),
        )[:_MAX_TOP_STEPS]
    ]
    if row.dismissed:
        status = "dismissed"
    elif row.muted:
        status = "muted"
    else:
        status = "pending"
    return {
        "cluster_id": candidate.cluster_id,
        "cluster_id_short": candidate.cluster_id[:8],
        "scope": scope,
        "status": status,
        "mute_expires_at": row.mute_expires_at.isoformat() if row.mute_expires_at else None,
        "cooling": row.cooling,
        "is_unstable": candidate.is_unstable,
        "is_cross_project": candidate.is_cross_project,
        "score": round(row.score, 2),
        "source": row.source,
        "behavior_evidence": row.behavior,
        "pattern_summary": (
            _display_text(candidate.queries[0], max_len=_PATTERN_MAX_LEN)
            if candidate.queries
            else ""
        ),
        "evidence": {
            "span_count": candidate.span_count,
            "distinct_task_keys": len(candidate.task_ids),
            "gold_rate": round(candidate.gold_rate, 2),
            "gold_task_count": len(candidate.gold_task_ids),
        },
        "example_queries": examples[:_MAX_EXAMPLES],
        "top_steps": top_steps,
        "age_days": row.age_days,
        "created_at": candidate.created_at.isoformat(),
        "ttl_expires_at": (
            candidate.ttl_expires_at.isoformat() if candidate.ttl_expires_at else None
        ),
        # Basename-only redaction: absolute paths never leave the store
        # (dedupe_project_distribution is the same privacy boundary the
        # CLI's JSON output uses).
        "project_distribution": dedupe_project_distribution(candidate.project_distribution),
        "cli_hint": CLI_HINT,
    }


def build_discoveries_payload(project_root: Path) -> dict[str, Any]:
    """Assemble the ``GET /api/discoveries`` response body.

    Read-only: no scans, no observation writes, no store creation.
    Missing stores (fresh project, no global pool) yield empty lists.
    Cards are sorted by ``evidence_score`` desc — same ordering as
    ``vibe skill discover``.
    """
    now = datetime.now(UTC)
    scope_dirs = _scope_dirs(project_root)
    by_id = _load_scoped_candidates(scope_dirs)
    dismissed_union, mutes_union = _load_signal_unions(scope_dirs, now)

    scoped_rows: list[tuple[Scope, DiscoveryRow]] = []
    for scope in _SCOPES:
        group = [c for s, c in by_id.values() if s == scope]
        if not group:
            continue
        obs_dir = scope_dirs[scope]
        rows = build_queue(
            group,
            DiscoverySignalStore(obs_dir),
            DiscoveryObservationStore(obs_dir),
            now=now,
            observe=False,  # read-only render — no growth bookkeeping from a GET
            extra_dismissed=dismissed_union,
            extra_mutes=mutes_union,
        )
        scoped_rows.extend((scope, row) for row in rows)
    scoped_rows.sort(
        key=lambda pair: (pair[1].score, pair[1].candidate.span_count, pair[1].candidate.cluster_id),
        reverse=True,
    )

    cards = [_row_to_card(scope, row) for scope, row in scoped_rows]

    def _count(key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for card in cards:
            value = str(card[key])
            counts[value] = counts.get(value, 0) + 1
        return counts

    return {
        "generated_at": now.isoformat(),
        "cli_hint": CLI_HINT,
        "stats": {
            "total": len(cards),
            "by_status": _count("status"),
            "by_scope": _count("scope"),
            "by_source": _count("source"),
            "cooling": sum(1 for card in cards if card["cooling"]),
        },
        "discoveries": cards,
    }
