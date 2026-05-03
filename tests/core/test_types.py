"""Tests for core type definitions."""


from vibesop.core.types import (
    BoostAmount,
    ConfidenceScore,
    MatcherCapabilities,
    MatcherCapabilitiesDict,
    RoutingMetadata,
    RoutingMetadataDict,
    SimilarityScore,
    SkillCandidate,
    SkillCandidateDict,
)


class TestSkillCandidate:
    """Test SkillCandidate TypedDict."""

    def test_full_construction(self):
        """SkillCandidate should accept all defined fields."""
        candidate = SkillCandidate(
            id="test/skill",
            name="Test Skill",
            description="A test skill",
            intent="testing",
            namespace="test",
            keywords=["test", "skill"],
            triggers=["test trigger"],
            tags=["test"],
            version="1.0.0",
            author="tester",
            skill_type="builtin",
            source="local",
        )
        assert candidate["id"] == "test/skill"
        assert candidate["name"] == "Test Skill"
        assert candidate["keywords"] == ["test", "skill"]

    def test_partial_construction(self):
        """SkillCandidate is total=False, so partial construction is allowed."""
        candidate = SkillCandidate(id="test/skill")
        assert candidate["id"] == "test/skill"
        assert "name" not in candidate

    def test_empty_construction(self):
        """SkillCandidate can be created with no fields."""
        candidate = SkillCandidate()
        assert candidate == {}


class TestMatcherCapabilities:
    """Test MatcherCapabilities TypedDict."""

    def test_full_construction(self):
        """MatcherCapabilities should accept all defined fields."""
        caps = MatcherCapabilities(
            type="semantic",
            speed="fast",
            accuracy="high",
            requires_semantic=True,
        )
        assert caps["type"] == "semantic"
        assert caps["requires_semantic"] is True

    def test_partial_construction(self):
        """MatcherCapabilities is total=False, so partial construction is allowed."""
        caps = MatcherCapabilities(type="keyword")
        assert caps["type"] == "keyword"
        assert "speed" not in caps


class TestRoutingMetadata:
    """Test RoutingMetadata TypedDict."""

    def test_full_construction(self):
        """RoutingMetadata should accept all defined fields."""
        meta = RoutingMetadata(
            namespace="test",
            matcher="semantic",
            scenario="test_scenario",
            override=True,
            boosted=False,
            original_confidence=0.85,
            preference_applied=True,
            ai_triage=False,
            model="gpt-4",
        )
        assert meta["namespace"] == "test"
        assert meta["original_confidence"] == 0.85
        assert meta["scenario"] == "test_scenario"

    def test_none_scenario(self):
        """scenario field may be None."""
        meta = RoutingMetadata(scenario=None)
        assert meta["scenario"] is None

    def test_partial_construction(self):
        """RoutingMetadata is total=False, so partial construction is allowed."""
        meta = RoutingMetadata(namespace="test")
        assert meta["namespace"] == "test"
        assert "matcher" not in meta


class TestTypeAliases:
    """Test type aliases are importable and usable."""

    def test_score_aliases(self):
        """ConfidenceScore, SimilarityScore, BoostAmount should accept floats."""
        confidence: ConfidenceScore = 0.95
        similarity: SimilarityScore = 0.87
        boost: BoostAmount = 0.15
        assert isinstance(confidence, float)
        assert isinstance(similarity, float)
        assert isinstance(boost, float)

    def test_dict_aliases(self):
        """Dict aliases should accept generic dicts."""
        candidate_dict: SkillCandidateDict = {"id": "test", "name": "Test"}
        caps_dict: MatcherCapabilitiesDict = {"type": "semantic"}
        meta_dict: RoutingMetadataDict = {"namespace": "test"}
        assert isinstance(candidate_dict, dict)
        assert isinstance(caps_dict, dict)
        assert isinstance(meta_dict, dict)


class TestExports:
    """Test public API exports."""

    def test_all_exports_present(self):
        """All expected names should be in __all__."""
        from vibesop.core import types as types_module

        expected = {
            "BoostAmount",
            "ConfidenceScore",
            "MatcherCapabilities",
            "MatcherCapabilitiesDict",
            "RoutingMetadata",
            "RoutingMetadataDict",
            "SimilarityScore",
            "SkillCandidate",
            "SkillCandidateDict",
        }
        assert set(types_module.__all__) == expected
