"""Tests for the P2 no-match market-search suggestion loop in ``vibe route``.

Covers:
- the machine-readable suggestion line printed on every single-route no-match
  (all output paths, including non-TTY);
- the strictly TTY-gated interactive teaser (frequency budget, global switch,
  dismissal, fault tolerance);
- the frequency-budget rules (per-cluster 7 days, global 1 day cooldown).

All questionary/network interactions are mocked; no real network access.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from vibesop.agent.runtime import InterceptionMode
from vibesop.cli.main import (
    _handle_missed_query_suggestion,
    _market_search_budget_allows,
    app,
)
from vibesop.core.skills.miss_counter import MissCounter
from vibesop.core.skills.missed_query_tracker import MissedQueryTracker
from vibesop.core.skills.suggestion_collector import SkillSuggestion, SkillSuggestionCollector

_QUERY = "zzz unobtainium skill"


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


def _fake_config_class(values: dict[str, Any]) -> type:
    """ConfigManager stub returning fixed values (hermetic; no real config files)."""

    class _FakeConfigManager:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def get(self, key: str, default: Any = None) -> Any:
            return values.get(key, default)

    return _FakeConfigManager


def _single_decision_interceptor() -> MagicMock:
    decision = MagicMock()
    decision.should_route = True
    decision.mode = InterceptionMode.SINGLE
    decision.query = _QUERY
    decision.reason = "route it"
    decision.analysis = None
    interceptor = MagicMock()
    interceptor.should_intercept.return_value = decision
    return interceptor


def _no_match_router(*, has_match: bool = False) -> MagicMock:
    """UnifiedRouter-like mock whose single-route result is a no-match."""
    router = MagicMock()
    routing_result = MagicMock()
    routing_result.primary = None
    routing_result.alternatives = []
    routing_result.routing_path = []
    routing_result.layer_details = []
    routing_result.duration_ms = 1.0
    router.route.return_value = routing_result

    single_orch = MagicMock()
    single_orch.mode.value = "single"
    single_orch.execution_plan = None
    single_orch.primary = None
    single_orch.alternatives = []
    single_orch.routing_path = []
    single_orch.layer_details = []
    single_orch.duration_ms = 1.0
    single_orch.original_query = _QUERY
    single_orch.has_match = has_match
    single_orch.single_fallback = None
    router._to_orchestration_result.return_value = single_orch

    router._config = SimpleNamespace(confirmation_mode="never", auto_select_threshold=0.9)
    router.routing_config = SimpleNamespace(transparency="full")
    return router


def _collector_at(project_root: Path) -> SkillSuggestionCollector:
    return SkillSuggestionCollector(storage_dir=project_root / ".vibe" / "instincts")


def _only_suggestion(project_root: Path) -> SkillSuggestion:
    suggestions = _collector_at(project_root).get_market_search_suggestions()
    assert len(suggestions) == 1
    return suggestions[0]


class TestMachineReadableLine:
    """The suggestion line is printed on every no-match, TTY or not."""

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_no_match_prints_market_search_line_non_tty(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_stdin.isatty.return_value = False
        mock_interceptor_cls.return_value = _single_decision_interceptor()
        mock_runtime_cls.return_value.router._router = _no_match_router()
        monkeypatch.chdir(tmp_path)

        result = cli_runner.invoke(app, ["route", _QUERY])

        assert result.exit_code == 0
        assert f'vibe market search "{_QUERY}"' in result.output

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_no_match_records_suggestion_in_inbox_non_tty(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-TTY/agent runs must still fill the unified inbox (teaser is TTY-only)."""
        mock_stdin.isatty.return_value = False
        mock_interceptor_cls.return_value = _single_decision_interceptor()
        mock_runtime_cls.return_value.router._router = _no_match_router()
        monkeypatch.chdir(tmp_path)
        counter = MissCounter(tmp_path)
        for _ in range(3):
            counter.record(_QUERY)

        result = cli_runner.invoke(app, ["route", _QUERY])

        assert result.exit_code == 0
        collector = _collector_at(tmp_path)
        pending = [s for s in collector.get_pending() if s.suggestion_type == "market-search"]
        assert len(pending) == 1
        assert pending[0].occurrences >= 3

    @patch("vibesop.agent.runtime.AgentRuntime")
    @patch("vibesop.agent.runtime.IntentInterceptor")
    @patch("vibesop.cli.main.sys.stdin")
    def test_match_does_not_print_market_search_line(
        self,
        mock_stdin: MagicMock,
        mock_interceptor_cls: MagicMock,
        mock_runtime_cls: MagicMock,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_stdin.isatty.return_value = False
        mock_interceptor_cls.return_value = _single_decision_interceptor()
        mock_runtime_cls.return_value.router._router = _no_match_router(has_match=True)
        monkeypatch.chdir(tmp_path)

        result = cli_runner.invoke(app, ["route", _QUERY])

        assert result.exit_code == 0
        assert "vibe market search" not in result.output

    def test_json_gate_skips_teaser(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
        prompt = MagicMock(side_effect=AssertionError("teaser must not run in JSON mode"))
        monkeypatch.setattr("vibesop.cli.main._maybe_prompt_market_search", prompt)

        _handle_missed_query_suggestion(_QUERY, json_output=True)

        assert f'vibe market search "{_QUERY}"' in capsys.readouterr().out
        prompt.assert_not_called()


class TestTeaserGating:
    """Teaser fires only on TTY + switch on + threshold reached + budget OK.

    Note: CliRunner replaces sys.stdin during invoke (isatty() is always
    False), so the TTY path is exercised by calling the handler directly with
    a mocked stdin — the same call site ``route()`` uses after rendering.
    """

    def _run_teaser(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        misses: int,
        config_values: dict[str, Any] | None = None,
        stdin_tty: bool = True,
    ) -> MagicMock:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "vibesop.core.config.manager.ConfigManager",
            _fake_config_class(config_values or {}),
        )
        counter = MissCounter(tmp_path)
        for _ in range(misses):
            counter.record(_QUERY)
        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: stdin_tty))
        select_mock = MagicMock(return_value="dismiss")  # non-search non-empty default
        monkeypatch.setattr("vibesop.cli.main._safe_questionary_select", select_mock)

        _handle_missed_query_suggestion(_QUERY, json_output=False)
        return select_mock

    def test_teaser_prompts_after_three_misses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        select_mock = self._run_teaser(tmp_path, monkeypatch, misses=3)

        select_mock.assert_called_once()
        prompt_text = select_mock.call_args.args[0]
        assert _QUERY in prompt_text
        assert "3 次未命中" in prompt_text
        # mock returned "dismiss" → mark_prompted only.
        assert _only_suggestion(tmp_path).last_prompted_at is not None

    def test_teaser_silent_below_threshold(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        select_mock = self._run_teaser(tmp_path, monkeypatch, misses=2)

        select_mock.assert_not_called()

    def test_teaser_respects_global_switch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        select_mock = self._run_teaser(
            tmp_path, monkeypatch, misses=3, config_values={"suggestions.enabled": False}
        )

        select_mock.assert_not_called()

    def test_teaser_silent_on_non_tty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        select_mock = self._run_teaser(tmp_path, monkeypatch, misses=3, stdin_tty=False)

        select_mock.assert_not_called()

    def test_teaser_blocked_by_recent_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        counter = MissCounter(tmp_path)
        for _ in range(3):
            counter.record(_QUERY)
        # Simulate a prompt shown moments ago for this same cluster.
        collector = _collector_at(tmp_path)
        tracker_cluster = MissedQueryTracker(tmp_path).suggest_for_live_query(
            _QUERY, MissCounter(tmp_path)
        )
        assert tracker_cluster is not None
        suggestion = collector.add_missed_query(tracker_cluster, "cmd")
        assert suggestion is not None
        collector.mark_prompted(suggestion.id)

        questionary_mock = self._run_teaser(tmp_path, monkeypatch, misses=0)

        questionary_mock.select.assert_not_called()

    def test_teaser_exception_never_breaks_routing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("vibesop.core.config.manager.ConfigManager", _fake_config_class({}))
        counter = MissCounter(tmp_path)
        for _ in range(3):
            counter.record(_QUERY)
        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
        # Simulate questionary crash (e.g., NoConsoleScreenBufferError) —
        # the _safe_questionary_select wrapper in confirmation.py must
        # catch it and return a default, so the teaser never explodes.
        questionary_mock = MagicMock()
        questionary_mock.select.side_effect = RuntimeError("boom")
        monkeypatch.setattr("vibesop.cli.confirmation.questionary", questionary_mock)

        # Must not raise — routing output is already printed at this point.
        _handle_missed_query_suggestion(_QUERY, json_output=False)


class TestTeaserChoices:
    """search / skip / dismiss branches of the teaser."""

    def _run_with_choice(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        choice: str | None,
    ) -> MagicMock:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("vibesop.core.config.manager.ConfigManager", _fake_config_class({}))
        counter = MissCounter(tmp_path)
        for _ in range(3):
            counter.record(_QUERY)
        monkeypatch.setattr("vibesop.cli.main.sys.stdin", SimpleNamespace(isatty=lambda: True))
        monkeypatch.setattr(
            "vibesop.cli.main._safe_questionary_select",
            lambda message, choices, default="skip": choice,
        )
        market_search_mock = MagicMock()
        monkeypatch.setattr("vibesop.cli.commands.market_cmd.search", market_search_mock)

        _handle_missed_query_suggestion(_QUERY, json_output=False)
        return market_search_mock

    def test_choice_search_invokes_market_search(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        market_search_mock = self._run_with_choice(tmp_path, monkeypatch, "search")

        market_search_mock.assert_called_once_with(query=_QUERY, page=1, json_output=False)
        assert _only_suggestion(tmp_path).last_prompted_at is not None

    def test_choice_skip_only_marks_prompted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        market_search_mock = self._run_with_choice(tmp_path, monkeypatch, "skip")

        market_search_mock.assert_not_called()
        suggestion = _only_suggestion(tmp_path)
        assert suggestion.last_prompted_at is not None
        assert suggestion.status == "pending"

    def test_choice_dismiss_dismisses_suggestion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        market_search_mock = self._run_with_choice(tmp_path, monkeypatch, "dismiss")

        market_search_mock.assert_not_called()
        assert _only_suggestion(tmp_path).status == "dismissed"


class TestFrequencyBudget:
    """Per-cluster 7-day re-prompt and global 1-day cooldown."""

    @staticmethod
    def _suggestion(last_prompted_at: datetime | None) -> SkillSuggestion:
        return SkillSuggestion(
            id="miss_x",
            pattern_steps=[],
            success_rate=0.0,
            occurrences=3,
            suggested_name="x",
            suggestion_type="market-search",
            last_prompted_at=last_prompted_at,
        )

    def _collector(self, suggestions: list[SkillSuggestion]) -> MagicMock:
        collector = MagicMock()
        collector.get_market_search_suggestions.return_value = suggestions
        return collector

    def test_never_prompted_allows(self) -> None:
        suggestion = self._suggestion(None)
        assert _market_search_budget_allows(self._collector([suggestion]), suggestion)

    def test_prompted_recently_blocks(self) -> None:
        suggestion = self._suggestion(datetime.now() - timedelta(days=3))
        assert not _market_search_budget_allows(self._collector([suggestion]), suggestion)

    def test_prompted_over_seven_days_ago_allows(self) -> None:
        suggestion = self._suggestion(datetime.now() - timedelta(days=8))
        assert _market_search_budget_allows(self._collector([suggestion]), suggestion)

    def test_global_cooldown_blocks_when_other_prompted_today(self) -> None:
        suggestion = self._suggestion(datetime.now() - timedelta(days=8))
        other = self._suggestion(datetime.now() - timedelta(hours=12))
        assert not _market_search_budget_allows(self._collector([suggestion, other]), suggestion)

    def test_global_cooldown_passes_when_other_prompted_over_a_day_ago(self) -> None:
        suggestion = self._suggestion(datetime.now() - timedelta(days=8))
        other = self._suggestion(datetime.now() - timedelta(days=2))
        assert _market_search_budget_allows(self._collector([suggestion, other]), suggestion)
