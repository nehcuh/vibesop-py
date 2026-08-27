"""Concrete matcher implementations for unified matching system.

This module provides production-ready implementations of the IMatcher protocol:
- KeywordMatcher: Fast keyword-based matching (<1ms)
- TFIDFMatcher: TF-IDF semantic matching (~5ms)
- EmbeddingMatcher: Vector embedding matching (~20ms)
- LevenshteinMatcher: Fuzzy matching for typos (~10ms)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vibesop.core.matching.base import (
    MatchResult,
    MatcherType,
    RoutingContext,
    SimilarityMetric,
)
from vibesop.core.matching.idf import (
    ANCHOR_STOPWORDS,
    IDFTable,
    candidate_token_set,
    find_anchors,
)
from vibesop.core.matching.similarity import SimilarityCalculator
from vibesop.core.matching.tfidf import TFIDFCalculator
from vibesop.core.matching.tokenizers import TokenizerConfig, tokenize

if TYPE_CHECKING:
    from vibesop.core.types import (
        ConfidenceScore,
        MatcherCapabilitiesDict,
        SkillCandidateDict,
    )

if TYPE_CHECKING:
    import numpy as np
else:
    try:
        import numpy as np
    except ImportError:
        np = None


@dataclass
class MatcherConfig:
    """Configuration for matchers."""

    min_confidence: float = 0.3
    case_sensitive: bool = False
    use_cache: bool = True
    tokenizer_config: TokenizerConfig = field(default_factory=TokenizerConfig)
    # --- M11 evidence-based scoring knobs (mirror RoutingConfig; populated
    # by RouterFactory.build_matchers from the active RoutingConfig). ---
    # Coverage-gate saturation point: bonus scale g = min(1, cov/ref).
    keyword_coverage_ref: float = 0.5
    # Minimum normalized IDF weight for a token to count as an anchor.
    keyword_anchor_idf_min: float = 0.78
    # Score cap when no anchor evidences the match.
    keyword_anchor_cap: float = 0.25
    # Multi-anchor exemption: >= this many name/keyword anchors plus
    # coverage >= keyword_multi_anchor_cov_floor saturate the gate (g=1).
    keyword_multi_anchor_min: int = 2
    keyword_multi_anchor_cov_floor: float = 0.08
    # Single-token names need this IDF weight to earn the name bonus.
    keyword_name_idf_min: float = 0.7
    # Drop TF-IDF results that have no anchor evidence.
    tfidf_anchor_gate_enabled: bool = True


def _is_meaningful_token(token: str) -> bool:
    """Shared meaningful-token convention for scoring denominators/filters.

    CJK characters are meaningful even as 2-character tokens; Latin tokens
    need at least 3 characters. Used by KeywordMatcher (partial-match bonus)
    and LevenshteinMatcher (coverage denominator); also imported by
    core/instinct/routing_pending.py for its low-information query gate.
    """
    if any("\u4e00" <= ch <= "\u9fff" for ch in token):
        return len(token) >= 2
    return len(token) >= 3


class KeywordMatcher:
    """Fast keyword-based matcher."""

    def __init__(self, config: MatcherConfig | None = None):
        self._config = config or MatcherConfig()
        self._cache: dict[str, list[MatchResult]] = {}
        self._idf: IDFTable | None = None

    def match(
        self,
        query: str,
        candidates: list[SkillCandidateDict],
        context: RoutingContext | None = None,  # noqa: ARG002
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Match query against candidates using keyword detection."""
        cache_key = f"keyword:{query}"
        if self._config.use_cache and cache_key in self._cache:
            return self._cache[cache_key][:top_k]

        # Tokenize query
        query_tokens = set(
            tokenize(query, self._config.tokenizer_config)
            if not self._config.case_sensitive
            else query.split()
        )

        results: list[MatchResult] = []

        for candidate in candidates:
            score = self._score(query_tokens, candidate)
            if score >= self._config.min_confidence:
                results.append(
                    MatchResult(
                        skill_id=str(candidate.get("id", "")),
                        confidence=score,
                        score_breakdown={"keyword_match": score},
                        matcher_type=MatcherType.KEYWORD,
                        matched_keywords=self._get_matched_keywords(query_tokens, candidate),
                        metadata={
                            "matcher": "keyword",
                            "namespace": candidate.get("namespace", "builtin"),
                        },
                    )
                )

        # Sort by confidence descending
        results.sort(key=lambda r: r.confidence, reverse=True)

        if self._config.use_cache:
            self._cache[cache_key] = results

        return results[:top_k]

    def score(
        self,
        query: str,
        candidate: SkillCandidateDict,
        context: RoutingContext | None = None,
    ) -> ConfidenceScore:
        _ = context  # Protocol requirement
        query_tokens = set(
            tokenize(query, self._config.tokenizer_config)
            if not self._config.case_sensitive
            else query.split()
        )
        return self._score(query_tokens, candidate)

    def _score(self, query_tokens: set[str], candidate: SkillCandidateDict) -> ConfidenceScore:
        """Dispatch to evidence-based scoring once the pool IDF table exists.

        Before warm_up (e.g. a standalone ``score()`` call on a single
        candidate) there is no corpus to measure specificity against, so the
        legacy additive formula is used unchanged.
        """
        if self._idf is None:
            return self._score_legacy(query_tokens, candidate)
        return self._score_evidence(query_tokens, candidate)

    def _score_evidence(
        self, query_tokens: set[str], candidate: SkillCandidateDict
    ) -> ConfidenceScore:
        """Evidence-based scoring (M11): bonuses are gated by evidence quality.

        evidence = specificity (IDF anchors) x coverage (idf-weighted share
        of meaningful query tokens that hit the candidate):

        - partial bonus: per-query-token BEST pair only (no cross-pair
          accumulation — the old loop summed over every candidate token, so
          any long query maxed the 0.4 cap against any candidate).
        - substring bonus: idf-discounted per hit (generic tokens like
          "review"/"design" contribute little).
        - coverage gate: both bonuses are scaled by
          g = min(1, cov / keyword_coverage_ref), where cov is the
          idf-weighted hit share over meaningful query tokens.
        - anchor gate: without any anchor (non-stopword, high-idf token with
          exact/name/keyword evidence) the score is capped at
          keyword_anchor_cap, below the matcher min_confidence floor.
          Function words (ANCHOR_STOPWORDS) contribute no evidence at all —
          excluded from anchors, bonuses, and the coverage numerator AND
          denominator.
        - multi-anchor exemption: >= keyword_multi_anchor_min anchors in the
          CURATED fields (name/keywords) plus non-trivial coverage saturate
          the gate (g=1) — a focused query that names several distinctive
          terms of the skill is a genuine match even when long.
        - name bonus: only for multi-token names or single-token names with
          high specificity (keyword_name_idf_min); not coverage-scaled
          (the user literally named the skill).

        Calibration record: .omx/artifacts/m11-design-a.md.
        """
        cfg = self._config
        idf = self._idf
        assert idf is not None  # guaranteed by _score dispatch

        _tmp_keywords = candidate.get("keywords", [])
        keywords_list = _tmp_keywords if isinstance(_tmp_keywords, list) else []
        name = str(candidate.get("name", "")).lower()
        keywords_text = " ".join(str(k).lower() for k in keywords_list)
        candidate_tokens = candidate_token_set(candidate)

        union = query_tokens | candidate_tokens
        if not union:
            return 0.0
        exact_matches = query_tokens & candidate_tokens
        base_score = len(exact_matches) / len(union)

        # Function words carry no signal (gate14b pi BLOCK: "can"/"together"
        # rode prefix/substring hits to saturate the coverage gate and lift a
        # junk match to 0.7). They earn NO evidence at all — not anchors, not
        # bonuses, not coverage mass (numerator or denominator).
        meaningful = [
            qt for qt in query_tokens if _is_meaningful_token(qt) and qt not in ANCHOR_STOPWORDS
        ]

        # Per-query-token best partial hit (prefix 0.15 / substring 0.08),
        # plus the hit weight used by coverage (exact 1.0 / prefix 0.6 /
        # substring 0.32).
        partial_raw = 0.0
        hit_weight: dict[str, float] = {}
        for qt in meaningful:
            if qt in exact_matches:
                hit_weight[qt] = 1.0
                continue
            best = 0.0
            for ct in candidate_tokens:
                if ct in exact_matches:
                    continue
                if qt.startswith(ct) or ct.startswith(qt):
                    best = max(best, 0.15)
                elif qt in ct or ct in qt:
                    best = max(best, 0.08)
            partial_raw += best
            hit_weight[qt] = best / 0.15 * 0.6 if best else 0.0

        denominator = sum(idf.weight(qt) for qt in meaningful) or 1.0
        coverage = min(
            1.0,
            sum(idf.weight(qt) * hit_weight.get(qt, 0.0) for qt in meaningful) / denominator,
        )
        # max(..., 1e-9): keyword_coverage_ref=0 would otherwise divide by
        # zero; 0 degrades to "always saturated" (coverage gating off).
        gate = min(1.0, coverage / max(cfg.keyword_coverage_ref, 1e-9))

        # Deliberately plain containment (not word-boundary-checked like
        # find_anchors): this is a weak, IDF-discounted bonus capped at 0.5 —
        # cap-lifting/gate power lives exclusively in the anchor check.
        substring_bonus = min(
            0.5,
            sum(
                0.25 * (0.4 + 0.6 * idf.weight(qt))
                for qt in meaningful
                if qt in name or qt in keywords_text
            ),
        )

        name_bonus = 0.0
        # sorted(): set iteration order is nondeterministic; the containment
        # test below must not depend on it.
        query_lower = " ".join(sorted(query_tokens))
        if (
            name
            and _is_meaningful_token(query_lower)
            and (query_lower in name or name in query_lower)
        ):
            name_tokens = [t for t in tokenize(name) if _is_meaningful_token(t)]
            # Note: keyword_name_idf_min (0.7) is deliberately below the
            # anchor bar keyword_anchor_idf_min (0.78) — the [0.7, 0.78)
            # band is inconsistent with the anchor gate but conservative
            # (name-in-query is stronger evidence than a bare keyword hit,
            # so it tolerates slightly lower specificity).
            if len(name_tokens) >= 2 or (
                name_tokens and max(idf.weight(t) for t in name_tokens) >= cfg.keyword_name_idf_min
            ):
                name_bonus = 0.4

        anchors, nk_anchors = find_anchors(
            meaningful, exact_matches, name, keywords_text, idf, cfg.keyword_anchor_idf_min
        )
        if (
            len(nk_anchors) >= cfg.keyword_multi_anchor_min
            and coverage >= cfg.keyword_multi_anchor_cov_floor
        ):
            gate = 1.0

        score = min(1.0, base_score + gate * (min(partial_raw, 0.4) + substring_bonus) + name_bonus)
        if not anchors:
            score = min(score, cfg.keyword_anchor_cap)
        return score

    def _score_legacy(
        self, query_tokens: set[str], candidate: SkillCandidateDict
    ) -> ConfidenceScore:
        """Pre-M11 additive scoring, kept verbatim as the unwarmed fallback."""
        _tmp_keywords = candidate.get("keywords", [])
        keywords_list = _tmp_keywords if isinstance(_tmp_keywords, list) else []
        # Get text fields from candidate
        name = str(candidate.get("name", "")).lower()
        description = str(candidate.get("description", "")).lower()
        intent = str(candidate.get("intent", "")).lower()
        keywords_text = " ".join(str(k).lower() for k in keywords_list)
        text_fields = [name, description, intent, keywords_text]

        combined_text = " ".join(text_fields)
        candidate_tokens = set(tokenize(combined_text))

        # Calculate Jaccard similarity
        union = query_tokens | candidate_tokens
        if not union:
            return 0.0

        exact_matches = query_tokens & candidate_tokens
        base_score = len(exact_matches) / len(union)

        # Bonus for prefix/substring matches (e.g., "debug" matches "debugging")
        partial_bonus = 0.0
        for qt in query_tokens:
            if not _is_meaningful_token(qt) or qt in exact_matches:
                continue
            for ct in candidate_tokens:
                if ct in exact_matches:
                    continue
                if qt.startswith(ct) or ct.startswith(qt):
                    partial_bonus += 0.15
                elif qt in ct or ct in qt:
                    partial_bonus += 0.08

        # Exact substring match in name or keywords gets strong bonus
        substring_bonus = 0.0
        for qt in query_tokens:
            if _is_meaningful_token(qt) and (qt in name or qt in keywords_text):
                substring_bonus += 0.25

        # Exact name match (full query contained in name or vice versa)
        name_bonus = 0.0
        # sorted(): set iteration order is nondeterministic; the containment
        # test below must not depend on it.
        query_lower = " ".join(sorted(query_tokens))
        if (
            name
            and _is_meaningful_token(query_lower)
            and (query_lower in name or name in query_lower)
        ):
            name_bonus = 0.4

        return min(
            1.0, base_score + min(partial_bonus, 0.4) + min(substring_bonus, 0.5) + name_bonus
        )

    def _get_matched_keywords(
        self,
        query_tokens: set[str],
        candidate: SkillCandidateDict,
    ) -> list[str]:
        _tmp_keywords = candidate.get("keywords", [])
        keywords_list = _tmp_keywords if isinstance(_tmp_keywords, list) else []
        text_fields = [
            str(candidate.get("name", "")),
            str(candidate.get("description", "")),
            " ".join(str(k) for k in keywords_list),
        ]

        combined_text = " ".join(text_fields).lower()
        candidate_tokens = set(tokenize(combined_text))

        return list(query_tokens & candidate_tokens)

    def warm_up(self, candidates: list[SkillCandidateDict]) -> None:
        # Explicit reset semantics: rebuild the pool-level IDF table from
        # whatever pool is given — an EMPTY pool resets to None, returning
        # the matcher to the legacy (unwarmed) formula — and always drop
        # cached results computed against the previous pool.
        self._idf = IDFTable.build(candidates) if candidates else None
        self._cache.clear()

    def get_capabilities(self) -> MatcherCapabilitiesDict:
        return {
            "type": "keyword",
            "speed": "fast",
            "accuracy": "medium",
            "requires_semantic": False,
        }


