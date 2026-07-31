"""Routing-quality pending queue (Sprint 1 — golden aha path).

Separate from ``SkillSuggestionCollector`` (workflow → skill drafts).
This store holds **route quality** items: low-confidence hits, no-matches,
and explicit user corrections waiting for accept/dismiss.

Design constraints (pi H1 + evolution final):
- Human-readable Chinese reasons
- ≤3 new pending items per calendar day (rate limit)
- Dedup: same query_hash + skill_id while still pending → no re-add
- Dismiss suppresses re-enqueue for 24h
- Accept/dismiss write back via InstinctLearner + PreferenceLearner (callers)
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from vibesop.utils.atomic_writer import write_text

logger = logging.getLogger(__name__)

__all__ = [
    "RoutingPendingItem",
    "RoutingPendingStore",
    "default_pending_path",
]

PendingKind = Literal["low_confidence", "no_match", "user_correction"]
PendingStatus = Literal["pending", "accepted", "dismissed"]

_MAX_NEW_PER_DAY = 3
_DISMISS_SUPPRESS_HOURS = 24
_LOW_CONF_THRESHOLD = 0.5


def default_pending_path(project_root: Path | None = None) -> Path:
    """Default path: ``<project>/.vibe/instincts/routing_pending.jsonl``."""
    root = project_root or Path.cwd()
    return root / ".vibe" / "instincts" / "routing_pending.jsonl"


def _now() -> datetime:
    return datetime.now(UTC)


def _day_key(dt: datetime | None = None) -> str:
    return (dt or _now()).date().isoformat()


@dataclass
class RoutingPendingItem:
    """One route-quality item awaiting human accept/dismiss."""

    id: str
    query: str
    skill_id: str | None
    confidence: float
    kind: PendingKind
    reason_zh: str
    status: PendingStatus = "pending"
    created_at: str = field(default_factory=lambda: _now().isoformat())
    resolved_at: str | None = None
    query_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "skill_id": self.skill_id,
            "confidence": self.confidence,
            "kind": self.kind,
            "reason_zh": self.reason_zh,
            "status": self.status,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "query_hash": self.query_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutingPendingItem:
        return cls(
            id=str(data["id"]),
            query=str(data.get("query", "")),
            skill_id=data.get("skill_id"),
            confidence=float(data.get("confidence", 0.0)),
            kind=data.get("kind", "low_confidence"),  # type: ignore[arg-type]
            reason_zh=str(data.get("reason_zh", "")),
            status=data.get("status", "pending"),  # type: ignore[arg-type]
            created_at=str(data.get("created_at", _now().isoformat())),
            resolved_at=data.get("resolved_at"),
            query_hash=str(data.get("query_hash", "")),
        )


class RoutingPendingStore:
    """Append-friendly JSONL store for routing pending items."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else default_pending_path()
        self._lock = threading.Lock()
        self._items: list[RoutingPendingItem] = []
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if not self._path.exists():
            self._items = []
            return
        items: list[RoutingPendingItem] = []
        try:
            for raw_line in self._path.read_text(encoding="utf-8").splitlines():
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    items.append(RoutingPendingItem.from_dict(json.loads(stripped)))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    logger.debug("skip corrupt pending row: %s", exc)
        except OSError as exc:
            logger.warning("failed to load routing pending store: %s", exc)
            items = []
        self._items = items

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(json.dumps(i.to_dict(), ensure_ascii=False) for i in self._items)
        if body:
            body += "\n"
        write_text(self._path, body)

    def list_pending(self, *, limit: int = 20) -> list[RoutingPendingItem]:
        with self._lock:
            pending = [i for i in self._items if i.status == "pending"]
            # Newest first
            pending.sort(key=lambda i: i.created_at, reverse=True)
            return pending[:limit]

    def get(self, item_id: str) -> RoutingPendingItem | None:
        with self._lock:
            for item in self._items:
                if item.id == item_id:
                    return item
            return None

    def count_created_today(self) -> int:
        """How many items were *created* today (any status) — rate limit basis."""
        today = _day_key()
        with self._lock:
            n = 0
            for item in self._items:
                try:
                    created = datetime.fromisoformat(item.created_at)
                    if _day_key(created) == today:
                        n += 1
                except ValueError:
                    continue
            return n

    def is_suppressed(self, query_hash: str, skill_id: str | None) -> bool:
        """True if a dismiss for same key happened within suppress window."""
        cutoff = _now() - timedelta(hours=_DISMISS_SUPPRESS_HOURS)
        with self._lock:
            for item in self._items:
                if item.status != "dismissed":
                    continue
                if item.query_hash != query_hash:
                    continue
                if (item.skill_id or None) != (skill_id or None):
                    continue
                try:
                    resolved = (
                        datetime.fromisoformat(item.resolved_at)
                        if item.resolved_at
                        else datetime.fromisoformat(item.created_at)
                    )
                except ValueError:
                    continue
                if resolved.tzinfo is None:
                    resolved = resolved.replace(tzinfo=UTC)
                if resolved >= cutoff:
                    return True
        return False

    def has_open(self, query_hash: str, skill_id: str | None) -> bool:
        with self._lock:
            for item in self._items:
                if item.status != "pending":
                    continue
                if item.query_hash == query_hash and (item.skill_id or None) == (
                    skill_id or None
                ):
                    return True
        return False

    def try_enqueue(
        self,
        *,
        query: str,
        skill_id: str | None,
        confidence: float,
        kind: PendingKind,
        reason_zh: str,
        query_hash: str,
    ) -> RoutingPendingItem | None:
        """Enqueue if rate limit / dedup / suppress allow. Returns item or None."""
        with self._lock:
            # Rate limit (created today, any status)
            today = _day_key()
            created_today = 0
            for item in self._items:
                try:
                    if _day_key(datetime.fromisoformat(item.created_at)) == today:
                        created_today += 1
                except ValueError:
                    continue
            if created_today >= _MAX_NEW_PER_DAY:
                logger.debug("routing pending daily cap reached (%d)", _MAX_NEW_PER_DAY)
                return None

            # Dedup open
            for item in self._items:
                if (
                    item.status == "pending"
                    and item.query_hash == query_hash
                    and (item.skill_id or None) == (skill_id or None)
                ):
                    return None

            # Suppress after dismiss
            cutoff = _now() - timedelta(hours=_DISMISS_SUPPRESS_HOURS)
            for item in self._items:
                if item.status != "dismissed":
                    continue
                if item.query_hash != query_hash:
                    continue
                if (item.skill_id or None) != (skill_id or None):
                    continue
                try:
                    resolved = (
                        datetime.fromisoformat(item.resolved_at)
                        if item.resolved_at
                        else datetime.fromisoformat(item.created_at)
                    )
                    if resolved.tzinfo is None:
                        resolved = resolved.replace(tzinfo=UTC)
                    if resolved >= cutoff:
                        return None
                except ValueError:
                    continue

            item = RoutingPendingItem(
                id=f"rp-{uuid.uuid4().hex[:12]}",
                query=query[:500],
                skill_id=skill_id,
                confidence=confidence,
                kind=kind,
                reason_zh=reason_zh,
                query_hash=query_hash,
            )
            self._items.append(item)
            self._save()
            return item

    def accept(self, item_id: str) -> RoutingPendingItem | None:
        return self._resolve(item_id, "accepted")

    def dismiss(self, item_id: str) -> RoutingPendingItem | None:
        return self._resolve(item_id, "dismissed")

    def _resolve(
        self, item_id: str, status: PendingStatus
    ) -> RoutingPendingItem | None:
        with self._lock:
            for item in self._items:
                if item.id != item_id:
                    continue
                if item.status != "pending":
                    return None
                item.status = status
                item.resolved_at = _now().isoformat()
                self._save()
                return item
            return None

    def stats(self) -> dict[str, int]:
        with self._lock:
            pending = sum(1 for i in self._items if i.status == "pending")
            accepted = sum(1 for i in self._items if i.status == "accepted")
            dismissed = sum(1 for i in self._items if i.status == "dismissed")
            today = _day_key()
            created_today = 0
            for item in self._items:
                try:
                    if _day_key(datetime.fromisoformat(item.created_at)) == today:
                        created_today += 1
                except ValueError:
                    continue
            return {
                "pending": pending,
                "accepted": accepted,
                "dismissed": dismissed,
                "created_today": created_today,
                "daily_cap": _MAX_NEW_PER_DAY,
                "total": len(self._items),
            }


