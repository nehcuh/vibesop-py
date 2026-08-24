"""CLI tests for ``vibe recall --cross-project`` (W5.1 Task 3.2).

Covers:
- Empty pool → friendly error
- Aggregation across 2 projects (per-project recall then merge)
- Output includes ``Project`` column
- JSON output shape (cross_project flag + project_alias per match)
- Edge cases: missing spans.jsonl, no matches above threshold

Storage mocks: pool.yaml redirected to ``tmp_path``; each fake project
gets its own ``.vibe/observability/spans.jsonl``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from vibesop.cli.commands import pool_cmd, recall_cmd
from vibesop.core.observability import process_identity

runner = CliRunner()


@pytest.fixture
def recall_app() -> typer.Typer:
    """Build a Typer app with the recall command registered.

    recall_cmd.register() wires it as ``app.command(name="recall")``,
    so we need a wrapper Typer for isolated testing.
    """
    app = typer.Typer()
    recall_cmd.register(app)
    return app


@pytest.fixture(autouse=True)
def isolated_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pool_path = tmp_path / "pool.yaml"
    monkeypatch.setattr(pool_cmd, "_DEFAULT_POOL_PATH", pool_path)
    return pool_path


@pytest.fixture(autouse=True)
def reset_process_identity():
    saved_session = process_identity._process_session_id
    saved_project = process_identity._process_project_id
    process_identity._process_session_id = None
    process_identity._process_project_id = None
    yield
    process_identity._process_session_id = saved_session
    process_identity._process_project_id = saved_project


@pytest.fixture(autouse=True)
def mock_embedding_cache():
    """Patch ``recall.get_embedding_cache`` so tests don't depend on fastembed.

    Returns deterministic sha1-derived vectors. Same query string → same
    vector → cosine = 1.0 → matches the threshold. Different queries →
    orthogonal vectors → cosine ≈ 0 → no match.
    """
    import numpy as np

    def _vec(query: str):
        v = np.zeros(384, dtype=np.float32)
        if not query:
            return v
        # Spread sha1 across 8 dims so different queries → different
        # directions (cosine < 1.0). Same query → same vector → cosine = 1.0.
        h = hashlib.sha1(query.encode()).digest()
        for i in range(8):
            v[i] = (h[i] / 255.0) + 0.01  # +0.01 ensures non-zero norm
        return v

    def _vec_batch(queries):
        return [_vec(q) for q in queries]

    with patch("vibesop.core.observability.recall.get_embedding_cache") as mock_get:
        cache = MagicMock()
        cache.embed = MagicMock(side_effect=_vec)
        cache.embed_batch = MagicMock(side_effect=_vec_batch)
        mock_get.return_value = cache
        yield mock_get


def _make_span(
    *,
    name: str,
    query: str,
    project_id: str,
    started_at: datetime | None = None,
    session_id: str = "test-session",
) -> dict:
    """Build a minimal span record compatible with recall_similar.

    recall_similar groups by ``task_id`` and extracts the representative
    query from ``input_data.query`` (NOT top-level ``query``).
    """
    ts = (started_at or datetime.now(UTC)).isoformat()
    return {
        "id": f"{project_id}-{name}-{ts}",
        "trace_id": f"trace-{project_id}",
        "span_id": f"span-{project_id}-{name}",
        "parent_span_id": None,
        "name": name,
        "kind": "internal",
        "started_at": ts,
        "ended_at": ts,
        "duration_ms": 10,
        "status": "ok",
        "session_id": session_id,
        "project_id": project_id,
        "task_id": query,
        "input_data": {"query": query},
        "attributes": {"query": query},
    }


def _write_spans_jsonl(project_dir: Path, spans: list[dict]) -> None:
    obs_dir = project_dir / ".vibe" / "observability"
    obs_dir.mkdir(parents=True, exist_ok=True)
    spans_file = obs_dir / "spans.jsonl"
    with spans_file.open("w", encoding="utf-8") as f:
        for span in spans:
            f.write(json.dumps(span, ensure_ascii=False) + "\n")


def _register_two_projects(
    tmp_path: Path, alias_a: str = "alpha", alias_b: str = "beta"
) -> tuple[Path, Path]:
    a = tmp_path / "proj-a"
    b = tmp_path / "proj-b"
    a.mkdir()
    b.mkdir()
    runner.invoke(pool_cmd.app, ["add", str(a), "--alias", alias_a])
    runner.invoke(pool_cmd.app, ["add", str(b), "--alias", alias_b])
    return a, b


class TestCrossProjectBasic:
    def test_cross_project_no_pool_errors(self, recall_app: typer.Typer) -> None:
        result = runner.invoke(recall_app, ["test query", "--cross-project"])
        assert result.exit_code != 0
        assert "No projects in pool" in result.output

    def test_cross_project_aggregates_across_projects(
        self, tmp_path: Path, recall_app: typer.Typer
    ) -> None:
        a, b = _register_two_projects(tmp_path)
        now = datetime.now(UTC)
        _write_spans_jsonl(
            a,
            [
                _make_span(
                    name="route",
                    query="how to test clustering algorithm",
                    project_id=str(a.resolve()),
                    started_at=now,
                )
            ],
        )
        _write_spans_jsonl(
            b,
            [
                _make_span(
                    name="route",
                    query="how to test clustering algorithm",
                    project_id=str(b.resolve()),
                    started_at=now,
                )
            ],
        )

        result = runner.invoke(
            recall_app,
            ["how to test clustering algorithm", "--cross-project", "-k", "5"],
        )
        assert result.exit_code == 0, result.output
        assert "alpha" in result.output
        assert "beta" in result.output

    def test_cross_project_output_includes_project_column(
        self, tmp_path: Path, recall_app: typer.Typer
    ) -> None:
        a, b = _register_two_projects(tmp_path)
        now = datetime.now(UTC)
        _write_spans_jsonl(
            a,
            [
                _make_span(
                    name="route",
                    query="setup python project",
                    project_id=str(a.resolve()),
                    started_at=now,
                )
            ],
        )
        _write_spans_jsonl(
            b,
            [
                _make_span(
                    name="route",
                    query="setup python project",
                    project_id=str(b.resolve()),
                    started_at=now,
                )
            ],
        )

        result = runner.invoke(recall_app, ["setup python project", "--cross-project"])
        assert result.exit_code == 0, result.output
        assert "Project" in result.output


class TestCrossProjectJson:
    def test_cross_project_json_output_shape(self, tmp_path: Path, recall_app: typer.Typer) -> None:
        a, b = _register_two_projects(tmp_path)
        now = datetime.now(UTC)
        _write_spans_jsonl(
            a,
            [
                _make_span(
                    name="route",
                    query="debug pytest failure",
                    project_id=str(a.resolve()),
                    started_at=now,
                )
            ],
        )
        _write_spans_jsonl(
            b,
            [
                _make_span(
                    name="route",
                    query="debug pytest failure",
                    project_id=str(b.resolve()),
                    started_at=now,
                )
            ],
        )

        result = runner.invoke(recall_app, ["debug pytest failure", "--cross-project", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["cross_project"] is True
        assert payload["projects_searched"] == 2
        assert payload["total"] == 2
        aliases = {m["project_alias"] for m in payload["matches"]}
        assert aliases == {"alpha", "beta"}


class TestCrossProjectEdgeCases:
    def test_cross_project_skips_project_without_spans(
        self, tmp_path: Path, recall_app: typer.Typer
    ) -> None:
        a, _b = _register_two_projects(tmp_path)
        now = datetime.now(UTC)
        _write_spans_jsonl(
            a,
            [
                _make_span(
                    name="route",
                    query="cross-project merge test",
                    project_id=str(a.resolve()),
                    started_at=now,
                )
            ],
        )

        result = runner.invoke(recall_app, ["cross-project merge test", "--cross-project"])
        assert result.exit_code == 0, result.output
        assert "alpha" in result.output

    def test_cross_project_no_matches_returns_zero(
        self, tmp_path: Path, recall_app: typer.Typer
    ) -> None:
        a, b = _register_two_projects(tmp_path)
        now = datetime.now(UTC)
        _write_spans_jsonl(
            a,
            [
                _make_span(
                    name="route",
                    query="cooking recipes italian pasta",
                    project_id=str(a.resolve()),
                    started_at=now,
                )
            ],
        )
        _write_spans_jsonl(
            b,
            [
                _make_span(
                    name="route",
                    query="gardening tips for tomatoes",
                    project_id=str(b.resolve()),
                    started_at=now,
                )
            ],
        )

        result = runner.invoke(
            recall_app,
            ["quantum physics entanglement theory", "--cross-project", "-t", "0.99"],
        )
        assert result.exit_code == 0, result.output
        assert "No matches" in result.output or "no matches" in result.output.lower()

    def test_cross_project_no_matches_json_emits_cross_project_shape(
        self, tmp_path: Path, recall_app: typer.Typer
    ) -> None:
        """Regression: cross-project no-matches JSON must include
        ``cross_project: true`` and ``projects_searched`` — not borrow
        the single-project JSON shape (silently dispatched to wrong path).
        """
        a, b = _register_two_projects(tmp_path)
        now = datetime.now(UTC)
        _write_spans_jsonl(
            a,
            [
                _make_span(
                    name="route",
                    query="cooking recipes italian pasta",
                    project_id=str(a.resolve()),
                    started_at=now,
                )
            ],
        )
        _write_spans_jsonl(
            b,
            [
                _make_span(
                    name="route",
                    query="gardening tips for tomatoes",
                    project_id=str(b.resolve()),
                    started_at=now,
                )
            ],
        )

        result = runner.invoke(
            recall_app,
            [
                "quantum physics entanglement theory",
                "--cross-project",
                "--json",
                "-t",
                "0.99",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["cross_project"] is True
        assert payload["projects_searched"] == 2
        assert payload["total"] == 0
        assert payload["matches"] == []
