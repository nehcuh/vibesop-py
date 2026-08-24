"""M7 Tier1 slice A: levenshtein calibration + query pre-cleaning.

Covers:
    - Levenshtein last-resort semantics in the matcher pipeline (it used to
      win the max-confidence aggregation with inflated fuzzy scores, e.g.
      "使用 review" → kimi-gated-fix @1.0 in routing_pending.jsonl)
    - Slash-command EXPLICIT routing (pins the pre-existing explicit_layer
      suffix-match logic so it can't regress)
    - <user_query> wrapper pre-cleaning at the route() entry point
    - Regression queries from .vibe/instincts/routing_pending.jsonl
"""

from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING, Any

from vibesop.core.config.manager import RoutingConfig
from vibesop.core.models import RoutingLayer
from vibesop.core.routing import UnifiedRouter
from vibesop.core.routing.explicit_layer import check_explicit_override
from vibesop.core.routing.unified import _unwrap_user_query

if TYPE_CHECKING:
    from pathlib import Path


def _candidate(skill_id: str, name: str, keywords: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": skill_id,
        "name": name,
        "description": name,
        "intent": name,
        "keywords": keywords or [],
        "namespace": "builtin",
        "enabled": True,
    }


def _router(tmp_path: Path) -> UnifiedRouter:
    config = RoutingConfig(enable_ai_triage=False)
    return UnifiedRouter(project_root=tmp_path, config=config)


# Candidate set mimicking the routing_pending.jsonl incident skills.
INCIDENT_CANDIDATES = [
    _candidate("builtin/code-review", "code review", ["review", "代码审查"]),
    _candidate("omx/tdd", "tdd", ["tdd", "test"]),
    _candidate("superpowers/systematic-debugging", "systematic debugging", ["debug", "调试"]),
    _candidate("kimi-gated-fix", "kimi gated fix", ["gated", "fix"]),
]


class TestLevenshteinLastResort:
    """Levenshtein is only consulted when the calibrated matchers miss."""

    def test_suppressed_when_calibrated_matchers_hit(self, tmp_path: Path) -> None:
        """ "使用 review": keyword/tfidf match code-review; levenshtein's fuzzy
        score must not override them."""
        router = _router(tmp_path)
        primary, _alts, _detail = router._run_matcher_pipeline_levenshtein_last(
            "使用 review", INCIDENT_CANDIDATES, None
        )
        assert primary is not None
        assert primary.skill_id == "builtin/code-review"
        assert primary.layer != RoutingLayer.LEVENSHTEIN

    def test_adopted_when_other_matchers_miss(self, tmp_path: Path) -> None:
        """A genuine typo that no calibrated matcher recognizes still routes
        via levenshtein (last resort is not "never")."""
        router = _router(tmp_path)
        candidates = [
            _candidate("systematic-debugging", "systematic debugging", ["debug"]),
        ]
        primary, _alts, _detail = router._run_matcher_pipeline_levenshtein_last(
            "systmatic", candidates, None
        )
        assert primary is not None
        assert primary.skill_id == "systematic-debugging"
        assert primary.layer == RoutingLayer.LEVENSHTEIN

    def test_full_route_still_matches_typo(self, tmp_path: Path) -> None:
        """End-to-end: the two-pass pipeline keeps typo routing working."""
        router = _router(tmp_path)
        candidates = [
            _candidate("systematic-debugging", "systematic debugging", ["debug"]),
        ]
        result = router.route("systmatic", candidates=candidates)
        assert result.has_match
        assert result.primary is not None
        assert result.primary.skill_id == "systematic-debugging"

    def test_concurrent_routes_restore_full_matcher_list(self, tmp_path: Path) -> None:
        """gate7 pi BLOCK + gate7b claude #2 regression: the read-swap-restore
        AND the full second pass must be one critical section. With the
        window artificially widened, concurrent routes must (a) leave
        ``pipeline._matchers`` intact — a thread that snapshots the *reduced*
        list must never get to "restore" it as the full one — and (b) never
        run a "full" pass that silently lacks Levenshtein (would make this
        typo query transiently return None)."""
        router = _router(tmp_path)
        expected = list(router._matcher_pipeline._matchers)
        assert any(layer == RoutingLayer.LEVENSHTEIN for layer, _ in expected)

        # Widen the swap window so interleaving is near-certain.
        original = router._matcher_pipeline.try_matcher_pipeline

        def slow_pipeline(*args: Any, **kwargs: Any) -> Any:
            time.sleep(0.01)
            return original(*args, **kwargs)

        router._matcher_pipeline.try_matcher_pipeline = slow_pipeline

        candidates = [_candidate("systematic-debugging", "systematic debugging", ["debug"])]
        errors: list[BaseException] = []
        primaries: list[Any] = []

        def worker() -> None:
            try:
                for _ in range(10):
                    primary, _alts, _detail = router._run_matcher_pipeline_levenshtein_last(
                        "systmatic", candidates, None
                    )
                    primaries.append(primary)
            except BaseException as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert router._matcher_pipeline._matchers == expected
        assert any(
            layer == RoutingLayer.LEVENSHTEIN for layer, _ in router._matcher_pipeline._matchers
        )
        # Pass-2 coverage: "systmatic" only matches via Levenshtein, so every
        # run proves the full pass really contained it (no transient miss).
        assert len(primaries) == 80
        assert all(p is not None and p.skill_id == "systematic-debugging" for p in primaries)


