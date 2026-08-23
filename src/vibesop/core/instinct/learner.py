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

        # Update confidence based on success rate and sample size
        # Use Wilson score interval for better small-sample behavior
        n = self.total_applications
        if n > 0:
            p = self.success_rate
            z = 1.96  # 95% confidence
            denominator = 1 + z**2 / n
            center = (p + z**2 / (2 * n)) / denominator
            self.confidence = center

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

    def _merge_disk_into_memory_locked(self) -> None:
        """Re-read ``instincts.jsonl`` from disk and merge any IDs that are
        NOT in our in-memory ``_instincts`` dict.

        In-memory wins for shared IDs (we just modified them). Disk-only IDs
        are promoted so a concurrent process's writes are not clobbered when
        we save. Called inside the cross-process lock; doesn't take
        ``self._lock`` (caller already holds it).

        Known limitation (adversarial review Phase B FLAW #2): for shared IDs,
        this merge replaces disk's ``success_count`` / ``failure_count`` with
        in-memory values, which silently drops a concurrent writer's counter
        updates. A delta-based merge (tracking per-id counts at load time and
        applying ``disk + (memory - loaded)``) is the proper fix but adds
        non-trivial state; deferred unless the feedback loop surfaces real
        loss. Trigger requires two writers mutating the SAME instinct's
        counters within the same load-save window — unlikely with the daily
        04:37 feedback-collect schedule vs daytime interactive use.
        """
        if not self.storage_path.exists():
            return
        try:
            with self.storage_path.open(encoding="utf-8") as f:
                for raw_line in f:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                        instinct = Instinct.from_dict(data)
                    except (json.JSONDecodeError, KeyError):
                        continue
                    if instinct.id not in self._instincts:
                        self._instincts[instinct.id] = instinct
        except OSError as e:
            logger.warning("Failed to re-read %s for merge: %s", self.storage_path, e)

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
                self._embedding_cache.clear()
                self._clear_epoch_at_load = current_epoch

            # Pick up concurrent writes from other processes (launchd
            # promote vs interactive learn, etc.). In-memory wins for
            # shared IDs; disk-only IDs are preserved.
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
            # Update if action changed
            if instinct.action != action:
                instinct.action = action
                instinct.confidence = 0.5  # Reset confidence
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
