"""Skill rating and review system.

Provides persistent star ratings and text reviews for skills.
Integrated with the skill evaluation system to influence quality scores.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SkillRating:
    """A single rating/review for a skill."""

    skill_id: str
    score: int  # 1-5 stars
    review: str = ""
    user_id: str = "local"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "score": self.score,
            "review": self.review,
            "user_id": self.user_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillRating:
        return cls(
            skill_id=data["skill_id"],
            score=data.get("score", 3),
            review=data.get("review", ""),
            user_id=data.get("user_id", "local"),
            created_at=data.get("created_at", ""),
        )


class SkillRatingStore:
    """Persistent rating & review store for skills.

    Storage: .vibe/ratings.jsonl (one JSON object per line)
    """

    STORE_FILE = Path(".vibe/ratings.jsonl")

    def __init__(self, store_path: Path | None = None) -> None:
        self._store_path = store_path or self.STORE_FILE
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._ratings: dict[str, list[SkillRating]] = {}
        self._load()

    def rate(self, skill_id: str, score: int, review: str = "", user_id: str = "local") -> SkillRating:
        if not 1 <= score <= 5:
            raise ValueError(f"Score must be 1-5, got {score}")

        rating = SkillRating(skill_id=skill_id, score=score, review=review, user_id=user_id)
        self._ratings.setdefault(skill_id, []).append(rating)
        self._save()
        logger.info("Rating saved: %s → %d/5", skill_id, score)
        return rating

    def get_ratings(self, skill_id: str) -> list[SkillRating]:
        return list(self._ratings.get(skill_id, []))

    def get_avg_score(self, skill_id: str) -> float | None:
        ratings = self.get_ratings(skill_id)
        if not ratings:
            return None
        return sum(r.score for r in ratings) / len(ratings)

    def get_count(self, skill_id: str) -> int:
        return len(self._ratings.get(skill_id, []))

    def get_top_rated(self, limit: int = 10, min_reviews: int = 1) -> list[tuple[str, float, int]]:
        scored = []
        for skill_id, ratings in self._ratings.items():
            if len(ratings) < min_reviews:
                continue
            avg = sum(r.score for r in ratings) / len(ratings)
            scored.append((skill_id, avg, len(ratings)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def _load(self) -> None:
        if not self._store_path.exists():
            return
        self._ratings = {}
        with self._store_path.open() as f:
            for raw_line in f:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    rating = SkillRating.from_dict(json.loads(stripped))
                    self._ratings.setdefault(rating.skill_id, []).append(rating)
                except (json.JSONDecodeError, KeyError):
                    continue

    def _save(self) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        with self._store_path.open("w") as f:
            for ratings in self._ratings.values():
                for rating in ratings:
                    f.write(json.dumps(rating.to_dict(), default=str) + "\n")
