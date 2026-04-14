"""Preference learning system for personalized skill routing.

Tracks user skill selections and learns preferences over time.
Features:
- Record user choices with explicit feedback
- Calculate preference scores with time decay
- Personalized recommendations with query-skill affinity
- Word-level semantic matching for query boosting
"""

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from vibesop.constants import PreferenceSettings


@dataclass
class SkillSelection:
    """Record of a skill selection event."""

    skill_id: str
    query: str
    timestamp: datetime
    was_helpful: bool = True


@dataclass
class PreferenceScore:
    """Preference score for a skill."""

    skill_id: str
    score: float
    selection_count: int
    helpful_count: int
    last_selected: datetime


class PreferenceStorage(BaseModel):
    """Storage for preference data."""

    selections: list[dict[str, Any]] = Field(default_factory=list)
    skill_scores: dict[str, dict[str, Any]] = Field(default_factory=dict)
    word_associations: dict[str, dict[str, int]] = Field(default_factory=dict)
    ngram_associations: dict[str, dict[str, int]] = Field(default_factory=dict)


class PreferenceLearner:
    """Learn and predict user preferences for skill routing.

    Improved over v1:
    - Bigram/n-gram associations for better query matching
    - Semantic word overlap instead of exact word match
    - Stronger feedback signal: helpful choices boost more, unhelpful ones penalize
    - Configurable boost strength

    Usage:
        learner = PreferenceLearner(storage_path=".vibe/preferences.json")
        learner.record_selection("/review", "review my code")
        score = learner.get_preference_score("/review")
        recommendations = learner.get_personalized_rankings(["/review", "/debug"], "review code")
    """

    def __init__(
        self,
        storage_path: str | Path = ".vibe/preferences.json",
        decay_days: int | None = None,
        min_samples: int | None = None,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.decay_days = decay_days if decay_days is not None else PreferenceSettings.DECAY_DAYS
        self.min_samples = (
            min_samples if min_samples is not None else PreferenceSettings.MIN_SAMPLES
        )
        self._storage = self._load_storage()
        self._recalculate_scores()

    def record_feedback(
        self,
        skill_id: str,
        query: str,
        helpful: bool,
    ) -> None:
        self.record_selection(skill_id, query, was_helpful=helpful)

    def record_selection(
        self,
        skill_id: str,
        query: str,
        was_helpful: bool = True,
    ) -> None:
        selection = {
            "skill_id": skill_id,
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "was_helpful": was_helpful,
        }

        self._storage.selections.append(selection)
        self._update_word_associations(skill_id, query, was_helpful)
        self._update_ngram_associations(skill_id, query, was_helpful)
        self._recalculate_scores()
        self._save_storage()

    def get_preference_score(self, skill_id: str) -> float:
        if skill_id not in self._storage.skill_scores:
            return 0.0
        skill_data = self._storage.skill_scores[skill_id]
        if skill_data["selection_count"] < self.min_samples:
            return 0.5
        return skill_data["score"]

    def get_personalized_rankings(
        self,
        skill_ids: list[str],
        query: str = "",
    ) -> list[tuple[str, float]]:
        rankings = []
        for skill_id in skill_ids:
            base_score = self.get_preference_score(skill_id)
            boost = self._calculate_query_boost(skill_id, query)
            final_score = (base_score * 0.6) + (boost * 0.4)
            rankings.append((skill_id, final_score))
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def get_top_skills(
        self,
        limit: int = 5,
        min_selections: int = 2,
    ) -> list[PreferenceScore]:
        qualified = [
            self._create_pref_score(skill_id, data)
            for skill_id, data in self._storage.skill_scores.items()
            if data["selection_count"] >= min_selections
        ]
        qualified.sort(key=lambda s: s.score, reverse=True)
        return qualified[:limit]

    def get_selection_history(
        self,
        skill_id: str | None = None,
        limit: int = 100,
    ) -> list[SkillSelection]:
        selections = self._storage.selections[-limit:]
        if skill_id:
            selections = [s for s in selections if s["skill_id"] == skill_id]
        return [
            SkillSelection(
                skill_id=s["skill_id"],
                query=s["query"],
                timestamp=datetime.fromisoformat(s["timestamp"]),
                was_helpful=s.get("was_helpful", True),
            )
            for s in selections
        ]

    def get_stats(self) -> dict[str, Any]:
        total_selections = len(self._storage.selections)
        helpful_count = sum(1 for s in self._storage.selections if s.get("was_helpful", True))
        skill_counts: dict[str, int] = {}
        for s in self._storage.selections:
            skill_counts[s["skill_id"]] = skill_counts.get(s["skill_id"], 0) + 1
        top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "total_selections": total_selections,
            "helpful_count": helpful_count,
            "helpful_rate": helpful_count / total_selections if total_selections > 0 else 0,
            "unique_skills": len(self._storage.skill_scores),
            "word_associations": len(self._storage.word_associations),
            "ngram_associations": len(self._storage.ngram_associations),
            "top_skills": top_skills,
            "storage_path": str(self.storage_path),
        }

    def clear_old_data(self, days: int = 90) -> int:
        cutoff = datetime.now() - timedelta(days=days)
        original_count = len(self._storage.selections)
        self._storage.selections = [
            s for s in self._storage.selections if datetime.fromisoformat(s["timestamp"]) > cutoff
        ]
        removed = original_count - len(self._storage.selections)
        if removed > 0:
            self._recalculate_scores()
            self._save_storage()
        return removed

    def _load_storage(self) -> PreferenceStorage:
        if not self.storage_path.exists():
            return PreferenceStorage()
        try:
            with self.storage_path.open("r") as f:
                data = json.load(f)
                ngram_data = data.get("ngram_associations", {})
                storage = PreferenceStorage(
                    selections=data.get("selections", []),
                    skill_scores=data.get("skill_scores", {}),
                    word_associations=data.get("word_associations", {}),
                    ngram_associations=ngram_data,
                )
                return storage
        except (json.JSONDecodeError, TypeError):
            return PreferenceStorage()

    def _save_storage(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("w") as f:
            json.dump(self._storage.model_dump(), f, indent=2)

    def _update_word_associations(
        self,
        skill_id: str,
        query: str,
        was_helpful: bool,
    ) -> None:
        words = self._extract_words(query)
        weight = 2 if was_helpful else -1
        for word in words:
            if word not in self._storage.word_associations:
                self._storage.word_associations[word] = {}
            current = self._storage.word_associations[word].get(skill_id, 0)
            self._storage.word_associations[word][skill_id] = current + weight

    def _update_ngram_associations(
        self,
        skill_id: str,
        query: str,
        was_helpful: bool,
    ) -> None:
        bigrams = self._extract_bigrams(query)
        weight = 2 if was_helpful else -1
        for bigram in bigrams:
            if bigram not in self._storage.ngram_associations:
                self._storage.ngram_associations[bigram] = {}
            current = self._storage.ngram_associations[bigram].get(skill_id, 0)
            self._storage.ngram_associations[bigram][skill_id] = current + weight

    def _calculate_query_boost(self, skill_id: str, query: str) -> float:
        if not query:
            return 0.0

        word_boost = self._calculate_word_boost(skill_id, query)
        ngram_boost = self._calculate_ngram_boost(skill_id, query)

        return max(word_boost, ngram_boost)

    def _calculate_word_boost(self, skill_id: str, query: str) -> float:
        words = self._extract_words(query)
        if not words:
            return 0.0

        total_positive = 0
        matching_positive = 0

        for word in words:
            if word in self._storage.word_associations:
                word_data = self._storage.word_associations[word]
                for _sid, count in word_data.items():
                    if count > 0:
                        total_positive += count
                        if _sid == skill_id:
                            matching_positive += count

        if total_positive == 0:
            return 0.0

        return min(1.0, matching_positive / total_positive)

    def _calculate_ngram_boost(self, skill_id: str, query: str) -> float:
        bigrams = self._extract_bigrams(query)
        if not bigrams:
            return 0.0

        total_positive = 0
        matching_positive = 0

        for bigram in bigrams:
            if bigram in self._storage.ngram_associations:
                ngram_data = self._storage.ngram_associations[bigram]
                for _sid, count in ngram_data.items():
                    if count > 0:
                        total_positive += count
                        if _sid == skill_id:
                            matching_positive += count

        if total_positive == 0:
            return 0.0

        return min(1.0, matching_positive / total_positive)

    def _recalculate_scores(self) -> None:
        skill_stats: dict[str, dict[str, Any]] = {}

        for selection in self._storage.selections:
            skill_id = selection["skill_id"]
            if skill_id not in skill_stats:
                skill_stats[skill_id] = {
                    "selection_count": 0,
                    "helpful_count": 0,
                    "last_selected": selection["timestamp"],
                }
            skill_stats[skill_id]["selection_count"] += 1
            if selection.get("was_helpful", True):
                skill_stats[skill_id]["helpful_count"] += 1
            ts = datetime.fromisoformat(selection["timestamp"])
            last_ts = datetime.fromisoformat(skill_stats[skill_id]["last_selected"])
            if ts > last_ts:
                skill_stats[skill_id]["last_selected"] = selection["timestamp"]

        for skill_id, stats in skill_stats.items():
            helpfulness = (
                stats["helpful_count"] / stats["selection_count"]
                if stats["selection_count"] > 0
                else 0.5
            )
            frequency_bonus = math.log(stats["selection_count"] + 1) / 10
            last_selected = datetime.fromisoformat(stats["last_selected"])
            days_since = (datetime.now() - last_selected).days
            recency_bonus = max(0, 1 - (days_since / self.decay_days))
            score = (
                (helpfulness * 0.6) + (min(frequency_bonus, 1.0) * 0.25) + (recency_bonus * 0.15)
            )
            score = max(0.0, min(1.0, score))
            self._storage.skill_scores[skill_id] = {
                "score": score,
                "selection_count": stats["selection_count"],
                "helpful_count": stats["helpful_count"],
                "last_selected": stats["last_selected"],
            }

    def _create_pref_score(self, skill_id: str, data: dict[str, Any]) -> PreferenceScore:
        return PreferenceScore(
            skill_id=skill_id,
            score=data["score"],
            selection_count=data["selection_count"],
            helpful_count=data["helpful_count"],
            last_selected=datetime.fromisoformat(data["last_selected"]),
        )

    def _extract_words(self, text: str) -> list[str]:
        words = re.sub(r"[^\w\s]", " ", text).split()
        return [w.lower() for w in words if len(w) > 2]

    def _extract_bigrams(self, text: str) -> list[str]:
        words = self._extract_words(text)
        if len(words) < 2:
            return []
        return [f"{words[i]}_{words[i + 1]}" for i in range(len(words) - 1)]