class TFIDFMatcher:
    """TF-IDF based semantic matcher."""

    def __init__(self, config: MatcherConfig | None = None):
        self._config = config or MatcherConfig()
        self._tfidf_calc = TFIDFCalculator()
        self._similarity_calc = SimilarityCalculator(metric=SimilarityMetric.COSINE)
        self._fitted = False
        self._candidate_vectors: dict[str, dict[str, float]] = {}
        self._idf: IDFTable | None = None

    def fit(self, candidates: list[dict[str, Any]]) -> None:
        documents = []
        self._candidate_ids = []

        for candidate in candidates:
            text = self._candidate_to_text(candidate)
            tokens = tokenize(text, self._config.tokenizer_config)
            documents.append(tokens)
            self._candidate_ids.append(candidate.get("id", ""))

        # Fit TF-IDF
        self._tfidf_calc.fit(documents)
        # Pool-level IDF for the anchor gate (shares the candidate-token
        # definition with KeywordMatcher so both matchers gate identically).
        # Skip degenerate pools (<2 docs): every token would get w=1.0,
        # making every hit an "anchor" and the gate a no-op — worse, score()'s
        # single-candidate fit would leave that table behind and neuter the
        # gate for subsequent real match() calls (gate14 claude nit).
        self._idf = IDFTable.build(candidates) if len(candidates) >= 2 else None
        self._fitted = True

    def match(
        self,
        query: str,
        candidates: list[SkillCandidateDict],
        context: RoutingContext | None = None,  # noqa: ARG002
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Match query against candidates using TF-IDF similarity."""
        if not self._fitted:
            self.fit(candidates)

        # Transform query
        query_tokens = tokenize(query, self._config.tokenizer_config)
        query_vec = self._tfidf_calc.transform(query_tokens)

        results: list[MatchResult] = []

        for candidate in candidates:
            skill_id = str(candidate.get("id", ""))
            candidate_text = self._candidate_to_text(candidate)
            candidate_tokens = tokenize(candidate_text, self._config.tokenizer_config)
            candidate_vec = self._tfidf_calc.transform(candidate_tokens)

            # Calculate cosine similarity using TF-IDF vectors
            score = query_vec.dot_product(candidate_vec)

            if score >= self._config.min_confidence:
                results.append(
                    MatchResult(
                        skill_id=skill_id,
                        confidence=score,
                        score_breakdown={"tfidf_cosine": score},
                        matcher_type=MatcherType.TFIDF,
                        semantic_score=score,
                        metadata={
                            "matcher": "tfidf",
                            "namespace": candidate.get("namespace", "builtin"),
                        },
                    )
                )

        results.sort(key=lambda r: r.confidence, reverse=True)

        # Anchor gate (M11): TF-IDF cosine keys on surface overlap, so a
        # short query sharing one generic term with a candidate (e.g.
        # "commit", "review") can reach a routable score on noise alone.
        # Require at least one anchor — a non-stopword, high-specificity
        # query token with exact/name/keyword evidence (same definition as
        # the KeywordMatcher gate). Results without anchor evidence are
        # dropped, deferring to lower layers / no-match.
        if self._config.tfidf_anchor_gate_enabled and self._idf is not None and results:
            by_id = {str(c.get("id", "")): c for c in candidates}
            # Tokenize the query once; the per-candidate gate reuses it.
            meaningful = [
                t
                for t in set(tokenize(query, self._config.tokenizer_config))
                if _is_meaningful_token(t)
            ]
            results = [
                r
                for r in results
                if r.skill_id in by_id and self._has_anchor(meaningful, by_id[r.skill_id])
            ]

        return results[:top_k]

    def _has_anchor(self, meaningful: list[str], candidate: SkillCandidateDict) -> bool:
        """True iff the (pre-tokenized) query carries an anchor for this candidate."""
        assert self._idf is not None
        _tmp_keywords = candidate.get("keywords", [])
        keywords_list = _tmp_keywords if isinstance(_tmp_keywords, list) else []
        name = str(candidate.get("name", "")).lower()
        keywords_text = " ".join(str(k).lower() for k in keywords_list)
        candidate_tokens = candidate_token_set(candidate)
        exact_matches = set(meaningful) & candidate_tokens
        anchors, _ = find_anchors(
            meaningful,
            exact_matches,
            name,
            keywords_text,
            self._idf,
            self._config.keyword_anchor_idf_min,
        )
        return bool(anchors)

    def score(
        self,
        query: str,
        candidate: SkillCandidateDict,
        context: RoutingContext | None = None,
    ) -> ConfidenceScore:
        _ = context  # Protocol requirement
        if not self._fitted:
            # Single candidate fit
            self.fit([candidate])

        query_tokens = tokenize(query, self._config.tokenizer_config)
        query_vec = self._tfidf_calc.transform(query_tokens)

        candidate_text = self._candidate_to_text(candidate)
        candidate_tokens = tokenize(candidate_text, self._config.tokenizer_config)
        candidate_vec = self._tfidf_calc.transform(candidate_tokens)

        return query_vec.dot_product(candidate_vec)

    def _candidate_to_text(self, candidate: SkillCandidateDict) -> str:
        _tmp_keywords = candidate.get("keywords", [])
        keywords_list = _tmp_keywords if isinstance(_tmp_keywords, list) else []
        _tmp_triggers = candidate.get("triggers", [])
        triggers_list = _tmp_triggers if isinstance(_tmp_triggers, list) else []

        # Optimized field weights based on failure analysis
        fields = [
            # Name - highest weight (most direct indicator)
            str(candidate.get("name", "")),
            str(candidate.get("name", "")),
            str(candidate.get("name", "")),
            str(candidate.get("name", "")),
            str(candidate.get("name", "")),
            # Intent - highest weight (semantic clarity)
            str(candidate.get("intent", "")),
            str(candidate.get("intent", "")),
            str(candidate.get("intent", "")),
            str(candidate.get("intent", "")),
            str(candidate.get("intent", "")),
            # Keywords - high weight (specific scenarios)
            " ".join(str(k) for k in keywords_list),
            " ".join(str(k) for k in keywords_list),
            " ".join(str(k) for k in keywords_list),
            # Triggers - medium weight (pattern matching)
            " ".join(str(t) for t in triggers_list),
            " ".join(str(t) for t in triggers_list),
            # Description - lowest weight (noisy, keep minimal)
            str(candidate.get("description", "")),
        ]
        return " ".join(fields)

    def warm_up(self, candidates: list[SkillCandidateDict]) -> None:
        if candidates:
            self.fit(candidates)
        else:
            # Explicit reset, symmetric with KeywordMatcher.warm_up: an empty
            # pool must not keep gating on stale fit/IDF statistics.
            self._fitted = False
            self._idf = None

    def get_capabilities(self) -> MatcherCapabilitiesDict:
        return {
            "type": "tfidf",
            "speed": "medium",
            "accuracy": "good",
            "requires_semantic": False,
        }


class EmbeddingMatcher:
    """Vector embedding matcher using sentence transformers."""

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        config: MatcherConfig | None = None,
    ):
        self._config = config or MatcherConfig()
        self._model_name = model_name
        self._model = None
        self._candidate_embeddings: dict[str, Any] | None = None

    def _load_model(self) -> None:
        if self._model is not None:
            return

        try:
            from vibesop.core.embedding_loader import load_sentence_transformer

            self._model = load_sentence_transformer(self._model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for EmbeddingMatcher. "
                "Install with: pip install sentence-transformers"
            ) from None

    def fit(self, candidates: list[dict[str, Any]]) -> None:
        if np is None:
            raise ImportError("numpy is required for EmbeddingMatcher")

        self._load_model()

        texts = [self._candidate_to_text(c) for c in candidates]
        assert self._model is not None
        embeddings = self._model.encode(texts)

        self._candidate_embeddings = {
            c.get("id", ""): embeddings[i] for i, c in enumerate(candidates)
        }
        self._candidate_ids = [c.get("id", "") for c in candidates]

    def match(
        self,
        query: str,
        candidates: list[SkillCandidateDict],
        context: RoutingContext | None = None,  # noqa: ARG002
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Match query using vector embeddings."""
        if np is None:
            return []

        self._load_model()

        # Fit if not already done
        if self._candidate_embeddings is None:
            self.fit(candidates)

        # Encode query
        assert self._model is not None
        query_embedding = self._model.encode([query])[0]

        results: list[MatchResult] = []

        assert self._candidate_embeddings is not None
        for candidate in candidates:
            skill_id = str(candidate.get("id", ""))
            if skill_id not in self._candidate_embeddings:
                continue

            candidate_embedding = self._candidate_embeddings[skill_id]

            # Calculate cosine similarity
            score = float(
                np.dot(query_embedding, candidate_embedding)
                / (np.linalg.norm(query_embedding) * np.linalg.norm(candidate_embedding) + 1e-10)
            )

            if score >= self._config.min_confidence:
                results.append(
                    MatchResult(
                        skill_id=skill_id,
                        confidence=score,
                        score_breakdown={"embedding_cosine": score},
                        matcher_type=MatcherType.EMBEDDING,
                        semantic_score=score,
                        metadata={
                            "matcher": "embedding",
                            "model": self._model_name,
                            "namespace": candidate.get("namespace", "builtin"),
                        },
                    )
                )

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:top_k]

    def score(
        self,
        query: str,
        candidate: SkillCandidateDict,
        context: RoutingContext | None = None,
    ) -> float:
        results = self.match(query, [candidate], context, top_k=1)
        return results[0].confidence if results else 0.0

    def _candidate_to_text(self, candidate: SkillCandidateDict) -> str:
        fields = [
            str(candidate.get("name", "")),
            str(candidate.get("description", "")),
            str(candidate.get("intent", "")),
        ]
        return " ".join(str(f) for f in fields if f)

    def warm_up(self, candidates: list[SkillCandidateDict]) -> None:
        if np is None:
            return
        self._load_model()
        if candidates and self._candidate_embeddings is None:
            self.fit(candidates)

    def get_capabilities(self) -> MatcherCapabilitiesDict:
        return {
            "type": "embedding",
            "speed": "slow",
            "accuracy": "excellent",
            "requires_semantic": True,
        }


