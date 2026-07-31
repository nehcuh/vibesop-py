"""W5.2 Task 2.1 — scan-candidates --cross-project CLI tests.

Verifies the new flag:
1. Unions spans from every pool member.
2. Writes candidates to the GLOBAL store (not cwd's project store).
3. Errors when pool is empty or no member has spans.
4. Silently skips members with missing/unreadable spans.jsonl.
5. Resulting candidates carry project_distribution.

Pattern mirrors test_recall_cross_project_cli.py: monkeypatch
``_DEFAULT_POOL_PATH`` + ``_GLOBAL_OBSERVATORY_DIR`` to tmp_path, then
register real projects via the pool add command and write spans to
each member's observability dir.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from typer.testing import CliRunner

from vibesop.cli.commands import pool_cmd, skill_commands
from vibesop.cli.main import app


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect pool.yaml + global observability dir to tmp_path."""
    pool_path = tmp_path / "pool.yaml"
    monkeypatch.setattr(pool_cmd, "_DEFAULT_POOL_PATH", pool_path)
    monkeypatch.setattr(
        skill_commands,
        "_GLOBAL_OBSERVABILITY_DIR",
        tmp_path / "fake_home" / ".vibe" / "observability",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _vec(query: str) -> np.ndarray:
    """Deterministic embedding that spreads queries across 8 dims.

    Single-dim mocks collapse all non-empty queries to cosine=1.0.
    """
    v = np.zeros(384, dtype=np.float32)
    if not query:
        return v
    h = hashlib.sha1(query.encode()).digest()
    for i in range(8):
        v[i] = (h[i] / 255.0) + 0.01
    return v


@pytest.fixture(autouse=True)
def mock_embedding_cache() -> None:
    # scan_candidates_cmd imports get_embedding_cache from the embedding module
    # at function call time; patch the source so all callers see the mock.
    with patch("vibesop.core.observability.embedding.get_embedding_cache") as mock_get:
        cache = MagicMock()
        cache.embed = MagicMock(side_effect=_vec)
        cache.embed_batch = MagicMock(side_effect=lambda qs: [_vec(q) for q in qs])
        mock_get.return_value = cache
        yield


def _make_span(
    *,
    project_id: str,
    task_id: str,
    query: str,
    name: str = "route:query",
) -> dict:
    return {
        "task_id": task_id,
        "input_data": {"query": query},
        "name": name,
        "project_id": project_id,
        "started_at": datetime(2026, 7, 30, tzinfo=UTC).isoformat(),
    }


def _write_spans_jsonl(project_dir: Path, spans: list[dict]) -> None:
    """Write spans to <project_dir>/.vibe/observability/spans.jsonl."""
    spans_file = project_dir / ".vibe" / "observability" / "spans.jsonl"
    spans_file.parent.mkdir(parents=True, exist_ok=True)
    with spans_file.open("w", encoding="utf-8") as f:
        for s in spans:
            f.write(json.dumps(s) + "\n")


def _register_two_projects(
    runner: CliRunner,
    pool_path: Path,
    project_a: Path,
    alias_a: str,
    project_b: Path,
    alias_b: str,
) -> None:
    runner.invoke(pool_cmd.app, ["add", str(project_a), "--alias", alias_a])
    runner.invoke(pool_cmd.app, ["add", str(project_b), "--alias", alias_b])


def _seed_learner_for_queries(queries: list[str]) -> None:
    """Pre-populate InstinctLearner so queries register as gold."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner()
    for q in queries:
        learner.learn(pattern=q, action="act")
        learner.record_outcome_for_query(q, success=True)


class TestScanCrossProject:
    def test_scan_cross_project_aggregates_across_pool_members(
        self, cli_runner: CliRunner, isolated_paths: Path
    ) -> None:
        """Two pool members → spans unioned → cross-project clusters formed."""
        proj_a = isolated_paths / "proj-a"
        proj_b = isolated_paths / "proj-b"
        proj_a.mkdir()
        proj_b.mkdir()
        _register_two_projects(
            cli_runner, isolated_paths / "pool.yaml", proj_a, "alpha", proj_b, "beta"
        )

        # Same query topic across both projects → should cluster together.
        _write_spans_jsonl(
            proj_a,
            [_make_span(project_id=str(proj_a), task_id="t1", query="shared diag fix")],
        )
        _write_spans_jsonl(
            proj_b,
            [_make_span(project_id=str(proj_b), task_id="t2", query="shared diag fix")],
        )
        _write_spans_jsonl(
            proj_b,
            [_make_span(project_id=str(proj_b), task_id="t3", query="shared diag fix")],
        )

        _seed_learner_for_queries(["shared diag fix"])

        result = cli_runner.invoke(app, ["skill", "scan-candidates", "--cross-project"])
        assert result.exit_code == 0, result.stdout
        assert "cross-project" in result.stdout.lower()

    def test_scan_cross_project_writes_to_global_store(
        self, cli_runner: CliRunner, isolated_paths: Path
    ) -> None:
        """Candidates land in ~/.vibe/observability/, not cwd's project store."""
        proj_a = isolated_paths / "proj-a"
        proj_a.mkdir()
        cli_runner.invoke(pool_cmd.app, ["add", str(proj_a), "--alias", "alpha"])

        _write_spans_jsonl(
            proj_a,
            [
                _make_span(project_id=str(proj_a), task_id=f"t{i}", query="shared diag fix")
                for i in range(3)
            ],
        )
        _seed_learner_for_queries(["shared diag fix"])

        result = cli_runner.invoke(app, ["skill", "scan-candidates", "--cross-project"])
        assert result.exit_code == 0, result.stdout

        # Global store should have the candidate
        global_store = skill_commands._get_candidate_store(scope="global")
        assert global_store.list_pending(), "expected candidate in global store"

        # Project store (cwd) should NOT have it
        project_store = skill_commands._get_candidate_store(scope="project")
        assert not project_store.list_pending(), "candidate should not be in project store"

    def test_scan_cross_project_empty_pool_errors(
        self, cli_runner: CliRunner, isolated_paths: Path
    ) -> None:
        """No pool members → exit 1 with hint to `vibe pool add`."""
        result = cli_runner.invoke(app, ["skill", "scan-candidates", "--cross-project"])
        assert result.exit_code == 1, result.stdout
        assert "vibe pool add" in result.stdout

    def test_scan_cross_project_missing_spans_file_skips_silently(
        self, cli_runner: CliRunner, isolated_paths: Path
    ) -> None:
        """Pool member without spans.jsonl is skipped, not an error."""
        proj_a = isolated_paths / "proj-a"
        proj_b = isolated_paths / "proj-b"  # no spans.jsonl
        proj_a.mkdir()
        proj_b.mkdir()
        _register_two_projects(
            cli_runner, isolated_paths / "pool.yaml", proj_a, "alpha", proj_b, "beta"
        )

        _write_spans_jsonl(
            proj_a,
            [
                _make_span(project_id=str(proj_a), task_id=f"t{i}", query="solo topic")
                for i in range(3)
            ],
        )
        _seed_learner_for_queries(["solo topic"])

        result = cli_runner.invoke(app, ["skill", "scan-candidates", "--cross-project"])
        assert result.exit_code == 0, result.stdout
        # proj_b silently skipped; alpha's 3 spans still formed a cluster.
        assert "1 pool member" in result.stdout or "pool member" in result.stdout

    def test_scan_cross_project_candidates_have_project_distribution(
        self, cli_runner: CliRunner, isolated_paths: Path
    ) -> None:
        """Resulting candidates carry project_distribution naming all contributors."""
        proj_a = isolated_paths / "proj-a"
        proj_b = isolated_paths / "proj-b"
        proj_a.mkdir()
        proj_b.mkdir()
        _register_two_projects(
            cli_runner, isolated_paths / "pool.yaml", proj_a, "alpha", proj_b, "beta"
        )

        # 2 spans from proj_a + 1 from proj_b, all sharing the topic → cross-project cluster.
        _write_spans_jsonl(
            proj_a,
            [
                _make_span(project_id=str(proj_a), task_id="t1", query="cross cut query"),
                _make_span(project_id=str(proj_a), task_id="t2", query="cross cut query"),
            ],
        )
        _write_spans_jsonl(
            proj_b,
            [_make_span(project_id=str(proj_b), task_id="t3", query="cross cut query")],
        )
        _seed_learner_for_queries(["cross cut query"])

        result = cli_runner.invoke(app, ["skill", "scan-candidates", "--cross-project"])
        assert result.exit_code == 0, result.stdout

        store = skill_commands._get_candidate_store(scope="global")
        candidates = store.list_pending()
        assert candidates, "expected at least one candidate"
        cross_proj_candidates = [c for c in candidates if c.is_cross_project]
        assert cross_proj_candidates, "expected at least one cross-project candidate"
        # project_distribution names both projects
        dist = cross_proj_candidates[0].project_distribution
        assert str(proj_a) in dist
        assert str(proj_b) in dist
        assert dist[str(proj_a)] == 2
        assert dist[str(proj_b)] == 1
