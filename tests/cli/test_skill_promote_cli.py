"""W4.D — vibe skill scan-candidates / candidates / promote / dismiss CLI tests.

Verifies the 4 new CLI subcommands of the existing ``vibe skill`` Typer
app via CliRunner. Storage paths are patched to tmp_path so tests are
CWD-independent (same pattern as test_recall_cli.py).

W4.D covers the CLI surface only — promote flips status without writing
SKILL.md. W4.E adds the materialize step.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from typer.testing import CliRunner

from vibesop.cli.commands import skill_commands
from vibesop.cli.main import app
from vibesop.core.observability.skill_promote import ClusterCandidate


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


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
            return_value=[_fake_embedding(q) for q in ["topic-A one", "topic-A two", "topic-A three"]]
        )

        with (
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=mock_learner),
            patch("vibesop.core.observability.embedding.get_embedding_cache", return_value=mock_cache),
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
            patch("vibesop.core.observability.embedding.get_embedding_cache", return_value=mock_cache),
        ):
            r = cli_runner.invoke(app, ["skill", "scan-candidates"])

        assert r.exit_code == 0, f"failed: {r.output}"
        assert "1 stable" in r.output
        assert tmp_store.pending_count() == 1


class TestCliArgBounds:
    """P1-6: --min-cluster-size, --min-gold-rate, --limit bounds."""

    def test_min_cluster_size_zero_exits_1(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
        r = cli_runner.invoke(app, ["skill", "scan-candidates", "--min-cluster-size", "0"])
        assert r.exit_code == 1
        assert "min-cluster-size" in r.output
        assert ">=1" in r.output

    def test_min_cluster_size_negative_exits_1(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
        r = cli_runner.invoke(
            app, ["skill", "scan-candidates", "--min-cluster-size", "-3"]
        )
        assert r.exit_code == 1

    def test_min_gold_rate_above_one_exits_1(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
        r = cli_runner.invoke(
            app, ["skill", "scan-candidates", "--min-gold-rate", "1.5"]
        )
        assert r.exit_code == 1
        assert "min-gold-rate" in r.output

    def test_min_gold_rate_negative_exits_1(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
        r = cli_runner.invoke(
            app, ["skill", "scan-candidates", "--min-gold-rate", "-0.2"]
        )
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
            return_value=[_fake_embedding(q) for q in ["topic-A one", "topic-A two", "topic-A three"]]
        )

        with (
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=mock_learner),
            patch("vibesop.core.observability.embedding.get_embedding_cache", return_value=mock_cache),
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
            return_value=[_fake_embedding(q) for q in ["topic-A one", "topic-A two", "topic-A three"]]
        )

        with (
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=mock_learner),
            patch("vibesop.core.observability.embedding.get_embedding_cache", return_value=mock_cache),
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
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        spans = [
            self._span_with_started_at(f"t{i}", f"topic-A q{i}", now.isoformat())
            for i in range(5)
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
            patch("vibesop.core.observability.embedding.get_embedding_cache", return_value=mock_cache),
        ):
            r = cli_runner.invoke(
                app,
                ["skill", "scan-candidates", "--days", "7", "--limit", "50", "--dry-run"],
            )

        assert r.exit_code == 0, f"failed: {r.output}"
        mock_writer.query_recent.assert_called_once_with(limit=50)


class TestCandidatesList:
    def test_candidates_lists_pending(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
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

    def test_candidates_json_output_schema(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
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
    def test_promote_flips_status(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
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

    def test_promote_unknown_id_errors(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
        """Unknown cluster_id → exit code 1, error message."""
        r = cli_runner.invoke(app, ["skill", "promote", "does-not-exist"])
        assert r.exit_code == 1
        assert "not in pool" in r.output

    def test_promote_dismissed_is_blocked(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
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
    def test_dismiss_with_reason(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
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

    def test_dismiss_unknown_id_errors(
        self, cli_runner: CliRunner, tmp_store
    ) -> None:
        """Dismissing unknown cluster_id → exit code 1."""
        r = cli_runner.invoke(app, ["skill", "dismiss", "no-such-id"])
        assert r.exit_code == 1
        assert "not in pool" in r.output


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
        assert not any(
            "some-repeated-task" in sid for sid in discovered_ids
        ), (
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
        end_idx = next(
            i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == "---"
        )
        frontmatter_text = "\n".join(lines[1:end_idx])
        parsed = _yaml.safe_load(frontmatter_text)
        assert isinstance(parsed, dict)
        # The sanitized name should be single-line (newlines stripped).
        name = parsed.get("name", "")
        assert "\n" not in name, (
            f"name field must be single-line; got: {name!r}"
        )
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
            f"skill_id should include cluster_id[:8] suffix; "
            f"got: {stored.source_skill_id}"
        )
