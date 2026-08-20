"""Tests for corpus-level IDF evidence primitives (idf.py, M11)."""

from __future__ import annotations

import math

from vibesop.core.matching.idf import (
    ANCHOR_STOPWORDS,
    IDFTable,
    candidate_token_set,
    find_anchors,
)


def _cand(skill_id, name="", description="", intent="", keywords=None):
    return {
        "id": skill_id,
        "name": name,
        "description": description,
        "intent": intent,
        "keywords": keywords or [],
    }


def _pool(n_filler=20):
    """20 filler docs sharing 'commonword' + 1 doc holding rare terms."""
    pool = [
        _cand(f"filler-{i}", name=f"Filler {i}", keywords=["commonword", "plainstuff"])
        for i in range(n_filler)
    ]
    pool.append(_cand("rare-skill", name="zephyrloom", keywords=["quilting", "zephyrloom"]))
    return pool


class TestIDFTable:
    def test_rare_token_outweighs_common_token(self):
        table = IDFTable.build(_pool())
        assert table.weight("quilting") > table.weight("commonword")

    def test_weights_normalized_in_unit_interval(self):
        table = IDFTable.build(_pool())
        for token in ("quilting", "commonword", "never-seen-token"):
            w = table.weight(token)
            assert 0.0 < w <= 1.0

    def test_unseen_token_gets_max_weight(self):
        table = IDFTable.build(_pool())
        assert table.weight("never-seen-token") == 1.0

    def test_weight_matches_smoothed_formula(self):
        table = IDFTable.build(_pool())
        n = table.n_docs
        df_common = 20
        expected = (math.log((n + 1) / (df_common + 1)) + 1.0) / (math.log(n + 1) + 1.0)
        assert table.weight("commonword") == expected

    def test_empty_pool(self):
        table = IDFTable.build([])
        assert table.n_docs == 0
        assert table.weight("anything") == 1.0

    def test_weight_is_pool_relative_not_absolute(self):
        """Same df ratio in a different-sized pool keeps the ordering signal."""
        small = IDFTable(n_docs=5, doc_freq={"rare": 1, "common": 4})
        large = IDFTable(n_docs=500, doc_freq={"rare": 25, "common": 400})
        for table in (small, large):
            assert table.weight("rare") > table.weight("common")


class TestCandidateTokenSet:
    def test_covers_name_description_intent_keywords(self):
        c = _cand(
            "x",
            name="Zeta",
            description="handles flurbles",
            intent="mend things",
            keywords=["Quilting"],
        )
        tokens = candidate_token_set(c)
        assert {"zeta", "flurbles", "mend", "quilting"} <= tokens

    def test_non_list_keywords_tolerated(self):
        c = _cand("x", name="zeta", keywords="not-a-list")
        assert "zeta" in candidate_token_set(c)


class TestFindAnchors:
    def test_anchor_requires_specificity_and_evidence(self):
        table = IDFTable.build(_pool())
        anchors, nk = find_anchors(
            ["quilting", "commonword"],
            {"quilting", "commonword"},
            name="",
            keywords_text="",
            idf=table,
            min_weight=0.78,
        )
        assert anchors == ["quilting"]  # commonword too generic to anchor
        assert nk == []  # exact hit only — not in name/keywords

    def test_stopword_never_anchors(self):
        # "not" is absent from the pool → max IDF; it must still be ineligible.
        table = IDFTable.build(_pool())
        anchors, _ = find_anchors(
            ["not"], {"not"}, name="", keywords_text="", idf=table, min_weight=0.78
        )
        assert anchors == []
        assert "not" in ANCHOR_STOPWORDS

    def test_function_words_never_anchor(self):
        """gate14 pi BLOCK: high-IDF function words in a description must not
        become anchors. Pin one representative per word class."""
        table = IDFTable.build(_pool())
        for word in ("get", "make", "because", "should", "some", "there"):
            assert word in ANCHOR_STOPWORDS, f"{word} missing from ANCHOR_STOPWORDS"
            anchors, _ = find_anchors(
                [word], {word}, name="", keywords_text="", idf=table, min_weight=0.78
            )
            assert anchors == [], f"{word} must not anchor"

    def test_default_stop_words_are_subset(self):
        """gate14b pi BLOCK: the documented superset claim must hold by
        construction — 'as' was in DEFAULT_STOP_WORDS but missing here."""
        from vibesop.core.matching.tokenizers import DEFAULT_STOP_WORDS

        assert set(DEFAULT_STOP_WORDS) <= set(ANCHOR_STOPWORDS)

    def test_gate14b_function_words_never_anchor(self):
        """gate14b pi BLOCK: 'can you together update today before friday'
        anchored oneshot-web-spec at 0.623 via 'together' alone."""
        table = IDFTable.build(_pool())
        for word in ("as", "like", "together", "fully", "today", "despite"):
            assert word in ANCHOR_STOPWORDS, f"{word} missing from ANCHOR_STOPWORDS"
            anchors, _ = find_anchors(
                [word], {word}, name="", keywords_text="", idf=table, min_weight=0.78
            )
            assert anchors == [], f"{word} must not anchor"

    def test_latin_substring_evidence_requires_word_boundary(self):
        """gate14 claude nit: "art" must not be evidenced by "smart"."""
        table = IDFTable.build(_pool())
        anchors, nk = find_anchors(
            ["art"], set(), name="", keywords_text="smart charts", idf=table, min_weight=0.78
        )
        assert anchors == [] and nk == []
        # ...but a whole-word occurrence still evidences.
        anchors, nk = find_anchors(
            ["art"], set(), name="", keywords_text="art class", idf=table, min_weight=0.78
        )
        assert anchors == ["art"] and nk == ["art"]

    def test_cjk_substring_evidence_keeps_plain_containment(self):
        table = IDFTable.build(_pool())
        # CJK has no word boundaries; plain containment is the correct semantic.
        anchors, nk = find_anchors(
            ["绗缝"], set(), name="", keywords_text="学习绗缝技艺", idf=table, min_weight=0.78
        )
        assert anchors == ["绗缝"] and nk == ["绗缝"]

    def test_name_and_keywords_count_as_curated(self):
        table = IDFTable.build(_pool())
        anchors, nk = find_anchors(
            ["zephyrloom", "quilting"],
            set(),
            name="zephyrloom",
            keywords_text="quilting",
            idf=table,
            min_weight=0.78,
        )
        assert sorted(anchors) == ["quilting", "zephyrloom"]
        assert sorted(nk) == ["quilting", "zephyrloom"]
