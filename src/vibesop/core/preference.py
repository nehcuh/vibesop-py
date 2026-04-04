"""Preference learning system for personalized skill routing.

Tracks user skill selections and learns preferences over time.
Features:
- Record user choices
- Calculate preference scores
- Personalized recommendations
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
    """Record of a skill selection event.

    Attributes:
        skill_id: Selected skill ID
        query: Original user query
        timestamp: When the selection was made
        was_helpful: Whether the user found it helpful
    """

    skill_id: str
    query: str
    timestamp: datetime
    was_helpful: bool = True


@dataclass
class PreferenceScore:
    """Preference score for a skill.

    Attributes:
        skill_id: Skill ID
        score: Calculated preference score
        selection_count: Times this skill was selected
        helpful_count: Times user confirmed helpful
        last_selected: Most recent selection time
    """

    skill_id: str
    score: float
    selection_count: int
    helpful_count: int
    last_selected: datetime


class PreferenceStorage(BaseModel):
    """Storage for preference data.

    Attributes:
        selections: List of all selections
        skill_scores: Dict of skill_id -> preference data
        word_associations: Word -> skill preferences
    """

    selections: list[dict[str, Any]] = Field(default_factory=list)
    skill_scores: dict[str, dict[str, Any]] = Field(default_factory=dict)
    word_associations: dict[str, dict[str, int]] = Field(default_factory=dict)


class PreferenceLearner:
    """Learn and predict user preferences for skill routing.

    Usage:
        learner = PreferenceLearner(storage_path=".vibe/preferences.json")
        learner.record_selection("/review", "review my code")
        score = learner.get_preference_score("/review")
        recommendations = learner.get_personalized_rankings(["/review", "/debug"])
    """

    def __init__(
        self,
        storage_path: str | Path = ".vibe/preferences.json",
        decay_days: int | None = None,
        min_samples: int | None = None,
    ) -> None:
        """Initialize the preference learner.

        Args:
            storage_path: Path to preference storage file
            decay_days: Days after which old data loses relevance
            min_samples: Minimum selections before trusting a preference
        """
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
        """Record explicit feedback for a skill recommendation.

        This allows recording feedback independently of a selection event,
        useful for correcting past recommendations.

        Args:
            skill_id: The skill that was recommended.
            query: The original user query.
            helpful: Whether the recommendation was helpful.
        """
        # Record as a selection event with the feedback
        self.record_selection(skill_id, query, was_helpful=helpful)

    def record_selection(
        self,
        skill_id: str,
        query: str,
        was_helpful: bool = True,
    ) -> None:
        """Record a skill selection event.

        Args:
            skill_id: Selected skill ID
            query: Original user query
            was_helpful: Whether user confirmed it was helpful
        """
        selection = {
            "skill_id": skill_id,
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "was_helpful": was_helpful,
        }

        self._storage.selections.append(selection)

        # Update word associations
        self._update_word_associations(skill_id, query, was_helpful)

        # Recalculate scores
        self._recalculate_scores()

        # Save to disk
        self._save_storage()

    def get_preference_score(self, skill_id: str) -> float:
        """Get preference score for a skill.

        Args:
            skill_id: Skill ID to get score for

        Returns:
            Preference score (0.0 to 1.0), or 0.0 if not enough data
        """
        if skill_id not in self._storage.skill_scores:
            return 0.0

        skill_data = self._storage.skill_scores[skill_id]

        # If not enough samples, return neutral score
        if skill_data["selection_count"] < self.min_samples:
            return 0.5

        return skill_data["score"]

    def get_personalized_rankings(
        self,
        skill_ids: list[str],
        query: str = "",
    ) -> list[tuple[str, float]]:
        """Get personalized rankings for skills.

        Args:
            skill_ids: List of skill IDs to rank
            query: Optional query for context boosting

        Returns:
            List of (skill_id, boosted_score) tuples, sorted by score descending
        """
        rankings = []

        for skill_id in skill_ids:
            # Base preference score
            base_score = self.get_preference_score(skill_id)

            # Apply query context boost
            boost = self._calculate_query_boost(skill_id, query)

            # Combine scores (70% preference, 30% context)
            final_score = (base_score * 0.7) + (boost * 0.3)

            rankings.append((skill_id, final_score))

        # Sort by score descending
        rankings.sort(key=lambda x: x[1], reverse=True)

        return rankings

    def get_top_skills(
        self,
        limit: int = 5,
        min_selections: int = 2,
    ) -> list[PreferenceScore]:
        """Get top preferred skills.

        Args:
            limit: Maximum number to return
            min_selections: Minimum selection count required

        Returns:
            List of PreferenceScore objects
        """
        qualified = [
            self._create_pref_score(skill_id, data)
            for skill_id, data in self._storage.skill_scores.items()
            if data["selection_count"] >= min_selections
        ]

        # Sort by score descending
        qualified.sort(key=lambda s: s.score, reverse=True)

        return qualified[:limit]

    def get_selection_history(
        self,
        skill_id: str | None = None,
        limit: int = 100,
    ) -> list[SkillSelection]:
        """Get selection history.

        Args:
            skill_id: Filter by specific skill (None = all)
            limit: Maximum records to return

        Returns:
            List of SkillSelection objects
        """
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
        """Get preference learning statistics.

        Returns:
            Dictionary with statistics
        """
        total_selections = len(self._storage.selections)

        # Count helpful vs not helpful
        helpful_count = sum(1 for s in self._storage.selections if s.get("was_helpful", True))

        # Most selected skills
        skill_counts: dict[str, int] = {}
        for s in self._storage.selections:
            skill_counts[s["skill_id"]] = skill_counts.get(s["skill_id"], 0) + 1

        top_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_selections": total_selections,
            "helpful_count": helpful_count,
            "helpful_rate": helpful_count / total_selections if total_selections > 0 else 0,
            "unique_skills": len(self._storage.skill_scores),
            "top_skills": top_skills,
            "storage_path": str(self.storage_path),
        }

    def clear_old_data(self, days: int = 90) -> int:
        """Clear old selection data.

        Args:
            days: Remove data older than this many days

        Returns:
            Number of records removed
        """
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
        """Load preference storage from disk.

        Returns:
            PreferenceStorage object
        """
        if not self.storage_path.exists():
            return PreferenceStorage()

        try:
            with self.storage_path.open("r") as f:
                data = json.load(f)
                return PreferenceStorage(**data)
        except (json.JSONDecodeError, TypeError):
            # File corrupted, return empty
            return PreferenceStorage()

    def _save_storage(self) -> None:
        """Save preference storage to disk."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        with self.storage_path.open("w") as f:
            json.dump(self._storage.model_dump(), f, indent=2)

    def _update_word_associations(
        self,
        skill_id: str,
        query: str,
        was_helpful: bool,  # noqa: ARG002
    ) -> None:
        """Update word -> skill associations.

        Args:
            skill_id: Selected skill
            query: User's query
            was_helpful: Whether user confirmed helpful (reserved for future use)
        """
        # Simple word extraction
        words = self._extract_words(query)

        for word in words:
            if word not in self._storage.word_associations:
                self._storage.word_associations[word] = {}

            if skill_id not in self._storage.word_associations[word]:
                self._storage.word_associations[word][skill_id] = 0

            self._storage.word_associations[word][skill_id] += 1

    def _calculate_query_boost(self, skill_id: str, query: str) -> float:
        """Calculate context boost based on query.

        Args:
            skill_id: Skill to check
            query: User's query

        Returns:
            Boost score (0.0 to 1.0)
        """
        if not query:
            return 0.0

        words = self._extract_words(query)
        if not words:
            return 0.0

        # Check word associations
        total_associations = 0
        matching_associations = 0

        for word in words:
            if word in self._storage.word_associations:
                word_data = self._storage.word_associations[word]
                total_associations += sum(word_data.values())
                matching_associations += word_data.get(skill_id, 0)

        if total_associations == 0:
            return 0.0

        return matching_associations / total_associations

    def _recalculate_scores(self) -> None:
        """Recalculate all preference scores."""
        skill_stats: dict[str, dict[str, Any]] = {}

        # Aggregate selections by skill
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

            # Update last_selected
            ts = datetime.fromisoformat(selection["timestamp"])
            last_ts = datetime.fromisoformat(skill_stats[skill_id]["last_selected"])
            if ts > last_ts:
                skill_stats[skill_id]["last_selected"] = selection["timestamp"]

        # Calculate scores
        for skill_id, stats in skill_stats.items():
            # Helpfulness rate (0.0 to 1.0)
            helpfulness = (
                stats["helpful_count"] / stats["selection_count"]
                if stats["selection_count"] > 0
                else 0.5
            )

            # Frequency bonus (logarithmic to prevent dominance)
            frequency_bonus = math.log(stats["selection_count"] + 1) / 10

            # Recency bonus (more recent = higher)
            last_selected = datetime.fromisoformat(stats["last_selected"])
            days_since = (datetime.now() - last_selected).days
            recency_bonus = max(0, 1 - (days_since / self.decay_days))

            # Combine: 60% helpfulness, 25% frequency, 15% recency
            score = (
                (helpfulness * 0.6) + (min(frequency_bonus, 1.0) * 0.25) + (recency_bonus * 0.15)
            )

            # Clamp to 0-1
            score = max(0.0, min(1.0, score))

            self._storage.skill_scores[skill_id] = {
                "score": score,
                "selection_count": stats["selection_count"],
                "helpful_count": stats["helpful_count"],
                "last_selected": stats["last_selected"],
            }

    def _create_pref_score(self, skill_id: str, data: dict[str, Any]) -> PreferenceScore:
        """Create PreferenceScore object.

        Args:
            skill_id: Skill ID
            data: Score data from storage

        Returns:
            PreferenceScore object
        """
        return PreferenceScore(
            skill_id=skill_id,
            score=data["score"],
            selection_count=data["selection_count"],
            helpful_count=data["helpful_count"],
            last_selected=datetime.fromisoformat(data["last_selected"]),
        )

    def _extract_words(self, text: str) -> list[str]:
        """Extract meaningful words from text.

        Args:
            text: Input text

        Returns:
            List of words
        """
        # Simple word extraction
        # Remove punctuation and split
        words = re.sub(r"[^\w\s]", " ", text).split()

        # Filter short words and convert to lowercase
        return [w.lower() for w in words if len(w) > 2]
