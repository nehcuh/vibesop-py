"""Tests for Hook base classes."""

from __future__ import annotations

from pathlib import Path

from vibesop.hooks.base import ScriptHook, TemplateHook
from vibesop.hooks.points import HookPoint


class TestScriptHook:
    """Tests for ScriptHook class."""

    def test_create_script_hook(self) -> None:
        """Test creating a script hook."""
        hook = ScriptHook(
            hook_name="test-hook",
            hook_point=HookPoint.PRE_SESSION_END,
            script_content="#!/bin/bash\necho test",
        )

        assert hook.hook_name == "test-hook"
        assert hook.hook_point == HookPoint.PRE_SESSION_END

    def test_script_hook_content(self) -> None:
        """Test script hook renders content correctly."""
        hook = ScriptHook(
            hook_name="test",
            hook_point=HookPoint.PRE_SESSION_END,
            script_content="#!/bin/bash\necho hello",
        )

        content = hook.render()
        assert "echo hello" in content


class TestTemplateHook:
    """Tests for TemplateHook class."""

    def test_create_template_hook(self) -> None:
        """Test creating a template hook."""
        hook = TemplateHook(
            hook_name="test-hook",
            hook_point=HookPoint.PRE_SESSION_END,
            template_path=Path("hooks/test.sh.j2"),
        )

        assert hook.hook_name == "test-hook"
        assert hook.hook_point == HookPoint.PRE_SESSION_END