# Aha demo builtins must not win pack-owned phrases via last-resort fuzzy
# match (`write tests` → commit-message, `review my changes` → code-review).
LEVENSHTEIN_EXCLUDED_SKILL_IDS = frozenset(
    {
        "builtin/commit-message",
        "builtin/code-review",
        "builtin/test-generation",
        "commit-message",
        "code-review",
        "test-generation",
    }
)


class LevenshteinMatcher:
    """Fuzzy matcher using Levenshtein distance."""

    def __init__(self, config: MatcherConfig | None = None):
        self._config = config or MatcherConfig()

    def match(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: RoutingContext | None = None,
        top_k: int = 10,
    ) -> list[MatchResult]:
        """Match query using Levenshtein distance."""
        results: list[MatchResult] = []

        for candidate in candidates:
            skill_id = str(candidate.get("id", ""))
            if skill_id in LEVENSHTEIN_EXCLUDED_SKILL_IDS:
                continue
            score = self.score(query, candidate, context)

            if score >= self._config.min_confidence:
                results.append(
                    MatchResult(
                        skill_id=str(candidate.get("id", "")),
                        confidence=score,
                        score_breakdown={"levenshtein": score},
                        matcher_type=MatcherType.LEVENSHTEIN,
                        metadata={
                            "matcher": "levenshtein",
                            "namespace": candidate.get("namespace", "builtin"),
                        },
                    )
                )

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:top_k]

    def score(
        self,
        query: str,
        candidate: SkillCandidateDict,
        context: RoutingContext | None = None,
    ) -> ConfidenceScore:
        _ = context  # Protocol requirement
        query_tokens = self._tokenize(query)
        candidate_tokens = self._candidate_tokens(candidate)

        if not query_tokens or not candidate_tokens:
            # Fallback to full-string comparison for very short inputs
            text = self._candidate_to_text(candidate)
            return self._normalized_similarity(query, text)

        # Score every meaningful query token against the best-matching
        # candidate token. Tokens below the similarity threshold count as 0
        # in the average — they used to be dropped from the denominator
        # entirely, so a single matching token could inflate the score to
        # 1.0 (e.g. "使用 review" scored 1.0 because only "review" counted).
        SIMILARITY_THRESHOLD = 0.7

        meaningful_tokens = [qt for qt in query_tokens if _is_meaningful_token(qt)]
        if not meaningful_tokens:
            return 0.0

        token_scores = []
        for qt in meaningful_tokens:
            best = max(self._normalized_similarity(qt, ct) for ct in candidate_tokens)
            token_scores.append(best if best >= SIMILARITY_THRESHOLD else 0.0)

        # Also include a bonus for exact name match
        name = str(candidate.get("name", "")).lower()
        name_bonus = 0.0
        if any(qt == name for qt in query_tokens):
            name_bonus = 0.15

        avg_score = sum(token_scores) / len(token_scores)
        return min(1.0, avg_score + name_bonus)

    def _normalized_similarity(self, s1: str, s2: str) -> float:
        distance = self._levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 1.0
        return 1.0 - (distance / max_len)

    def _tokenize(self, text: str) -> list[str]:
        import re

        return [t.lower() for t in re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text) if len(t) > 1]

    def _candidate_tokens(self, candidate: SkillCandidateDict) -> list[str]:
        tokens: set[str] = set()
        for key in ("name", "keywords", "tags"):
            value = candidate.get(key)
            if isinstance(value, str):
                tokens.update(self._tokenize(str(value)))
            elif isinstance(value, list):
                for item in value:
                    tokens.update(self._tokenize(str(item)))
        # Include skill ID parts as tokens
        skill_id = str(candidate.get("id", ""))
        tokens.update(skill_id.replace("/", " ").replace("-", " ").lower().split())
        return list(tokens)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Optimal string alignment distance (Levenshtein + adjacent transposition).

        Transposing adjacent characters costs 1 edit instead of 2: it is the
        most common typo class, and plain Levenshtein scored "reivew"→"review"
        at 2/6 = 0.667 similarity — below the 0.7 token threshold, so the
        coverage fix above would have zeroed genuine transposition typos.

        The discount only applies when BOTH tokens are ≥6 chars: at 4-5 chars
        it promoted real distinct-word pairs over the 0.7 threshold and
        misrouted end-to-end (form/from 0.75, trail/trial 0.8, angel/angle
        0.8, dairy/diary 0.8 — gate7 pi finding). Shorter pairs fall back to
        plain Levenshtein, i.e. exactly the pre-OSA behavior.

        Known residual: even at exactly 6+ chars, real distinct-word pairs
        can still clear 0.7 (casual/causal = 0.833 routable end-to-end —
        gate7b). Accepted with mitigations rather than a higher cutoff (which
        would kill genuine long-token typos like configuartion): Levenshtein
        is last-resort in the matcher pipeline, and weak-layer hits go to the
        human review queue (routing_pending).
        """
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        # s2 is the shorter token, so this means both are ≥6 chars.
        allow_transposition = len(s2) >= 6

        previous_row = list(range(len(s2) + 1))
        prev_prev_row: list[int] | None = None

        for i, c1 in enumerate(s1):
            current_row = [i + 1]

            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)

                best = min(insertions, deletions, substitutions)
                if (
                    allow_transposition
                    and prev_prev_row is not None
                    and i > 0
                    and j > 0
                    and c1 == s2[j - 1]
                    and s1[i - 1] == c2
                ):
                    best = min(best, prev_prev_row[j - 1] + 1)

                current_row.append(best)

            prev_prev_row = previous_row
            previous_row = current_row

        return previous_row[-1]

    def _candidate_to_text(self, candidate: SkillCandidateDict) -> str:
        return (
            str(str(candidate.get("name", ""))) + " " + str(str(candidate.get("description", "")))
        )

    def warm_up(self, candidates: list[SkillCandidateDict]) -> None:
        pass

    def get_capabilities(self) -> MatcherCapabilitiesDict:
        return {
            "type": "levenshtein",
            "speed": "medium",
            "accuracy": "medium",
            "requires_semantic": False,
        }


# Convenience exports
__all__ = [
    "EmbeddingMatcher",
    "KeywordMatcher",
    "LevenshteinMatcher",
    "MatcherConfig",
    "TFIDFMatcher",
]
