"""Multi-turn conversation support for VibeSOP routing.

Provides conversation context tracking, follow-up query detection,
and enhanced routing based on conversation history.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ConversationTurn:
    """A single turn in a conversation."""

    query: str
    skill_id: str | None
    timestamp: float
    intent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "skill_id": self.skill_id,
            "timestamp": self.timestamp,
            "intent": self.intent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationTurn:
        return cls(
            query=data["query"],
            skill_id=data.get("skill_id"),
            timestamp=data["timestamp"],
            intent=data.get("intent"),
        )


FOLLOW_UP_PATTERNS = {
    "continuation": [
        "继续",
        "go on",
        "continue",
        "proceed",
        "next step",
        "接着",
        "然后",
        "下一步",
        "继续刚才的",
        "继续之前的",
        "还没完",
        "还有问题",
        "后续",
        "follow up",
    ],
    "retry": [
        "再试一次",
        "retry",
        "try again",
        "再来一次",
        "again",
        "重新",
        "重做",
        "再执行",
        "还是不行",
        "仍然报错",
        "同样的错误",
        "还是报错",
        "依旧失败",
    ],
    "alternative": [
        "换个方法",
        "another way",
        "different approach",
        "alternatively",
        "或者",
        "另一种",
        "其他方法",
        "还有别的办法吗",
    ],
    "clarification": [
        "什么意思",
        "what do you mean",
        "explain",
        " clarify",
        "不清楚",
        "不明白",
        "详细点",
        "说具体点",
        "能再解释一下吗",
        "具体怎么做",
        "详细说明",
    ],
    "refinement": [
        "更具体",
        "more specific",
        "refine",
        "narrow down",
        "更精确",
        "更准确",
        "限定一下",
        "能不能更",
        "再深入",
        "再细化",
    ],
}


class ConversationContext:
    """Manages multi-turn conversation state for intelligent routing.

    Tracks conversation history, detects follow-up queries, and
    provides context-aware routing hints.
    """

    def __init__(
        self,
        conversation_id: str | None = None,
        max_history: int = 10,
        follow_up_timeout: float = 900.0,  # 15 minutes
        storage_dir: str | Path = ".vibe/conversations",
    ) -> None:
        self.conversation_id = conversation_id or str(uuid.uuid4())[:8]
        self._max_history = max_history
        self._follow_up_timeout = follow_up_timeout
        self._storage_dir = Path(storage_dir)
        self._lock = threading.Lock()
        self._turns: list[ConversationTurn] = []
        self._last_activity = time.time()
        # Reusable similarity calculator (cosine over term-frequency vectors)
        from vibesop.core.matching.base import SimilarityMetric
        from vibesop.core.matching.similarity import SimilarityCalculator

        self._similarity_calc = SimilarityCalculator(metric=SimilarityMetric.COSINE)
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _file_path(self) -> Path:
        return self._storage_dir / f"{self.conversation_id}.json"

    def _load(self) -> None:
        path = self._file_path()
        if not path.exists():
            return
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            self._turns = [ConversationTurn.from_dict(t) for t in data.get("turns", [])]
            self._last_activity = data.get("last_activity", time.time())
        except (OSError, json.JSONDecodeError):
            pass

    def save(self) -> None:
        """Persist conversation state to disk."""
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        path = self._file_path()
        with path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "conversation_id": self.conversation_id,
                    "turns": [t.to_dict() for t in self._turns],
                    "last_activity": self._last_activity,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def add_turn(self, query: str, skill_id: str | None = None, intent: str | None = None) -> None:
        """Record a new conversation turn."""
        with self._lock:
            turn = ConversationTurn(
                query=query,
                skill_id=skill_id,
                timestamp=time.time(),
                intent=intent,
            )
            self._turns.append(turn)
            if len(self._turns) > self._max_history:
                self._turns = self._turns[-self._max_history :]
            self._last_activity = time.time()
        self.save()

    def get_history(self) -> list[ConversationTurn]:
        """Return conversation history (oldest first)."""
        with self._lock:
            return list(self._turns)

    def get_last_turn(self) -> ConversationTurn | None:
        """Return the most recent turn, or None if no history."""
        with self._lock:
            return self._turns[-1] if self._turns else None

    def get_last_skill(self) -> str | None:
        """Return the skill from the most recent turn."""
        turn = self.get_last_turn()
        return turn.skill_id if turn else None

    # ------------------------------------------------------------------
    # Follow-up detection
    # ------------------------------------------------------------------

    def _semantic_similarity(self, query: str, previous_query: str) -> float:
        """Calculate semantic similarity using cosine over term-frequency vectors.

        Replaces the previous Jaccard token-overlap approach, which only
        considered binary term presence. Cosine similarity on TF vectors
        is more nuanced: it accounts for term frequency and produces
        smoother scores that better reflect topical overlap.
        """
        try:
            scores = self._similarity_calc.calculate(query, [previous_query])
            return scores[0]
        except Exception:
            return 0.0

    def is_follow_up(self, query: str) -> tuple[bool, str | None]:
        """Detect if a query is a follow-up to the previous turn.

        Returns:
            (is_follow_up, follow_up_type) where follow_up_type is one of:
            "continuation", "retry", "alternative", "clarification",
            "refinement", "pronoun_reference", "semantic_continuation",
            or None if not a follow-up.
        """
        # Check timeout - conversations expire after timeout
        if time.time() - self._last_activity > self._follow_up_timeout:
            return False, None

        # Empty or very short queries are not follow-ups
        query_lower = query.lower().strip()
        if len(query_lower) < 2:
            return False, None

        # Check explicit follow-up patterns
        for follow_up_type, patterns in FOLLOW_UP_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in query_lower:
                    return True, follow_up_type

        # Pronoun-based detection (e.g., "it", "that", "this")
        # Relaxed: no longer limited to 5 words — pronouns in short-to-medium
        # queries often indicate referential continuity.
        if self._turns:
            pronoun_indicators = [
                "it",
                "that",
                "this",
                "them",
                "those",
                "these",
                "它",
                "这个",
                "那个",
                "它们",
                "那些",
            ]
            words = query_lower.split()
            if len(words) <= 15 and any(p in words for p in pronoun_indicators):
                return True, "pronoun_reference"

        # Semantic similarity: if the current query is topically similar
        # to the previous one, treat it as a contextual continuation.
        last_turn = self.get_last_turn()
        if last_turn and last_turn.query:
            sim = self._semantic_similarity(query, last_turn.query)
            if sim >= 0.45:
                return True, "semantic_continuation"

        return False, None

    def build_contextual_query(self, query: str) -> str | None:
        """Build an enriched query by injecting missing context from history.

        Instead of naively concatenating the full previous query (which
        duplicates overlapping terms and introduces misleading template words
        like "follow-up" that can confuse keyword matchers), we only append
        terms from the previous query that are NOT already present in the
        current query. This:
          - Prevents TF-IDF dilution from duplicate terms
          - Avoids keyword matcher confusion from template words
          - Keeps the current query's intent primary while providing
            disambiguating context from history

        Returns the enriched query if this is a follow-up, or None if not.
        """
        is_follow, _follow_type = self.is_follow_up(query)
        if not is_follow:
            return None

        last_turn = self.get_last_turn()
        if not last_turn:
            return None

        from vibesop.core.matching.tokenizers import DEFAULT_STOP_WORDS, tokenize

        current_tokens = set(tokenize(query))
        previous_tokens = set(tokenize(last_turn.query))

        # Only inject terms that provide new context (not already in current
        # query) and are not stop words.
        missing = previous_tokens - current_tokens - DEFAULT_STOP_WORDS

        if not missing:
            # Current query is self-contained; no enrichment needed
            return query

        # Append context terms without any template words that could mislead
        # matchers.  The terms are sorted for deterministic output.
        context_terms = " ".join(sorted(missing))
        return f"{query} {context_terms}"

    # ------------------------------------------------------------------
    # Routing hints
    # ------------------------------------------------------------------

    def get_routing_hints(self) -> dict[str, Any]:
        """Generate routing hints based on conversation history."""
        hints: dict[str, Any] = {}

        last_turn = self.get_last_turn()
        if last_turn and last_turn.skill_id:
            hints["previous_skill"] = last_turn.skill_id
            hints["previous_query"] = last_turn.query

        # Detect topic drift vs. topic persistence
        if len(self._turns) >= 2:
            recent_skills = [t.skill_id for t in self._turns[-3:] if t.skill_id]
            if recent_skills and len(set(recent_skills)) == 1:
                hints["sticky_skill"] = recent_skills[0]

        return hints

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    @classmethod
    def cleanup_expired(
        cls, storage_dir: str | Path = ".vibe/conversations", max_age: float = 86400.0
    ) -> int:
        """Remove conversation files older than max_age seconds.

        Returns number of files removed.
        """
        removed = 0
        dir_path = Path(storage_dir)
        if not dir_path.exists():
            return 0
        now = time.time()
        for path in dir_path.glob("*.json"):
            try:
                if now - path.stat().st_mtime > max_age:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
        return removed