# Last-resort matchers often report inflated confidence (e.g. Levenshtein
# normalized distance → 1.0). Still surface them for human review in dogfood.
_WEAK_MATCH_LAYERS = frozenset({"levenshtein", "custom", "fallback_llm"})


def build_reason_zh(
    kind: PendingKind,
    *,
    skill_id: str | None,
    confidence: float,
    layer: str | None = None,
) -> str:
    """Human-readable Chinese reason for pending list."""
    if kind == "no_match":
        return "路由未命中任何技能。请确认意图后 accept（可 --skill）或 dismiss。"
    if kind == "low_confidence":
        skill = skill_id or "（未知）"
        layer_norm = (layer or "").strip().lower()
        if layer_norm in _WEAK_MATCH_LAYERS:
            return (
                f"末层弱匹配（{layer_norm}）到 {skill}（报告置信 {confidence:.0%}，"
                f"可能虚高）。若正确请 accept，错误请 dismiss。"
            )
        return (
            f"低置信路由到 {skill}（{confidence:.0%}）。"
            f"若正确请 accept，错误请 dismiss。"
        )
    return f"用户纠正候选：{skill_id or '（无技能）'}。"


def should_enqueue_from_route(
    *,
    has_match: bool,
    confidence: float,
    threshold: float = _LOW_CONF_THRESHOLD,
    layer: str | None = None,
) -> PendingKind | None:
    """Decide whether a route result should create a pending item.

    Enqueue when:
    - no match / FALLBACK_LLM sentinel (``has_match`` false), or
    - confidence below threshold, or
    - primary layer is a weak last-resort matcher (levenshtein/custom) even if
      confidence looks high — real cmspark dogfood: nonsense queries still hit
      levenshtein@1.0 and never entered the queue under conf-only rules.
    """
    if not has_match:
        return "no_match"
    if confidence < threshold:
        return "low_confidence"
    layer_norm = (layer or "").strip().lower()
    if layer_norm in _WEAK_MATCH_LAYERS:
        return "low_confidence"
    return None
