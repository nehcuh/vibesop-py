"""Fuzzy matching using Levenshtein distance.

Implements Layer 4 of the routing system:
- Levenshtein distance for string similarity
- Phonetic matching for sound-alike terms
- Typo tolerance
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class FuzzyMatch:
    """Result of fuzzy matching.

    Attributes:
        skill_id: Matched skill ID
        score: Similarity score (0.0 to 1.0)
        distance: Levenshtein distance
        matched_text: The text that matched
    """

    skill_id: str
    score: float
    distance: int
    matched_text: str


class FuzzyMatcher:
    """Fuzzy matcher using Levenshtein distance.

    Usage:
        matcher = FuzzyMatcher()
        matcher.index_skills(config_loader.get_all_skills())
        result = matcher.match("reviw")  # Typo for "review"
        print(result.skill_id)  # /review
    """

    def __init__(
        self,
        min_similarity: float = 0.6,
        max_distance: int = 3,
    ) -> None:
        """Initialize the fuzzy matcher.

        Args:
            min_similarity: Minimum similarity threshold (0.0 to 1.0)
            max_distance: Maximum Levenshtein distance to consider
        """
        self.min_similarity = min_similarity
        self.max_distance = max_distance
        self._phrases: dict[str, str] = {}  # phrase -> skill_id mapping

    def index_skills(self, skills: list[dict[str, Any]]) -> None:
        """Index skills for fuzzy matching.

        Args:
            skills: List of skill definitions
        """
        self._phrases.clear()

        for skill in skills:
            skill_id = skill.get("id", "")

            # Extract phrases from skill_id
            # e.g., "gstack/review" -> ["gstack", "review"]
            parts = skill_id.split("/")
            for part in parts:
                self._phrases[part.lower()] = skill_id

            # Extract from intent
            intent = skill.get("intent", "")
            # Add keywords from intent (simple extraction)
            keywords = self._extract_keywords(intent)
            for keyword in keywords:
                self._phrases[keyword.lower()] = skill_id

    def match(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[FuzzyMatch]:
        """Find fuzzy matches for a query.

        Args:
            query: User query string (may contain typos)
            top_k: Number of top results to return

        Returns:
            List of fuzzy matches, sorted by score descending
        """
        if not self._phrases:
            return []

        # Tokenize query
        query_lower = query.lower()
        tokens = query_lower.split()

        matches = []

        # Try matching each token against known phrases
        for token in tokens:
            # Skip very short tokens
            if len(token) < 2:
                continue

            best_match = None
            best_score = 0.0

            for phrase, skill_id in self._phrases.items():
                # Calculate Levenshtein distance
                distance = self._levenshtein_distance(token, phrase)

                if distance <= self.max_distance:
                    # Calculate similarity score
                    max_len = max(len(token), len(phrase))
                    similarity = 1.0 - (distance / max_len)

                    if similarity > best_score:
                        best_score = similarity
                        best_match = (skill_id, phrase, similarity, distance)

            if (
                best_match
                and best_score >= self.min_similarity
                and not any(m.skill_id == best_match[0] for m in matches)
            ):
                    matches.append(
                        FuzzyMatch(
                            skill_id=best_match[0],
                            score=best_match[2],
                            distance=best_match[3],
                            matched_text=best_match[1],
                        )
                    )

        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)

        return matches[:top_k]

    def _levenshtein_distance(
        self,
        s1: str,
        s2: str,
    ) -> int:
        """Calculate Levenshtein distance between two strings.

        Uses dynamic programming for O(m*n) time complexity.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Edit distance (number of insertions, deletions, substitutions)
        """
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        # Previous row of distances
        previous_row = list(range(len(s2) + 1))

        for i, c1 in enumerate(s1):
            current_row = [i + 1]

            for j, c2 in enumerate(s2):
                # Calculate costs
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)

                # Take minimum
                current_row.append(min(insertions, deletions, substitutions))

            previous_row = current_row

        return previous_row[-1]

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from intent text.

        Args:
            text: Intent description

        Returns:
            List of keyword phrases
        """
        # Simple keyword extraction
        # Split by common separators
        separators = [" ", "-", "_", "/", "."]
        keywords = [text]

        for sep in separators:
            new_keywords = []
            for kw in keywords:
                new_keywords.extend(kw.split(sep))
            keywords = new_keywords

        # Filter and clean
        cleaned = []
        for kw in keywords:
            cleaned_kw = kw.strip().lower()
            if len(cleaned_kw) >= 3:  # Only keep meaningful keywords
                cleaned.append(cleaned_kw)

        return list(set(cleaned))  # Remove duplicates

    def suggest_corrections(
        self,
        query: str,
        max_suggestions: int = 3,
    ) -> list[str]:
        """Suggest spelling corrections for query terms.

        Args:
            query: Query string (may contain typos)
            max_suggestions: Maximum number of suggestions

        Returns:
            List of corrected query suggestions
        """
        matches = self.match(query, top_k=max_suggestions)

        if not matches:
            return []

        suggestions = []
        for match in matches:
            # Find and replace the typo
            query_parts = query.split()
            corrected_parts = []

            for part in query_parts:
                part_lower = part.lower()
                # Calculate distance to matched phrase
                distance = self._levenshtein_distance(
                    part_lower,
                    match.matched_text,
                )
                if distance <= self.max_distance:
                    # Suggest correction
                    corrected_parts.append(match.matched_text)
                else:
                    corrected_parts.append(part)

            suggestion = " ".join(corrected_parts)
            if suggestion not in suggestions:
                suggestions.append(suggestion)

        return suggestions[:max_suggestions]