class TestSlashExplicitRouting:
    """Pin the pre-existing slash-command logic in explicit_layer.py.

    The suffix-match branch (``/review`` → ``builtin/code-review`` via
    ``-review``) already existed; these tests lock it in so the matcher
    layers never see exact slash invocations again.
    """

    def test_unit_dash_suffix_match(self) -> None:
        candidates = [_candidate("builtin/code-review", "code review")]
        skill_id, _remainder = check_explicit_override("/review", candidates)
        assert skill_id == "builtin/code-review"

    def test_unit_namespace_suffix_match(self) -> None:
        candidates = [_candidate("omx/tdd", "tdd")]
        skill_id, _remainder = check_explicit_override("/tdd", candidates)
        assert skill_id == "omx/tdd"

    def test_unit_unknown_slash_falls_through(self) -> None:
        skill_id, _remainder = check_explicit_override("/nosuchskill", INCIDENT_CANDIDATES)
        assert skill_id is None

    def test_route_slash_review_is_explicit(self, tmp_path: Path) -> None:
        result = _router(tmp_path).route("/review", candidates=INCIDENT_CANDIDATES)
        assert result.has_match
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/code-review"
        assert result.primary.layer == RoutingLayer.EXPLICIT
        assert result.primary.confidence == 1.0

    def test_route_slash_tdd_is_explicit(self, tmp_path: Path) -> None:
        result = _router(tmp_path).route("/tdd", candidates=INCIDENT_CANDIDATES)
        assert result.has_match
        assert result.primary is not None
        assert result.primary.skill_id == "omx/tdd"
        assert result.primary.layer == RoutingLayer.EXPLICIT

    def test_route_unknown_slash_no_fuzzy_garbage(self, tmp_path: Path) -> None:
        """An unknown slash command must not fall into a 1.0 levenshtein hit."""
        result = _router(tmp_path).route("/nosuchskill", candidates=INCIDENT_CANDIDATES)
        assert result.primary is None or result.primary.layer in (
            RoutingLayer.FALLBACK_LLM,
            RoutingLayer.NO_MATCH,
        )


