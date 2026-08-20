"""Corpus-level IDF evidence primitives for matcher scoring (M11).

The keyword/TF-IDF matchers historically scored queries with purely additive
bonuses (prefix/substring/name) that were decoupled from query coverage: a
100-token query mentioning two generic words ("review", "复审") could reach
0.9+ against any candidate whose name/keywords contained them. This module
provides the shared evidence primitives used to fix that:

- ``IDFTable``: document-frequency statistics over the candidate pool
  (document = name + description + intent + keywords token set), giving a
  normalized per-token specificity weight ``w(t) ∈ (0, 1]``.
- ``find_anchors``: the "anchor" test — a meaningful query token that is
  BOTH highly specific (``w(t) >= anchor_min``) AND evidenced against the
  candidate (exact token hit, or word-boundary-respecting occurrence in
  name/keywords). Anchors are the specificity gate; coverage is computed by
  the callers.

Design note: the weights are pool-relative by construction and deliberately
pool-size-agnostic (log-compressed, normalized by the pool's own max), so
the mechanism does not depend on a particular catalog size. English function
words are additionally excluded via ``ANCHOR_STOPWORDS``: in a corpus of
skill names/keywords/descriptions, words like "get"/"not" are RARE (high
IDF) yet semantically empty — IDF alone cannot tell them apart from
genuinely distinctive terms.

See ``.omx/artifacts/m11-design-a.md`` for the calibration record.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any

from vibesop.core.matching.tokenizers import tokenize

if TYPE_CHECKING:
    from vibesop.core.types import SkillCandidateDict

# English function words excluded from keyword-score bonus/coverage/anchor
# evidence (anchors, partial/substring bonuses, and coverage
# numerator/denominator — gate14b: stopword prefix hits like "can"⊂"canvas"
# saturated the coverage gate and lifted a junk match to 0.7). The Jaccard
# base_score and whole-name containment bonus are deliberately NOT filtered
# (bounded, and the anchorless cap keeps them below the matcher floor).
# Deliberately
# SELF-CONTAINED — a literal union of the tokenizer's DEFAULT_STOP_WORDS and
# the standard function-word classes (articles, pronouns, modals, copulas,
# prepositions, conjunctions, common adverbs/determiners, high-frequency
# generic verbs): the canonical tokenizer only applies its own stop-word
# list in CLEAN mode while matchers run in CJK mode, so none of these are
# filtered before scoring, and referencing DEFAULT_STOP_WORDS here would
# silently break if that list's semantics change. In a skill-catalog corpus
# such words are RARE — e.g. "get" has w=0.83 in the 239-candidate M11
# calibration pool — and would otherwise pose as high-specificity anchors
# (gate14 pi BLOCK: "get this working on the new branch before the deadline"
# anchored mattpocock/grill-me via "get" alone). CJK needs no list: bigram
# tokenization already binds particles to context.
ANCHOR_STOPWORDS: frozenset[str] = frozenset(
    {
        # articles / determiners / quantifiers
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "each",
        "every",
        "all",
        "any",
        "both",
        "either",
        "neither",
        "some",
        "no",
        "such",
        "same",
        "other",
        "others",
        "another",
        "much",
        "many",
        "few",
        "more",
        "most",
        "less",
        "least",
        "enough",
        "several",
        "own",
        # pronouns
        "i",
        "me",
        "my",
        "mine",
        "we",
        "us",
        "our",
        "ours",
        "you",
        "your",
        "yours",
        "he",
        "him",
        "his",
        "she",
        "her",
        "hers",
        "it",
        "its",
        "they",
        "them",
        "their",
        "theirs",
        "who",
        "whom",
        "whose",
        "which",
        "what",
        "whatever",
        "whoever",
        "myself",
        "yourself",
        "himself",
        "herself",
        "itself",
        "ourselves",
        "themselves",
        "one",
        "ones",
        "someone",
        "anyone",
        "everyone",
        "something",
        "anything",
        "everything",
        "nothing",
        "nobody",
        "anybody",
        "everybody",
        # copulas / auxiliaries / modals
        "am",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "done",
        "have",
        "has",
        "had",
        "having",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "ought",
        # prepositions
        "in",
        "on",
        "at",
        "by",
        "for",
        "from",
        "of",
        "to",
        "with",
        "about",
        "above",
        "below",
        "under",
        "over",
        "between",
        "among",
        "into",
        "onto",
        "through",
        "during",
        "before",
        "after",
        "around",
        "against",
        "along",
        "across",
        "behind",
        "beyond",
        "within",
        "without",
        "upon",
        "off",
        "out",
        "up",
        "down",
        "per",
        "via",
        # conjunctions / connectives
        "and",
        "or",
        "but",
        "nor",
        "so",
        "yet",
        "if",
        "then",
        "than",
        "because",
        "although",
        "though",
        "unless",
        "until",
        "while",
        "whereas",
        "since",
        "as",
        "like",
        "despite",
        "except",
        "besides",
        "regarding",
        "concerning",
        "toward",
        "towards",
        "underneath",
        "amongst",
        "therefore",
        "thus",
        "hence",
        "however",
        "moreover",
        "furthermore",
        "otherwise",
        "meanwhile",
        "whether",
        # common adverbs / misc function words
        "not",
        "very",
        "too",
        "just",
        "also",
        "only",
        "even",
        "still",
        "now",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "again",
        "once",
        "always",
        "never",
        "often",
        "sometimes",
        "usually",
        "already",
        "really",
        "quite",
        "rather",
        "instead",
        "anyway",
        "maybe",
        "perhaps",
        "probably",
        "etc",
        "yes",
        "well",
        "else",
        "ever",
        "nearly",
        "almost",
        "barely",
        "hardly",
        "seldom",
        "rarely",
        "soon",
        "later",
        "today",
        "tomorrow",
        "yesterday",
        "tonight",
        "somehow",
        "somewhat",
        "anywhere",
        "everywhere",
        "nowhere",
        "elsewhere",
        "anyhow",
        "ahead",
        "aside",
        "apart",
        "alone",
        "forward",
        "forwards",
        "backward",
        "backwards",
        "together",
        "fully",
        "accordingly",
        "thereby",
        "thereafter",
        "therein",
        "thereof",
        "wherein",
        "hereby",
        "hereafter",
        "henceforth",
        "nevertheless",
        "nonetheless",
        # high-frequency generic verbs (superset of DEFAULT_STOP_WORDS'
        # programming stop words)
        "use",
        "get",
        "make",
        "go",
        "take",
        "come",
        "keep",
        "let",
        "put",
        "say",
        "said",
        "see",
        "look",
        "want",
        "give",
        "tell",
        "work",
        "worked",
        "working",
        "need",
        "needs",
        "try",
        "tried",
        "going",
        "got",
        "made",
        "gotten",
    }
)

_CJK_RE = re.compile(r"[一-鿿]")


def _substring_evidence(token: str, text: str) -> bool:
    """Word-boundary-aware containment for anchor evidence.

    CJK tokens keep plain substring semantics (no word boundaries in CJK).
    Latin tokens must occur as a whole word — otherwise "art" would be
    evidenced by "smart" (gate14 claude nit).
    """
    if _CJK_RE.search(token):
        return token in text
    return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text) is not None


def candidate_token_set(candidate: SkillCandidateDict) -> set[str]:
    """Token set of a candidate's matchable text (name+description+intent+keywords).

    Must stay in sync with the text KeywordMatcher._score builds its
    candidate_tokens from — the IDF statistics describe exactly that corpus.
    """
    _tmp_keywords = candidate.get("keywords", [])
    keywords_list = _tmp_keywords if isinstance(_tmp_keywords, list) else []
    combined_text = " ".join(
        [
            str(candidate.get("name", "")).lower(),
            str(candidate.get("description", "")).lower(),
            str(candidate.get("intent", "")).lower(),
            " ".join(str(k).lower() for k in keywords_list),
        ]
    )
    return set(tokenize(combined_text))


class IDFTable:
    """Normalized IDF weights over a candidate pool.

    ``weight(t) = (ln((N+1)/(df(t)+1)) + 1) / (ln(N+1) + 1)`` — smoothed,
    log-compressed, and normalized by the pool's own maximum so weights land
    in (0, 1] regardless of pool size N.
    """

    def __init__(self, n_docs: int, doc_freq: dict[str, int]) -> None:
        self.n_docs = n_docs
        self._doc_freq = doc_freq
        self._max = math.log(n_docs + 1) + 1.0

    @classmethod
    def build(cls, candidates: list[dict[str, Any]]) -> IDFTable:
        doc_freq: dict[str, int] = {}
        for candidate in candidates:
            for token in candidate_token_set(candidate):
                doc_freq[token] = doc_freq.get(token, 0) + 1
        return cls(n_docs=len(candidates), doc_freq=doc_freq)

    def weight(self, token: str) -> float:
        """Normalized specificity weight in (0, 1]; unseen tokens get 1.0."""
        df = self._doc_freq.get(token, 0)
        return (math.log((self.n_docs + 1) / (df + 1)) + 1.0) / self._max


def find_anchors(
    meaningful_tokens: list[str],
    exact_matches: set[str],
    name: str,
    keywords_text: str,
    idf: IDFTable,
    min_weight: float,
) -> tuple[list[str], list[str]]:
    """Split meaningful query tokens into (anchors, name/keyword anchors).

    An anchor is a non-stopword token with ``idf.weight(t) >= min_weight``
    that is evidenced against the candidate: exact token-set hit, or a
    word-boundary-respecting occurrence in the candidate's name or keywords
    text. The second return value restricts to the curated fields
    (name/keywords) only — description hits are free-text coincidences and
    do not count as curated evidence (used by the multi-anchor coverage-gate
    exemption in KeywordMatcher).
    """
    anchors: list[str] = []
    nk_anchors: list[str] = []
    for token in meaningful_tokens:
        if token in ANCHOR_STOPWORDS or idf.weight(token) < min_weight:
            continue
        nk_hit = _substring_evidence(token, name) or _substring_evidence(token, keywords_text)
        if token in exact_matches or nk_hit:
            anchors.append(token)
            if nk_hit:
                nk_anchors.append(token)
    return anchors, nk_anchors


__all__ = [
    "ANCHOR_STOPWORDS",
    "IDFTable",
    "candidate_token_set",
    "find_anchors",
]
