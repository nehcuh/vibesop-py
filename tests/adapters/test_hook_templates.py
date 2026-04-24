"""Tests for the shared hook template rendering.

Verifies that ``render_route_hook()`` in ``_shared.py`` produces valid
shell scripts for all three platform adapters.
"""

import pytest

from vibesop.adapters._shared import render_route_hook


class TestRenderRouteHook:
    """Tests for ``render_route_hook()``."""

    def test_default_params(self) -> None:
        """Default parameters produce a valid shell script."""
        result = render_route_hook()
        assert result.startswith("#!/bin/bash")
        assert "VibeSOP Route Hook for OpenCode" in result

    def test_claude_code_config(self) -> None:
        """Claude Code config enables overrides, orchestration, context."""
        result = render_route_hook(
            platform="claude-code",
            platform_name="Claude Code",
            purpose="Trigger VibeSOP routing and inject skill context",
            enable_explicit_overrides=True,
            enable_orchestration=True,
            include_additional_context=True,
            no_match_message=True,
        )
        assert result.startswith("#!/bin/bash")
        assert "VibeSOP Route Hook for Claude Code" in result
        assert "EXPLICIT SKILL" in result
        assert "orchestrate" in result
        assert "No matching skill found" in result
        assert "additionalContext" in result

    def test_opencode_config(self) -> None:
        """OpenCode config disables overrides, orchestration, context."""
        result = render_route_hook(
            platform="opencode",
            platform_name="OpenCode",
            purpose="Quick command handling and auto-routing for OpenCode",
            enable_explicit_overrides=False,
            enable_orchestration=False,
            include_additional_context=False,
            no_match_message=False,
        )
        assert result.startswith("#!/bin/bash")
        assert "VibeSOP Route Hook for OpenCode" in result
        assert "EXPLICIT SKILL" not in result
        assert "orchestrate" not in result
        assert "No matching skill found" not in result
        assert "additionalContext" not in result

    def test_kimi_cli_config(self) -> None:
        """Kimi CLI config enables context and no-match message."""
        result = render_route_hook(
            platform="kimi-cli",
            platform_name="Kimi CLI",
            purpose="Auto-routing via [[hooks]] in config.toml",
            enable_explicit_overrides=False,
            enable_orchestration=False,
            include_additional_context=True,
            no_match_message=True,
        )
        assert result.startswith("#!/bin/bash")
        assert "VibeSOP Route Hook for Kimi CLI" in result
        assert "EXPLICIT SKILL" not in result
        assert "orchestrate" not in result
        assert "No matching skill found" in result
        assert "additionalContext" in result

    def test_platforms_differ(self) -> None:
        """Each platform config produces distinct output."""
        claude = render_route_hook(platform="claude-code", platform_name="Claude Code")
        opencode = render_route_hook(platform="opencode", platform_name="OpenCode")
        kimi = render_route_hook(platform="kimi-cli", platform_name="Kimi CLI")
        assert "Claude Code" in claude
        assert "OpenCode" in opencode
        assert "Kimi CLI" in kimi
        assert claude != opencode
        assert claude != kimi
        assert opencode != kimi

    def test_version_in_header(self) -> None:
        """Version string appears in the generated header."""
        result = render_route_hook(version="9.99.0")
        assert "VibeSOP v9.99.0" in result

    def test_custom_purpose(self) -> None:
        """Custom purpose appears in the header comment."""
        result = render_route_hook(purpose="my custom purpose")
        assert "my custom purpose" in result

    def test_invalid_platform(self) -> None:
        """Invalid platform still renders (template handles unknown gracefully)."""
        result = render_route_hook(platform="unknown-platform")
        assert result.startswith("#!/bin/bash")
        # Should not have any platform-specific usage block rendered
        assert "claude-code" not in result
