"""Tests for SkillRecommender."""

from vibesop.integrations.skill_recommender import SkillRecommender

CANDIDATES = [
    {
        "id": "systematic-debugging",
        "namespace": "builtin",
        "intent": "Find root cause before attempting fixes",
        "triggers": ["error", "debug", "crash"],
        "priority": "P0",
    },
    {
        "id": "gstack/investigate",
        "namespace": "gstack",
        "intent": "Systematic debugging with root cause investigation",
        "triggers": ["error", "bug", "debug", "stack trace"],
        "priority": "P1",
    },
    {
        "id": "superpowers/optimize",
        "namespace": "superpowers",
        "intent": "Performance optimization and profiling guidance",
        "triggers": ["performance", "slow", "optimize"],
        "priority": "P1",
    },
    {
        "id": "gstack/office-hours",
        "namespace": "gstack",
        "intent": "Brainstorm new product ideas and evaluate whether to build",
        "triggers": ["brainstorm", "idea", "product"],
        "priority": "P2",
    },
]


class TestSkillRecommender:
    def test_recommend_by_query_keywords(self):
        recommender = SkillRecommender()
        results = recommender.recommend("I got a crash and need to debug", CANDIDATES, top_k=2)
        assert len(results) == 2
        assert results[0].skill_id in ("systematic-debugging", "gstack/investigate")
        assert results[0].score > 0.0

    def test_recommend_empty_candidates(self):
        recommender = SkillRecommender()
        results = recommender.recommend("anything", [], top_k=3)
        assert results == []

    def test_recommend_respects_top_k(self):
        recommender = SkillRecommender()
        results = recommender.recommend("debug", CANDIDATES, top_k=1)
        assert len(results) == 1

    def test_recommend_scores_are_sorted(self):
        recommender = SkillRecommender()
        results = recommender.recommend("debug performance", CANDIDATES, top_k=4)
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_recommend_from_patterns(self):
        recommender = SkillRecommender()
        pattern = "debug database connection error"
        results = recommender.recommend(pattern, CANDIDATES, top_k=2)
        assert any(r.skill_id in ("systematic-debugging", "gstack/investigate") for r in results)

    def test_recommend_excludes_namespaces(self):
        recommender = SkillRecommender()
        results = recommender.recommend("debug crash", CANDIDATES, top_k=3, exclude_namespaces=["gstack"])
        assert all(r.namespace != "gstack" for r in results)