class TestUserQueryUnwrap:
    """route() strips a whole-query <user_query> wrapper before matching."""

    def test_unwrap_full_wrapper(self) -> None:
        assert _unwrap_user_query("<user_query>\n可以\n</user_query>") == "可以"
        assert _unwrap_user_query("  <user_query>debug this</user_query>  ") == "debug this"

    def test_unwrap_leaves_other_markup_alone(self) -> None:
        assert _unwrap_user_query("<other>debug</other>") == "<other>debug</other>"
        partial = "prefix <user_query>debug</user_query>"
        assert _unwrap_user_query(partial) == partial

    def test_unwrap_pathological_double_close_unchanged(self) -> None:
        """A second closing tag inside the wrapper must NOT unwrap — the
        naive non-greedy pattern turned this into 'fix</user_query> mid'."""
        pathological = "<user_query>fix</user_query> mid </user_query>"
        assert _unwrap_user_query(pathological) == pathological
        nested_close = "<user_query>a</user_query></user_query>"
        assert _unwrap_user_query(nested_close) == nested_close

    def test_unwrap_still_handles_normal_wrapper(self) -> None:
        assert _unwrap_user_query("<user_query>fix</user_query>") == "fix"
        assert _unwrap_user_query("<user_query>multi\nline\nquery</user_query>\n") == (
            "multi\nline\nquery"
        )

    def test_route_wrapped_query_matches_unwrapped(self, tmp_path: Path) -> None:
        router = _router(tmp_path)
        wrapped = router.route("<user_query>/review</user_query>", candidates=INCIDENT_CANDIDATES)
        bare = router.route("/review", candidates=INCIDENT_CANDIDATES)
        assert wrapped.primary is not None and bare.primary is not None
        assert wrapped.primary.skill_id == bare.primary.skill_id == "builtin/code-review"
        assert wrapped.primary.layer == RoutingLayer.EXPLICIT

    def test_wrapped_junk_markup_still_rejected(self, tmp_path: Path) -> None:
        """Unwrapping must not smuggle harness markup past the junk guard."""
        result = _router(tmp_path).route(
            "<user_query><system-reminder>junk</system-reminder></user_query>",
            candidates=INCIDENT_CANDIDATES,
        )
        assert result.primary is None

    def test_wrapped_junk_skips_telemetry(self, tmp_path: Path) -> None:
        """gate7 pi finding: markup revealed by the unwrap must keep the
        "junk never lands in the miss counter" invariant — route()'s
        telemetry block short-circuits for it."""
        router = _router(tmp_path)
        result = router.route(
            "<user_query><system-reminder>junk</system-reminder></user_query>",
            candidates=INCIDENT_CANDIDATES,
        )
        assert result.primary is None
        miss_file = tmp_path / ".vibe" / "miss_counter.json"
        assert not miss_file.exists() or json.loads(miss_file.read_text()) == {}
        pending_file = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
        assert not pending_file.exists() or not pending_file.read_text().strip()

    def test_unwrap_is_idempotent(self) -> None:
        """route() and _single_skill_route both unwrap (double layer) — the
        second pass over an already-unwrapped query must be a no-op."""
        wrapped = "<user_query>debug this</user_query>"
        once = _unwrap_user_query(wrapped)
        assert _unwrap_user_query(once) == once == "debug this"

    def test_single_skill_route_wrapped_junk_rejected(self, tmp_path: Path) -> None:
        """gate7b pi NIT-3: direct _single_skill_route callers (Orchestrator,
        session context, PlanBuilder) bypass route()'s entry unwrap — the
        sunk unwrap + junk re-check must reject wrapped markup here too."""
        result = _router(tmp_path)._single_skill_route(
            "<user_query><system-reminder>junk</system-reminder></user_query>",
            candidates=INCIDENT_CANDIDATES,
        )
        assert result.primary is None
        assert not result.has_match

    def test_orchestrate_wrapped_junk_no_mismatch(self, tmp_path: Path) -> None:
        """gate7b pi NIT-3: the same wrapped junk via orchestrate() must not
        fuzzy-match a skill (it used to hit an unrelated matcher result)."""
        result = _router(tmp_path).orchestrate(
            "<user_query><system-reminder>junk</system-reminder></user_query>",
            candidates=INCIDENT_CANDIDATES,
        )
        assert result.primary is None


class TestIncidentRegressions:
    """Regression set from .vibe/instincts/routing_pending.jsonl."""

    def test_shiyong_review_not_inflated_levenshtein(self, tmp_path: Path) -> None:
        """ "使用 review" used to route to kimi-gated-fix @1.0 via levenshtein."""
        result = _router(tmp_path).route("使用 review", candidates=INCIDENT_CANDIDATES)
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/code-review"
        assert result.primary.layer != RoutingLayer.LEVENSHTEIN

    def test_review_my_code_routes_to_review_skill(self, tmp_path: Path) -> None:
        result = _router(tmp_path).route("review my code", candidates=INCIDENT_CANDIDATES)
        assert result.primary is not None
        assert result.primary.skill_id == "builtin/code-review"
        assert result.primary.skill_id != "kimi-gated-fix"

    def test_debug_this_routes_to_debugging(self, tmp_path: Path) -> None:
        result = _router(tmp_path).route("debug this", candidates=INCIDENT_CANDIDATES)
        assert result.primary is not None
        assert "debug" in result.primary.skill_id

    def test_keyi_no_garbage_match(self, tmp_path: Path) -> None:
        """ "可以" is conversational noise — no skill may claim it, least of
        all at an inflated 1.0."""
        result = _router(tmp_path).route("可以", candidates=INCIDENT_CANDIDATES)
        assert result.primary is None or result.primary.layer in (
            RoutingLayer.FALLBACK_LLM,
            RoutingLayer.NO_MATCH,
        )

    def test_wrapped_keyi_no_garbage_match(self, tmp_path: Path) -> None:
        """The exact routing_pending.jsonl shape: wrapper + noise query."""
        result = _router(tmp_path).route(
            "<user_query>\n可以\n</user_query>", candidates=INCIDENT_CANDIDATES
        )
        assert result.primary is None or result.primary.layer in (
            RoutingLayer.FALLBACK_LLM,
            RoutingLayer.NO_MATCH,
        )

    def test_xiu_bug_no_inflated_levenshtein(self, tmp_path: Path) -> None:
        """ "修 bug" may match or miss, but never via a 1.0 levenshtein hit."""
        result = _router(tmp_path).route("修 bug", candidates=INCIDENT_CANDIDATES)
        assert not (
            result.primary is not None
            and result.primary.layer == RoutingLayer.LEVENSHTEIN
            and result.primary.confidence >= 0.99
        )
