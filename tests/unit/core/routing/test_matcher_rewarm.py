"""Reload forces matcher re-warm (M11): pool-level statistics (keyword IDF
table, TF-IDF fit) must rebuild against the reloaded candidate pool."""

from __future__ import annotations

from vibesop.core.matching.strategies import KeywordMatcher
from vibesop.core.routing.unified import UnifiedRouter


class TestMatcherRewarmOnReload:
    def test_reload_candidates_resets_and_rebuilds_warm_state(self, tmp_path):
        router = UnifiedRouter(project_root=tmp_path)
        router.route("hello there", record_telemetry=False)  # triggers warm-up
        assert router._matchers_warmed is True

        router.reload_candidates()
        assert router._matchers_warmed is False

        router.route("hello again", record_telemetry=False)
        assert router._matchers_warmed is True
        # The keyword matcher re-warmed against the (possibly empty) reloaded
        # pool: warm_up always clears the query cache, and rebuilds the IDF
        # table iff the pool is non-empty.
        km = next(
            m for _layer, m in router._matcher_pipeline._matchers if isinstance(m, KeywordMatcher)
        )
        # Builtin skills load regardless of project_root, so the reloaded pool
        # is non-empty and the IDF table must have been rebuilt.
        assert km._idf is not None
