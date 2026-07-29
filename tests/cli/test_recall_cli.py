"""W2 Task A — ``vibe recall`` CLI smoke tests via CliRunner.

Uses explicit ``--span-file`` to avoid CWD-dependent singleton state
(same pattern as test_route_cli_task_id.py uses for fresh_tracer).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.main import app


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def span_file(tmp_path: Path) -> Path:
    """Explicit span file path — passed via --span-file to bypass CWD state."""
    f = tmp_path / "spans.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    return f


def _write_spans(span_file: Path, spans: list[dict]) -> None:
    with span_file.open("w", encoding="utf-8") as f:
        for s in spans:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _fake_embedding(query: str):
    """Deterministic, never-zero embedding for testing.

    Uses sha1 (not hash()) because Python's hash() is process-randomized
    via PYTHONHASHSEED — using it produced flaky tests where different
    process seeds gave different cosine sims. v[0] is in 1-9 (never 0)
    so cosine is always well-defined.
    """
    import hashlib

    import numpy as np

    h = int(hashlib.sha1(query.encode()).hexdigest(), 16)
    v = np.zeros(384, dtype=np.float32)
    v[0] = (h % 9) + 1  # 1-9, never zero
    return v


class TestRecallCli:
    def test_no_spans_returns_empty_message(
        self, cli_runner: CliRunner, span_file: Path
    ) -> None:
        r = cli_runner.invoke(
            app, ["recall", "anything", "--span-file", str(span_file)]
        )
        assert r.exit_code == 0
        assert "No spans recorded" in r.output or "matches" in r.output.lower()

    def test_json_output_empty(
        self, cli_runner: CliRunner, span_file: Path
    ) -> None:
        r = cli_runner.invoke(
            app,
            ["recall", "anything", "--json", "--span-file", str(span_file)],
        )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["matches"] == []

    def test_json_output_with_matches(
        self, cli_runner: CliRunner, span_file: Path
    ) -> None:
        _write_spans(
            span_file,
            [
                {
                    "task_id": "t1",
                    "input_data": {"query": "screenshot permission popup"},
                    "name": "route:query",
                    "timestamp": "2026-07-28T12:00:00+00:00",
                }
            ],
        )
        with patch(
            "vibesop.core.observability.recall.get_embedding_cache"
        ) as mock_get_cache:
            cache = MagicMock()
            cache.embed = MagicMock(side_effect=_fake_embedding)
            cache.embed_batch = MagicMock(
                return_value=[_fake_embedding("screenshot permission popup")]
            )
            mock_get_cache.return_value = cache
            r = cli_runner.invoke(
                app,
                [
                    "recall",
                    "screenshot popup keeps appearing",
                    "--json",
                    "--span-file",
                    str(span_file),
                ],
            )
        assert r.exit_code == 0, f"failed: {r.output}"
        data = json.loads(r.output)
        assert len(data["matches"]) >= 1
        assert data["matches"][0]["task_id"] == "t1"

    def test_text_output_shows_table(
        self, cli_runner: CliRunner, span_file: Path
    ) -> None:
        _write_spans(
            span_file,
            [
                {
                    "task_id": "t1",
                    "input_data": {"query": "screenshot permission"},
                    "name": "route:query",
                    "timestamp": "2026-07-28T12:00:00+00:00",
                }
            ],
        )
        with patch(
            "vibesop.core.observability.recall.get_embedding_cache"
        ) as mock_get_cache:
            cache = MagicMock()
            cache.embed = MagicMock(side_effect=_fake_embedding)
            cache.embed_batch = MagicMock(
                return_value=[_fake_embedding("screenshot permission")]
            )
            mock_get_cache.return_value = cache
            r = cli_runner.invoke(
                app,
                ["recall", "screenshot permission", "--span-file", str(span_file)],
            )
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "t1" in r.output
        assert "Recall" in r.output

    def test_threshold_filter_via_cli(
        self, cli_runner: CliRunner, span_file: Path
    ) -> None:
        """High threshold via CLI flag filters out weak matches."""
        _write_spans(
            span_file,
            [
                {
                    "task_id": "t1",
                    "input_data": {"query": "alpha"},
                    "name": "route:query",
                    "timestamp": "2026-07-28T12:00:00+00:00",
                }
            ],
        )
        import numpy as np

        def _zero_sim(query: str):
            v = np.zeros(384, dtype=np.float32)
            v[0] = 1.0 if query == "different" else 0.0
            v[1] = 1.0 if query != "different" else 0.0
            return v

        with patch(
            "vibesop.core.observability.recall.get_embedding_cache"
        ) as mock_get_cache:
            cache = MagicMock()
            cache.embed = MagicMock(side_effect=_zero_sim)
            cache.embed_batch = MagicMock(return_value=[_zero_sim("alpha")])
            mock_get_cache.return_value = cache
            r = cli_runner.invoke(
                app,
                [
                    "recall",
                    "different",
                    "--threshold",
                    "0.70",
                    "--json",
                    "--span-file",
                    str(span_file),
                ],
            )
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["matches"] == []
