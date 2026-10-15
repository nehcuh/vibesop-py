"""BM25 candidate recall and reciprocal-rank fusion, without optional ML deps."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from vibesop.core.matching.tokenizers import DEFAULT_STOP_WORDS
from vibesop.core.routing.triage_recall import EmbeddingRecall

_ATOMS = re.compile(r"[a-z0-9_]+(?:[-./:][a-z0-9_]+)*|[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+")


def lexical_tokens(text: str) -> list[str]:
    """Keep identifiers adjacent to CJK intact; use overlapping CJK bigrams.

    Namespaced/hyphenated atoms are indexed both whole and by component.
    This tokenizer is local to recall, leaving existing matcher contracts intact.
    """
    tokens: list[str] = []
    for atom in _ATOMS.findall(text.lower()):
        if atom[0].isascii():
            if atom not in DEFAULT_STOP_WORDS:
                tokens.append(atom)
            if re.search(r"[-./:]", atom):
                tokens.extend(t for t in re.split(r"[-./:]", atom) if t not in DEFAULT_STOP_WORDS)
        elif len(atom) == 1:
            tokens.append(atom)
        else:
            tokens.extend(atom[i : i + 2] for i in range(len(atom) - 1))
    return tokens


def bm25_recall(query: str, candidates: list[dict[str, Any]], top_n: int) -> list[str]:
    """Rank positive lexical evidence with BM25 (k1=1.2, b=0.75).

    Scores are corpus-relative; they never become routing confidence. Sorting
    equal scores by full ID keeps discovery order from deciding the shortlist.
    """
    if not candidates or top_n <= 0:
        return []
    docs = [
        Counter(lexical_tokens(EmbeddingRecall._candidate_text(c) + " " + str(c.get("name", ""))))
        for c in candidates
    ]
    lengths = [sum(doc.values()) for doc in docs]
    average = sum(lengths) / len(docs)
    if not average:
        return []
    frequencies = Counter(t for doc in docs for t in doc)
    query_terms = sorted(set(lexical_tokens(query)))
    scores: list[tuple[str, float]] = []
    for candidate, doc, length in zip(candidates, docs, lengths, strict=True):
        score = 0.0
        for token in query_terms:
            tf = doc[token]
            if tf:
                idf = math.log1p(
                    (len(docs) - frequencies[token] + 0.5) / (frequencies[token] + 0.5)
                )
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / average))
        if score > 0:
            scores.append((str(candidate["id"]), score))
    return [sid for sid, _ in sorted(scores, key=lambda item: (-item[1], item[0]))[:top_n]]


def fuse_rankings(*rankings: list[str], top_n: int, k: int = 60) -> list[str]:
    """RRF with k=60, counting each identity at most once per recall lane."""
    scores: Counter[str] = Counter()
    for ranking in rankings:
        for rank, sid in enumerate(dict.fromkeys(ranking), 1):
            scores[sid] += 1 / (k + rank)
    return sorted(scores, key=lambda sid: (-scores[sid], sid))[: max(0, top_n)]
