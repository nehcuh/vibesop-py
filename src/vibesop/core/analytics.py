"""Usage analytics and feedback collection for orchestration.

Records execution data, user feedback, and skill quality metrics
to enable continuous improvement of the routing system.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vibesop.utils.redaction import redact_sensitive

logger = logging.getLogger(__name__)

_RAPID_REROUTE_SECONDS = 10.0
_OVERLAP_THRESHOLD = 0.5
_HASH_LENGTH = 16


@dataclass
class ExecutionRecord:
    """Record of a single orchestration execution."""

    query: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    mode: str = "single"  # single or orchestrated
    primary_skill: str | None = None
    plan_steps: list[str] = field(default_factory=list)
    step_count: int = 0
    duration_ms: float = 0.0
    user_modified: bool = False  # Did user edit the plan?
    user_satisfied: bool | None = None  # User feedback
    routing_layers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "primary_skill": self.primary_skill,
            "plan_steps": self.plan_steps,
            "step_count": self.step_count,
            "duration_ms": self.duration_ms,
            "user_modified": self.user_modified,
            "user_satisfied": self.user_satisfied,
            "routing_layers": self.routing_layers,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionRecord:
        return cls(
            query=data["query"],
            timestamp=data.get("timestamp", datetime.now(UTC).isoformat()),
            mode=data.get("mode", "single"),
            primary_skill=data.get("primary_skill"),
            plan_steps=data.get("plan_steps", []),
            step_count=data.get("step_count", 0),
            duration_ms=data.get("duration_ms", 0.0),
            user_modified=data.get("user_modified", False),
            user_satisfied=data.get("user_satisfied"),
            routing_layers=data.get("routing_layers", []),
            metadata=data.get("metadata", {}),
        )


class LastRouteTracker:
    """Tracks the previous route per project to derive implicit feedback signals.

    Persists ``.vibe/last_route.json`` (token hashes + skill + timestamp — no
    raw query text). Read-modify-write is serialised via a sibling ``.lock``
    file (same pattern as ``.vibe/instincts.jsonl.lock``). The state this
    process last wrote is cached in memory, so the steady-state critical
    section skips the file read entirely; cross-process interleavings degrade
    to per-process signals (best-effort telemetry, last writer wins).

    Fails open: corrupt state, lock contention, or any IO error yields no
    implicit signals and never breaks the routing/analytics main flow.
    """

    def __init__(self, storage_dir: str | Path = ".vibe") -> None:
        self.state_path = Path(storage_dir) / "last_route.json"
        self.lock_path = Path(storage_dir) / "last_route.lock"
        # In-memory copy of the state this process last wrote. While held,
        # the file read inside the lock is skipped (steady-state hot path
        # drops from stat+open+read+parse to zero reads). Cross-process
        # staleness is accepted: implicit signals are best-effort telemetry
        # about *this* session's re-routes, and a concurrent writer's state
        # being overwritten by our next write matches "last route wins".
        self._cached_state: dict[str, Any] | None = None

    def compute_and_update(
        self,
        query: str,
        skill: str | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Compute implicit signals vs. the last route, then record this one.

        Returns the signal fields to merge into the analytics event; empty
        dict on first route or any failure (silent degradation).
        """
        try:
            from vibesop.utils.file_lock import cross_process_lock

            now = now or datetime.now(UTC)
            normalized = " ".join(redact_sensitive(query).split()).lower()
            token_hashes = sorted({_hash_token(t) for t in normalized.split() if t})
            # Non-blocking: a contended lock must never stall routing (M1d);
            # the critical section is a tiny RMW so contention is rare.
            with cross_process_lock(self.lock_path, blocking=False):
                last = self._cached_state if self._cached_state is not None else self._read()
                signals = _implicit_signals(last, token_hashes, now)
                state = {
                    "token_hashes": token_hashes,
                    "skill": skill,
                    "timestamp": now.isoformat(),
                }
                self._write(state)
                # Cache only after a successful write, so a failed _write
                # (exception → silent degradation) never poisons the cache.
                self._cached_state = state
            return signals
        except Exception as e:  # telemetry must never break routing
            logger.debug("Implicit feedback signals unavailable: %s", e)
            return {}

    def _read(self) -> dict[str, Any] | None:
        """Read last-route state; corrupt/missing state returns None (self-heals
        on the next ``_write``). Single open — no ``exists()`` pre-check."""
        try:
            with self.state_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _write(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)


