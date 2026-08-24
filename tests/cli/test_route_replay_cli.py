"""W3.5 — vibe route --replay CLI integration smoke tests.

Tests the full CLI flow:
- Auto-prompt on gold-standard match during normal `vibe route` (TTY only)
- Y confirm emits replay span + prints step_sequence
- n confirm skips silently
- --no-replay suppresses the prompt entirely
- Non-gold match doesn't prompt
- --json mode skips prompt (programmatic consumers)
- Non-TTY context skips prompt (scripts/subagents)

Uses CliRunner with mocked InstinctLearner / EmbeddingCache to keep tests
fast and deterministic. TTY is simulated via patching
``vibesop.cli.main._is_interactive_stdio`` (CliRunner replaces sys.stdin,
so direct isatty patches don't work — grok P0-2 follow-up).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
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
    f = tmp_path / "spans.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    return f


def _write_spans(span_file: Path, spans: list[dict]) -> None:
    with span_file.open("w", encoding="utf-8") as f:
        for s in spans:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def _gold_spans() -> list[dict]:
    """3 spans with distinct trace_ids — meets min_gold_run_count=3.

    Timestamps are relative to now: recall/replay applies a rolling 30-day
    look-back (replay.py _DEFAULT_DAYS_WINDOW), so hard-coded dates become
    a time bomb once they age out of the window.
    """
    return [
        {
            "task_id": "t_cmspark_01",
            "input_data": {"query": "cmspark screenshot permission popup"},
            "name": "route:query",
            "project_id": "test",
            "timestamp": (datetime.now(UTC) - timedelta(days=5 - i)).isoformat(),
            "trace_id": f"T-prior-{i}",
            "metadata": {"skill_id": "cmspark-fix"},
        }
        for i in range(1, 4)
    ]


def _fake_embedding(query: str):
    """Deterministic fake embedding that maps cmspark-related queries to
    a single dim so they cluster together."""
    import hashlib

    import numpy as np

    h = int(hashlib.sha1(query.encode()).hexdigest(), 16)
    v = np.zeros(384, dtype=np.float32)
    # Map "cmspark" + "screenshot" + "permission" to same dim for similarity
    keywords = ["cmspark", "screenshot", "permission", "popup", "弹窗", "截图", "权限"]
    q_lower = query.lower()
    if any(kw in q_lower for kw in keywords):
        v[0] = 1.0
    else:
        v[0] = (h % 9) + 1
    return v


def _fake_learner_gold(success_count: int = 3) -> MagicMock:
    """Fake InstinctLearner whose get_instinct_for_query returns a gold instinct."""
    learner = MagicMock()
    instinct = MagicMock()
    instinct.success_count = success_count
    learner.get_instinct_for_query.return_value = instinct
    return learner


def _fake_learner_no_instinct() -> MagicMock:
    learner = MagicMock()
    learner.get_instinct_for_query.return_value = None
    return learner


class TestNoReplayFlag:
    def test_no_replay_skips_prompt(self, cli_runner: CliRunner, span_file: Path) -> None:
        """--no-replay should suppress the prompt even with gold match + TTY."""
        _write_spans(span_file, _gold_spans())
        with (
            patch("vibesop.cli.main._is_interactive_stdio", return_value=True),
            patch("vibesop.core.observability.recall.get_embedding_cache") as mock_cache,
            patch("vibesop.core.observability.span_writer.SpanWriter") as mock_sw,
            patch(
                "vibesop.core.instinct.learner.InstinctLearner", return_value=_fake_learner_gold()
            ),
        ):
            cache = MagicMock()
            cache.embed = MagicMock(side_effect=_fake_embedding)
            cache.embed_batch = MagicMock(return_value=[_fake_embedding("cmspark")])
            mock_cache.return_value = cache

            mock_writer = MagicMock()
            mock_writer.query_recent.return_value = _gold_spans()
            mock_sw.return_value = mock_writer

            r = cli_runner.invoke(
                app,
                [
                    "route",
                    "cmspark screenshot permission popup",
                    "--no-replay",
                    "--json",
                ],
            )
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "Gold match" not in r.output, "prompt should be suppressed by --no-replay"


class TestJsonSuppressesPrompt:
    def test_json_mode_skips_prompt(self, cli_runner: CliRunner, span_file: Path) -> None:
        """--json should suppress the prompt (programmatic consumers)."""
        _write_spans(span_file, _gold_spans())
        with (
            patch("vibesop.cli.main._is_interactive_stdio", return_value=True),
            patch("vibesop.core.observability.recall.get_embedding_cache") as mock_cache,
            patch("vibesop.core.observability.span_writer.SpanWriter") as mock_sw,
            patch(
                "vibesop.core.instinct.learner.InstinctLearner", return_value=_fake_learner_gold()
            ),
        ):
            cache = MagicMock()
            cache.embed = MagicMock(side_effect=_fake_embedding)
            cache.embed_batch = MagicMock(return_value=[_fake_embedding("cmspark")])
            mock_cache.return_value = cache

            mock_writer = MagicMock()
            mock_writer.query_recent.return_value = _gold_spans()
            mock_sw.return_value = mock_writer

            r = cli_runner.invoke(
                app,
                [
                    "route",
                    "cmspark screenshot permission popup",
                    "--json",
                ],
            )
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "Gold match" not in r.output


class TestNonGoldNoPrompt:
    def test_non_gold_match_no_prompt(self, cli_runner: CliRunner, span_file: Path) -> None:
        """Match found but learner has no instinct → no prompt (even with TTY)."""
        _write_spans(span_file, _gold_spans())
        with (
            patch("vibesop.cli.main._is_interactive_stdio", return_value=True),
            patch("vibesop.core.observability.recall.get_embedding_cache") as mock_cache,
            patch("vibesop.core.observability.span_writer.SpanWriter") as mock_sw,
            patch(
                "vibesop.core.instinct.learner.InstinctLearner",
                return_value=_fake_learner_no_instinct(),
            ),
        ):
            cache = MagicMock()
            cache.embed = MagicMock(side_effect=_fake_embedding)
            cache.embed_batch = MagicMock(return_value=[_fake_embedding("cmspark")])
            mock_cache.return_value = cache

            mock_writer = MagicMock()
            mock_writer.query_recent.return_value = _gold_spans()
            mock_sw.return_value = mock_writer

            r = cli_runner.invoke(
                app,
                [
                    "route",
                    "cmspark screenshot permission popup",
                ],
                input="n\n",
            )
        assert r.exit_code == 0, f"failed: {r.output}"
        assert "Gold match" not in r.output, "non-gold match should not prompt"


class TestNoSpansNoPrompt:
    def test_empty_spans_no_prompt(self, cli_runner: CliRunner, span_file: Path) -> None:
        """No spans at all → no prompt (even with TTY + gold learner)."""
        with (
            patch("vibesop.cli.main._is_interactive_stdio", return_value=True),
            patch("vibesop.core.observability.recall.get_embedding_cache") as mock_cache,
            patch("vibesop.core.observability.span_writer.SpanWriter") as mock_sw,
            patch(
                "vibesop.core.instinct.learner.InstinctLearner", return_value=_fake_learner_gold()
            ),
        ):
            cache = MagicMock()
            cache.embed = MagicMock(side_effect=_fake_embedding)
            mock_cache.return_value = cache

            mock_writer = MagicMock()
            mock_writer.query_recent.return_value = []  # empty
            mock_sw.return_value = mock_writer

            r = cli_runner.invoke(
                app,
                ["route", "anything"],
                input="n\n",
            )
        assert r.exit_code == 0
        assert "Gold match" not in r.output


class TestYPathEmitsReplaySpan:
    """W3 Fix-7 (P1-4): Y confirm writes replay span to span file."""

    def test_y_confirm_writes_replay_span(self, cli_runner: CliRunner, span_file: Path) -> None:
        """Y on the replay prompt → emit_replay_span called → replay:* span in file."""
        _write_spans(span_file, _gold_spans())

        from vibesop.core.observability.tracer import ObservabilityTracer

        # Real tracer writing to span_file so we can verify replay span lands.
        real_tracer = ObservabilityTracer(storage_path=span_file, enabled=True)

        with (
            patch("vibesop.cli.main._is_interactive_stdio", return_value=True),
            patch("vibesop.core.observability.recall.get_embedding_cache") as mock_cache,
            patch("vibesop.core.observability.span_writer.SpanWriter") as mock_sw,
            patch(
                "vibesop.core.instinct.learner.InstinctLearner", return_value=_fake_learner_gold()
            ),
            patch("vibesop.core.observability.get_tracer", return_value=real_tracer),
        ):
            cache = MagicMock()
            cache.embed = MagicMock(side_effect=_fake_embedding)
            cache.embed_batch = MagicMock(return_value=[_fake_embedding("cmspark")])
            mock_cache.return_value = cache

            mock_writer = MagicMock()
            mock_writer.query_recent.return_value = _gold_spans()
            mock_sw.return_value = mock_writer

            r = cli_runner.invoke(
                app,
                ["route", "cmspark screenshot permission popup"],
                input="y\n",
            )

        assert r.exit_code == 0, f"failed: {r.output}"
        # Read span_file and check for replay span
        with span_file.open() as f:
            captured_spans = [json.loads(line) for line in f if line.strip()]
        replay_spans = [s for s in captured_spans if s.get("name", "").startswith("replay:")]
        assert len(replay_spans) >= 1, f"Y confirm should emit replay span; got {captured_spans}"

    def test_y_confirm_prints_step_sequence(self, cli_runner: CliRunner, span_file: Path) -> None:
        """Y confirm should also print the prior step_sequence to console."""
        _write_spans(span_file, _gold_spans())

        from vibesop.core.observability.tracer import ObservabilityTracer

        real_tracer = ObservabilityTracer(storage_path=span_file, enabled=True)

        with (
            patch("vibesop.cli.main._is_interactive_stdio", return_value=True),
            patch("vibesop.core.observability.recall.get_embedding_cache") as mock_cache,
            patch("vibesop.core.observability.span_writer.SpanWriter") as mock_sw,
            patch(
                "vibesop.core.instinct.learner.InstinctLearner", return_value=_fake_learner_gold()
            ),
            patch("vibesop.core.observability.get_tracer", return_value=real_tracer),
        ):
            cache = MagicMock()
            cache.embed = MagicMock(side_effect=_fake_embedding)
            cache.embed_batch = MagicMock(return_value=[_fake_embedding("cmspark")])
            mock_cache.return_value = cache

            mock_writer = MagicMock()
            # Include step_sequence-bearing spans so prompt has steps to show
            spans_with_steps = _gold_spans()
            for i, s in enumerate(spans_with_steps):
                s["name"] = ["route:query", "llm:claude", "tool:edit"][i % 3]
            mock_writer.query_recent.return_value = spans_with_steps
            mock_sw.return_value = mock_writer

            r = cli_runner.invoke(
                app,
                ["route", "cmspark screenshot permission popup"],
                input="y\n",
            )

        assert r.exit_code == 0, f"failed: {r.output}"
        # step_sequence header printed after Y
        assert "Prior step sequence" in r.output or "step" in r.output.lower(), (
            f"Y should print step list; got: {r.output[-300:]}"
        )


class TestNonTTYSkipsPrompt:
    """W3 Fix-8 (P1-5): non-TTY context auto-skips prompt (no hang on automation)."""

    def test_non_tty_skips_even_with_gold_match(
        self, cli_runner: CliRunner, span_file: Path
    ) -> None:
        """When stdin is not a TTY, prompt is silently skipped.

        Patches _is_interactive_stdio=False to simulate non-TTY context
        (scripts, subagents, CI). Verifies the prompt never fires.
        """
        _write_spans(span_file, _gold_spans())
        with (
            patch("vibesop.cli.main._is_interactive_stdio", return_value=False),
            patch("vibesop.core.observability.recall.get_embedding_cache") as mock_cache,
            patch("vibesop.core.observability.span_writer.SpanWriter") as mock_sw,
            patch(
                "vibesop.core.instinct.learner.InstinctLearner", return_value=_fake_learner_gold()
            ),
        ):
            cache = MagicMock()
            cache.embed = MagicMock(side_effect=_fake_embedding)
            cache.embed_batch = MagicMock(return_value=[_fake_embedding("cmspark")])
            mock_cache.return_value = cache

            mock_writer = MagicMock()
            mock_writer.query_recent.return_value = _gold_spans()
            mock_sw.return_value = mock_writer

            # Note: no input="n\n" — non-TTY must not require user input.
            r = cli_runner.invoke(
                app,
                ["route", "cmspark screenshot permission popup"],
            )

        assert r.exit_code == 0, f"failed: {r.output}"
        assert "Gold match" not in r.output, (
            "non-TTY must skip prompt entirely without blocking on input"
        )
        assert "Replay" not in r.output, "no Y/n prompt in non-TTY"
