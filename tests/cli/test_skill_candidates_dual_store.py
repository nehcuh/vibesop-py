"""W5.2 Task 2.2 + 2.3 — candidates dual-store merge + Projects column + filter.

Verifies:
- Reads from BOTH project + global stores.
- Dedup by cluster_id (prefer more heterogeneous record).
- Table gains Projects column + [CROSS-PROJECT] tag.
- JSON gains project_distribution + is_cross_project.
- ``--cross-project-only`` filter excludes single-project candidates.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands import pool_cmd, skill_commands
from vibesop.cli.main import app
from vibesop.core.observability.skill_promote import (
    ClusterCandidate,
    ClusterCandidateStore,
)


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect cwd + global observability + pool path to tmp_path."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        skill_commands,
        "_GLOBAL_OBSERVABILITY_DIR",
        tmp_path / "fake_home" / ".vibe" / "observability",
    )
    monkeypatch.setattr(pool_cmd, "_DEFAULT_POOL_PATH", tmp_path / "pool.yaml")
    return tmp_path


def _make_candidate(
    *,
    cluster_id: str,
    queries: list[str],
    project_distribution: dict[str, int],
    span_count: int = 5,
    gold_rate: float = 0.8,
) -> ClusterCandidate:
    return ClusterCandidate(
        cluster_id=cluster_id,
        task_ids=[f"t-{cluster_id}-{i}" for i in range(len(queries))],
        queries=queries,
        span_count=span_count,
        gold_rate=gold_rate,
        gold_task_ids=[f"t-{cluster_id}-0"],
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        project_distribution=project_distribution,
    )


@pytest.fixture
def dual_store(tmp_path: Path) -> tuple[ClusterCandidateStore, ClusterCandidateStore]:
    """Build paired project + global stores rooted at tmp_path."""
    project_store = ClusterCandidateStore(storage_dir=tmp_path / ".vibe" / "observability")
    global_store = ClusterCandidateStore(
        storage_dir=tmp_path / "fake_home" / ".vibe" / "observability"
    )
    return project_store, global_store


class TestDualStoreMerge:
    def test_candidates_merges_project_and_global_stores(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
    ) -> None:
        """Candidates from BOTH stores appear in the listing."""
        project_store, global_store = dual_store
        project_store.upsert(
            _make_candidate(
                cluster_id="proj-only-1",
                queries=["project local task"],
                project_distribution={"/users/me/proj-a": 3},
            )
        )
        global_store.upsert(
            _make_candidate(
                cluster_id="global-only-1",
                queries=["cross project task"],
                project_distribution={"/users/me/proj-a": 2, "/users/me/proj-b": 1},
            )
        )

        with (
            patch.object(skill_commands, "_get_candidate_store") as mock_get,
        ):
            def fake_get(scope: str = "project") -> ClusterCandidateStore:
                return global_store if scope == "global" else project_store
            mock_get.side_effect = fake_get

            result = cli_runner.invoke(app, ["skill", "candidates", "--json"])

        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        ids = {row["cluster_id"] for row in payload}
        assert ids == {"proj-only-1", "global-only-1"}

    def test_candidates_dedup_prefers_more_heterogeneous_record(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
    ) -> None:
        """Same cluster_id in both → keep the more-heterogeneous record."""
        project_store, global_store = dual_store
        # Project store sees only proj-a (1 project)
        project_store.upsert(
            _make_candidate(
                cluster_id="shared-id",
                queries=["shared task"],
                project_distribution={"/users/me/proj-a": 3},
                span_count=3,
            )
        )
        # Global store sees both proj-a + proj-b (2 projects)
        global_store.upsert(
            _make_candidate(
                cluster_id="shared-id",
                queries=["shared task"],
                project_distribution={"/users/me/proj-a": 2, "/users/me/proj-b": 1},
                span_count=3,
            )
        )

        with patch.object(skill_commands, "_get_candidate_store") as mock_get:
            def fake_get(scope: str = "project") -> ClusterCandidateStore:
                return global_store if scope == "global" else project_store
            mock_get.side_effect = fake_get

            result = cli_runner.invoke(app, ["skill", "candidates", "--json"])

        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        assert len(payload) == 1, f"expected dedup, got {len(payload)}"
        row = payload[0]
        assert row["cluster_id"] == "shared-id"
        assert row["is_cross_project"] is True
        # Privacy (omx-code-review HIGH #2): JSON project_distribution
        # uses basenames only, never absolute paths.
        assert "proj-b" in row["project_distribution"]
        assert "/users/me/" not in json.dumps(row["project_distribution"])


class TestProjectsColumnAndTag:
    def test_candidates_table_shows_projects_column(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
        isolated_paths: Path,
    ) -> None:
        """Table output includes the Projects column with aliases."""
        project_store, _ = dual_store
        # Create a real project dir so pool add's existence check passes.
        proj_a = isolated_paths / "proj-a"
        proj_a.mkdir()
        cli_runner.invoke(
            pool_cmd.app,
            ["add", str(proj_a), "--alias", "alpha"],
        )
        project_store.upsert(
            _make_candidate(
                cluster_id="local-1",
                queries=["some task"],
                project_distribution={str(proj_a.resolve()): 3},
            )
        )

        with patch.object(skill_commands, "_get_candidate_store") as mock_get:
            def fake_get(scope: str = "project") -> ClusterCandidateStore:
                return project_store
            mock_get.side_effect = fake_get

            result = cli_runner.invoke(app, ["skill", "candidates"])

        assert result.exit_code == 0, result.stdout
        assert "Projects" in result.stdout
        assert "alpha×3" in result.stdout

    def test_candidates_table_tags_cross_project(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
    ) -> None:
        """Cross-project candidates get the [XP] tag in ID column."""
        _, global_store = dual_store
        global_store.upsert(
            _make_candidate(
                cluster_id="xp-1",
                queries=["cross task"],
                project_distribution={"/users/me/a": 2, "/users/me/b": 1},
            )
        )

        with patch.object(skill_commands, "_get_candidate_store") as mock_get:
            def fake_get(scope: str = "project") -> ClusterCandidateStore:
                return global_store
            mock_get.side_effect = fake_get

            result = cli_runner.invoke(app, ["skill", "candidates"])

        assert result.exit_code == 0, result.stdout
        assert "[XP]" in result.stdout

    def test_candidates_json_includes_project_distribution(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
    ) -> None:
        """JSON payload carries project_distribution + is_cross_project."""
        _, global_store = dual_store
        global_store.upsert(
            _make_candidate(
                cluster_id="xp-2",
                queries=["x task"],
                project_distribution={"/users/me/a": 4, "/users/me/b": 2},
            )
        )

        with patch.object(skill_commands, "_get_candidate_store") as mock_get:
            def fake_get(scope: str = "project") -> ClusterCandidateStore:
                return global_store
            mock_get.side_effect = fake_get

            result = cli_runner.invoke(app, ["skill", "candidates", "--json"])

        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        row = payload[0]
        assert "project_distribution" in row
        # Privacy (omx-code-review HIGH #2): JSON emits basenames only.
        assert row["project_distribution"] == {"a": 4, "b": 2}
        assert row["is_cross_project"] is True


class TestCrossProjectOnlyFilter:
    def test_candidates_cross_project_only_filters_out_single_project(
        self,
        cli_runner: CliRunner,
        dual_store: tuple[ClusterCandidateStore, ClusterCandidateStore],
    ) -> None:
        """--cross-project-only excludes single-project candidates."""
        project_store, global_store = dual_store
        project_store.upsert(
            _make_candidate(
                cluster_id="single-1",
                queries=["local only"],
                project_distribution={"/users/me/proj-a": 3},
            )
        )
        global_store.upsert(
            _make_candidate(
                cluster_id="xp-1",
                queries=["cross task"],
                project_distribution={"/users/me/a": 2, "/users/me/b": 1},
            )
        )

        with patch.object(skill_commands, "_get_candidate_store") as mock_get:
            def fake_get(scope: str = "project") -> ClusterCandidateStore:
                return global_store if scope == "global" else project_store
            mock_get.side_effect = fake_get

            result = cli_runner.invoke(app, ["skill", "candidates", "--cross-project-only", "--json"])

        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        ids = {row["cluster_id"] for row in payload}
        assert ids == {"xp-1"}, f"expected only cross-project, got {ids}"
