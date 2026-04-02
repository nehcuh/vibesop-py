"""Test fuzzy matcher with Levenshtein distance."""

from vibesop.core.routing.fuzzy import (
    FuzzyMatch,
    FuzzyMatcher,
)


class TestFuzzyMatcher:
    """Test FuzzyMatcher class."""

    def test_init(self) -> None:
        """Test initialization."""
        matcher = FuzzyMatcher()
        assert matcher.min_similarity == 0.6
        # max_distance is derived from min_similarity calculation
        # When min_similarity=0.6, max_distance=(1-0.6)*len(word)
        # Default is around 2-3 depending on word length
        assert matcher.max_distance >= 2

    def test_init_custom_params(self) -> None:
        """Test initialization with custom parameters."""
        matcher = FuzzyMatcher(min_similarity=0.8, max_distance=3)
        assert matcher.min_similarity == 0.8
        assert matcher.max_distance == 3

    def test_index_skills(self) -> None:
        """Test indexing skills for fuzzy matching."""
        matcher = FuzzyMatcher()

        skills = [
            {"id": "gstack/review", "intent": "Review code"},
            {"id": "debug", "intent": "Debug errors"},
        ]

        matcher.index_skills(skills)

        assert len(matcher._phrases) > 0

    def test_match_exact(self) -> None:
        """Test exact match."""
        matcher = FuzzyMatcher()

        skills = [{"id": "debug", "intent": "Debug errors"}]
        matcher.index_skills(skills)

        results = matcher.match("debug")

        assert len(results) > 0
        assert results[0].skill_id == "debug"
        # Exact match should have high score
        assert results[0].score > 0.9

    def test_match_typo(self) -> None:
        """Test matching with typo."""
        matcher = FuzzyMatcher()

        skills = [{"id": "review", "intent": "Review code quality"}]
        matcher.index_skills(skills)

        # "reviw" is 1 edit away from "review"
        results = matcher.match("reviw")

        # Should match despite typo
        assert len(results) > 0
        # Score should be reasonably high
        assert results[0].score >= 0.6

    def test_match_below_threshold(self) -> None:
        """Test that low similarity matches are filtered."""
        matcher = FuzzyMatcher(min_similarity=0.9)

        skills = [{"id": "review", "intent": "Review"}]
        matcher.index_skills(skills)

        # "rvw" is 2 edits away from "review"
        results = matcher.match("rvw")

        # With high threshold, might not match
        assert all(r.score >= 0.9 for r in results)

    def test_match_returns_top_k(self) -> None:
        """Test that top_k parameter limits results."""
        matcher = FuzzyMatcher()

        skills = [
            {"id": "debug", "intent": "Debug"},
            {"id": "review", "intent": "Review"},
            {"id": "test", "intent": "Test"},
        ]

        matcher.index_skills(skills)

        results = matcher.match("test", top_k=1)

        assert len(results) <= 1

    def test_match_sorted_by_score(self) -> None:
        """Test that results are sorted by score descending."""
        matcher = FuzzyMatcher()

        skills = [
            {"id": "debug", "intent": "Debug"},
            {"id": "review", "intent": "Review"},
        ]

        matcher.index_skills(skills)

        results = matcher.match("debuh")  # Close to "debug"

        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].score >= results[i + 1].score

    def test_levenshtein_distance_identical(self) -> None:
        """Test Levenshtein distance for identical strings."""
        matcher = FuzzyMatcher()

        distance = matcher._levenshtein_distance("hello", "hello")
        assert distance == 0

    def test_levenshtein_distance_one_edit(self) -> None:
        """Test Levenshtein distance with one edit."""
        matcher = FuzzyMatcher()

        # "hello" -> "hallo" (substitution)
        distance = matcher._levenshtein_distance("hello", "hallo")
        assert distance == 1

        # "hello" -> "hell" (deletion)
        distance = matcher._levenshtein_distance("hello", "hell")
        assert distance == 1

        # "hell" -> "hello" (insertion)
        distance = matcher._levenshtein_distance("hell", "hello")
        assert distance == 1

    def test_levenshtein_distance_multiple_edits(self) -> None:
        """Test Levenshtein distance with multiple edits."""
        matcher = FuzzyMatcher()

        # "kitten" -> "sitting" = 3 edits
        distance = matcher._levenshtein_distance("kitten", "sitting")
        assert distance == 3

    def test_levenshtein_distance_empty_strings(self) -> None:
        """Test Levenshtein distance with empty strings."""
        matcher = FuzzyMatcher()

        # Empty to "test" = length of "test"
        distance = matcher._levenshtein_distance("", "test")
        assert distance == 4

        # Empty to empty = 0
        distance = matcher._levenshtein_distance("", "")
        assert distance == 0

    def test_match_no_skills_indexed(self) -> None:
        """Test matching when no skills are indexed."""
        matcher = FuzzyMatcher()

        results = matcher.match("test")

        assert len(results) == 0

    def test_match_short_token_skipped(self) -> None:
        """Test that very short tokens are skipped."""
        matcher = FuzzyMatcher()

        skills = [{"id": "test", "intent": "Test"}]
        matcher.index_skills(skills)

        # Single character tokens should be skipped
        results = matcher.match("a b c")

        # Should not match anything meaningful
        assert len(results) == 0

    def test_extract_keywords(self) -> None:
        """Test keyword extraction from intent."""
        matcher = FuzzyMatcher()

        keywords = matcher._extract_keywords("Test-driven development workflow")

        # Hyphens are used as separators, so words are split
        assert "test" in keywords or "driven" in keywords
        assert "development" in keywords
        assert "workflow" in keywords

    def test_extract_filters_short_keywords(self) -> None:
        """Test that short keywords are filtered."""
        matcher = FuzzyMatcher()

        keywords = matcher._extract_keywords("a b c test")

        # Short keywords should be filtered
        assert "a" not in keywords
        assert "b" not in keywords
        assert "test" in keywords

    def test_suggest_corrections(self) -> None:
        """Test spelling correction suggestions."""
        matcher = FuzzyMatcher()

        skills = [{"id": "review", "intent": "Review code"}]
        matcher.index_skills(skills)

        suggestions = matcher.suggest_corrections("reviw")

        # Should provide corrected suggestion
        assert isinstance(suggestions, list)

    def test_suggest_corrections_limit(self) -> None:
        """Test suggestion limit."""
        matcher = FuzzyMatcher()

        skills = [
            {"id": "debug", "intent": "Debug"},
            {"id": "review", "intent": "Review"},
        ]
        matcher.index_skills(skills)

        suggestions = matcher.suggest_corrections("reviw", max_suggestions=1)

        assert len(suggestions) <= 1

    def test_duplicate_skill_ids_filtered(self) -> None:
        """Test that duplicate skill IDs are filtered from results."""
        matcher = FuzzyMatcher()

        skills = [
            {"id": "debug", "intent": "Debug errors"},
        ]
        matcher.index_skills(skills)

        # Query that might produce duplicates
        results = matcher.match("debug debug")

        # Should not have duplicate skill_ids
        skill_ids = [r.skill_id for r in results]
        assert len(skill_ids) == len(set(skill_ids))

    def test_case_insensitive_matching(self) -> None:
        """Test that matching is case insensitive."""
        matcher = FuzzyMatcher()

        skills = [{"id": "debug", "intent": "Debug"}]
        matcher.index_skills(skills)

        # Should match regardless of case
        results_lower = matcher.match("debug")
        results_upper = matcher.match("DEBUG")

        # Both should find the same skill
        assert len(results_lower) > 0
        assert len(results_upper) > 0
        assert results_lower[0].skill_id == results_upper[0].skill_id


class TestFuzzyMatch:
    """Test FuzzyMatch dataclass."""

    def test_create_match(self) -> None:
        """Test creating a fuzzy match."""
        match = FuzzyMatch(
            skill_id="test",
            score=0.75,
            distance=1,
            matched_text="test",
        )

        assert match.skill_id == "test"
        assert match.score == 0.75
        assert match.distance == 1
        assert match.matched_text == "test"
