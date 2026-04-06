"""Preference learning integration with UnifiedRouter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vibesop.core.matching import MatchResult

if TYPE_CHECKING:
    from vibesop.core.preference import PreferenceLearner


class PreferenceBooster:
    """Apply preference boosts to match results."""

    def __init__(
        self,
        enabled: bool = True,
        weight: float = 0.3,
        min_samples: int = 2,
        storage_path: str = ".vibe/preferences.json",
    ):
        self.enabled = enabled
        self.weight = max(0.0, min(1.0, weight))
        self.min_samples = min_samples
        self._storage_path = storage_path
        self._learner: PreferenceLearner | None = None

    def _get_learner(self) -> PreferenceLearner:
        if self._learner is None:
            from vibesop.core.preference import PreferenceLearner

            self._learner = PreferenceLearner(
                storage_path=self._storage_path,
                min_samples=self.min_samples,
            )
        return self._learner

    def boost(self, matches: list[MatchResult], query: str = "") -> list[MatchResult]:
        if not self.enabled or not matches:
            return list(matches)
        try:
            learner = self._get_learner()
        except Exception:
            return list(matches)

        skill_ids = [m.skill_id for m in matches]
        rankings = learner.get_personalized_rankings(skill_ids, query)
        score_map = dict(rankings)

        boosted = []
        for match in matches:
            pref_score = score_map.get(match.skill_id, 0.0)
            if pref_score > 0:
                new_confidence = match.confidence * (1 - self.weight) + pref_score * self.weight
                new_confidence = max(0.0, min(1.0, new_confidence))
            else:
                new_confidence = match.confidence
            boosted.append(
                MatchResult(
                    skill_id=match.skill_id,
                    confidence=new_confidence,
                    score_breakdown={
                        **match.score_breakdown,
                        "preference_boost": pref_score * self.weight,
                    },
                    matcher_type=match.matcher_type,
                    matched_keywords=match.matched_keywords,
                    matched_patterns=match.matched_patterns,
                    semantic_score=match.semantic_score,
                    metadata={**match.metadata, "preference_applied": pref_score > 0},
                )
            )
        boosted.sort(key=lambda m: m.confidence, reverse=True)
        return boosted

    def record_selection(self, skill_id: str, query: str, helpful: bool = True) -> None:
        if not self.enabled:
            return
        try:
            learner = self._get_learner()
            learner.record_selection(skill_id, query, was_helpful=helpful)
        except Exception:
            pass
