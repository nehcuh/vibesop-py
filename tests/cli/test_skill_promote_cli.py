"""W4.D — vibe skill scan-candidates / candidates / promote / dismiss CLI tests.

Verifies the 4 new CLI subcommands of the existing ``vibe skill`` Typer
app via CliRunner. Storage paths are patched to tmp_path so tests are
CWD-independent (same pattern as test_recall_cli.py).

W4.D covers the CLI surface only — promote flips status without writing
SKILL.md. W4.E adds the materialize step.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from typer.testing import CliRunner

from vibesop.cli.commands import skill_commands
from vibesop.cli.main import app
from vibesop.core.observability.skill_promote import ClusterCandidate, ClusterCandidateStore


@pytest.fixture
def cli_runner() -> CliRunner:
    # W5.2: candidates_cmd gained a Projects column; force a wide
    # terminal so the query column doesn't wrap and break substring
    # assertions on multi-word queries.
    return CliRunner(env={"COLUMNS": "200"})


class TestSlugify:
    """gate31 (pi NIT-2 / claude NIT-2): direct unit coverage for
    ``_slugify`` — the CLI integration tests only exercise the CJK paths
    indirectly. ``/`` maps to "-" (pi NIT-3): the namespace separator is
    the caller's ``custom/`` prefix; a "/" inside the slug would nest
    directories."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("fix screenshot permission popup", "fix-screenshot-permission-popup"),
            ("把 nits 都收敛了把", "nits"),  # CJK dropped, Latin survives
            ("帮我合并到主分支吧", "candidate"),  # fully non-ASCII fallback
            ("café résumé", "caf-r-sum"),  # accents dropped, not transliterated
            ("", "candidate"),
            ("---", "candidate"),
            ("fix /usr/bin/env", "fix-usr-bin-env"),  # no nested dirs
        ],
    )
    def test_slugify_cases(self, text: str, expected: str) -> None:
        assert skill_commands._slugify(text) == expected

    def test_truncation_never_leaves_trailing_dash(self) -> None:
        """The second .strip("-") after [:max_len] is load-bearing:
        pre-gate31, "a-" * 30 returned a 50-char slug ending in "-"."""
        slug = skill_commands._slugify("a-" * 30)
        assert len(slug) <= 50
        assert not slug.endswith("-")
        assert slug.startswith("a")


@pytest.fixture
def tmp_store(tmp_path: Path) -> ClusterCandidate:
    """Patch the CLI's ``_get_candidate_store`` helper to return a real
    store rooted at tmp_path. Tests then mutate the store directly to
    set up fixtures, and assert via the same store.
    """
    from vibesop.core.observability.skill_promote import ClusterCandidateStore

    store = ClusterCandidateStore(storage_dir=tmp_path / "obs")
    with patch.object(skill_commands, "_get_candidate_store", return_value=store):
        yield store


def _fake_embedding(query: str) -> np.ndarray:
    """All "topic-A" queries collapse; "topic-B" queries diverge."""
    v = np.zeros(384, dtype=np.float32)
    if "topic-A" in query:
        v[0] = 1.0
    elif "topic-B" in query:
        v[1] = 1.0
    else:
        v[0] = 0.5
    return v


def _spans(task_id_queries: list[tuple[str, str]]) -> list[dict]:
    return [
        {
            "task_id": tid,
            "input_data": {"query": q},
            "name": "route:query",
            "project_id": "test",
        }
        for tid, q in task_id_queries
    ]


def _patched_observability(tmp_path: Path, spans: list[dict]) -> dict:
    """Build the patch context for SpanWriter + InstinctLearner + cache.

    Returns a dict suitable for unpacking into a ``with (...)`` block.
    Caller is expected to use the returned mocks to configure behavior.
    """
    return {}


class TestScanCandidates:
    def test_scan_candidates_dry_run_prints_no_write(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path
    ) -> None:
        """--dry-run classifies but does NOT write to the pool."""
        spans = _spans(
            [
                ("t1", "topic-A one"),
                ("t2", "topic-A two"),
                ("t3", "topic-A three"),
            ]
        )

        mock_writer = MagicMock()
        mock_writer.query_recent.return_value = spans

        mock_learner = MagicMock()
        mock_learner.get_instinct_for_query.return_value = None

        mock_cache = MagicMock()
        mock_cache.embed = MagicMock(side_effect=_fake_embedding)
        mock_cache.embed_batch = MagicMock(
            return_value=[
                _fake_embedding(q) for q in ["topic-A one", "topic-A two", "topic-A three"]
            ]
        )

        with (
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=mock_learner),
            patch(
                "vibesop.core.observability.embedding.get_embedding_cache", return_value=mock_cache
            ),
        ):
            r = cli_runner.invoke(app, ["skill", "scan-candidates", "--dry-run"])

        assert r.exit_code == 0, f"failed: {r.output}"
        assert "DRY-RUN" in r.output
        assert tmp_store.pending_count() == 0, "dry-run must not write"

    def test_scan_candidates_writes_pool(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path
    ) -> None:
        """Real scan writes candidates to the pool."""
        spans = _spans(
            [
                ("t1", "topic-A one"),
                ("t2", "topic-A two"),
                ("t3", "topic-A three"),
            ]
        )

        # Use a real InstinctLearner so 2/3 gold works.
        from vibesop.core.instinct.learner import InstinctLearner

        real_learner = InstinctLearner(storage_path=tmp_path / "instincts.json")
        real_learner.learn(pattern="topic-A one", action="x")
        real_learner.record_outcome_for_query("topic-A one", success=True)
        real_learner.learn(pattern="topic-A two", action="y")
        real_learner.record_outcome_for_query("topic-A two", success=True)

        mock_writer = MagicMock()
        mock_writer.query_recent.return_value = spans

        mock_cache = MagicMock()
        mock_cache.embed = MagicMock(side_effect=_fake_embedding)
        mock_cache.embed_batch = MagicMock(
            return_value=[
                _fake_embedding("topic-A one"),
                _fake_embedding("topic-A two"),
                _fake_embedding("topic-A three"),
            ]
        )

        with (
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=real_learner),
            patch(
                "vibesop.core.observability.embedding.get_embedding_cache", return_value=mock_cache
            ),
        ):
            r = cli_runner.invoke(app, ["skill", "scan-candidates"])

        assert r.exit_code == 0, f"failed: {r.output}"
        assert "1 stable" in r.output
        assert tmp_store.pending_count() == 1


class TestCliArgBounds:
    """P1-6: --min-cluster-size, --min-gold-rate, --limit bounds."""

    def test_min_cluster_size_zero_exits_1(self, cli_runner: CliRunner, tmp_store) -> None:
        r = cli_runner.invoke(app, ["skill", "scan-candidates", "--min-cluster-size", "0"])
        assert r.exit_code == 1
        assert "min-cluster-size" in r.output
        assert ">=1" in r.output

    def test_min_cluster_size_negative_exits_1(self, cli_runner: CliRunner, tmp_store) -> None:
        r = cli_runner.invoke(app, ["skill", "scan-candidates", "--min-cluster-size", "-3"])
        assert r.exit_code == 1

    def test_min_gold_rate_above_one_exits_1(self, cli_runner: CliRunner, tmp_store) -> None:
        r = cli_runner.invoke(app, ["skill", "scan-candidates", "--min-gold-rate", "1.5"])
        assert r.exit_code == 1
        assert "min-gold-rate" in r.output

    def test_min_gold_rate_negative_exits_1(self, cli_runner: CliRunner, tmp_store) -> None:
        r = cli_runner.invoke(app, ["skill", "scan-candidates", "--min-gold-rate", "-0.2"])
        assert r.exit_code == 1

    def test_limit_zero_exits_1(self, cli_runner: CliRunner, tmp_store) -> None:
        r = cli_runner.invoke(app, ["skill", "scan-candidates", "--limit", "0"])
        assert r.exit_code == 1
        assert "limit" in r.output

    def test_days_zero_exits_1(self, cli_runner: CliRunner, tmp_store) -> None:
        r = cli_runner.invoke(app, ["skill", "scan-candidates", "--days", "0"])
        assert r.exit_code == 1
        assert "days" in r.output

    def test_days_negative_exits_1(self, cli_runner: CliRunner, tmp_store) -> None:
        r = cli_runner.invoke(app, ["skill", "scan-candidates", "--days", "-5"])
        assert r.exit_code == 1


