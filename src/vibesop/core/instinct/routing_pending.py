"""Routing-quality pending queue (Sprint 1 — golden aha path).

Separate from ``SkillSuggestionCollector`` (workflow → skill drafts).
This store holds **route quality** items: low-confidence hits, no-matches,
and explicit user corrections waiting for accept/dismiss.

Design constraints (pi H1 + evolution final):
- Human-readable Chinese reasons
- ≤3 new pending items per calendar day (rate limit)
- Dedup: same query_hash while still pending → no re-add (M7: the same
  garbage query routed to 2 skills must not consume 2 of the 3 daily slots;
  the daily cap likewise counts distinct query_hash, not rows)
- Low-information queries (<2 meaningful tokens — "可以", "✓", "/review")
  are NOT enqueued; they degrade into MissCounter records so a genuine
  false positive still surfaces as a frequent miss (M7 dogfood: the review
  queue died of alert fatigue, 7/7 items were low-info junk)
- Dismiss suppresses re-enqueue for 24h
- Accept/dismiss write back via InstinctLearner + PreferenceLearner (callers)
- Writes are serialized cross-process: every ``vibe route`` builds a fresh
  store instance, so ``try_enqueue``/``_resolve`` re-read the file under a
  ``cross_process_lock`` sidecar lock before rewriting it (RMW — locking
  only the write would still lose updates from stale in-memory items)
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
from vibesop.utils.file_lock import cross_process_lock

logger = logging.getLogger(__name__)

__all__ = [
    "RoutingPendingItem",
    "RoutingPendingStore",
    "default_pending_path",
    "is_low_information_query",
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


# Exact-match acknowledgment/confirmation phrases (pi NIT-7): CJK replies
# like "知道了" tokenize into >=2 overlapping bigrams, all "meaningful" under
# the shared convention, so the token rule alone lets them through. Matching
# is whole-string exact (after strip + lowercase + whitespace collapse) so a
# real query merely containing one of these words ("修一下没问题这个报错")
# is NOT blocked.
_ACKNOWLEDGMENT_QUERIES = frozenset(
    {
        "知道了",
        "没问题",
        "收到",
        "好的",
        "可以",
        "可以吗",
        "好",
        "嗯",
        "谢谢",
        "ok",
        "okay",
        "yes",
        "no",
        "thanks",
    }
)


def is_low_information_query(query: str) -> bool:
    """True when *query* carries too little signal to be worth human review.

    Token-based, not char-based: a character wall would kill legitimate short
    forms, while the token rule only blocks queries with fewer than 2
    *meaningful* tokens ("可以" → 1 CJK token, "✓" → 0, "/review" → 1).
    Multi-token queries like "review my code" pass — their review-queue
    noise is a matcher-side problem, handled elsewhere.

    Two rules, either suffices:

    1. **Acknowledgment stopword** — the whole query (strip + lowercase +
       collapsed whitespace) exactly equals a member of
       ``_ACKNOWLEDGMENT_QUERIES``. This catches CJK confirmation replies
       ("知道了", "没问题", "收到") that penetrate the token rule: their
       overlapping bigrams are all >=2-char CJK tokens and thus all
       "meaningful". Exact-match only, so real queries containing these
       words are never blocked. Residual boundary (accepted): longer
       variants like "好的明白了" are not in the set and pass — if they are
       junk they surface via the MissCounter degradation record instead.
    2. **Token rule** — fewer than 2 meaningful tokens.

    The meaningful-token criterion is the shared module-level
    ``_is_meaningful_token`` from ``core/matching/strategies.py`` (CJK >=2
    chars, Latin >=3) — imported lazily alongside the tokenizer, mirroring
    ``instinct/learner.py``; matching never imports instinct, so there is
    no import cycle.
    """
    normalized = " ".join(query.split()).lower()
    if normalized in _ACKNOWLEDGMENT_QUERIES:
        return True

    from vibesop.core.matching.strategies import _is_meaningful_token
    from vibesop.core.matching.tokenizers import tokenize

    meaningful = sum(1 for t in tokenize(query) if _is_meaningful_token(t))
    return meaningful < 2


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

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        miss_counter: Any | None = None,
    ) -> None:
        self._path = Path(path) if path else default_pending_path()
        self._lock_path = self._path.with_name(self._path.name + ".lock")
        self._lock = threading.Lock()
        self._items: list[RoutingPendingItem] = []
        # MissCounter for gate-blocked low-info queries. Injectable for
        # tests; otherwise lazily derived from the default store layout.
        self._miss_counter = miss_counter
        self._miss_counter_probed = miss_counter is not None
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
        with self._lock:
            return self._created_today_locked()

    def _created_today_locked(self) -> int:
        """Daily-cap count. Caller must hold ``self._lock``.

        Counted by distinct query_hash (M7): one garbage query routed to N
        skills costs 1 daily slot, not N. Legacy rows with an empty
        query_hash count individually so historical files keep working.
        """
        today = _day_key()
        hashes: set[str] = set()
        legacy_rows = 0
        for item in self._items:
            try:
                created = datetime.fromisoformat(item.created_at)
            except ValueError:
                continue
            if _day_key(created) != today:
                continue
            if item.query_hash:
                hashes.add(item.query_hash)
            else:
                legacy_rows += 1
        return len(hashes) + legacy_rows

    def _get_miss_counter(self) -> Any | None:
        """Lazy MissCounter for gate-blocked low-info queries.

        Derived from the default layout (``<root>/.vibe/instincts/...`` →
        ``MissCounter(<root>)`` writes ``<root>/.vibe/miss_counter.json``).
        Returns None for non-standard store paths — the gate still blocks,
        just without a degradation record.
        """
        if self._miss_counter_probed:
            return self._miss_counter
        self._miss_counter_probed = True
        if self._path.parent.name != "instincts" or self._path.parent.parent.name != ".vibe":
            return None
        try:
            from vibesop.core.skills.miss_counter import MissCounter

            self._miss_counter = MissCounter(self._path.parent.parent.parent)
        except Exception as exc:  # telemetry must never break routing
            logger.debug("miss counter unavailable for low-info gate: %s", exc)
        return self._miss_counter

    def _record_low_info_miss(self, query: str) -> None:
        counter = self._get_miss_counter()
        if counter is None:
            return
        try:
            counter.record(query)
        except Exception as exc:  # telemetry must never break routing
            logger.debug("failed to record low-info query miss: %s", exc)

    def is_suppressed(self, query_hash: str, skill_id: str | None) -> bool:
        """True if a dismiss for same query_hash happened within the window.

        Keyed by query_hash only, aligned with the dedup key (M7): a
        dismissed query re-routed through a different skill_id stays
        suppressed. Empty legacy hashes fall back to (hash, skill_id).
        """
        cutoff = _now() - timedelta(hours=_DISMISS_SUPPRESS_HOURS)
        with self._lock:
            for item in self._items:
                if item.status != "dismissed":
                    continue
                if item.query_hash != query_hash:
                    continue
                if not query_hash and (item.skill_id or None) != (skill_id or None):
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
                if item.query_hash == query_hash and (item.skill_id or None) == (skill_id or None):
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
        """Enqueue if rate limit / dedup / suppress allow. Returns item or None.

        Low-information queries (<2 meaningful tokens) are not enqueued;
        they degrade into a MissCounter record so a genuine false positive
        still surfaces as a frequent miss. The read-modify-write cycle runs
        under both the threading lock and a cross-process sidecar lock, and
        the file is re-read inside the lock — every ``vibe route`` builds a
        fresh store instance, so in-memory ``_items`` may be stale.
        """
        if is_low_information_query(query):
            logger.debug("routing pending: skip low-information query %r", query[:80])
            # no_match queries are already counted by the router's always-on
            # miss telemetry (UnifiedRouter._record_route_miss fires on the
            # same event just before enqueue) — recording again would
            # double-count a single user query. low_confidence / correction
            # kinds are not covered there, so record the degradation here.
            if kind != "no_match":
                self._record_low_info_miss(query)
            return None
        with self._lock:
            try:
                with cross_process_lock(self._lock_path):
                    self._load()
                    return self._try_enqueue_locked(
                        query=query,
                        skill_id=skill_id,
                        confidence=confidence,
                        kind=kind,
                        reason_zh=reason_zh,
                        query_hash=query_hash,
                    )
            except OSError as exc:
                logger.warning("routing pending enqueue skipped (lock failed: %s)", exc)
                return None

    def _try_enqueue_locked(
        self,
        *,
        query: str,
        skill_id: str | None,
        confidence: float,
        kind: PendingKind,
        reason_zh: str,
        query_hash: str,
    ) -> RoutingPendingItem | None:
        """Caller must hold ``self._lock`` and the cross-process lock."""
        # Rate limit (created today, any status, distinct query_hash)
        if self._created_today_locked() >= _MAX_NEW_PER_DAY:
            logger.debug("routing pending daily cap reached (%d)", _MAX_NEW_PER_DAY)
            return None

        # Dedup open — keyed by query_hash only (M7): the same query routed
        # to a different skill must not enqueue a second row. Empty legacy
        # hashes fall back to (hash, skill_id) so a hash-less historical row
        # cannot block every future enqueue.
        #
        # Accepted tradeoff (pi NIT-4, gate7b review): pending dedup has no
        # expiry — if the query first pends under the WRONG skill A and the
        # router later lands on the correct skill B, that newer (better)
        # signal is swallowed until a human resolves A. Accepted because the
        # queue is tiny (daily cap 3) and the pending row still carries the
        # query text for review; the alternative (expiry/re-enqueue) would
        # re-open the alert-fatigue flood this queue died of in dogfood.
        for item in self._items:
            if item.status != "pending" or item.query_hash != query_hash:
                continue
            if query_hash or (item.skill_id or None) == (skill_id or None):
                return None

        # Suppress after dismiss — keyed by query_hash only, aligned with the
        # dedup key above (M7): a dismissed query re-routed through a
        # different skill_id must stay suppressed, otherwise the "one garbage
        # query costs one daily slot" intent is bypassed. Empty legacy hashes
        # fall back to (hash, skill_id), same as dedup.
        cutoff = _now() - timedelta(hours=_DISMISS_SUPPRESS_HOURS)
        for item in self._items:
            if item.status != "dismissed":
                continue
            if item.query_hash != query_hash:
                continue
            if not query_hash and (item.skill_id or None) != (skill_id or None):
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

    def _resolve(self, item_id: str, status: PendingStatus) -> RoutingPendingItem | None:
        with self._lock:
            try:
                with cross_process_lock(self._lock_path):
                    # Re-read under the lock: the item may have been resolved
                    # by another process since this instance loaded.
                    self._load()
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
            except OSError as exc:
                logger.warning("routing pending resolve skipped (lock failed: %s)", exc)
                return None

    def stats(self) -> dict[str, int]:
        with self._lock:
            pending = sum(1 for i in self._items if i.status == "pending")
            accepted = sum(1 for i in self._items if i.status == "accepted")
            dismissed = sum(1 for i in self._items if i.status == "dismissed")
            return {
                "pending": pending,
                "accepted": accepted,
                "dismissed": dismissed,
                "created_today": self._created_today_locked(),
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
        return f"低置信路由到 {skill}（{confidence:.0%}）。若正确请 accept，错误请 dismiss。"
    return f"用户纠正候选：{skill_id or '（无技能）'}。"


def should_enqueue_from_route(
    *,
    has_match: bool,
    confidence: float,
    threshold: float = _LOW_CONF_THRESHOLD,
    layer: str | None = None,
) -> PendingKind | None:
    """Decide whether a route result should create a pending item.

    Note: this is the route-quality half of the policy. The low-information
    query gate runs separately (and first) inside
    ``RoutingPendingStore.try_enqueue`` — see ``is_low_information_query``.

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
