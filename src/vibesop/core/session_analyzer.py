"""Session history analyzer for pattern detection and skill suggestion.

Analyzes conversation history to:
1. Detect repeated query patterns
2. Identify skill creation opportunities
3. Generate automatic suggestions

Usage:
    analyzer = SessionAnalyzer()
    patterns = analyzer.analyze_session(session_data)
    suggestions = analyzer.generate_skill_suggestions(patterns)
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class QueryPattern:
    """A detected pattern in user queries.

    Attributes:
        queries: List of similar queries
        frequency: How often this pattern appears
        suggested_skill: Suggested skill name
        confidence: Confidence score [0, 1]
    """

    queries: list[str]
    frequency: int
    suggested_skill: str
    confidence: float


@dataclass
class SkillSuggestion:
    """Suggestion for creating a new skill.

    Attributes:
        skill_name: Suggested skill name
        description: What this skill would do
        trigger_queries: Example queries that would trigger it
        frequency: How often these queries appear
        confidence: Confidence score [0, 1]
        estimated_value: Estimated value of creating this skill
    """

    skill_name: str
    description: str
    trigger_queries: list[str]
    frequency: int
    confidence: float
    estimated_value: str  # "high", "medium", "low"


class SessionAnalyzer:
    """Analyze session history for patterns and skill suggestions.

    Example:
        >>> analyzer = SessionAnalyzer()
        >>> suggestions = analyzer.analyze_session_file("session.jsonl")
        >>> for suggestion in suggestions:
        ...     print(f"{suggestion.skill_name}: {suggestion.frequency} queries")
    """

    def __init__(
        self,
        min_frequency: int = 3,
        min_confidence: float = 0.7,
    ) -> None:
        """Initialize the session analyzer.

        Args:
            min_frequency: Minimum times a pattern must appear to be considered
            min_confidence: Minimum confidence threshold for suggestions
        """
        self.min_frequency = min_frequency
        self.min_confidence = min_confidence

    def analyze_session_file(
        self,
        session_file: Path | str,
    ) -> list[SkillSuggestion]:
        """Analyze a session file for patterns.

        Args:
            session_file: Path to session file (.jsonl or .json)

        Returns:
            List of skill suggestions
        """
        session_file = Path(session_file)

        if not session_file.exists():
            return []

        # Load session data
        if session_file.suffix == ".jsonl":
            queries = self._load_jsonl(session_file)
        else:
            queries = self._load_json(session_file)

        # Analyze patterns
        patterns = self._detect_patterns(queries)

        # Generate suggestions
        return self._generate_suggestions(patterns)

    def analyze_session_data(
        self,
        session_data: list[dict[str, Any]],
    ) -> list[SkillSuggestion]:
        """Analyze session data directly.

        Args:
            session_data: List of session entries

        Returns:
            List of skill suggestions
        """
        queries = self._extract_queries(session_data)
        patterns = self._detect_patterns(queries)
        return self._generate_suggestions(patterns)

    def _load_jsonl(self, file_path: Path) -> list[str]:
        """Load queries from JSONL file."""
        queries: list[str] = []

        for line in file_path.read_text(encoding="utf-8").strip().split("\n"):
            if not line:
                continue

            try:
                entry = json.loads(line)
                query = self._extract_query_from_entry(entry)
                if query:
                    queries.append(query)
            except (json.JSONDecodeError, KeyError):
                continue

        return queries

    def _load_json(self, file_path: Path) -> list[str]:
        """Load queries from JSON file."""
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))

            if isinstance(data, list):
                return self._extract_queries(data)  # type: ignore[reportUnknownArgumentType]
            elif isinstance(data, dict) and "messages" in data:
                return self._extract_queries(data["messages"])  # type: ignore[reportUnknownArgumentType]
            else:
                return []
        except (json.JSONDecodeError, KeyError):
            return []

    def _extract_queries(self, session_data: list[dict[str, Any]]) -> list[str]:
        """Extract user queries from session data."""
        queries: list[str] = []

        for entry in session_data:
            query = self._extract_query_from_entry(entry)
            if query:
                queries.append(query)

        return queries

    def _extract_query_from_entry(self, entry: dict[str, Any]) -> str | None:
        """Extract query from a single session entry."""
        # Try different message formats
        if "content" in entry:
            content = entry["content"]
        elif "message" in entry:
            content = entry["message"]
        elif "text" in entry:
            content = entry["text"]
        else:
            return None

        # Only extract user messages
        if entry.get("role") != "user" and entry.get("type") != "user":
            return None

        # Skip very short queries
        if len(content.strip()) < 10:
            return None

        return content.strip()

    def _detect_patterns(self, queries: list[str]) -> list[QueryPattern]:
        """Detect repeated patterns in queries.

        Uses string similarity clustering to find similar queries.
        Works with both English and Chinese queries.
        """
        if len(queries) < self.min_frequency:
            return []

        # Cluster by string similarity
        clusters = self._cluster_by_similarity(queries)

        # Convert to patterns
        patterns: list[QueryPattern] = []
        for cluster_queries in clusters:
            if len(cluster_queries) >= self.min_frequency:
                pattern = self._create_pattern(cluster_queries)
                if pattern.confidence >= self.min_confidence:
                    patterns.append(pattern)

        # Sort by frequency
        patterns.sort(key=lambda p: p.frequency, reverse=True)

        return patterns

    def _extract_keywords(self, query: str) -> set[str]:
        """Extract meaningful keywords from query."""
        # Convert to lowercase and tokenize
        words = query.lower().split()

        # Filter out common words
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "i",
            "me",
            "my",
            "myself",
            "we",
            "our",
            "ours",
            "ourselves",
            "you",
            "your",
            "yours",
            "yourself",
            "yourselves",
            "he",
            "him",
            "his",
            "himself",
            "she",
            "her",
            "hers",
            "herself",
            "it",
            "its",
            "itself",
            "they",
            "them",
            "their",
            "theirs",
            "themselves",
            "what",
            "which",
            "who",
            "whom",
            "this",
            "that",
            "these",
            "those",
            "am",
            "having",
            "doing",
            "帮",
            "我",
            "请",
            "的",
            "了",
            "是",
            "在",
            "有",
            "和",
            "与",
            "或",
            "但",
        }

        keywords: set[str] = set()
        for word in words:
            clean_word = re.sub(r"[^\w\s]", "", word)
            if clean_word not in stopwords and len(clean_word) > 2:
                keywords.add(clean_word)

        return keywords

    def _cluster_by_similarity(
        self,
        queries: list[str],
        similarity_threshold: float = 0.35,
    ) -> list[list[str]]:
        """Cluster queries by string similarity.

        Uses a simple character-based similarity that works for both
        English and Chinese.

        Args:
            queries: List of query strings
            similarity_threshold: Minimum similarity to cluster together

        Returns:
            List of query clusters
        """
        clusters: list[list[str]] = []
        used: set[int] = set()

        for i, query1 in enumerate(queries):
            if i in used:
                continue

            cluster = [query1]
            used.add(i)

            # Find similar queries
            for j, query2 in enumerate(queries):
                if j in used or j == i:
                    continue

                similarity = self._calculate_similarity(query1, query2)
                if similarity >= similarity_threshold:
                    cluster.append(query2)
                    used.add(j)

            clusters.append(cluster)

        return clusters

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings.

        Uses character overlap ratio which works for both
        English and Chinese text.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity score [0, 1]
        """
        set1 = set(str1.lower())
        set2 = set(str2.lower())

        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        return intersection / union

    def _create_pattern(self, queries: list[str]) -> QueryPattern:
        """Create a pattern from a cluster of queries."""
        # Extract common keywords
        all_keywords: list[set[str]] = [self._extract_keywords(q) for q in queries]
        common_keywords: set[str] = set.intersection(*all_keywords) if all_keywords else set()  # type: ignore[reportUnknownMemberType, reportUnknownVariableType]

        if common_keywords:
            skill_name = "-".join(sorted(common_keywords)[:3])
        else:
            # Use first query's first few words
            first_words = queries[0].split()[:3]
            skill_name = "-".join(first_words).lower()

        # Calculate confidence based on consistency
        confidence = min(1.0, len(queries) / 10.0)

        return QueryPattern(
            queries=queries,
            frequency=len(queries),
            suggested_skill=skill_name,
            confidence=confidence,
        )

    def _generate_suggestions(
        self,
        patterns: list[QueryPattern],
    ) -> list[SkillSuggestion]:
        """Generate skill suggestions from patterns."""
        suggestions: list[SkillSuggestion] = []

        for pattern in patterns:
            # Estimate value based on frequency and confidence
            if pattern.frequency >= 5 and pattern.confidence >= 0.7:
                estimated_value = "high"
            elif pattern.frequency >= 3 and pattern.confidence >= 0.4:
                estimated_value = "medium"
            else:
                estimated_value = "low"

            # Generate description from queries
            description = self._generate_description(pattern.queries)

            suggestion = SkillSuggestion(
                skill_name=pattern.suggested_skill,
                description=description,
                trigger_queries=pattern.queries[:5],  # Top 5 examples
                frequency=pattern.frequency,
                confidence=pattern.confidence,
                estimated_value=estimated_value,
            )

            suggestions.append(suggestion)

        # Sort by estimated value and frequency
        value_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: (value_order[s.estimated_value], -s.frequency))

        return suggestions

    def _generate_description(self, queries: list[str]) -> str:
        """Generate a description from example queries."""
        if not queries:
            return "Automatically generated skill from usage patterns"

        # Use first query as base
        first_query = queries[0]

        # Extract main action
        action_words = [
            "help",
            "create",
            "fix",
            "debug",
            "review",
            "test",
            "检查",
            "修复",
            "调试",
            "审查",
            "测试",
            "帮助",
            "创建",
        ]

        for word in action_words:
            if word in first_query.lower():
                return f"Handle requests related to: {first_query[:50]}..."

        # Fallback
        return f"Automatically generated skill from {len(queries)} similar queries"
