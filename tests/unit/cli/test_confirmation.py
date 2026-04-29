"""Tests for confirmation flow — _needs_confirmation 3-state logic."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from vibesop.cli.confirmation import _needs_confirmation


def _mock_router(confirmation_mode: str = "always", auto_select_threshold: float = 0.6):
    router = MagicMock()
    router._config.confirmation_mode = confirmation_mode
    router._config.auto_select_threshold = auto_select_threshold
    return router


def _mock_result(confidence: float = 0.85, has_primary: bool = True):
    result = MagicMock()
    if has_primary:
        result.primary = MagicMock()
        result.primary.confidence = confidence
        result.primary.skill_id = "test-skill"
    else:
        result.primary = None
    result.alternatives = []
    return result


def _mock_orchestrated_result(confidence: float = 0.85):
    result = MagicMock()
    result.execution_plan = MagicMock()
    result.execution_plan.steps = [MagicMock()]
    result.execution_plan.steps[0].confidence = confidence
    result.primary = MagicMock()
    result.primary.skill_id = "test-orch-skill"
    result.primary.confidence = confidence
    result.alternatives = []
    result.single_fallback = MagicMock()
    result.single_fallback.skill_id = "test-fallback"
    return result


class TestNeedsConfirmation:
    """Test the _needs_confirmation function with all three modes."""

    def test_always_mode_needs_confirmation(self, monkeypatch) -> None:
        """confirmation_mode='always' → always needs confirmation."""
        monkeypatch.setattr("vibesop.cli.confirmation.sys.stdin.isatty", lambda: True)
        router = _mock_router(confirmation_mode="always")
        result = _mock_result(confidence=0.95)
        assert _needs_confirmation(result, router) is True

    def test_never_mode_skips_confirmation(self) -> None:
        """confirmation_mode='never' → never needs confirmation."""
        router = _mock_router(confirmation_mode="never")
        result = _mock_result()
        assert _needs_confirmation(result, router) is False

    def test_yes_flag_skips_confirmation(self) -> None:
        """--yes flag overrides always mode."""
        router = _mock_router(confirmation_mode="always")
        result = _mock_result()
        assert _needs_confirmation(result, router, yes=True) is False

    def test_json_output_skips_confirmation(self) -> None:
        """JSON output mode skips confirmation."""
        router = _mock_router(confirmation_mode="always")
        result = _mock_result()
        assert _needs_confirmation(result, router, json_output=True) is False

    def test_validate_mode_skips_confirmation(self) -> None:
        """Validation mode skips confirmation."""
        router = _mock_router(confirmation_mode="always")
        result = _mock_result()
        assert _needs_confirmation(result, router, validate=True) is False

    def test_not_tty_skips_confirmation(self, monkeypatch) -> None:
        """Non-TTY stdin skips confirmation."""
        monkeypatch.setattr("vibesop.cli.confirmation.sys.stdin.isatty", lambda: False)
        router = _mock_router(confirmation_mode="always")
        result = _mock_result()
        assert _needs_confirmation(result, router) is False

    def test_ambiguous_only_with_high_confidence_skips(self, monkeypatch) -> None:
        """ambiguous_only mode + high confidence → skips confirmation."""
        monkeypatch.setattr("vibesop.cli.confirmation.sys.stdin.isatty", lambda: True)
        router = _mock_router(confirmation_mode="ambiguous_only", auto_select_threshold=0.6)
        result = _mock_result(confidence=0.85)
        assert _needs_confirmation(result, router) is False

    def test_ambiguous_only_with_low_confidence_needs(self, monkeypatch) -> None:
        """ambiguous_only mode + low confidence → needs confirmation."""
        monkeypatch.setattr("vibesop.cli.confirmation.sys.stdin.isatty", lambda: True)
        router = _mock_router(confirmation_mode="ambiguous_only", auto_select_threshold=0.6)
        result = _mock_result(confidence=0.40)
        assert _needs_confirmation(result, router) is True

    def test_ambiguous_only_not_primary_skips(self) -> None:
        """ambiguous_only mode without primary → skips."""
        router = _mock_router(confirmation_mode="ambiguous_only", auto_select_threshold=0.6)
        result = _mock_result(has_primary=False)
        assert _needs_confirmation(result, router) is False

    def test_orchestrated_always_confirmation(self, monkeypatch) -> None:
        """Orchestrated results always need confirmation in always mode."""
        monkeypatch.setattr("vibesop.cli.confirmation.sys.stdin.isatty", lambda: True)
        router = _mock_router(confirmation_mode="always")
        result = _mock_orchestrated_result()
        assert _needs_confirmation(result, router, is_orchestrated=True) is True

    def test_orchestrated_ambiguous_all_confident_skips(self, monkeypatch) -> None:
        """Orchestrated result with all steps confident + ambiguous_only → skips."""
        monkeypatch.setattr("vibesop.cli.confirmation.sys.stdin.isatty", lambda: True)
        router = _mock_router(confirmation_mode="ambiguous_only", auto_select_threshold=0.6)
        result = _mock_orchestrated_result(confidence=0.85)
        assert _needs_confirmation(result, router, is_orchestrated=True) is False

    def test_orchestrated_ambiguous_not_all_confident_needs(self, monkeypatch) -> None:
        """Orchestrated result with low-confidence steps + ambiguous_only → needs."""
        monkeypatch.setattr("vibesop.cli.confirmation.sys.stdin.isatty", lambda: True)
        router = _mock_router(confirmation_mode="ambiguous_only", auto_select_threshold=0.6)
        result = _mock_orchestrated_result(confidence=0.40)
        assert _needs_confirmation(result, router, is_orchestrated=True) is True
