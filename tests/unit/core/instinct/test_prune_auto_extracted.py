"""Tests for ``InstinctLearner.prune_auto_extracted`` (Tier2 existing-data hygiene).

The auto_extract path historically minted instincts from garbage queries
(low-info acknowledgments, 700+ char megaprompts) and from weak last-resort
layers with inflated confidence. ``prune_auto_extracted`` removes those rows
using the same gates that now block new mints — the quality gate
(``is_auto_extract_worthy``) AND the trusted-layer gate — while never
touching human-confirmed instincts (manual, routing_pending accept/dismiss,
or anything with explicit positive feedback), whatever their pattern.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.instinct.learner import InstinctLearner

GOOD_PATTERN = "debug this routing error now"
LOW_INFO_PATTERN = "ok ok ok ok"  # zero meaningful tokens
MEGAPROMPT_PATTERN = " ".join(["fix the flaky routing test"] * 30)  # > 300 chars
ACTION = "suggest builtin/systematic-debugging skill"


def _learner(tmp_path: Path) -> InstinctLearner:
    return InstinctLearner(storage_path=tmp_path / "instincts.jsonl")


def _learn_auto(learner: InstinctLearner, pattern: str, **overrides) -> None:
    kwargs = {
        "action": ACTION,
        "context": "keyword",
        "tags": ["routing", "auto_extracted"],
        "source": "auto_routing",
    }
    kwargs.update(overrides)
    learner.learn(pattern=pattern, **kwargs)


class TestPruneAutoExtracted:
    def test_dry_run_reports_without_removing(self, tmp_path: Path) -> None:
        learner = _learner(tmp_path)
        _learn_auto(learner, LOW_INFO_PATTERN)
        _learn_auto(learner, MEGAPROMPT_PATTERN)
        _learn_auto(learner, GOOD_PATTERN)

        victims = learner.prune_auto_extracted(dry_run=True)

        assert {v.pattern for v in victims} == {LOW_INFO_PATTERN, MEGAPROMPT_PATTERN}
        assert len(learner.instincts) == 3  # nothing removed
        # And nothing changed on disk either.
        assert len(_learner(tmp_path).instincts) == 3

    def test_apply_removes_junk_and_keeps_good(self, tmp_path: Path) -> None:
        learner = _learner(tmp_path)
        _learn_auto(learner, LOW_INFO_PATTERN)
        _learn_auto(learner, MEGAPROMPT_PATTERN)
        _learn_auto(learner, GOOD_PATTERN)

        victims = learner.prune_auto_extracted(dry_run=False)

        assert {v.pattern for v in victims} == {LOW_INFO_PATTERN, MEGAPROMPT_PATTERN}
        remaining = {i.pattern for i in learner.instincts.values()}
        assert remaining == {GOOD_PATTERN}
        # Persisted: a fresh learner on the same file sees the pruned store.
        assert {i.pattern for i in _learner(tmp_path).instincts.values()} == {GOOD_PATTERN}

    def test_legacy_auto_routing_rows_without_tag_are_caught(self, tmp_path: Path) -> None:
        """Historical rows may carry source=auto_routing without the tag."""
        learner = _learner(tmp_path)
        _learn_auto(learner, LOW_INFO_PATTERN, tags=["routing"])

        victims = learner.prune_auto_extracted(dry_run=False)

        assert len(victims) == 1
        assert learner.instincts == {}

    def test_human_confirmed_instincts_survive_even_with_junk_pattern(
        self, tmp_path: Path
    ) -> None:
        """Only auto_extracted rows are eligible — manual/pending-accept
        instincts with a low-info pattern are the user's explicit choice."""
        learner = _learner(tmp_path)
        learner.learn(pattern=LOW_INFO_PATTERN, action=ACTION, source="manual")
        learner.learn(
            pattern=MEGAPROMPT_PATTERN,
            action=ACTION,
            context="routing_pending_accept",
            tags=["routing", "pending_accept"],
            source="routing_pending",
        )

        victims = learner.prune_auto_extracted(dry_run=False)

        assert victims == []
        assert len(learner.instincts) == 2

    def test_prune_empty_store_is_noop(self, tmp_path: Path) -> None:
        learner = _learner(tmp_path)
        assert learner.prune_auto_extracted(dry_run=False) == []


class TestPruneLayerGate:
    """gate8 nit: mint gate is conf AND trusted layer AND quality — prune must
    also enforce the layer axis, or legacy weak-layer mints with good-looking
    patterns survive forever."""

    @pytest.mark.parametrize("layer", ["levenshtein", "custom", "fallback_llm", "ai_triage"])
    def test_weak_layer_context_pruned_even_with_good_pattern(
        self, tmp_path: Path, layer: str
    ) -> None:
        learner = _learner(tmp_path)
        _learn_auto(learner, GOOD_PATTERN, context=layer)

        victims = learner.prune_auto_extracted(dry_run=False)

        assert [v.pattern for v in victims] == [GOOD_PATTERN]
        assert learner.instincts == {}

    def test_trusted_layer_context_with_good_pattern_survives(self, tmp_path: Path) -> None:
        learner = _learner(tmp_path)
        _learn_auto(learner, GOOD_PATTERN, context="keyword")
        _learn_auto(learner, "please review my code changes", context="semantic_index")

        assert learner.prune_auto_extracted(dry_run=False) == []
        assert len(learner.instincts) == 2

    @pytest.mark.parametrize("context", ["", "extracted_from_experiment", "weird"])
    def test_unknown_or_missing_context_falls_back_to_quality_gate(
        self, tmp_path: Path, context: str
    ) -> None:
        """Documented leniency: context that isn't a known routing layer value
        is NOT treated as untrusted — the quality gate alone decides."""
        learner = _learner(tmp_path)
        _learn_auto(learner, GOOD_PATTERN, context=context)

        assert learner.prune_auto_extracted(dry_run=False) == []
        assert len(learner.instincts) == 1

    def test_unknown_context_junk_pattern_still_pruned(self, tmp_path: Path) -> None:
        learner = _learner(tmp_path)
        _learn_auto(learner, LOW_INFO_PATTERN, context="")

        assert len(learner.prune_auto_extracted(dry_run=False)) == 1


class TestPruneHumanConfirmationGuard:
    """gate8 nit 1 (pi was right): learn() merges by id, so accept write-back
    used to keep source="auto_routing" + the auto_extracted tag — prune would
    have deleted a human-confirmed instinct. Fixed two ways; pin both."""

    def test_positive_outcome_marks_human_confirmation(self, tmp_path: Path) -> None:
        """Legacy rows accepted BEFORE the re-tagging fix still carry the
        auto_extracted tag — but success_count > 0 only ever comes from
        explicit positive feedback, so prune skips them."""
        learner = _learner(tmp_path)
        _learn_auto(learner, MEGAPROMPT_PATTERN, context="levenshtein")
        learner.record_outcome_for_query(MEGAPROMPT_PATTERN, success=True)

        assert learner.prune_auto_extracted(dry_run=False) == []
        assert len(learner.instincts) == 1

    def test_negative_outcome_does_not_protect(self, tmp_path: Path) -> None:
        """Dismiss/feedback-no is explicit confirmation that the row IS junk —
        failure_count must not shield it from prune."""
        learner = _learner(tmp_path)
        _learn_auto(learner, MEGAPROMPT_PATTERN, context="levenshtein")
        learner.record_outcome_for_query(MEGAPROMPT_PATTERN, success=False)

        assert len(learner.prune_auto_extracted(dry_run=False)) == 1
        assert learner.instincts == {}
