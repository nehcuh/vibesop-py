"""Tests for candidate prefilter."""

import pytest

from vibesop.core.optimization.prefilter import CandidatePrefilter, COMPLEXITY_INDICATORS


class TestCandidatePrefilterInit:
    """Test initialization."""

    def test_default_init(self):
        prefilter = CandidatePrefilter()
        assert prefilter._cluster_index is None
        assert "gstack" in prefilter._namespace_keywords

    def test_custom_namespace_keywords(self):
        prefilter = CandidatePrefilter(namespace_keywords={"custom": ["kw1"]})
        assert prefilter._namespace_keywords == {"custom": ["kw1"]}


class TestFromCandidates:
    """Test factory method."""

    def test_from_candidates_discovers_namespaces(self):
        candidates = [
            {"id": "custom/skill", "namespace": "custom", "tags": ["tag1"]},
        ]
        prefilter = CandidatePrefilter.from_candidates(candidates)
        assert "custom" in prefilter._namespace_keywords

    def test_from_candidates_merges_defaults(self):
        candidates = [
            {"id": "gstack/skill", "namespace": "gstack", "tags": ["review"]},
        ]
        prefilter = CandidatePrefilter.from_candidates(candidates)
        assert "gstack" in prefilter._namespace_keywords
        assert "review" in prefilter._namespace_keywords["gstack"]

    def test_from_candidates_empty(self):
        prefilter = CandidatePrefilter.from_candidates([])
        assert "gstack" in prefilter._namespace_keywords


class TestGetTriggeredNamespaces:
    """Test namespace triggering."""

    def test_trigger_gstack(self):
        prefilter = CandidatePrefilter()
        triggered = prefilter._get_triggered_namespaces("use gstack")
        assert "gstack" in triggered

    def test_trigger_superpowers(self):
        prefilter = CandidatePrefilter()
        triggered = prefilter._get_triggered_namespaces("superpowers help")
        assert "superpowers" in triggered

    def test_no_trigger(self):
        prefilter = CandidatePrefilter()
        triggered = prefilter._get_triggered_namespaces("hello world")
        assert triggered == set()

    def test_case_insensitive(self):
        prefilter = CandidatePrefilter()
        triggered = prefilter._get_triggered_namespaces("GSTACK")
        assert "gstack" in triggered


class TestFilterByPriority:
    """Test priority filtering."""

    def test_p0_always_included(self):
        prefilter = CandidatePrefilter()
        candidates = [
            {"id": "p0", "priority": "P0", "namespace": "ext"},
        ]
        result = prefilter._filter_by_priority("hello", candidates)
        assert len(result) == 1

    def test_builtin_always_included(self):
        prefilter = CandidatePrefilter()
        candidates = [
            {"id": "b", "namespace": "builtin"},
        ]
        result = prefilter._filter_by_priority("hello", candidates)
        assert len(result) == 1

    def test_complex_query_includes_all(self):
        prefilter = CandidatePrefilter()
        candidates = [
            {"id": "ext", "priority": "P2", "namespace": "external"},
        ]
        result = prefilter._filter_by_priority("architecture design", candidates)
        assert len(result) == 1

    def test_triggered_namespace_included(self):
        prefilter = CandidatePrefilter()
        candidates = [
            {"id": "g", "priority": "P2", "namespace": "gstack"},
        ]
        result = prefilter._filter_by_priority("use gstack", candidates)
        assert len(result) == 1

    def test_non_triggered_p2_excluded(self):
        prefilter = CandidatePrefilter()
        candidates = [
            {"id": "ext", "priority": "P2", "namespace": "external"},
        ]
        result = prefilter._filter_by_priority("hello", candidates)
        assert len(result) == 0


class TestFilterByNamespace:
    """Test namespace filtering."""

    def test_triggered_namespace_filters(self):
        prefilter = CandidatePrefilter()
        candidates = [
            {"id": "g1", "namespace": "gstack"},
            {"id": "s1", "namespace": "superpowers"},
        ]
        result = prefilter._filter_by_namespace("use gstack", candidates)
        assert len(result) == 1
        assert result[0]["id"] == "g1"

    def test_p0_kept_when_namespace_triggered(self):
        prefilter = CandidatePrefilter()
        candidates = [
            {"id": "p0", "priority": "P0", "namespace": "builtin"},
            {"id": "g1", "namespace": "gstack"},
        ]
        result = prefilter._filter_by_namespace("use gstack", candidates)
        assert len(result) == 2

    def test_no_trigger_passes_through(self):
        prefilter = CandidatePrefilter()
        candidates = [
            {"id": "g1", "namespace": "gstack"},
            {"id": "s1", "namespace": "superpowers"},
        ]
        result = prefilter._filter_by_namespace("hello", candidates)
        assert len(result) == 2


class TestFilter:
    """Test main filter method."""

    def test_empty_candidates(self):
        prefilter = CandidatePrefilter()
        assert prefilter.filter("hello", []) == []

    def test_filter_pipeline(self):
        prefilter = CandidatePrefilter()
        candidates = [
            {"id": "p0", "priority": "P0", "namespace": "builtin"},
            {"id": "g1", "priority": "P2", "namespace": "gstack"},
            {"id": "ext", "priority": "P2", "namespace": "external"},
        ]
        result = prefilter.filter("use gstack", candidates)
        ids = [c["id"] for c in result]
        assert "p0" in ids
        assert "g1" in ids
        assert "ext" not in ids

    def test_complex_query_keeps_all(self):
        prefilter = CandidatePrefilter()
        candidates = [
            {"id": "ext1", "priority": "P2", "namespace": "external"},
            {"id": "ext2", "priority": "P2", "namespace": "other"},
        ]
        result = prefilter.filter("this is a complex architecture design", candidates)
        assert len(result) == 2


class TestDiscoverNamespaceKeywords:
    """Test namespace discovery."""

    def test_discover_from_namespace_field(self):
        candidates = [
            {"id": "custom/skill", "namespace": "custom"},
        ]
        discovered = CandidatePrefilter._discover_namespace_keywords(candidates)
        assert "custom" in discovered
        assert "custom" in discovered["custom"]

    def test_discover_from_tags(self):
        candidates = [
            {"id": "custom/skill", "namespace": "custom", "tags": ["tag1", "tag2"]},
        ]
        discovered = CandidatePrefilter._discover_namespace_keywords(candidates)
        assert "tag1" in discovered["custom"]
        assert "tag2" in discovered["custom"]

    def test_no_namespace_skipped(self):
        candidates = [
            {"id": "skill"},
        ]
        discovered = CandidatePrefilter._discover_namespace_keywords(candidates)
        assert discovered == {}

    def test_multiple_candidates_same_namespace(self):
        candidates = [
            {"id": "custom/a", "namespace": "custom", "tags": ["tag1"]},
            {"id": "custom/b", "namespace": "custom", "tags": ["tag2"]},
        ]
        discovered = CandidatePrefilter._discover_namespace_keywords(candidates)
        assert "tag1" in discovered["custom"]
        assert "tag2" in discovered["custom"]


class TestComplexityIndicators:
    """Test complexity indicator constants."""

    def test_indicators_exist(self):
        assert "complex" in COMPLEXITY_INDICATORS
        assert "architecture" in COMPLEXITY_INDICATORS
        assert "架构" in COMPLEXITY_INDICATORS