def _hash_token(token: str) -> str:
    """Per-token hash so Jaccard overlap can be computed without storing raw
    query text (hashed-set equality matches raw-set equality)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:_HASH_LENGTH]


def _implicit_signals(
    last: dict[str, Any] | None,
    token_hashes: list[str],
    now: datetime,
) -> dict[str, Any]:
    """Derive implicit quality signals from the previous route state."""
    if not last:
        return {}

    signals: dict[str, Any] = {}
    try:
        last_ts = datetime.fromisoformat(str(last["timestamp"]))
        # Clamp clock skew (e.g. NTP rollback) to 0 instead of reporting
        # negative seconds.
        seconds = max(0.0, (now - last_ts).total_seconds())
        signals["seconds_since_last_route"] = round(seconds, 3)
        signals["is_rapid_reroute"] = seconds < _RAPID_REROUTE_SECONDS
    except (KeyError, TypeError, ValueError):
        pass

    last_tokens = set(last.get("token_hashes") or [])
    if last_tokens and token_hashes:
        union = last_tokens | set(token_hashes)
        jaccard = len(last_tokens & set(token_hashes)) / len(union)
        signals["query_overlap_with_last"] = jaccard > _OVERLAP_THRESHOLD

    return signals


class AnalyticsStore:
    """Persistent store for execution analytics.

    Stores records as JSONL in .vibe/analytics.jsonl
    """

    def __init__(self, storage_dir: str | Path = ".vibe") -> None:
        self.storage_path = Path(storage_dir) / "analytics.jsonl"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        # One tracker per store: previously constructed per record(), which
        # also defeated its in-memory state cache (see LastRouteTracker).
        self._last_route = LastRouteTracker(self.storage_path.parent)

    def record(self, record: ExecutionRecord) -> None:
        """Append an execution record (query redacted — F-06).

        Also merges implicit feedback signals (seconds since last route,
        rapid re-route, query overlap) derived from ``.vibe/last_route.json``
        — additive fields only, absent when unavailable (M1d).

        Hot-path IO: the analytics write itself is a bare O(1) append (no
        lock, no read). The implicit-signal update adds one non-blocking
        lock + one small JSON write; the state read is served from the
        tracker's in-memory cache in steady state, so a record costs one
        lock + two writes total instead of lock + read + two writes.
        """
        try:
            data = record.to_dict()
            data["query"] = redact_sensitive(data["query"])
            data.update(self._last_route.compute_and_update(record.query, record.primary_skill))
            with self.storage_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Failed to record analytics: %s", e)

    def clear(self) -> int:
        """Delete the analytics log (F-08). Returns records removed, 0 if absent."""
        if not self.storage_path.exists():
            return 0
        with self.storage_path.open("r", encoding="utf-8") as f:
            count = sum(1 for _ in f)
        self.storage_path.unlink()
        logger.info("Cleared analytics log: %d records", count)
        return count

    def list_records(
        self,
        limit: int = 100,
        skill_id: str | None = None,
    ) -> list[ExecutionRecord]:
        """List recent execution records."""
        if not self.storage_path.exists():
            return []

        records: list[ExecutionRecord] = []
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in reversed(lines):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    if skill_id and data.get("primary_skill") != skill_id:
                        continue
                    records.append(ExecutionRecord.from_dict(data))
                    if len(records) >= limit:
                        break
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError as e:
            logger.warning("Failed to read analytics: %s", e)

        return list(reversed(records))

    def get_skill_stats(self, skill_id: str) -> dict[str, Any]:
        """Get usage statistics for a specific skill."""
        records = self.list_records(limit=1000, skill_id=skill_id)

        if not records:
            return {"total_uses": 0, "satisfaction_rate": None}

        total = len(records)
        satisfied = sum(1 for r in records if r.user_satisfied is True)
        dissatisfied = sum(1 for r in records if r.user_satisfied is False)
        modified = sum(1 for r in records if r.user_modified)

        return {
            "total_uses": total,
            "satisfaction_rate": satisfied / total if total > 0 else None,
            "dissatisfaction_rate": dissatisfied / total if total > 0 else None,
            "modification_rate": modified / total if total > 0 else None,
            "avg_duration_ms": sum(r.duration_ms for r in records) / total if total > 0 else 0,
        }

    def get_low_quality_skills(self, threshold: float = 0.5) -> list[tuple[str, float]]:
        """Identify skills with low satisfaction rates.

        Returns list of (skill_id, satisfaction_rate) tuples.
        """
        all_records = self.list_records(limit=1000)
        skill_ids = {r.primary_skill for r in all_records if r.primary_skill}

        low_quality: list[tuple[str, float]] = []
        for skill_id in skill_ids:
            stats = self.get_skill_stats(skill_id)
            satisfaction = stats.get("satisfaction_rate")
            total = stats.get("total_uses", 0)
            if total >= 3 and satisfaction is not None and satisfaction < threshold:
                low_quality.append((skill_id, satisfaction))

        return sorted(low_quality, key=lambda x: x[1])

    def get_popular_skills(self, limit: int = 20) -> list[tuple[str, int, float]]:
        """Get most-used skills with usage counts and avg satisfaction.

        Args:
            limit: Maximum number of skills to return

        Returns:
            List of (skill_id, use_count, satisfaction_rate) sorted by use_count desc
        """
        all_records = self.list_records(limit=2000)
        skill_counts: dict[str, int] = {}
        skill_satisfaction: dict[str, list[bool]] = {}

        for record in all_records:
            if record.primary_skill:
                skill_counts[record.primary_skill] = skill_counts.get(record.primary_skill, 0) + 1
                if record.user_satisfied is not None:
                    if record.primary_skill not in skill_satisfaction:
                        skill_satisfaction[record.primary_skill] = []
                    skill_satisfaction[record.primary_skill].append(record.user_satisfied)

        result: list[tuple[str, int, float]] = []
        for skill_id, count in skill_counts.items():
            sats = skill_satisfaction.get(skill_id, [])
            avg_sat = sum(sats) / len(sats) if sats else 0.5
            result.append((skill_id, count, avg_sat))

        result.sort(key=lambda x: (-x[1], -x[2]))
        return result[:limit]


def degradation_satisfaction_analysis(
    records: list[ExecutionRecord],
) -> dict[str, dict[str, float]]:
    """Correlate routing degradation level with user satisfaction.

    Joins the ``degradation_level`` carried on each record's metadata (set by
    ``UnifiedRouter._record_execution``) with ``user_satisfied`` feedback.
    Answers: are DEGRADE/SUGGEST-level routes actually useful to users?
    """
    if not records:
        return {}

    by_level: dict[str, dict[str, float]] = {}
    for r in records:
        level = r.metadata.get("degradation_level", "unknown") if r.metadata else "unknown"
        bucket = by_level.setdefault(level, {"count": 0.0, "satisfied": 0.0, "dissatisfied": 0.0})
        bucket["count"] += 1
        if r.user_satisfied is True:
            bucket["satisfied"] += 1
        elif r.user_satisfied is False:
            bucket["dissatisfied"] += 1

    return {
        level: {
            "count": int(b["count"]),
            "satisfaction_rate": b["satisfied"] / b["count"] if b["count"] else 0.0,
            "dissatisfaction_rate": b["dissatisfied"] / b["count"] if b["count"] else 0.0,
        }
        for level, b in sorted(by_level.items())
    }
