"""Instinct learning system for pattern extraction."""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from vibesop.utils.atomic_writer import write_text

logger = logging.getLogger(__name__)


def _wilson_confidence(success_count: int, failure_count: int) -> float:
    """Wilson score center for a Bernoulli rate.

    Returns 0.5 when there is no evidence so a reset row matches
    ``Instinct``'s default confidence. ``Instinct.update`` uses the same
    formula for ``n > 0``.
    """
    n = success_count + failure_count
    if n <= 0:
        return 0.5
    p = success_count / n
    z = 1.96  # 95% confidence
    denominator = 1 + z**2 / n
    return (p + z**2 / (2 * n)) / denominator


def _confidence_matches_update(success_count: int, failure_count: int, confidence: float) -> bool:
    """True when ``confidence`` is the Wilson value ``update()`` would store."""
    if success_count + failure_count <= 0:
        return False
    return confidence == _wilson_confidence(success_count, failure_count)


@dataclass
class Instinct:
    """A learned pattern or rule of thumb."""

    id: str
    pattern: str
    action: str
    context: str = ""
    confidence: float = 0.5
    success_count: int = 0
    failure_count: int = 0
    times_matched: int = 0  # Neutral signal: count of times the router matched this instinct
    last_used: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)
    source: str = "extracted"
    tags: list[str] = field(default_factory=list)

    @property
    def total_applications(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        if self.total_applications == 0:
            return 0.5
        return self.success_count / self.total_applications

    @property
    def is_reliable(self) -> bool:
        """Whether this instinct is reliable enough to use."""
        return self.total_applications >= 3 and self.success_rate >= 0.6 and self.confidence >= 0.5

    def update(self, success: bool) -> None:
        """Update instinct based on new evidence."""
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        # Update confidence based on success rate and sample size.
        # Wilson score interval for better small-sample behavior.
        if self.total_applications > 0:
            self.confidence = _wilson_confidence(self.success_count, self.failure_count)

        self.last_used = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pattern": self.pattern,
            "action": self.action,
            "context": self.context,
            "confidence": self.confidence,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "times_matched": self.times_matched,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Instinct:
        return cls(
            id=data["id"],
            pattern=data["pattern"],
            action=data["action"],
            context=data.get("context", ""),
            confidence=data.get("confidence", 0.5),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            times_matched=data.get("times_matched", 0),
            last_used=datetime.fromisoformat(data["last_used"]) if data.get("last_used") else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            source=data.get("source", "extracted"),
            tags=data.get("tags", []),
        )


@dataclass
class SequencePattern:
    """A detected repeatable sequence of actions that may become a skill."""

    steps: list[str]
    success_count: int = 0
    total_count: int = 0
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    context_tags: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count else 0.0

    @property
    def is_candidate(self) -> bool:
        return self.total_count >= 5 and self.success_rate >= 0.8 and len(self.steps) >= 3

    @property
    def sequence_hash(self) -> str:
        import hashlib

        return hashlib.md5("→".join(self.steps).encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": self.steps,
            "success_count": self.success_count,
            "total_count": self.total_count,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "context_tags": self.context_tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SequencePattern:
        return cls(
            steps=data["steps"],
            success_count=data.get("success_count", 0),
            total_count=data.get("total_count", 0),
            first_seen=datetime.fromisoformat(data["first_seen"]),
            last_seen=datetime.fromisoformat(data["last_seen"]),
            context_tags=data.get("context_tags", []),
        )


# Auto-extraction quality gate (Tier2 junk-instinct fix). The router only
# auto-mints instincts from patterns passing ``is_auto_extract_worthy``, and
# ``InstinctLearner.prune_auto_extracted`` removes existing auto_extracted
# rows that fail it. Patterns longer than this many chars are one-off
# megaprompts, not reusable routing patterns (real-world dogfood: 700+ char
# prompts were stored as instinct patterns and can never match again via the
# Jaccard/bigram scorer).
AUTO_EXTRACT_MAX_PATTERN_CHARS = 300


def is_auto_extract_worthy(pattern: str) -> bool:
    """True when a query pattern is worth minting as an auto_extracted instinct.

    Rejects on either rule:
      1. length — beyond ``AUTO_EXTRACT_MAX_PATTERN_CHARS`` the pattern is a
         one-off megaprompt that will never re-match;
      2. low information — reuses ``is_low_information_query`` from
         ``routing_pending`` (the M7 review-queue gate), imported lazily;
         routing_pending only imports utils at module level, so no cycle.
    """
    if len(pattern) > AUTO_EXTRACT_MAX_PATTERN_CHARS:
        return False
    from vibesop.core.instinct.routing_pending import is_low_information_query

    return not is_low_information_query(pattern)


def _is_untrusted_layer_context(context: str) -> bool:
    """True when *context* is a known routing layer the mint gate distrusts.

    ``Instinct.context`` stores ``match.layer.value`` at mint time, so this
    lets prune catch legacy instincts minted by weak last-resort layers
    (levenshtein/custom/fallback_llm) or ai_triage even when their pattern
    passes the quality gate (gate8 nit: mint gate is conf AND layer AND
    quality, prune must enforce the same axes).

    Unknown/missing context (empty string, free-text contexts like
    ``"extracted_from_experiment"``) returns False — the decision then falls
    back to the quality gate alone. Lazy imports: models is light, and
    unified is only pulled in here (never at module level) so learner stays
    importable without the router stack.
    """
    normalized = (context or "").strip().lower()
    if not normalized:
        return False
    from vibesop.core.models import RoutingLayer
    from vibesop.core.routing.unified import AUTO_EXTRACT_TRUSTED_LAYERS

    known = {layer.value for layer in RoutingLayer}
    if normalized not in known:
        return False
    return normalized not in {layer.value for layer in AUTO_EXTRACT_TRUSTED_LAYERS}


@dataclass(frozen=True)
class _InstinctBaseline:
    """Per-id snapshot taken at load (and refreshed after each merged save)."""

    pattern: str
    action: str
    context: str
    confidence: float
    success_count: int
    failure_count: int
    times_matched: int
    last_used: datetime | None
    created_at: datetime
    source: str
    tags: tuple[str, ...]

    @classmethod
    def capture(cls, instinct: Instinct) -> _InstinctBaseline:
        return cls(
            pattern=instinct.pattern,
            action=instinct.action,
            context=instinct.context,
            confidence=instinct.confidence,
            success_count=instinct.success_count,
            failure_count=instinct.failure_count,
            times_matched=instinct.times_matched,
            last_used=instinct.last_used,
            created_at=instinct.created_at,
            source=instinct.source,
            tags=tuple(instinct.tags),
        )


@dataclass
class _DiskInstincts:
    """Latest ``instincts.jsonl`` snapshot read under the cross-process lock."""

    rows: dict[str, Instinct]
    membership_known: bool


def _assign_instinct_fields(dst: Instinct, src: Instinct) -> None:
    """Copy persisted fields onto ``dst`` without replacing the object."""
    dst.pattern = src.pattern
    dst.action = src.action
    dst.context = src.context
    dst.confidence = src.confidence
    dst.success_count = src.success_count
    dst.failure_count = src.failure_count
    dst.times_matched = src.times_matched
    dst.last_used = src.last_used
    dst.created_at = src.created_at
    dst.source = src.source
    dst.tags = list(src.tags)


def _later_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return left if left >= right else right


def _evidence_key(pattern: str, action: str) -> tuple[str, str]:
    """Success and failure belong to this pair, not to the row id alone."""
    return (pattern, action)


def _apply_times_matched_delta(memory: Instinct, disk: Instinct, base: _InstinctBaseline) -> None:
    """``times_matched`` is neutral and is not success/failure evidence."""
    memory.times_matched = max(0, disk.times_matched + (memory.times_matched - base.times_matched))


def _apply_counter_delta(
    memory: Instinct, disk: Instinct, base: _InstinctBaseline
) -> tuple[int, int, float]:
    """Apply ``disk + (memory - loaded)`` and return the pre-merge evidence.

    Caller must already know memory, disk, and the baseline share one
    pattern+action. A different action must not use this delta.
    """
    pre_success = memory.success_count
    pre_failure = memory.failure_count
    pre_confidence = memory.confidence
    memory.success_count = max(0, disk.success_count + (pre_success - base.success_count))
    memory.failure_count = max(0, disk.failure_count + (pre_failure - base.failure_count))
    _apply_times_matched_delta(memory, disk, base)
    return pre_success, pre_failure, pre_confidence


def _adopt_unedited_fields(memory: Instinct, disk: Instinct, base: _InstinctBaseline) -> None:
    """Keep a local edit; otherwise take the newer disk value."""
    if memory.pattern == base.pattern:
        memory.pattern = disk.pattern
    if memory.action == base.action:
        memory.action = disk.action
    if memory.context == base.context:
        memory.context = disk.context
    if memory.source == base.source:
        memory.source = disk.source
    if tuple(memory.tags) == base.tags:
        memory.tags = list(disk.tags)
    if memory.created_at == base.created_at:
        memory.created_at = disk.created_at
    if memory.last_used == base.last_used:
        memory.last_used = disk.last_used
    else:
        memory.last_used = _later_datetime(memory.last_used, disk.last_used)


def _reconcile_confidence(
    memory: Instinct,
    disk: Instinct,
    base: _InstinctBaseline,
    pre_success: int,
    pre_failure: int,
    pre_confidence: float,
) -> None:
    counts_unchanged = memory.success_count == pre_success and memory.failure_count == pre_failure
    if pre_confidence != base.confidence:
        produced_by_update = _confidence_matches_update(pre_success, pre_failure, pre_confidence)
        if produced_by_update and not counts_unchanged:
            memory.confidence = _wilson_confidence(memory.success_count, memory.failure_count)
        else:
            memory.confidence = pre_confidence
        return
    disk_counts = (
        memory.success_count == disk.success_count and memory.failure_count == disk.failure_count
    )
    if disk_counts or counts_unchanged:
        memory.confidence = disk.confidence if disk_counts else pre_confidence
        return
    memory.confidence = _wilson_confidence(memory.success_count, memory.failure_count)


def _merge_aligned_new_action(memory: Instinct, disk: Instinct, base: _InstinctBaseline) -> None:
    """Both sides already share a new pattern+action; the baseline is the old one.

    Local success/failure are that new action's own counts, starting at zero
    when the action changed. Add them to disk. Do not subtract the previous
    action's baseline, or a second switch to the new action wipes the peer's
    evidence (and a zero baseline would keep the old counters).
    """
    pre_success = memory.success_count
    pre_failure = memory.failure_count
    pre_confidence = memory.confidence
    memory.success_count = max(0, disk.success_count + pre_success)
    memory.failure_count = max(0, disk.failure_count + pre_failure)
    _apply_times_matched_delta(memory, disk, base)
    _adopt_unedited_fields(memory, disk, base)
    if pre_success == 0 and pre_failure == 0:
        memory.confidence = disk.confidence
        return
    if _confidence_matches_update(pre_success, pre_failure, pre_confidence):
        memory.confidence = _wilson_confidence(memory.success_count, memory.failure_count)
        return
    memory.confidence = pre_confidence


def _merge_local_action_change(memory: Instinct, disk: Instinct, base: _InstinctBaseline) -> None:
    """This process changed pattern+action. Keep the reset evidence.

    Disk may still be the previous action, including feedback recorded on it
    after this process loaded. Those counters are not the new action's evidence.
    """
    _apply_times_matched_delta(memory, disk, base)
    _adopt_unedited_fields(memory, disk, base)


def _merge_disk_action_change(memory: Instinct, disk: Instinct, base: _InstinctBaseline) -> None:
    """Disk pattern+action changed. Drop this process's old-action feedback.

    The in-memory row may still be the action this process loaded and then
    accepted or rejected. That delta must not move onto the new action, and
    the old action must not be written back. ``times_matched`` stays neutral.
    Other local edits (context, source, tags) are kept.
    """
    local_context = memory.context
    local_source = memory.source
    local_tags = list(memory.tags)
    local_created_at = memory.created_at
    local_last_used = memory.last_used
    local_matched = memory.times_matched
    _assign_instinct_fields(memory, disk)
    if local_context != base.context:
        memory.context = local_context
    if local_source != base.source:
        memory.source = local_source
    if tuple(local_tags) != base.tags:
        memory.tags = local_tags
    if local_created_at != base.created_at:
        memory.created_at = local_created_at
    if local_last_used != base.last_used:
        memory.last_used = _later_datetime(local_last_used, disk.last_used)
    memory.times_matched = max(0, disk.times_matched + (local_matched - base.times_matched))


def _merge_shared_instinct(memory: Instinct, disk: Instinct, base: _InstinctBaseline) -> None:
    """Merge one id that this process already loaded.

    Untouched rows copy disk. Same pattern+action as the baseline uses the
    counter delta. Any other pattern+action is a different evidence domain:
    the side that changed action keeps that action's evidence and does not
    inherit the other action's successes or failures.
    """
    if _InstinctBaseline.capture(memory) == base:
        _assign_instinct_fields(memory, disk)
        return
    memory_key = _evidence_key(memory.pattern, memory.action)
    disk_key = _evidence_key(disk.pattern, disk.action)
    base_key = _evidence_key(base.pattern, base.action)
    if memory_key == disk_key == base_key:
        pre_success, pre_failure, pre_confidence = _apply_counter_delta(memory, disk, base)
        _adopt_unedited_fields(memory, disk, base)
        _reconcile_confidence(memory, disk, base, pre_success, pre_failure, pre_confidence)
        return
    if memory_key == disk_key:
        _merge_aligned_new_action(memory, disk, base)
        return
    if memory_key == base_key:
        _merge_disk_action_change(memory, disk, base)
        return
    _merge_local_action_change(memory, disk, base)


def _merge_unloaded_overlap(memory: Instinct, disk: Instinct) -> None:
    """Same id appeared on disk for a row this process did not load.

    A zero-evidence ``learn()`` must not wipe another instance's counters
    when the action matches, and must not inherit them when the action
    differs. Non-zero local counters are an absolute upsert (``set_instinct``).
    """
    local_evidence = (
        memory.success_count != 0 or memory.failure_count != 0 or memory.times_matched != 0
    )
    if local_evidence:
        return
    if memory.action == disk.action:
        _assign_instinct_fields(memory, disk)
        return
    new_action = memory.action
    _assign_instinct_fields(memory, disk)
    memory.action = new_action
    memory.success_count = 0
    memory.failure_count = 0
    memory.confidence = 0.5


class InstinctLearner:
    """Learn and manage instincts from experience."""

    def __init__(self, storage_path: Path | None = None):
        self.storage_path = storage_path or Path(".vibe/instincts.jsonl")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self._instincts: dict[str, Instinct] = {}
        self._sequences: dict[str, SequencePattern] = {}
        self._embedding_model_name = "paraphrase-multilingual-MiniLM-L12-v2"
        self._embedding_model: Any | None = None
        self._embedding_cache: dict[str, Any] = {}
        try:
            import numpy as np  # type: ignore[import-untyped]

            self._numpy = np
        except ImportError:
            self._numpy = None
        self._lock = threading.RLock()
        # Snapshot at load, including action. Same pattern+action applies
        # disk + (memory - loaded) (D11). A different action does not (D13).
        self._baselines: dict[str, _InstinctBaseline] = {}
        # Generation counter for clear() — bumped on every purge so concurrent
        # learners detect that their in-memory state is stale (loaded before
        # the clear) and drop it instead of resurrecting purged data via merge
        # (adversarial review Phase B FLAW #1, CRITICAL).
        self._clear_epoch_at_load = self._read_clear_epoch()
        self._load()

    def _clear_epoch_path(self) -> Path:
        return self.storage_path.parent / "clear_epoch"

    def _read_clear_epoch(self) -> int:
        """Return the current clear-generation marker (0 if absent)."""
        try:
            return int(self._clear_epoch_path().read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return 0

    def _bump_clear_epoch_locked(self) -> None:
        """Increment the clear-generation marker. Called inside the
        cross-process lock during ``clear()``."""
        try:
            write_text(self._clear_epoch_path(), str(self._read_clear_epoch() + 1))
        except OSError as e:
            # Non-fatal — at worst, a concurrent learner resurrects data on
            # its next save. Worst case is no worse than pre-fix behavior.
            logger.warning("Failed to bump clear epoch: %s", e)

    def _load(self) -> None:
        if self.storage_path.exists():
            with self.storage_path.open(encoding="utf-8") as f:
                for raw_line in f:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                        instinct = Instinct.from_dict(data)
                        self._instincts[instinct.id] = instinct
                    except (json.JSONDecodeError, KeyError):
                        continue
            self._embedding_cache.clear()
        self._refresh_baselines_locked()
        # Always probe for sequences.jsonl even when instincts.jsonl is absent
        # — otherwise a project that has recorded tool-call sequences but no
        # learned instincts would silently drop every sequence on next load
        # (adversarial review Phase B note: pre-existing Phase A bug surfaced
        # by the record_sequence lock test).
        self._load_sequences()

    @contextmanager
    def _cross_process_lock(self, data_path: Path) -> Generator[None]:
        """Acquire an exclusive advisory lock on a sibling ``.lock`` file.

        Threading is already protected by ``self._lock`` (RLock); this adds
        cross-process serialisation so a launchd tick running
        ``vibe instinct feedback-collect`` and an interactive session running
        ``vibe instinct learn`` cannot race the read-modify-write of
        ``instincts.jsonl`` / ``sequences.jsonl``.

        Delegates to ``vibesop.utils.file_lock.cross_process_lock`` so
        Windows gets real mutual exclusion via ``msvcrt.locking`` instead
        of the previous silent no-op (deep-diagnosis-2026-07-24 P0-3).
        The lock lives on a sibling file (not the data file) so atomic
        rename inside ``write_text`` does not release it.
        """
        from vibesop.utils.file_lock import CouldNotLock, cross_process_lock

        lock_path = data_path.with_suffix(data_path.suffix + ".lock")
        try:
            with cross_process_lock(lock_path):
                yield
        except (OSError, CouldNotLock) as e:
            # Lock acquisition failure is non-fatal — warn and proceed unlocked.
            # Better to write with a race window than to lose the entire tick.
            logger.warning("Failed to acquire cross-process lock on %s: %s", lock_path, e)
            yield

    @staticmethod
    def _backup_locked(data_path: Path) -> None:
        """Copy ``data_path`` to ``data_path.bak`` before overwriting.

        Provides a single-step recovery point if the write succeeds but a
        later read is corrupt (rare; usually caused by external tampering).
        Called inside the cross-process lock.
        """
        if not data_path.exists():
            return
        try:
            backup_path = data_path.with_suffix(data_path.suffix + ".bak")
            backup_path.write_bytes(data_path.read_bytes())
        except OSError as e:
            logger.warning("Failed to back up %s: %s", data_path, e)

    def _refresh_baselines_locked(self) -> None:
        """Record the post-merge counters so the next save does not re-apply them."""
        self._baselines = {
            instinct_id: _InstinctBaseline.capture(instinct)
            for instinct_id, instinct in self._instincts.items()
        }

    def _read_disk_instincts_locked(self) -> _DiskInstincts | None:
        """Read the latest instincts file. ``None`` means the read failed."""
        if not self.storage_path.exists():
            return _DiskInstincts(rows={}, membership_known=True)
        rows: dict[str, Instinct] = {}
        skipped = 0
        try:
            with self.storage_path.open(encoding="utf-8") as handle:
                for raw_line in handle:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                        instinct = Instinct.from_dict(data)
                    except (json.JSONDecodeError, KeyError):
                        skipped += 1
                        continue
                    rows[instinct.id] = instinct
        except OSError as exc:
            logger.warning("Failed to re-read %s for merge: %s", self.storage_path, exc)
            return None
        # A partially unreadable file is not proof that missing ids were deleted.
        return _DiskInstincts(rows=rows, membership_known=skipped == 0)

    def _drop_untouched_deleted_ids_locked(self, disk_rows: dict[str, Instinct]) -> None:
        """Drop loaded rows that a delete/prune/clear removed and we did not edit.

        Dirty local edits and ids created after load are left in place. ``clear``
        still drops every stale row via the epoch guard before this runs.
        """
        for instinct_id, memory in list(self._instincts.items()):
            if instinct_id in disk_rows or instinct_id not in self._baselines:
                continue
            if _InstinctBaseline.capture(memory) == self._baselines[instinct_id]:
                del self._instincts[instinct_id]

    def _merge_disk_into_memory_locked(self) -> None:
        """Re-read ``instincts.jsonl`` and merge it into memory.

        Called inside both ``self._lock`` and the cross-process lock. Disk-only
        ids are adopted. Shared ids whose pattern and action still match the
        loaded baseline apply ``disk + (memory - loaded)`` to ``success_count``,
        ``failure_count``, and ``times_matched`` (D11). Success and failure are
        bound to pattern+action (D13): a local action change keeps its reset
        and does not import the other action's counters; a disk action change
        drops this process's feedback on the old action. ``times_matched`` stays
        the neutral counter either way. An untouched row takes the disk version
        wholesale, which also keeps a delete or prune from being rewritten.
        Baselines, including action, are refreshed to the merged row so a later
        save does not apply the same delta again.
        """
        disk = self._read_disk_instincts_locked()
        if disk is None:
            return
        if disk.membership_known:
            self._drop_untouched_deleted_ids_locked(disk.rows)
        for instinct_id, disk_instinct in disk.rows.items():
            memory = self._instincts.get(instinct_id)
            if memory is None:
                self._instincts[instinct_id] = disk_instinct
                continue
            base = self._baselines.get(instinct_id)
            if base is None:
                _merge_unloaded_overlap(memory, disk_instinct)
            else:
                _merge_shared_instinct(memory, disk_instinct, base)
        self._refresh_baselines_locked()

    def _merge_disk_sequences_into_memory_locked(self) -> None:
        """Same merge semantics for ``sequences.jsonl``."""
        seq_path = self.storage_path.parent / "sequences.jsonl"
        if not seq_path.exists():
            return
        try:
            with seq_path.open(encoding="utf-8") as f:
                for raw_line in f:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                        pattern = SequencePattern.from_dict(data)
                    except (json.JSONDecodeError, KeyError):
                        continue
                    if pattern.sequence_hash not in self._sequences:
                        self._sequences[pattern.sequence_hash] = pattern
        except OSError as e:
            logger.warning("Failed to re-read %s for merge: %s", seq_path, e)

    def _save(self) -> None:
        with self._lock, self._cross_process_lock(self.storage_path):
            # Clear-epoch guard (adversarial review Phase B FLAW #1): if
            # another process called clear() after we loaded, our in-memory
            # state is stale and would resurrect purged data via the merge
            # below. Detect via the generation counter and drop our state.
            current_epoch = self._read_clear_epoch()
            if current_epoch > self._clear_epoch_at_load:
                logger.info(
                    "Detected clear() epoch advance (%d -> %d); dropping stale in-memory state",
                    self._clear_epoch_at_load,
                    current_epoch,
                )
                self._instincts.clear()
                self._sequences.clear()
                self._baselines.clear()
                self._embedding_cache.clear()
                self._clear_epoch_at_load = current_epoch

            # Latest disk snapshot under both locks, then per-id counter delta.
            # learn/record_outcome/save and the CLI writers that call them land
            # here. clear() deliberately does not. routing_pending is another store.
            self._merge_disk_into_memory_locked()
            self._merge_disk_sequences_into_memory_locked()
            self._backup_locked(self.storage_path)
            seq_path = self.storage_path.parent / "sequences.jsonl"
            if seq_path.exists():
                self._backup_locked(seq_path)

            content = "".join(
                json.dumps(instinct.to_dict()) + "\n" for instinct in self._instincts.values()
            )
            write_text(self.storage_path, content)
            self._save_sequences()

    @property
    def instincts(self) -> dict[str, Instinct]:
        """Read-only view of learned instincts."""
        return dict(self._instincts)

    def has_instinct(self, instinct_id: str) -> bool:
        """Check if an instinct with the given ID exists."""
        return instinct_id in self._instincts

    def set_instinct(self, instinct: Instinct) -> None:
        """Add or replace an instinct."""
        with self._lock:
            self._instincts[instinct.id] = instinct
            self._embedding_cache.clear()

    def save(self) -> None:
        """Persist all instincts to storage."""
        self._save()

    def clear(self) -> int:
        """Remove all learned instincts (F-08). Returns count removed.

        Skips the disk-merge step that ``_save`` normally does — clear is a
        destructive privacy purge, so disk state must NOT be preserved.
        Deletes the data files entirely (``.bak`` included so the pre-clear
        state cannot be recovered post-purge). Bumps a generation counter so
        any concurrent in-memory learner detects the clear on its next save
        and drops its stale state instead of resurrecting purged data via
        merge (adversarial review Phase B FLAW #1, CRITICAL).
        """
        with self._lock, self._cross_process_lock(self.storage_path):
            count = len(self._instincts)
            self._instincts.clear()
            self._sequences.clear()
            self._baselines.clear()
            self._embedding_cache.clear()
            for path in (
                self.storage_path,
                self.storage_path.with_suffix(self.storage_path.suffix + ".bak"),
                self.storage_path.parent / "sequences.jsonl",
                self.storage_path.parent / "sequences.jsonl.bak",
            ):
                try:
                    path.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning("Failed to remove %s during clear: %s", path, e)
            # Bump the epoch AFTER file deletion so a concurrent reader sees
            # the new epoch only once the data is gone.
            self._bump_clear_epoch_locked()
            self._clear_epoch_at_load = self._read_clear_epoch()
        return count

    def prune_auto_extracted(self, *, dry_run: bool = True) -> list[Instinct]:
        """Remove auto_extracted instincts that fail the mint-time gates.

        Targets only instincts minted by the router's auto_extract path
        (``source == "auto_routing"`` or tagged ``auto_extracted``). A row is
        pruned when EITHER gate fails (gate8 review nit — the mint gate
        requires conf AND trusted layer AND quality, so prune enforces both
        the quality and the layer axis):

          1. quality gate — pattern fails ``is_auto_extract_worthy``; or
          2. layer gate — stored ``context`` (the layer value recorded at
             mint time) is a known routing layer outside
             ``unified.AUTO_EXTRACT_TRUSTED_LAYERS`` (legacy weak-layer
             mints whose pattern happens to look fine). Unknown/missing
             context falls back to the quality gate alone (documented
             leniency for pre-layer-tracking rows).

        Human-confirmed instincts are NEVER touched:

          - ``vibe instinct accept`` re-sources/re-tags merged instincts to
            ``routing_pending``/``pending_accept`` at accept time (gate8
            fix: ``learn()`` merges by id and used to keep the auto_extracted
            tag), and
          - any row with ``success_count > 0`` is skipped outright — that
            count is only ever incremented by explicit positive user
            feedback (accept / ``vibe feedback`` yes), which protects rows
            accepted before the re-tagging fix.

        ``dry_run=True`` (default) writes nothing; the returned list is what
        WOULD be removed. Returns the pruned (or would-be-pruned) instincts.
        """
        with self._lock, self._cross_process_lock(self.storage_path):
            # Clear-epoch guard, mirroring _save exactly (sequences too): if
            # another process purged since we loaded, drop stale in-memory
            # state instead of resurrecting it via the merge below or a later
            # save.
            current_epoch = self._read_clear_epoch()
            if current_epoch > self._clear_epoch_at_load:
                self._instincts.clear()
                self._sequences.clear()
                self._baselines.clear()
                self._embedding_cache.clear()
                self._clear_epoch_at_load = current_epoch
            # Merge concurrent writes first so we prune against the fullest
            # view of the store (same RMW discipline as _save).
            self._merge_disk_into_memory_locked()
            victims = [
                i
                for i in self._instincts.values()
                if (i.source == "auto_routing" or "auto_extracted" in i.tags)
                and i.success_count == 0  # explicit positive feedback => human-confirmed
                and (
                    not is_auto_extract_worthy(i.pattern) or _is_untrusted_layer_context(i.context)
                )
            ]
            if dry_run or not victims:
                return victims
            for victim in victims:
                del self._instincts[victim.id]
                self._baselines.pop(victim.id, None)
            self._embedding_cache.clear()
            self._backup_locked(self.storage_path)
            # Write instincts.jsonl directly — NOT _save(), which re-acquires
            # the cross-process lock on the same file (non-reentrant flock).
            content = "".join(
                json.dumps(instinct.to_dict()) + "\n" for instinct in self._instincts.values()
            )
            write_text(self.storage_path, content)
            return victims

    def learn(
        self,
        pattern: str,
        action: str,
        context: str = "",
        tags: list[str] | None = None,
        source: str = "manual",
    ) -> Instinct:
        with self._lock:
            return self._learn_locked(pattern, action, context, tags, source)

    def _learn_locked(
        self,
        pattern: str,
        action: str,
        context: str = "",
        tags: list[str] | None = None,
        source: str = "manual",
    ) -> Instinct:
        # Generate ID from pattern
        instinct_id = self.generate_id(pattern)

        # Check if already exists
        if instinct_id in self._instincts:
            instinct = self._instincts[instinct_id]
            # Evidence is bound to pattern+action. Keep the row id, but a new
            # action must not inherit the previous action's successes (D13).
            if instinct.action != action:
                instinct.action = action
                instinct.confidence = 0.5
                instinct.success_count = 0
                instinct.failure_count = 0
        else:
            instinct = Instinct(
                id=instinct_id,
                pattern=pattern,
                action=action,
                context=context,
                source=source,
                tags=tags or [],
            )
            self._instincts[instinct_id] = instinct
        self._embedding_cache.clear()
        self._save()
        return instinct

    def record_outcome(self, instinct_id: str, success: bool) -> None:
        with self._lock:
            if instinct_id not in self._instincts:
                return

            self._instincts[instinct_id].update(success)
            self._save()

    def record_outcome_for_query(self, query: str, success: bool) -> None:
        """Record an outcome for the instinct whose pattern matches this query.

        Derives the instinct id the same way ``learn()`` does, so the two stay
        in sync. No-op if no instinct exists for the query. Called by the
        routing feedback path (``UnifiedRouter.record_feedback_outcome``) when a
        user explicitly accepts (``success=True``) or rejects (``success=False``)
        a route — this is the missing reward signal that closes the instinct ->
        routing feedback loop (Phase 0 finding).
        """
        self.record_outcome(self.generate_id(query), success)

    def get_instinct_for_query(self, query: str) -> Instinct | None:
        """Look up the instinct whose pattern matches this query.

        Returns ``None`` if no instinct has been learned for the query.
        Used by task-memory gold-standard detection (W1 Task C) to find
        the success/failure record for a given cluster's representative
        query without breaking ``_instincts`` encapsulation.
        """
        instinct_id = self.generate_id(query)
        with self._lock:
            return self._instincts.get(instinct_id)

    def find_matching(
        self,
        query: str,
        context: str = "",
        min_confidence: float = 0.5,
    ) -> list[Instinct]:
        matches = []

        for instinct in self._instincts.values():
            # Skip unreliable instincts
            if not instinct.is_reliable or instinct.confidence < min_confidence:
                continue

            # Check if pattern matches query
            score = self._match_score(instinct.pattern, query)

            # Boost score for context match
            if context and instinct.context:
                context_score = self._match_score(instinct.context, context)
                score = max(score, context_score * 0.8)

            if score > 0.3:  # Threshold for match
                matches.append((instinct, score))

        # Sort by score (descending)
        matches.sort(key=lambda x: x[1], reverse=True)

        return [instinct for instinct, _ in matches]

    def get_reliable_instincts(self, tag: str | None = None) -> list[Instinct]:
        instincts = [i for i in self._instincts.values() if i.is_reliable]

        if tag:
            instincts = [i for i in instincts if tag in i.tags]

        # Sort by confidence
        instincts.sort(key=lambda i: i.confidence, reverse=True)

        return instincts

    def extract_from_experiment(
        self,
        hypothesis: str,
        outcome: str,
        was_successful: bool,
    ) -> Instinct | None:
        """Extract an instinct from an experiment result."""
        # Simple extraction: hypothesis -> pattern, outcome -> action
        # In a more sophisticated version, this would use NLP

        pattern = hypothesis.lower()
        action = outcome if was_successful else f"Avoid: {outcome}"

        instinct = self.learn(
            pattern=pattern,
            action=action,
            context="extracted_from_experiment",
            tags=["autoresearch"],
            source="experiment",
        )

        # Record the outcome
        self.record_outcome(instinct.id, was_successful)

        return instinct

    def generate_id(self, pattern: str) -> str:
        """Deterministic id for a pattern (same normalized pattern → same id).

        Public so that callers like ``vibe instinct auto-promote`` can derive
        the same id a ``learner.learn`` call would have produced, enabling
        idempotent re-runs (set_instinct overwrites instead of duplicating).
        """
        import hashlib

        # Normalize and hash
        normalized = re.sub(r"\s+", " ", pattern.lower().strip())
        hash_obj = hashlib.md5(normalized.encode())
        return f"instinct_{hash_obj.hexdigest()[:12]}"

    def _embedding_enabled(self) -> bool:
        if self._numpy is None:
            return False
        if self._embedding_model is not None:
            return True
        try:
            from vibesop.core.embedding_loader import load_sentence_transformer

            self._embedding_model = load_sentence_transformer(self._embedding_model_name)
            return True
        except (ImportError, OSError, RuntimeError):
            return False

    def _get_embedding(self, text: str) -> Any:
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        if not self._embedding_enabled():
            raise RuntimeError("Embedding model not available")
        assert self._embedding_model is not None
        emb = self._embedding_model.encode([text])[0]
        self._embedding_cache[text] = emb
        return emb

    def _compute_embedding_similarity(self, pattern: str, text: str) -> float:
        try:
            pattern_emb = self._get_embedding(pattern)
            text_emb = self._get_embedding(text)
            np = self._numpy
            assert np is not None
            return float(
                np.dot(pattern_emb, text_emb)
                / (np.linalg.norm(pattern_emb) * np.linalg.norm(text_emb) + 1e-10)
            )
        except (OSError, ValueError, TypeError, RuntimeError) as e:
            # Fail open (same "recall must never break routing" convention as
            # triage_recall.recall): embedding I/O failures — a flaky model
            # download or corrupt HF cache surfacing as OSError from the
            # load/encode path — must not break matching; callers fall back
            # to the lexical score.
            logger.debug("Embedding similarity unavailable, using lexical only: %s", e)
            return 0.0

    def _match_score(self, pattern: str, text: str) -> float:
        """Calculate match score between pattern and text."""
        from vibesop.core.matching.tokenizers import tokenize

        pattern_tokens = tokenize(pattern)
        text_tokens = tokenize(text)

        pattern_words = set(pattern_tokens)
        text_words = set(text_tokens)

        if not pattern_words:
            return 0.0

        # Jaccard similarity
        intersection = pattern_words & text_words
        union = pattern_words | text_words
        jaccard = len(intersection) / len(union) if union else 0.0

        # Containment: how much of the pattern is found in the text
        containment = len(intersection) / len(pattern_words) if pattern_words else 0.0

        # Bigram overlap for phrase-level matching
        def _bigrams(tokens: list[str]) -> set[str]:
            return {f"{tokens[i]} {tokens[i + 1]}" for i in range(len(tokens) - 1)}

        pattern_bigrams = _bigrams(pattern_tokens)
        text_bigrams = _bigrams(text_tokens)
        if pattern_bigrams:
            bigram_overlap = len(pattern_bigrams & text_bigrams) / len(pattern_bigrams)
        else:
            bigram_overlap = 0.0

        lexical_score = 0.4 * jaccard + 0.4 * containment + 0.2 * bigram_overlap

        # Semantic boost via embeddings when available
        embedding_score = 0.0
        if self._numpy is not None:
            try:
                embedding_score = self._compute_embedding_similarity(pattern, text)
            except (ValueError, TypeError, RuntimeError):
                embedding_score = 0.0

        return max(lexical_score, embedding_score)

    def get_stats(self) -> dict[str, Any]:
        total = len(self._instincts)
        reliable = sum(1 for i in self._instincts.values() if i.is_reliable)

        by_source: dict[str, int] = {}
        for instinct in self._instincts.values():
            source = instinct.source
            by_source[source] = by_source.get(source, 0) + 1

        return {
            "total_instincts": total,
            "reliable_instincts": reliable,
            "by_source": by_source,
            "avg_confidence": sum(i.confidence for i in self._instincts.values()) / total
            if total > 0
            else 0,
            "sequence_candidates": sum(1 for s in self._sequences.values() if s.is_candidate),
        }

    # --- Sequence Pattern Detection ---

    def record_sequence(
        self, steps: list[str], success: bool, context: str = ""
    ) -> SequencePattern | None:
        """Record a sequence of tool calls and detect repeatable patterns."""
        if len(steps) < 3:
            return None

        seq_path = self.storage_path.parent / "sequences.jsonl"
        # Hold the *store-level* lock (storage_path) across mutation + persist.
        # Phase B kimi milestone P1: must NOT use seq_path's own lock, because
        # _save() and clear() take the storage_path lock while writing
        # sequences.jsonl. Two different lock files would not mutually exclude,
        # reopening both FLAW #1 (sequences resurrection) and FLAW #3 (lost
        # sequence updates). Single lock file for the whole store.
        with self._lock, self._cross_process_lock(self.storage_path):
            # Clear-epoch guard: if another process purged since we loaded,
            # drop our stale in-memory sequences (mirrors _save's check).
            current_epoch = self._read_clear_epoch()
            if current_epoch > self._clear_epoch_at_load:
                self._sequences.clear()
                self._clear_epoch_at_load = current_epoch

            # Pick up sequences written by a concurrent process so we don't
            # clobber them. In-memory wins for shared hashes (we just bumped
            # the count); disk-only hashes are preserved.
            self._merge_disk_sequences_into_memory_locked()

            import hashlib

            seq_hash = hashlib.md5("→".join(steps).encode()).hexdigest()[:12]

            if seq_hash in self._sequences:
                pattern = self._sequences[seq_hash]
            else:
                pattern = SequencePattern(steps=steps)
                self._sequences[seq_hash] = pattern

            pattern.total_count += 1
            if success:
                pattern.success_count += 1
            pattern.last_seen = datetime.now()

            if context:
                context_lower = context.lower()
                for tag in (
                    "debugging",
                    "testing",
                    "linting",
                    "deploying",
                    "refactoring",
                    "building",
                    "security",
                ):
                    if tag in context_lower and tag not in pattern.context_tags:
                        pattern.context_tags.append(tag)

            # Symmetric .bak rotation with _save (pi P2 nit #1): without this,
            # sequences.jsonl had no recovery point when written via
            # record_sequence.
            self._backup_locked(seq_path)
            self._save_sequences()

            return pattern if pattern.is_candidate else None

    def get_sequence_candidates(self, min_confidence: float = 0.5) -> list[SequencePattern]:
        return [
            s
            for s in self._sequences.values()
            if s.is_candidate and s.success_rate >= min_confidence
        ]

    def _load_sequences(self) -> None:
        seq_path = self.storage_path.parent / "sequences.jsonl"
        if not seq_path.exists():
            return
        self._sequences = {}
        with seq_path.open(encoding="utf-8") as f:
            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    pattern = SequencePattern.from_dict(data)
                    self._sequences[pattern.sequence_hash] = pattern
                except (json.JSONDecodeError, KeyError):
                    continue

    def _save_sequences(self) -> None:
        seq_path = self.storage_path.parent / "sequences.jsonl"
        content = "".join(
            json.dumps(pattern.to_dict()) + "\n" for pattern in self._sequences.values()
        )
        write_text(seq_path, content)

    def export_for_routing(self) -> list[dict[str, Any]]:
        return [
            {
                "id": i.id,
                "pattern": i.pattern,
                "action": i.action,
                "confidence": i.confidence,
                "success_rate": i.success_rate,
            }
            for i in self.get_reliable_instincts()
        ]


# Convenience functions


def learn_instinct(
    pattern: str,
    action: str,
    storage_path: Path | None = None,
    **kwargs: Any,
) -> Instinct:
    learner = InstinctLearner(storage_path)
    return learner.learn(pattern, action, **kwargs)


def get_routing_suggestion(
    query: str,
    storage_path: Path | None = None,
) -> str | None:
    learner = InstinctLearner(storage_path)
    matches = learner.find_matching(query)

    if matches:
        return matches[0].action

    return None
