"""Tests for platform-agnostic session tracking."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibesop.core.sessions import (
    GenericSessionTracker,
    HookBasedSessionTracker,
    get_tracker,
    _detect_platform,
)
from vibesop.core.sessions.context import RoutingSuggestion


class TestGenericSessionTracker:
    """Test generic session tracker."""

    def test_init(self, tmp_path):
        """Test GenericSessionTracker initialization."""
        tracker = GenericSessionTracker(project_root=".", config_dir=tmp_path)

        assert tracker.is_available() is True
        assert tracker.get_platform_name() == "generic"

    def test_enable(self, tmp_path):
        """Test enabling generic tracker."""
        tracker = GenericSessionTracker(project_root=".", config_dir=tmp_path)

        result = tracker.enable()

        assert result is True
        assert tmp_path.exists()

    def test_disable(self, tmp_path):
        """Test disabling generic tracker."""
        tracker = GenericSessionTracker(project_root=".", config_dir=tmp_path)

        # Create a state file first
        state_file = tmp_path / "session-state.json"
        state_file.write_text("{}")

        result = tracker.disable()

        assert result is True
        assert not state_file.exists()

    def test_record_tool_use(self, tmp_path):
        """Test recording tool usage."""
        tracker = GenericSessionTracker(project_root=".", config_dir=tmp_path)

        tracker.record_tool_use("read", skill="systematic-debugging")
        tracker.record_tool_use("bash", skill="systematic-debugging")

        summary = tracker._context.get_session_summary()
        assert summary["tool_use_count"] == 2

    def test_check_reroute(self, tmp_path):
        """Test checking for re-routing."""
        tracker = GenericSessionTracker(project_root=".", config_dir=tmp_path)

        tracker._context.set_current_skill("systematic-debugging")
        suggestion = tracker.check_reroute("design new architecture")

        assert isinstance(suggestion, RoutingSuggestion)

    def test_state_persistence(self, tmp_path):
        """Test that state is persisted to disk."""
        tracker = GenericSessionTracker(project_root=".", config_dir=tmp_path)

        # Set current skill first
        tracker._context.set_current_skill("test-skill")

        # Record some tool usage (with the skill)
        tracker.record_tool_use("read", skill="test-skill")

        # State should be saved
        state_file = tmp_path / "session-state.json"
        assert state_file.exists()

        # Load state in new tracker
        tracker2 = GenericSessionTracker(project_root=".", config_dir=tmp_path)
        assert tracker2._context._current_skill == "test-skill"


class TestHookBasedSessionTracker:
    """Test hook-based session tracker."""

    def test_init(self, tmp_path):
        """Test HookBasedSessionTracker initialization."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir(parents=True)

        tracker = HookBasedSessionTracker(
            project_root=".", platform="claude-code", hooks_dir=hooks_dir
        )

        assert tracker.get_platform_name() == "claude-code"

    def test_is_available_with_hooks(self, tmp_path):
        """Test availability when hooks exist."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "pre-tool-use.sh").write_text("#!/bin/bash\necho test")

        tracker = HookBasedSessionTracker(
            project_root=".", platform="claude-code", hooks_dir=hooks_dir
        )

        assert tracker.is_available() is True

    def test_is_available_without_hooks(self, tmp_path):
        """Test availability when hooks don't exist."""
        hooks_dir = tmp_path / "hooks"

        tracker = HookBasedSessionTracker(
            project_root=".", platform="claude-code", hooks_dir=hooks_dir
        )

        assert tracker.is_available() is False

    def test_record_tool_use(self, tmp_path):
        """Test recording tool usage."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir(parents=True)

        tracker = HookBasedSessionTracker(
            project_root=".", platform="claude-code", hooks_dir=hooks_dir
        )

        tracker.record_tool_use("read", skill="systematic-debugging")

        assert len(tracker._context._tool_history) == 1
        assert tracker._context._tool_history[0].tool_name == "read"

    def test_check_reroute(self, tmp_path):
        """Test checking for re-routing."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir(parents=True)

        tracker = HookBasedSessionTracker(
            project_root=".", platform="claude-code", hooks_dir=hooks_dir
        )

        tracker._context.set_current_skill("systematic-debugging")
        suggestion = tracker.check_reroute("design new architecture")

        assert isinstance(suggestion, RoutingSuggestion)


class TestPlatformDetection:
    """Test platform auto-detection."""

    def test_detect_claude_code(self):
        """Test detecting Claude Code."""
        with patch.dict("os.environ", {"CLAUDE_SESSION_FILE": "/tmp/test"}):
            platform = _detect_platform()
            assert platform == "claude-code"

    def test_detect_opencode(self, tmp_path):
        """Test detecting OpenCode."""
        # Create .opencode directory
        opencode_dir = tmp_path / ".opencode"
        opencode_dir.mkdir(parents=True)

        with patch("pathlib.Path.home", return_value=tmp_path):
            platform = _detect_platform()
            assert platform == "opencode"

    def test_detect_generic(self):
        """Test defaulting to generic."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("pathlib.Path.home", return_value=Path("/tmp/noopencode")):
                platform = _detect_platform()
                assert platform == "generic"


class TestGetTracker:
    """Test get_tracker factory function."""

    def test_get_tracker_auto_claude_code(self):
        """Test getting tracker for Claude Code."""
        with patch.dict("os.environ", {"CLAUDE_SESSION_FILE": "/tmp/test"}):
            tracker = get_tracker(platform="auto")
            assert isinstance(tracker, HookBasedSessionTracker)
            assert tracker.get_platform_name() == "claude-code"

    def test_get_tracker_auto_generic(self):
        """Test getting generic tracker."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("pathlib.Path.home", return_value=Path("/tmp/noopencode")):
                tracker = get_tracker(platform="auto")
                assert isinstance(tracker, GenericSessionTracker)

    def test_get_tracker_explicit_claude_code(self):
        """Test explicitly requesting Claude Code tracker."""
        tracker = get_tracker(platform="claude-code")
        assert isinstance(tracker, HookBasedSessionTracker)

    def test_get_tracker_explicit_generic(self):
        """Test explicitly requesting generic tracker."""
        tracker = get_tracker(platform="generic")
        assert isinstance(tracker, GenericSessionTracker)

    def test_get_tracker_explicit_opencode(self):
        """Test explicitly requesting OpenCode tracker."""
        tracker = get_tracker(platform="opencode")
        assert isinstance(tracker, GenericSessionTracker)  # OpenCode uses generic