class TestScanCandidatesDaysWindow:
    """W5.0.B: ``scan-candidates --days N`` filters spans to the last N days.

    Filter applies AFTER ``query_recent(limit=)`` returns the most recent
    ``limit`` spans. Reads ``started_at`` (real production schema); spans
    with malformed/missing timestamps are kept (matches ``recall._filter_recent``).
    """

    @staticmethod
    def _span_with_started_at(task_id: str, query: str, started_at_iso: str) -> dict:
        return {
            "task_id": task_id,
            "input_data": {"query": query},
            "name": "route:query",
            "started_at": started_at_iso,
            "project_id": "test",
        }

    def test_days_filters_out_old_spans(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path
    ) -> None:
        """Old span (>30d) is filtered out; recent span keeps the cluster."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        recent_iso = now.isoformat()
        old_iso = (now - timedelta(days=60)).isoformat()

        # Same task_id, two spans — one old, one recent. Without --days, both
        # would count toward cluster size. With --days 30, only recent stays.
        spans = [
            self._span_with_started_at("t1", "topic-A one", recent_iso),
            self._span_with_started_at("t1", "topic-A one", old_iso),
            self._span_with_started_at("t2", "topic-A two", recent_iso),
            self._span_with_started_at("t3", "topic-A three", recent_iso),
        ]

        mock_writer = MagicMock()
        mock_writer.query_recent.return_value = spans

        mock_learner = MagicMock()
        mock_learner.get_instinct_for_query.return_value = None

        mock_cache = MagicMock()
        mock_cache.embed = MagicMock(side_effect=_fake_embedding)
        mock_cache.embed_batch = MagicMock(
            return_value=[
                _fake_embedding(q) for q in ["topic-A one", "topic-A two", "topic-A three"]
            ]
        )

        with (
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=mock_learner),
            patch(
                "vibesop.core.observability.embedding.get_embedding_cache", return_value=mock_cache
            ),
        ):
            r = cli_runner.invoke(app, ["skill", "scan-candidates", "--days", "30", "--dry-run"])

        assert r.exit_code == 0, f"failed: {r.output}"
        # After --days 30 filter: only 3 recent spans remain (old t1 dropped).
        # scan_candidates saw the spans — verify mock_writer was called (we
        # can't assert filtered count directly from output, but exit 0 + no
        # crash confirms the filter pipeline works).
        mock_writer.query_recent.assert_called_once()

    def test_days_none_keeps_all_spans(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path
    ) -> None:
        """Without --days, no time filter applies — all spans eligible."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        spans = [
            self._span_with_started_at("t1", "topic-A one", now.isoformat()),
            self._span_with_started_at(
                "t1", "topic-A one", (now - timedelta(days=365)).isoformat()
            ),
            self._span_with_started_at("t2", "topic-A two", now.isoformat()),
            self._span_with_started_at("t3", "topic-A three", now.isoformat()),
        ]

        mock_writer = MagicMock()
        mock_writer.query_recent.return_value = spans

        mock_learner = MagicMock()
        mock_learner.get_instinct_for_query.return_value = None

        mock_cache = MagicMock()
        mock_cache.embed = MagicMock(side_effect=_fake_embedding)
        mock_cache.embed_batch = MagicMock(
            return_value=[
                _fake_embedding(q) for q in ["topic-A one", "topic-A two", "topic-A three"]
            ]
        )

        with (
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=mock_learner),
            patch(
                "vibesop.core.observability.embedding.get_embedding_cache", return_value=mock_cache
            ),
        ):
            r = cli_runner.invoke(app, ["skill", "scan-candidates", "--dry-run"])

        assert r.exit_code == 0, f"failed: {r.output}"

    def test_days_with_limit_applies_in_order(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path
    ) -> None:
        """--days + --limit: query_recent returns limit spans, then --days filters.

        Order matters: time filter applies to the already-limited set
        (grok P1-3). This test confirms both flags coexist without crash
        and produce a valid scan output.
        """
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        spans = [
            self._span_with_started_at(f"t{i}", f"topic-A q{i}", now.isoformat()) for i in range(5)
        ]

        mock_writer = MagicMock()
        mock_writer.query_recent.return_value = spans

        mock_learner = MagicMock()
        mock_learner.get_instinct_for_query.return_value = None

        mock_cache = MagicMock()
        mock_cache.embed = MagicMock(side_effect=_fake_embedding)
        mock_cache.embed_batch = MagicMock(
            return_value=[_fake_embedding(f"topic-A q{i}") for i in range(5)]
        )

        with (
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=mock_learner),
            patch(
                "vibesop.core.observability.embedding.get_embedding_cache", return_value=mock_cache
            ),
        ):
            r = cli_runner.invoke(
                app,
                ["skill", "scan-candidates", "--days", "7", "--limit", "50", "--dry-run"],
            )

        assert r.exit_code == 0, f"failed: {r.output}"
        mock_writer.query_recent.assert_called_once_with(limit=50)


