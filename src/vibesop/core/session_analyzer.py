"""Session history analyzer for pattern detection and skill suggestion.

Analyzes conversation history to:
1. Detect repeated query patterns
2. Identify skill creation opportunities
3. Generate automatic suggestions

Improvements over v1:
- Word-level Jaccard similarity instead of character-level
- CJK-aware tokenization for Chinese queries
- Bigram overlap for better semantic grouping
- Stopwords filtered at token level, not raw character level
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class QueryPattern:
    """A detected pattern in user queries."""

    queries: list[str]
    frequency: int
    suggested_skill: str
    confidence: float


@dataclass
class SkillSuggestion:
    """Suggestion for creating a new skill."""

    skill_name: str
    description: str
    trigger_queries: list[str]
    frequency: int
    confidence: float
    estimated_value: str


ENGLISH_STOPWORDS = frozenset(
    {
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
        "and",
        "but",
        "or",
    }
)

CHINESE_STOPWORDS = frozenset(
    {
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
        "这",
        "那",
        "个",
        "一",
        "不",
        "也",
        "就",
        "都",
        "要",
        "会",
        "能",
        "可以",
        "把",
        "被",
        "让",
        "给",
        "到",
        "去",
        "来",
        "上",
        "下",
        "中",
        "里",
        "外",
        "前",
        "后",
        "还",
        "又",
        "再",
        "很",
        "太",
        "吗",
        "呢",
        "吧",
        "啊",
        "嗯",
        "哦",
    }
)

ALL_STOPWORDS = ENGLISH_STOPWORDS | CHINESE_STOPWORDS


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
        self.min_frequency = min_frequency
        self.min_confidence = min_confidence

    def analyze_session_file(
        self,
        session_file: Path | str,
    ) -> list[SkillSuggestion]:
        session_file = Path(session_file)
        if not session_file.exists():
            return []

        if session_file.suffix == ".jsonl":
            queries = self._load_jsonl(session_file)
        else:
            queries = self._load_json(session_file)

        patterns = self._detect_patterns(queries)
        return self._generate_suggestions(patterns)

    def analyze_session_data(
        self,
        session_data: list[dict[str, Any]],
    ) -> list[SkillSuggestion]:
        queries = self._extract_queries(session_data)
        patterns = self._detect_patterns(queries)
        return self._generate_suggestions(patterns)

    def _load_jsonl(self, file_path: Path) -> list[str]:
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
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return self._extract_queries(data)
            elif isinstance(data, dict) and "messages" in data:
                return self._extract_queries(data["messages"])
            else:
                return []
        except (json.JSONDecodeError, KeyError):
            return []

    def _extract_queries(self, session_data: list[dict[str, Any]]) -> list[str]:
        queries: list[str] = []
        for entry in session_data:
            query = self._extract_query_from_entry(entry)
            if query:
                queries.append(query)
        return queries

    def _extract_query_from_entry(self, entry: dict[str, Any]) -> str | None:
        if "content" in entry:
            content = entry["content"]
        elif "message" in entry:
            content = entry["message"]
        elif "text" in entry:
            content = entry["text"]
        else:
            return None

        if entry.get("role") != "user" and entry.get("type") != "user":
            return None

        min_length = 4 if any("\u4e00" <= c <= "\u9fff" for c in content) else 10
        if len(content.strip()) < min_length:
            return None

        return content.strip()

    def _detect_patterns(self, queries: list[str]) -> list[QueryPattern]:
        if len(queries) < self.min_frequency:
            return []

        clusters = self._cluster_by_similarity(queries)
        patterns: list[QueryPattern] = []
        for cluster_queries in clusters:
            if len(cluster_queries) >= self.min_frequency:
                pattern = self._create_pattern(cluster_queries)
                if pattern.confidence >= self.min_confidence:
                    patterns.append(pattern)

        patterns.sort(key=lambda p: p.frequency, reverse=True)
        return patterns

    def _tokenize_query(self, query: str) -> set[str]:
        """Tokenize query into meaningful tokens.

        For English: extract alphabetic words (filtered by stopwords).
        For Chinese: extract overlapping character bigrams (sliding window)
        and single characters, filtered by Chinese stopwords.
        """
        tokens: set[str] = set()
        query_lower = query.lower()

        # Extract CJK segments and produce overlapping bigrams
        cjk_segments = re.findall(r"[\u4e00-\u9fff]+", query_lower)
        for segment in cjk_segments:
            # Single characters (filtered by stopwords)
            for ch in segment:
                if ch not in CHINESE_STOPWORDS:
                    tokens.add(ch)
            # Overlapping 2-character bigrams (sliding window)
            for i in range(len(segment) - 1):
                bigram = segment[i : i + 2]
                if bigram not in CHINESE_STOPWORDS:
                    tokens.add(bigram)

        # Extract English words
        english_words = re.findall(r"[a-zA-Z]{2,}", query_lower)
        for word in english_words:
            if word not in ENGLISH_STOPWORDS:
                tokens.add(word)

        return tokens

    def _extract_bigrams(self, tokens: set[str]) -> set[str]:
        """Extract bigrams from sorted tokens for better semantic matching."""
        sorted_tokens = sorted(tokens)
        if len(sorted_tokens) < 2:
            return set()
        return {f"{sorted_tokens[i]}_{sorted_tokens[i + 1]}" for i in range(len(sorted_tokens) - 1)}

    def calculate_similarity(self, query1: str, query2: str) -> float:
        """Calculate similarity between two queries (public API).

        Uses word-level Jaccard on tokenized queries.
        """
        tokens1 = self._tokenize_query(query1)
        tokens2 = self._tokenize_query(query2)
        return self._calculate_similarity(tokens1, tokens2)

    def _cluster_by_similarity(
        self,
        queries: list[str],
        similarity_threshold: float = 0.25,
    ) -> list[list[str]]:
        """Cluster queries by word-level Jaccard similarity.

        Uses token overlap instead of character overlap for much better
        semantic grouping. "database error" and "database connection failed"
        will cluster together, but "database error" and "baseball era" will not.
        """
        tokenized = [(q, self._tokenize_query(q)) for q in queries]
        clusters: list[list[str]] = []
        used: set[int] = set()

        for i, (query1, tokens1) in enumerate(tokenized):
            if i in used:
                continue

            cluster = [query1]
            used.add(i)

            for j, (query2, tokens2) in enumerate(tokenized):
                if j in used or j == i:
                    continue

                similarity = self._calculate_similarity(tokens1, tokens2)
                if similarity >= similarity_threshold:
                    cluster.append(query2)
                    used.add(j)

            clusters.append(cluster)

        return clusters

    def _calculate_similarity(self, tokens1: set[str], tokens2: set[str]) -> float:
        """Calculate word-level Jaccard similarity between two token sets.

        This is semantically meaningful — two queries about "debugging errors"
        will share "debug" and "error" tokens, giving high similarity.
        Character-level Jaccard was meaningless (shared characters != shared meaning).
        """
        if not tokens1 or not tokens2:
            return 0.0

        # Combine unigram and bigram similarity for better coverage
        bigrams1 = self._extract_bigrams(tokens1)
        bigrams2 = self._extract_bigrams(tokens2)

        # Unigram Jaccard
        uni_intersection = len(tokens1 & tokens2)
        uni_union = len(tokens1 | tokens2)
        uni_sim = uni_intersection / uni_union if uni_union > 0 else 0.0

        # Bigram Jaccard (if both have bigrams)
        if bigrams1 and bigrams2:
            bi_intersection = len(bigrams1 & bigrams2)
            bi_union = len(bigrams1 | bigrams2)
            bi_sim = bi_intersection / bi_union if bi_union > 0 else 0.0
            return max(uni_sim, bi_sim)

        return uni_sim

    def _extract_keywords(self, query: str) -> set[str]:
        return self._tokenize_query(query)

    def _create_pattern(self, queries: list[str]) -> QueryPattern:
        all_keywords: list[set[str]] = [self._extract_keywords(q) for q in queries]
        non_empty = [kw for kw in all_keywords if kw]
        common_keywords: set[str] = (
            set.intersection(*non_empty)
            if len(non_empty) >= 2
            else (non_empty[0] if non_empty else set())
        )

        if common_keywords:
            skill_name = "-".join(sorted(common_keywords)[:3])
        else:
            first_words = queries[0].split()[:3]
            skill_name = "-".join(first_words).lower()

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
        suggestions: list[SkillSuggestion] = []
        for pattern in patterns:
            if pattern.frequency >= 5 and pattern.confidence >= 0.7:
                estimated_value = "high"
            elif pattern.frequency >= 3 and pattern.confidence >= 0.4:
                estimated_value = "medium"
            else:
                estimated_value = "low"

            description = self._generate_description(pattern.queries)
            suggestion = SkillSuggestion(
                skill_name=pattern.suggested_skill,
                description=description,
                trigger_queries=pattern.queries[:5],
                frequency=pattern.frequency,
                confidence=pattern.confidence,
                estimated_value=estimated_value,
            )
            suggestions.append(suggestion)

        value_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: (value_order[s.estimated_value], -s.frequency))
        return suggestions

    def _generate_description(self, queries: list[str]) -> str:
        if not queries:
            return "Automatically generated skill from usage patterns"

        first_query = queries[0]
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

        return f"Automatically generated skill from {len(queries)} similar queries"