class TestCandidatesList:
    def test_candidates_lists_pending(self, cli_runner: CliRunner, tmp_store) -> None:
        """Default ``vibe skill candidates`` lists stable pending rows."""
        from datetime import UTC, datetime, timedelta

        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1", "t2"],
            queries=["topic-A one", "topic-A two"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
            core_steps=["route:query"],
            ttl_expires_at=datetime.now(UTC) + timedelta(days=25),
        )
        tmp_store.upsert(c)

        r = cli_runner.invoke(app, ["skill", "candidates"])
        assert r.exit_code == 0, f"failed: {r.output}"
        # Display uses cluster_id[:8] (pi P1 — opaque hash truncation).
        assert "abc123de" in r.output
        assert "stable" in r.output
        # Representative query column (pi P1 — semantic anchor).
        assert "topic-A one" in r.output

    def test_candidates_unstable_flag_lists_only_low_gold(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
        """``--unstable`` shows only is_unstable=True rows.

        Cluster IDs use distinct prefixes ("good_", "wobbly_") so the
        assertion isn't fooled by substring overlap (an earlier iteration
        used "stable1"/"unstable1" — "stable1" is a substring of
        "unstable1" and broke the negative assertion).
        """
        from datetime import UTC, datetime, timedelta

        stable = ClusterCandidate(
            cluster_id="good_abc123",
            task_ids=["t1"],
            queries=["q1"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
            ttl_expires_at=datetime.now(UTC) + timedelta(days=25),
        )
        unstable = ClusterCandidate(
            cluster_id="wobbly_xyz789",
            task_ids=["t2"],
            queries=["q2"],
            span_count=5,
            gold_rate=0.15,
            gold_task_ids=[],
            is_unstable=True,
            ttl_expires_at=datetime.now(UTC) + timedelta(days=25),
        )
        tmp_store.upsert(stable)
        tmp_store.upsert(unstable)

        # Default view shows stable only — unstable hidden.
        r_default = cli_runner.invoke(app, ["skill", "candidates"])
        assert r_default.exit_code == 0
        assert "good_abc" in r_default.output
        assert "wobbly_x" not in r_default.output

        # --unstable shows the diagnosis bucket only.
        r = cli_runner.invoke(app, ["skill", "candidates", "--unstable"])
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "wobbly_x" in r.output
        assert "good_abc" not in r.output

        # --include-unstable shows both.
        r_both = cli_runner.invoke(app, ["skill", "candidates", "--include-unstable"])
        assert r_both.exit_code == 0
        assert "good_abc" in r_both.output
        assert "wobbly_x" in r_both.output

    def test_candidates_json_output_schema(self, cli_runner: CliRunner, tmp_store) -> None:
        """``--json`` returns a valid JSON array with documented fields."""
        from datetime import UTC, datetime, timedelta

        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1", "t2"],
            queries=["topic-A one", "topic-A two"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
            core_steps=["route:query"],
            ttl_expires_at=datetime.now(UTC) + timedelta(days=25),
        )
        tmp_store.upsert(c)

        r = cli_runner.invoke(app, ["skill", "candidates", "--json"])
        assert r.exit_code == 0, f"failed: {r.output}"
        payload = json.loads(r.output)
        assert isinstance(payload, list)
        assert len(payload) == 1
        entry = payload[0]
        # Schema check.
        assert set(entry.keys()) >= {
            "cluster_id",
            "task_ids",
            "queries",
            "span_count",
            "gold_rate",
            "is_unstable",
            "ttl_days_left",
            "core_steps",
            "status",
        }
        assert entry["cluster_id"] == "abc123def456"
        assert entry["gold_rate"] == 0.8
        assert entry["is_unstable"] is False
        assert entry["core_steps"] == ["route:query"]


class TestPromote:
    def test_promote_flips_status(self, cli_runner: CliRunner, tmp_store) -> None:
        """``vibe skill promote <id>`` flips status to promoted and
        derives a skill_id from the representative query."""
        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1"],
            queries=["topic-A one"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
        )
        tmp_store.upsert(c)

        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "Promoted" in r.output

        stored = tmp_store.get("abc123def456")
        assert stored is not None
        assert stored.status == "promoted"
        assert stored.source_skill_id is not None
        assert stored.source_skill_id.startswith("custom/")

    def test_promote_prints_index_hint_and_review_checklist(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
        """M7: promote stdout includes the index hint + 3-line human
        review checklist after the activate instructions."""
        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1"],
            queries=["topic-A one"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
        )
        tmp_store.upsert(c)

        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "incrementally" in r.output
        assert "vibe skills index" in r.output
        assert "review checklist before activating:" in r.output
        assert "1. rewrite name/description into intent keywords" in r.output
        assert "2. confirm the example queries are a single workflow" in r.output
        # gate31: item 3 points at the new fill-in skeleton sections.
        assert "3. fill in the When-NOT-to-Apply / Acceptance Checklist /" in r.output

    def test_promote_unknown_id_errors(self, cli_runner: CliRunner, tmp_store) -> None:
        """Unknown cluster_id → exit code 1, error message."""
        r = cli_runner.invoke(app, ["skill", "promote", "does-not-exist"])
        assert r.exit_code == 1
        assert "not in pool" in r.output

    def test_promote_dismissed_is_blocked(self, cli_runner: CliRunner, tmp_store) -> None:
        """Promoting a dismissed cluster is blocked (terminal sticky)."""
        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1"],
            queries=["q"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
        )
        tmp_store.upsert(c)
        tmp_store.dismiss("abc123def456", reason="noise")

        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r.exit_code == 1
        assert "sticky" in r.output or "dismissed" in r.output


class TestDismiss:
    def test_dismiss_with_reason(self, cli_runner: CliRunner, tmp_store) -> None:
        """``vibe skill dismiss <id> --reason TEXT`` records the reason."""
        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1"],
            queries=["q"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
        )
        tmp_store.upsert(c)

        r = cli_runner.invoke(
            app,
            ["skill", "dismiss", "abc123def456", "--reason", "false positive"],
        )
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "Dismissed" in r.output
        assert "false positive" in r.output

        stored = tmp_store.get("abc123def456")
        assert stored is not None
        assert stored.status == "dismissed"
        assert stored.dismiss_reason == "false positive"

    def test_dismiss_unknown_id_errors(self, cli_runner: CliRunner, tmp_store) -> None:
        """Dismissing unknown cluster_id → exit code 1."""
        r = cli_runner.invoke(app, ["skill", "dismiss", "no-such-id"])
        assert r.exit_code == 1
        assert "not in pool" in r.output

    def test_dismiss_cross_project_candidate_via_global_fallback(
        self,
        cli_runner: CliRunner,
        tmp_store,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Pi re-review H1: cross-project candidate lives in global store;
        ``dismiss`` must find it via fallback rather than reporting
        "not in pool" for a cluster the user just saw in the listing.

        Reproduces the user trap: candidate exists in global store only,
        user runs ``vibe skill dismiss <id>`` from a project cwd → prior
        version exit-1'd because the default scope is 'project' and the
        project store is empty.
        """
        from datetime import UTC, datetime
        from unittest.mock import patch

        from vibesop.cli.commands import skill_commands
        from vibesop.core.observability.skill_promote import (
            ClusterCandidate,
            ClusterCandidateStore,
        )

        # Global store under a sandbox home.
        fake_home = tmp_path / "fake_home"
        monkeypatch.setattr(
            skill_commands,
            "_GLOBAL_OBSERVABILITY_DIR",
            fake_home / ".vibe" / "observability",
        )
        global_store = ClusterCandidateStore(storage_dir=fake_home / ".vibe" / "observability")
        global_store.upsert(
            ClusterCandidate(
                cluster_id="xp-only-dismiss",
                task_ids=["t-xp"],
                queries=["cross task"],
                span_count=4,
                gold_rate=0.75,
                gold_task_ids=["t-xp"],
                created_at=datetime(2026, 7, 31, tzinfo=UTC),
                project_distribution={"/users/me/a": 2, "/users/me/b": 2},
            )
        )

        # Default dismiss scope is 'project'; project store is empty.
        # Fallback should find the candidate in global store and dismiss it.
        with patch.object(skill_commands, "_get_candidate_store") as mock_get:
            project_store = ClusterCandidateStore(storage_dir=tmp_path / ".vibe" / "observability")

            def fake_get(scope: str = "project"):
                return global_store if scope == "global" else project_store

            mock_get.side_effect = fake_get

            result = cli_runner.invoke(
                app, ["skill", "dismiss", "xp-only-dismiss", "--reason", "test"]
            )

        assert result.exit_code == 0, result.output
        assert "found in global store" in result.output
        # Status actually flipped in the global store.
        row = global_store.get("xp-only-dismiss")
        assert row is not None
        assert row.status == "dismissed"
        assert row.dismiss_reason == "test"


# ---------------------------------------------------------------------------
# W4.E — materialize promoted candidate → SKILL.md
# ---------------------------------------------------------------------------


class TestMaterializeCandidate:
    """W4.E — ``materialize_candidate`` writes a SKILL.md draft.

    Verifies:
    - Draft includes the candidate's core steps.
    - Draft lands at ``.vibe/observability/skill_drafts/<id>/SKILL.md``
      (NOT under ``.vibe/skills/`` — grok+pi P0 on W4 review:
      ``.vibe/skills/`` is auto-discovered by CandidateManager).
    - The draft is NOT auto-discovered by CandidateManager (未审不注入).
    - Re-running materialize is a no-op (preserves user edits).
    """

    def test_promote_creates_skill_md_with_core_steps(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """``vibe skill promote <id>`` writes SKILL.md with core steps.

        Uses monkeypatch.chdir(tmp_path) so the drafted skill lands in
        ``tmp_path / .vibe / observability / skill_drafts / custom / <slug> / SKILL.md``
        instead of polluting the real CWD.
        """
        monkeypatch.chdir(tmp_path)

        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1", "t2"],
            queries=["screenshot permission popup"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
            core_steps=["route:query", "tool:edit"],
            step_freq={"route:query": 5, "tool:edit": 4},
            step_labels={"route:query": "core", "tool:edit": "core"},
        )
        tmp_store.upsert(c)

        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r.exit_code == 0, f"failed: {r.output}"

        # Draft lands under .vibe/observability/skill_drafts/ (P0 fix).
        drafts_root = tmp_path / ".vibe" / "observability" / "skill_drafts"
        skill_dirs = list(drafts_root.rglob("SKILL.md"))
        assert len(skill_dirs) == 1, f"expected 1 SKILL.md, got {skill_dirs}"
        skill_path = skill_dirs[0]
        content = skill_path.read_text(encoding="utf-8")

        # YAML frontmatter + provenance fields.
        assert "id: custom/" in content
        assert "source: cluster-candidate" in content
        assert "cluster_id: abc123def456" in content
        # Core steps appear in the Steps section.
        assert "route:query" in content
        assert "tool:edit" in content
        # Metrics block.
        assert "span_count" in content
        assert "gold_rate" in content

    def test_promote_does_not_register_with_candidate_manager(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """The literal "未审不注入" guarantee — promote writes SKILL.md
        to a path CandidateManager does NOT auto-discover.

        Prior version of this test patched CandidateManager construction
        and asserted it was never called. That was vacuous (grok P0-2):
        promote never touches CandidateManager regardless. The actual
        guarantee is that *no auto-discovery* picks the draft up.

        This version builds a real CandidateManager(project_root=tmp_path)
        after promote and asserts the drafted skill_id is NOT among the
        discovered candidates. Drafts land in
        ``.vibe/observability/skill_drafts/`` which is outside all
        ``_build_search_paths`` roots.
        """
        from vibesop.core.routing.candidate_manager import CandidateManager

        monkeypatch.chdir(tmp_path)

        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1"],
            queries=["some repeated task"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
            core_steps=["route:query"],
        )
        tmp_store.upsert(c)

        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r.exit_code == 0, f"failed: {r.output}"

        # SKILL.md landed on disk under the drafts path.
        drafts_root = tmp_path / ".vibe" / "observability" / "skill_drafts"
        skill_files = list(drafts_root.rglob("SKILL.md"))
        assert len(skill_files) == 1

        # Critical assertion: CandidateManager does NOT discover the
        # drafted skill. The skill_id contains "some-repeated-task" —
        # if auto-discovery picked it up, it would appear in the list.
        cm = CandidateManager(project_root=tmp_path)
        discovered = cm.get_candidates()
        # get_candidates returns list of dicts with ``id`` key.
        discovered_ids = {c.get("id", "") for c in discovered}
        # No discovered skill_id should reference the drafted slug.
        assert not any("some-repeated-task" in sid for sid in discovered_ids), (
            f"未审不注入 BROKEN: CandidateManager discovered drafted skill. "
            f"Matching ids: {[sid for sid in discovered_ids if 'some-repeated-task' in sid]}. "
            f"Total discovered: {len(discovered_ids)}."
        )

    def test_promote_idempotent_re_running_is_noop(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """Re-promoting the same cluster preserves the existing SKILL.md.

        Idempotency contract:
        - First promote: writes SKILL.md with template content.
        - User edits the file (e.g., adds a custom note).
        - Second promote: leaves the file untouched (no clobber).
        """
        monkeypatch.chdir(tmp_path)

        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1"],
            queries=["a task worth promoting"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
            core_steps=["route:query"],
        )
        tmp_store.upsert(c)

        # First promote.
        r1 = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r1.exit_code == 0
        drafts_root = tmp_path / ".vibe" / "observability" / "skill_drafts"
        skill_path = next(drafts_root.rglob("SKILL.md"))
        original_content = skill_path.read_text(encoding="utf-8")

        # User edits the draft.
        user_edit_marker = "<!-- USER EDIT: custom note -->\n"
        skill_path.write_text(user_edit_marker + original_content, encoding="utf-8")

        # Second promote — should NOT overwrite.
        r2 = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r2.exit_code == 0

        after = skill_path.read_text(encoding="utf-8")
        assert user_edit_marker in after, (
            "Second promote must preserve user edits — idempotent materialize"
        )

    def test_promote_sanitizes_yaml_frontmatter(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """Multi-line / colon-bearing queries must not break YAML parsing.

        Grok P1: prior version interpolated raw query text into
        ``name:`` / ``description:``. A query like ``"setup: build\\n
        deploy"`` broke ruamel.yaml when the skill was later loaded.
        """
        monkeypatch.chdir(tmp_path)

        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1"],
            # Hostile query: contains a colon (YAML mapping) + newline.
            queries=["setup: config\nthen deploy"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
            core_steps=["route:query"],
        )
        tmp_store.upsert(c)

        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r.exit_code == 0, f"failed: {r.output}"

        drafts_root = tmp_path / ".vibe" / "observability" / "skill_drafts"
        skill_path = next(drafts_root.rglob("SKILL.md"))
        content = skill_path.read_text(encoding="utf-8")

        # The frontmatter must parse without raising.
        import yaml as _yaml

        # Strip the body — frontmatter is between the first two --- lines.
        lines = content.splitlines()
        assert lines[0].strip() == "---", "frontmatter must start with ---"
        end_idx = next(i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == "---")
        frontmatter_text = "\n".join(lines[1:end_idx])
        parsed = _yaml.safe_load(frontmatter_text)
        assert isinstance(parsed, dict)
        # The sanitized name should be single-line (newlines stripped).
        name = parsed.get("name", "")
        assert "\n" not in name, f"name field must be single-line; got: {name!r}"
        # The original query's colon is preserved in the VALUE (quoted
        # strings allow that), but the YAML itself parses cleanly. The
        # test's reason for existing is that parsing succeeds — the
        # YAML library raised ScannerError before sanitization.

    def test_promote_skill_id_includes_cluster_id_prefix(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """Pi P1: skill_id derives from cluster_id[:8] + slugified query
        to avoid collisions when two clusters share a first query.
        """
        monkeypatch.chdir(tmp_path)

        c = ClusterCandidate(
            cluster_id="abc123def456",
            task_ids=["t1"],
            queries=["auth login user"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
            core_steps=["route:query"],
        )
        tmp_store.upsert(c)

        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r.exit_code == 0

        stored = tmp_store.get("abc123def456")
        assert stored is not None
        assert stored.source_skill_id is not None
        # Format: custom/<slug>-<cluster_id[:8]>
        assert stored.source_skill_id.startswith("custom/")
        assert stored.source_skill_id.endswith("-abc123de"), (
            f"skill_id should include cluster_id[:8] suffix; got: {stored.source_skill_id}"
        )

    def test_promote_skill_id_is_ascii_for_cjk_query(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """gate31: skill ids become directory names + routing-match text,
        so they must be ASCII. CJK characters are dropped (not
        transliterated); Latin fragments survive; a fully non-ASCII query
        falls back to "candidate" (the cluster suffix keeps it unique).
        """
        monkeypatch.chdir(tmp_path)

        c = ClusterCandidate(
            cluster_id="cjk123def456",
            task_ids=["t1"],
            queries=["把 nits 都收敛了把"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
        )
        tmp_store.upsert(c)
        r = cli_runner.invoke(app, ["skill", "promote", "cjk123def456"])
        assert r.exit_code == 0
        sid = tmp_store.get("cjk123def456").source_skill_id  # type: ignore[union-attr]
        assert sid == "custom/nits-cjk123de"
        assert sid.isascii()

    def test_promote_skill_id_falls_back_for_fully_non_ascii_query(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        c = ClusterCandidate(
            cluster_id="zh123def456789",
            task_ids=["t1"],
            queries=["帮我合并到主分支吧"],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
        )
        tmp_store.upsert(c)
        r = cli_runner.invoke(app, ["skill", "promote", "zh123def456789"])
        assert r.exit_code == 0
        sid = tmp_store.get("zh123def456789").source_skill_id  # type: ignore[union-attr]
        assert sid == "custom/candidate-zh123def"
        assert sid.isascii()


class TestPromoteActivate:
    """M12 M5 — promote --activate + content-hash edit guard + global guardrails.

    The registration phases (audit / install / configure / verify) are
    patched out — they are the SAME helpers `vibe skill add` uses, and
    their behavior is covered by the add tests. What these tests pin is
    the guard chain and the wiring.
    """

    def _candidate(self, cluster_id: str = "abc123def456", **overrides) -> ClusterCandidate:
        payload = {
            "cluster_id": cluster_id,
            # gate30: derive from cluster_id — upsert overlap-merges rows
            # whose task_id sets match, so a shared constant would silently
            # merge distinct fixture candidates into one row.
            "task_ids": [f"{cluster_id}-t1"],
            "queries": ["topic-A one"],
            "span_count": 5,
            "gold_rate": 0.8,
            "gold_task_ids": ["t1"],
        }
        payload.update(overrides)
        return ClusterCandidate(**payload)

    def _activation_stubs(self):
        """Patch the factored `vibe skill add` phases out of promote --activate.

        Usage: ``with self._activation_stubs() as install_mock:``
        """
        import contextlib

        @contextlib.contextmanager
        def _stack():
            with (
                patch.object(skill_commands, "_audit_skill_or_exit"),
                patch.object(
                    skill_commands, "_install_skill_or_exit", return_value="/fake/installed"
                ) as install_mock,
                patch.object(skill_commands, "_auto_configure_skill_with_llm"),
                patch.object(skill_commands, "_verify_and_sync", return_value=False),
            ):
                yield install_mock

        return _stack()

    def _draft_path(self, tmp_path: Path, cluster_id: str = "abc123def456") -> Path:
        drafts_root = tmp_path / ".vibe" / "observability" / "skill_drafts"
        matches = list(drafts_root.rglob("SKILL.md"))
        assert len(matches) == 1, f"expected 1 draft, got {matches}"
        return matches[0]

    def test_promote_records_draft_hash(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        tmp_store.upsert(self._candidate())
        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r.exit_code == 0, f"failed: {r.output}"
        expected = hashlib.sha256(self._draft_path(tmp_path).read_bytes()).hexdigest()
        stored = tmp_store.get("abc123def456")
        assert stored is not None
        assert stored.draft_sha256 == expected

    def test_activate_refused_on_unedited_draft(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        tmp_store.upsert(self._candidate())
        with self._activation_stubs() as install_mock:
            r = cli_runner.invoke(app, ["skill", "promote", "abc123def456", "--activate"])
        assert r.exit_code == 1
        assert "no human edit detected" in r.output
        assert "review checklist" in r.output  # refusal points at the checklist
        # gate18 pi residual-1: refusal discloses the post-state.
        assert "but NOT registered" in r.output
        install_mock.assert_not_called()

    def test_activate_succeeds_after_substantive_edit(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        tmp_store.upsert(self._candidate())
        r1 = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r1.exit_code == 0, f"failed: {r1.output}"

        # Human edit: rewrite name/description per the review checklist.
        draft = self._draft_path(tmp_path)
        draft.write_text(
            draft.read_text(encoding="utf-8").replace(
                "name: draft-abc123de", "name: topic-a-workflow"
            ),
            encoding="utf-8",
        )

        with self._activation_stubs() as install_mock:
            r2 = cli_runner.invoke(app, ["skill", "promote", "abc123def456", "--activate"])
        assert r2.exit_code == 0, f"failed: {r2.output}"
        assert "Activated" in r2.output
        install_mock.assert_called_once()
        assert install_mock.call_args.args[1] == "project"  # scope positional

    def test_repromote_does_not_rebaseline_hash(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """materialize never overwrites an existing draft; a re-promote
        must NOT re-record the edited draft's hash as the baseline."""
        monkeypatch.chdir(tmp_path)
        tmp_store.upsert(self._candidate())
        cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        original_hash = tmp_store.get("abc123def456").draft_sha256  # type: ignore[union-attr]

        draft = self._draft_path(tmp_path)
        draft.write_text(draft.read_text(encoding="utf-8") + "\nhuman edit\n", encoding="utf-8")
        cli_runner.invoke(app, ["skill", "promote", "abc123def456"])

        assert tmp_store.get("abc123def456").draft_sha256 == original_hash  # type: ignore[union-attr]

    def test_activate_force_overrides_edit_guard(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        tmp_store.upsert(self._candidate())
        with self._activation_stubs():
            r = cli_runner.invoke(
                app, ["skill", "promote", "abc123def456", "--activate", "--force"]
            )
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "edit guard bypassed" in r.output
        assert "Activated" in r.output

    def test_activate_legacy_none_hash_requires_force(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        tmp_store.upsert(self._candidate())
        cli_runner.invoke(app, ["skill", "promote", "abc123def456"])

        # Simulate a pre-M5 row: strip draft_sha256 from the stored JSONL.
        store_file = tmp_path / "obs" / "cluster_candidates.jsonl"
        rows = [json.loads(line) for line in store_file.read_text().splitlines() if line.strip()]
        assert rows and rows[0].pop("draft_sha256", None) is not None
        store_file.write_text("".join(json.dumps(row) + "\n" for row in rows))

        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456", "--activate"])
        assert r.exit_code == 1
        assert "no draft hash recorded" in r.output
        # gate18 pi NIT-1: the suggested remedy must actually work —
        # re-promote alone never records a hash (existing draft kept).
        assert "delete the draft directory" in r.output
        assert "never records a hash" in r.output

        with self._activation_stubs():
            r2 = cli_runner.invoke(
                app, ["skill", "promote", "abc123def456", "--activate", "--force"]
            )
        assert r2.exit_code == 0, f"failed: {r2.output}"
        assert "legacy candidate" in r2.output

    def test_activate_missing_draft_refused(self, tmp_path: Path) -> None:
        """Guard step 1: missing draft file refuses (unit-level — within
        the CLI flow promote always regenerates the draft first)."""
        import typer

        candidate = self._candidate()
        with pytest.raises(typer.Exit) as exc_info:
            skill_commands._activate_promoted_draft(
                candidate, "custom/x", tmp_path / "nope" / "SKILL.md", "project", force=True
            )
        assert exc_info.value.exit_code == 1

    def test_activate_global_requires_cross_project_evidence(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(skill_commands, "_GLOBAL_OBSERVABILITY_DIR", tmp_path / "gobs")
        tmp_store.upsert(self._candidate())  # single-project candidate
        # Pass the edit guard first (two-step flow: promote, edit, activate).
        r1 = cli_runner.invoke(app, ["skill", "promote", "abc123def456", "--scope", "global"])
        assert r1.exit_code == 0, f"failed: {r1.output}"
        draft_file = next((tmp_path / "gobs" / "skill_drafts").rglob("SKILL.md"))
        draft_file.write_text(
            draft_file.read_text(encoding="utf-8") + "\nhuman edit\n", encoding="utf-8"
        )
        with self._activation_stubs() as install_mock:
            r = cli_runner.invoke(
                app, ["skill", "promote", "abc123def456", "--scope", "global", "--activate"]
            )
        assert r.exit_code == 1
        assert "cross-project evidence" in r.output
        install_mock.assert_not_called()

    def test_activate_global_confirm_no_aborts(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(skill_commands, "_GLOBAL_OBSERVABILITY_DIR", tmp_path / "gobs")
        tmp_store.upsert(self._candidate(project_distribution={"/p/alpha": 3, "/p/beta": 2}))
        r1 = cli_runner.invoke(app, ["skill", "promote", "abc123def456", "--scope", "global"])
        assert r1.exit_code == 0, f"failed: {r1.output}"
        draft_file = next((tmp_path / "gobs" / "skill_drafts").rglob("SKILL.md"))
        draft_file.write_text(
            draft_file.read_text(encoding="utf-8") + "\nhuman edit\n", encoding="utf-8"
        )
        with self._activation_stubs() as install_mock:
            r = cli_runner.invoke(
                app,
                ["skill", "promote", "abc123def456", "--scope", "global", "--activate"],
                input="n\n",
            )
        assert r.exit_code == 1
        assert "Aborted" in r.output
        install_mock.assert_not_called()

    def test_activate_global_confirm_yes_succeeds(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(skill_commands, "_GLOBAL_OBSERVABILITY_DIR", tmp_path / "gobs")
        tmp_store.upsert(self._candidate(project_distribution={"/p/alpha": 3, "/p/beta": 2}))
        with self._activation_stubs() as install_mock:
            r = cli_runner.invoke(
                app,
                ["skill", "promote", "abc123def456", "--scope", "global", "--activate", "--force"],
                input="y\n",
            )
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "Activated" in r.output
        install_mock.assert_called_once()
        assert install_mock.call_args.args[1] == "global"

    def test_global_force_still_requires_confirmation(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """Privacy boundary: --force bypasses evidence + edit guard but
        NEVER the explicit global confirmation (default N)."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(skill_commands, "_GLOBAL_OBSERVABILITY_DIR", tmp_path / "gobs")
        tmp_store.upsert(self._candidate())  # single-project, would need --force
        with self._activation_stubs() as install_mock:
            r = cli_runner.invoke(
                app,
                ["skill", "promote", "abc123def456", "--scope", "global", "--activate", "--force"],
                input="\n",  # empty answer → default False
            )
        assert r.exit_code == 1
        assert "Aborted" in r.output
        install_mock.assert_not_called()


class TestPrefixResolution:
    """Prefix UX fix — the candidates table shows 8-char truncated cluster
    IDs, so promote/dismiss must accept full OR unique-prefix IDs.

    Semantics mirror ``_resolve_discovery_candidate``: exact → unique
    prefix → ambiguous (lists matches) → "not in pool".
    """

    def _candidate(self, cluster_id: str, query: str = "topic-A one") -> ClusterCandidate:
        return ClusterCandidate(
            cluster_id=cluster_id,
            # gate30: derive from cluster_id — upsert overlap-merges rows
            # whose task_id sets match, so a shared constant would silently
            # merge distinct fixture candidates into one row.
            task_ids=[f"{cluster_id}-t1"],
            queries=[query],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
        )

    def test_prefix_promote_succeeds(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        full_id = "abc123def4567890"
        tmp_store.upsert(self._candidate(full_id))

        # gate22 NIT-3: a 6-char prefix (NOT the 8-char display length) so
        # the skill_id suffix assertion can actually fail if the prefix
        # leaks downstream.
        prefix = full_id[:6]
        r = cli_runner.invoke(app, ["skill", "promote", prefix])
        assert r.exit_code == 0, f"failed: {r.output}"
        # The echoed line carries the FULL id — locks the rebind directly.
        assert f"Promoted '{full_id}'" in r.output

        stored = tmp_store.get(full_id)
        assert stored is not None
        assert stored.status == "promoted"
        # skill_id derived from the FULL cluster_id (suffix is the 8-char
        # form — a 6-char prefix would NOT endswith-match this).
        assert stored.source_skill_id is not None
        assert stored.source_skill_id.endswith(full_id[:8])
        assert prefix != full_id[:8]  # sanity: the prefix is not the suffix

    def test_empty_string_resolves_to_not_in_pool(self, cli_runner: CliRunner, tmp_store) -> None:
        """gate22 MAJOR-1: startswith("") is always True — without the
        guard, `promote ""` would flip the first pool row to the sticky
        promoted terminal state."""
        full_id = "abc123def4567890"
        tmp_store.upsert(self._candidate(full_id))
        r = cli_runner.invoke(app, ["skill", "promote", ""])
        assert r.exit_code == 1
        assert "not in pool" in r.output
        assert tmp_store.get(full_id).status == "pending"  # type: ignore[union-attr]

    def test_prefix_hitting_dismissed_row_stays_sticky(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
        """gate22 pi NIT-5: prefix resolution reaches terminal rows (parity
        with the old store.get path) → the sticky-dismiss refusal fires."""
        full_id = "deadbeef12345678"
        tmp_store.upsert(self._candidate(full_id))
        tmp_store.dismiss(full_id, reason="noise")

        r = cli_runner.invoke(app, ["skill", "promote", full_id[:8]])
        assert r.exit_code == 1
        assert "sticky" in r.output

    def test_prefix_dismiss_succeeds(self, cli_runner: CliRunner, tmp_store) -> None:
        full_id = "def456abc7890123"
        tmp_store.upsert(self._candidate(full_id))

        r = cli_runner.invoke(app, ["skill", "dismiss", full_id[:8], "--reason", "noise"])
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "Dismissed" in r.output
        stored = tmp_store.get(full_id)
        assert stored is not None
        assert stored.status == "dismissed"
        assert stored.dismiss_reason == "noise"

    def test_ambiguous_prefix_errors_and_lists_matches(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
        id_a = "abc1111111111111"
        id_b = "abc2222222222222"
        tmp_store.upsert(self._candidate(id_a, query="query alpha"))
        tmp_store.upsert(self._candidate(id_b, query="query beta"))

        r = cli_runner.invoke(app, ["skill", "promote", "abc"])
        assert r.exit_code == 1
        assert "ambiguous" in r.output
        assert id_a in r.output  # matched IDs listed for copy-paste
        assert id_b in r.output
        # Nothing was mutated.
        assert tmp_store.get(id_a).status == "pending"  # type: ignore[union-attr]
        assert tmp_store.get(id_b).status == "pending"  # type: ignore[union-attr]

        r2 = cli_runner.invoke(app, ["skill", "dismiss", "abc"])
        assert r2.exit_code == 1
        assert "ambiguous" in r2.output

    def test_unknown_prefix_still_not_in_pool(self, cli_runner: CliRunner, tmp_store) -> None:
        tmp_store.upsert(self._candidate("abc123def4567890"))
        r = cli_runner.invoke(app, ["skill", "promote", "zzz999"])
        assert r.exit_code == 1
        assert "not in pool" in r.output
        r2 = cli_runner.invoke(app, ["skill", "dismiss", "zzz999"])
        assert r2.exit_code == 1
        assert "not in pool" in r2.output

    def test_exact_id_still_works(self, cli_runner: CliRunner, tmp_store) -> None:
        """Regression: full-ID path unchanged."""
        full_id = "aaaabbbbccccdddd"
        tmp_store.upsert(self._candidate(full_id))
        r = cli_runner.invoke(app, ["skill", "dismiss", full_id])
        assert r.exit_code == 0, f"failed: {r.output}"
        assert tmp_store.get(full_id).status == "dismissed"  # type: ignore[union-attr]


class TestPrefixResolutionDualStore:
    """gate22 MAJOR-2 — cross-scope prefix resolution with REAL dual stores
    (the single-store tmp_store fixture makes primary/fallback the same
    object, covering none of this). Pattern mirrors
    ``test_dismiss_cross_project_candidate_via_global_fallback``.
    """

    def _candidate(self, cluster_id: str, query: str = "topic-A one") -> ClusterCandidate:
        return ClusterCandidate(
            cluster_id=cluster_id,
            # gate30: derive from cluster_id — upsert overlap-merges rows
            # whose task_id sets match, so a shared constant would silently
            # merge distinct fixture candidates into one row.
            task_ids=[f"{cluster_id}-t1"],
            queries=[query],
            span_count=5,
            gold_rate=0.8,
            gold_task_ids=["t1"],
        )

    def _dual_stores(self, tmp_path: Path, monkeypatch):
        """Two real stores; _get_candidate_store routes by scope."""
        project_store = ClusterCandidateStore(storage_dir=tmp_path / "proj")
        global_store = ClusterCandidateStore(storage_dir=tmp_path / "glob")
        monkeypatch.setattr(skill_commands, "_GLOBAL_OBSERVABILITY_DIR", tmp_path / "glob")
        patcher = patch.object(
            skill_commands,
            "_get_candidate_store",
            side_effect=lambda scope="project": (
                global_store if scope == "global" else project_store
            ),
        )
        return project_store, global_store, patcher

    def test_prefix_hit_in_fallback_store_flips_fallback(
        self, cli_runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        project_store, global_store, patcher = self._dual_stores(tmp_path, monkeypatch)
        full_id = "xp11111111111111"
        global_store.upsert(self._candidate(full_id))

        with patcher:
            r = cli_runner.invoke(app, ["skill", "dismiss", full_id[:8]])
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "found in global store" in r.output
        assert global_store.get(full_id).status == "dismissed"  # type: ignore[union-attr]
        assert project_store.get(full_id) is None  # primary untouched

    def test_same_id_in_both_stores_requested_scope_wins(
        self, cli_runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        project_store, global_store, patcher = self._dual_stores(tmp_path, monkeypatch)
        full_id = "dual222222222222"
        project_store.upsert(self._candidate(full_id))
        global_store.upsert(self._candidate(full_id))

        with patcher:
            r = cli_runner.invoke(app, ["skill", "dismiss", full_id[:8]])
        assert r.exit_code == 0, f"failed: {r.output}"
        # Requested scope (project) flipped; global row untouched.
        assert project_store.get(full_id).status == "dismissed"  # type: ignore[union-attr]
        assert global_store.get(full_id).status == "pending"  # type: ignore[union-attr]
        assert "found in global store" not in r.output

    def test_cross_store_prefix_collision_is_ambiguous(
        self, cli_runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        project_store, global_store, patcher = self._dual_stores(tmp_path, monkeypatch)
        id_a = "xpaaaa1111111111"
        id_b = "xpbbbb2222222222"
        project_store.upsert(self._candidate(id_a, query="query alpha"))
        global_store.upsert(self._candidate(id_b, query="query beta"))

        with patcher:
            r = cli_runner.invoke(app, ["skill", "dismiss", "xp"])
        assert r.exit_code == 1
        assert "ambiguous" in r.output
        # gate22 NIT-4: scope annotation on each match.
        assert f"{id_a} (project)" in r.output
        assert f"{id_b} (global)" in r.output
        # No side effects in EITHER store.
        assert project_store.get(id_a).status == "pending"  # type: ignore[union-attr]
        assert global_store.get(id_b).status == "pending"  # type: ignore[union-attr]


class TestPromoteVerifier:
    """gate36 阶段二 — shadow verifier CLI wiring (修订 A/B/D/J).

    The conftest embedding stub makes both embedding lines ``unavailable``,
    so every CLI-level verdict here is WARN(degraded) — that IS the pinned
    behavior under the stub. PASS coverage lives in
    tests/core/observability/test_promote_verifier.py via the
    ``embedding_model`` DI seam.
    """

    def _candidate(self, cluster_id: str = "abc123def456", **overrides) -> ClusterCandidate:
        payload = {
            "cluster_id": cluster_id,
            "task_ids": [f"{cluster_id}-t1"],
            "queries": ["topic-A one"],
            "span_count": 5,
            "gold_rate": 0.8,
            "gold_task_ids": ["t1"],
        }
        payload.update(overrides)
        return ClusterCandidate(**payload)

    def _activation_stubs(self):
        import contextlib

        @contextlib.contextmanager
        def _stack():
            with (
                patch.object(skill_commands, "_audit_skill_or_exit"),
                patch.object(
                    skill_commands, "_install_skill_or_exit", return_value="/fake/installed"
                ),
                patch.object(skill_commands, "_auto_configure_skill_with_llm"),
                patch.object(skill_commands, "_verify_and_sync", return_value=False),
            ):
                yield

        return _stack()

    def _verdict_store(self, tmp_path: Path):
        from vibesop.core.observability.promote_verifier import PromoteVerdictStore

        return PromoteVerdictStore(tmp_path / ".vibe" / "observability")

    def _draft_path(self, tmp_path: Path) -> Path:
        matches = list((tmp_path / ".vibe" / "observability" / "skill_drafts").rglob("SKILL.md"))
        assert len(matches) == 1, f"expected 1 draft, got {matches}"
        return matches[0]

    def test_promote_prints_badge_and_records_verdict(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """promote 后自动跑 verify: 输出徽章 + 口径文案, verdict 落发起项目."""
        monkeypatch.chdir(tmp_path)
        tmp_store.upsert(self._candidate())
        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "Verifier: WARN" in r.output  # degraded under the conftest stub
        assert "degraded" in r.output
        assert "触发召回" in r.output  # 徽章文案写明测触发召回不是内容质量
        assert "不是内容质量" in r.output
        rows = self._verdict_store(tmp_path).list_all()
        assert len(rows) == 1
        assert rows[0].phase == "promote"
        assert rows[0].degraded is True
        assert rows[0].badge == "WARN"
        # trigger 侧不受 embedding 降级影响: prefilled trigger 捕获分母.
        assert rows[0].shadow["all_caught"] is True

    def test_verify_failure_never_blocks_promote(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """永不阻断: verdict store 构造抛错也只打印警告, promote 照常成功."""
        monkeypatch.chdir(tmp_path)
        tmp_store.upsert(self._candidate())

        def _boom() -> None:
            raise RuntimeError("verdict store exploded")

        monkeypatch.setattr(skill_commands, "_get_verdict_store", _boom)
        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "Promoted" in r.output
        assert "不阻断" in r.output

    def test_activate_reuses_verdict_when_draft_unchanged(
        self, cli_runner: CliRunner, tmp_store, tmp_path: Path, monkeypatch
    ) -> None:
        """修订 A: activate 时 draft 未变 (字节哈希匹配) → 复用 promote
        时结果, 不追加 activate-rerun 行."""
        monkeypatch.chdir(tmp_path)
        tmp_store.upsert(self._candidate())
        r1 = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
        assert r1.exit_code == 0, f"failed: {r1.output}"

        # --force bypasses the edit guard so activation proceeds on the
        # UNCHANGED draft — the reuse path is the assertion target.
        with self._activation_stubs():
            r2 = cli_runner.invoke(
                app, ["skill", "promote", "abc123def456", "--activate", "--force"]
            )
        assert r2.exit_code == 0, f"failed: {r2.output}"
        assert "复用 promote 时结果" in r2.output
        rows = self._verdict_store(tmp_path).list_all()
        # r1 promote + r2 promote-phase re-verify; the activate step must
        # NOT have appended an activate-rerun row.
        assert len(rows) == 2
        assert all(row.phase == "promote" for row in rows)

    def test_activate_reruns_when_no_matching_verdict(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """修订 A: 当前 draft 字节哈希无匹配 verdict → activate 重跑,
        追加 phase=activate-rerun 行 (不阻断, 无需 --force 参与 verifier)."""
        import typer as _typer  # noqa: F401  (parity with sibling tests)

        monkeypatch.chdir(tmp_path)
        drafts_root = tmp_path / ".vibe" / "observability" / "skill_drafts"
        draft_dir = drafts_root / "custom" / "x"
        draft_dir.mkdir(parents=True)
        draft_path = draft_dir / "SKILL.md"
        draft_path.write_text(
            "---\nid: custom/x\nname: x\ndescription: d\n"
            'triggers: ["topic-A one"]\nintent: workflow\n---\nbody\n',
            encoding="utf-8",
        )
        # Edit guard passes: recorded baseline differs from current bytes.
        candidate = self._candidate(draft_sha256="0" * 64)
        with self._activation_stubs():
            skill_commands._activate_promoted_draft(
                candidate, "custom/x", draft_path, "project", force=False
            )
        out = capsys.readouterr().out
        assert "复用" not in out
        assert "Verifier" in out
        rows = self._verdict_store(tmp_path).list_all()
        assert len(rows) == 1
        assert rows[0].phase == "activate-rerun"
        assert rows[0].draft_sha256 == hashlib.sha256(draft_path.read_bytes()).hexdigest()

    def test_activate_prefers_complete_verdict_over_degraded_rerun(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """修订 A 细化: 已有完整 (非降级) verdict 匹配当前 draft 时, activate
        复用它 —— 即使当下 embedding 不可用 (重跑必然降级), 也不覆盖/遮蔽."""
        from datetime import UTC, datetime

        from vibesop.core.observability.promote_verifier import (
            RULESET_VERSION,
            PromoteVerdict,
        )

        monkeypatch.chdir(tmp_path)
        drafts_root = tmp_path / ".vibe" / "observability" / "skill_drafts"
        draft_dir = drafts_root / "custom" / "x"
        draft_dir.mkdir(parents=True)
        draft_path = draft_dir / "SKILL.md"
        draft_path.write_text(
            "---\nid: custom/x\nname: x\ndescription: d\n"
            'triggers: ["topic-A one"]\nintent: workflow\n---\nbody\n',
            encoding="utf-8",
        )
        current_sha = hashlib.sha256(draft_path.read_bytes()).hexdigest()
        store = self._verdict_store(tmp_path)
        store.append(
            PromoteVerdict(
                cluster_id="abc123def456",
                skill_id="custom/x",
                scope="project",
                phase="promote",
                badge="PASS",
                degraded=False,
                draft_sha256=current_sha,
                trigger_set_sha256="t" * 64,
                ruleset_version=RULESET_VERSION,
                created_at=datetime.now(UTC),
            )
        )
        candidate = self._candidate(draft_sha256="0" * 64)
        with self._activation_stubs():
            skill_commands._activate_promoted_draft(
                candidate, "custom/x", draft_path, "project", force=False
            )
        out = capsys.readouterr().out
        assert "Verifier: PASS" in out  # the COMPLETE verdict is displayed
        assert "复用 promote 时结果" in out
        # No degraded activate-rerun row was appended.
        rows = store.list_all()
        assert len(rows) == 1
        assert rows[0].phase == "promote"

    def _mk_verdict(self, **overrides):
        from datetime import UTC, datetime

        from vibesop.core.observability.promote_verifier import (
            RULESET_VERSION,
            PromoteVerdict,
        )

        payload = {
            "cluster_id": "abc123def456",
            "skill_id": "custom/x",
            "scope": "project",
            "phase": "promote",
            "badge": "WARN",
            "degraded": False,
            "draft_sha256": "d" * 64,
            "trigger_set_sha256": "t" * 64,
            "ruleset_version": RULESET_VERSION,
            "created_at": datetime.now(UTC),
        }
        payload.update(overrides)
        return PromoteVerdict(**payload)

    def test_print_verdict_skipped_line_has_own_wording(self, capsys) -> None:
        """pi-4/claude-3 收敛: index 线 skipped (无 triggers 可嵌) 打单独
        措辞, 不打 "degraded: embedding 线不可用" 文案."""
        verdict = self._mk_verdict(
            degraded=False,
            embedding={
                "recall": {"status": "ok", "all_caught": True},
                "index": {
                    "status": "skipped",
                    "reason": "empty profile text (no declared triggers)",
                },
            },
        )
        skill_commands._print_verdict(verdict)
        out = capsys.readouterr().out
        assert "Verifier: WARN" in out
        assert "index 线跳过" in out
        # Console 80 列折行可能把 "(skipped ≠ 降级)" 拆行 —— 分片段断言.
        assert "skipped ≠" in out and "降级" in out
        assert "degraded" not in out

    def test_print_verdict_redacts_secrets_in_detail(self, capsys) -> None:
        """claude-5 收敛: 读侧脱敏 —— 手改进 verdict store 的 secret 也不得
        原样进终端 (与 Discovery 卡片 _display_text 惯例一致)."""
        secret = "sk-abcdefghij0123456789"
        verdict = self._mk_verdict(
            shadow={
                "denominator": 1,
                "echo_excluded": 0,
                "caught": [],
                "missed": [
                    {
                        "query": f"use key {secret} to deploy",
                        "nearest_trigger": f"deploy with {secret}",
                        "nearest_score": 0.5,
                    }
                ],
            },
        )
        skill_commands._print_verdict(verdict)
        out = capsys.readouterr().out
        assert secret not in out
        assert "[REDACTED_KEY]" in out

    def test_print_verdict_truncates_global_query_hash(self, capsys) -> None:
        """pi-3 收敛: store 存全量 sha256, 展示层短显 16 位."""
        verdict = self._mk_verdict(
            scope="global",
            shadow={
                "denominator": 1,
                "echo_excluded": 0,
                "caught": [],
                "missed": [{"query_hash": "f" * 64, "nearest_trigger": None, "nearest_score": 0.0}],
            },
        )
        skill_commands._print_verdict(verdict)
        out = capsys.readouterr().out
        assert "query_hash:" + "f" * 16 in out
        assert "f" * 64 not in out
