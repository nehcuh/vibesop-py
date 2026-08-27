"""Tests for QuickstartRunner class."""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import MagicMock, patch

from vibesop.installer.quickstart_runner import QuickstartConfig, QuickstartRunner


class TestQuickstartRunner:
    """Tests for the quickstart wizard."""

    def test_create_runner(self) -> None:
        """Test creating a QuickstartRunner."""
        runner = QuickstartRunner()
        assert runner is not None
        assert "claude-code" in runner._supported_platforms
        assert "opencode" in runner._supported_platforms
        assert "grok-build" in runner._supported_platforms

    def test_supported_platforms(self) -> None:
        """Test that supported platforms are defined."""
        runner = QuickstartRunner()
        assert len(runner._supported_platforms) >= 2
        assert "grok-build" in runner._supported_platforms
        assert set(runner._supported_platforms) >= {
            "claude-code",
            "kimi-cli",
            "opencode",
            "pi",
            "grok-build",
        }

    def test_available_integrations_excludes_gstack(self) -> None:
        """gstack is deliberately excluded from default quickstart installs.

        Users must install gstack explicitly via `vibe install gstack`.
        See constants.DEFAULT_AUTO_INSTALL_PACKS.
        """
        runner = QuickstartRunner()
        assert "gstack" not in runner._available_integrations
        assert "superpowers" in runner._available_integrations
        assert "omx" in runner._available_integrations
        assert "mattpocock" in runner._available_integrations

    def test_ask_yes_no_default_yes(self) -> None:
        """Test _ask_yes_no with default yes and empty input."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value=""):
            assert runner._ask_yes_no("Test?", default=True) is True

    def test_ask_yes_no_default_no(self) -> None:
        """Test _ask_yes_no with default no and empty input."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value=""):
            assert runner._ask_yes_no("Test?", default=False) is False

    def test_ask_yes_no_explicit_yes(self) -> None:
        """Test _ask_yes_no with explicit yes."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", side_effect=["y"]):
            assert runner._ask_yes_no("Test?", default=False) is True

    def test_ask_yes_no_explicit_no(self) -> None:
        """Test _ask_yes_no with explicit no."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", side_effect=["n"]):
            assert runner._ask_yes_no("Test?", default=True) is False

    def test_ask_yes_no_invalid_then_valid(self) -> None:
        """Test _ask_yes_no with invalid input then valid."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", side_effect=["maybe", "yes"]):
            assert runner._ask_yes_no("Test?", default=False) is True

    def test_ask_choice_default(self) -> None:
        """Test _ask_choice with empty input returns default."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value=""):
            assert runner._ask_choice("Pick", ["1", "2"], default="1") == "1"

    def test_ask_choice_explicit(self) -> None:
        """Test _ask_choice with explicit choice."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value="2"):
            assert runner._ask_choice("Pick", ["1", "2"], default="1") == "2"

    def test_ask_choice_invalid_then_valid(self) -> None:
        """Test _ask_choice with invalid input then valid."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", side_effect=["3", "1"]):
            assert runner._ask_choice("Pick", ["1", "2"], default="2") == "1"

    def test_ask_platform(self) -> None:
        """Test _ask_platform returns selected platform."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value="1"):
            assert runner._ask_platform() == "claude-code"

    def test_ask_install_type_global(self) -> None:
        """Test _ask_install_type returns global config."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value="1"):
            config = runner._ask_install_type(Path("/tmp/project"))
            assert config.global_install is True
            # Third-party packs are opt-in since the adoption redesign.
            assert config.install_integrations is False

    def test_ask_install_type_project(self) -> None:
        """Test _ask_install_type returns project config."""
        runner = QuickstartRunner()
        with patch.object(builtins, "input", return_value="2"):
            config = runner._ask_install_type(Path("/tmp/project"))
            assert config.global_install is False
            assert config.install_integrations is False

    def test_show_summary_does_not_raise(self) -> None:
        """Test _show_summary does not raise."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="claude-code",
            install_integrations=True,
            install_hooks=False,
            project_path=Path("/tmp"),
            global_install=True,
        )
        runner._show_summary(config)  # Should not raise

    def test_show_next_steps_global(self) -> None:
        """Test _show_next_steps for global install."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="claude-code",
            install_integrations=True,
            install_hooks=True,
            project_path=Path.home(),
            global_install=True,
        )
        runner._show_next_steps(config)  # Should not raise

    def test_show_next_steps_grok_build(self, capsys) -> None:
        """Global grok-build next steps must point at ~/.grok, not ~/.claude."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="grok-build",
            install_integrations=True,
            install_hooks=True,
            project_path=Path.home(),
            global_install=True,
        )
        runner._show_next_steps(config)
        captured = capsys.readouterr()
        assert "grok-build" in captured.out
        assert "~/.grok" in captured.out

    def test_run_uses_provided_platform(self, tmp_path: Path) -> None:
        """Passing platform= skips the interactive platform prompt."""
        runner = QuickstartRunner()
        # Global install type, then cancel at confirm — no platform prompt.
        with patch.object(builtins, "input", side_effect=["1", "n"]):
            result = runner.run(project_path=tmp_path, platform="grok-build")
        assert result["config"] is not None
        assert result["config"].platform == "grok-build"
        assert result["success"] is False

    def test_show_next_steps_project(self) -> None:
        """Test _show_next_steps for project install."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="opencode",
            install_integrations=False,
            install_hooks=False,
            project_path=Path("/tmp"),
            global_install=False,
        )
        runner._show_next_steps(config)  # Should not raise

    def test_run_cancelled_at_confirm(self, tmp_path: Path) -> None:
        """Test run cancelled by user at confirmation step."""
        runner = QuickstartRunner()
        # Global install: integrations/hooks defaults are non-None, so only
        # install type, platform, and confirm inputs are needed.
        inputs = ["1", "1", "n"]
        with patch.object(builtins, "input", side_effect=inputs):
            result = runner.run(project_path=tmp_path)
        assert result["success"] is False
        assert result["config"] is not None

    def test_execute_installation_global(self, tmp_path: Path) -> None:
        """Test _execute_installation for global install."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="opencode",
            install_integrations=False,
            install_hooks=False,
            project_path=tmp_path,
            global_install=True,
        )
        success = runner._execute_installation(config)
        assert success is True

    def test_execute_installation_project(self, tmp_path: Path) -> None:
        """Test _execute_installation for project install."""
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="opencode",
            install_integrations=False,
            install_hooks=False,
            project_path=tmp_path,
            global_install=False,
        )
        success = runner._execute_installation(config)
        assert success is True

    def test_execute_installation_reports_hooks_from_single_install(self, tmp_path: Path) -> None:
        """Hooks come from the first installer.install() call — do not reinstall.

        Repro: quickstart called install() twice; the second hit _is_configured
        and returned no hooks_installed, so the wizard printed
        "No hooks available for this platform" even for claude-code/grok-build.
        """
        runner = QuickstartRunner()
        config = QuickstartConfig(
            platform="grok-build",
            install_integrations=False,
            install_hooks=True,
            project_path=tmp_path,
            global_install=True,
        )
        mock_installer = MagicMock()
        mock_installer.install.return_value = {
            "success": True,
            "hooks_installed": ["vibesop-route.json"],
            "files_created": [str(tmp_path / "hooks" / "vibesop-route.json")],
            "errors": [],
        }
        mock_installer._platforms = {
            "grok-build": {"config_dir": tmp_path},
        }
        mock_indexer = MagicMock()
        mock_indexer.global_index_path.exists.return_value = True
        mock_indexer.build_index.return_value = MagicMock(success=True)

        with (
            patch("vibesop.installer.init_support._ensure_global_config"),
            patch(
                "vibesop.installer.quickstart_runner.VibeSOPInstaller",
                return_value=mock_installer,
            ),
            patch(
                "vibesop.core.skills.indexer.SkillIndexer",
                return_value=mock_indexer,
            ),
        ):
            success = runner._execute_installation(config)

        assert success is True
        assert mock_installer.install.call_count == 1


class TestRouteDemo:
    """Post-install keyless demo (_run_route_demo)."""

    def _config(self) -> QuickstartConfig:
        return QuickstartConfig(
            platform="claude-code",
            install_integrations=False,
            install_hooks=True,
            project_path=Path("/tmp"),
            global_install=True,
        )

    def test_demo_renders_hits_and_misses(self, capsys) -> None:
        """Hits print the matched skill id; fallbacks print 'no builtin match'."""
        runner = QuickstartRunner()
        fake_router = MagicMock()
        fake_router.route.side_effect = [
            {"skill_id": "builtin/slash-list", "confidence": 0.79},
            {"skill_id": "builtin/session-end", "confidence": 0.95},
            {"skill_id": "fallback-llm", "confidence": 1.0},
        ]
        with patch(
            "vibesop.core.routing.lightweight_api.LightweightRouter",
            return_value=fake_router,
        ) as mock_cls:
            runner._run_route_demo(self._config())

        assert mock_cls.call_args.kwargs.get("project_root") == Path("/tmp")
        assert fake_router.route.call_count == 3
        out = capsys.readouterr().out
        assert "builtin/slash-list (79%)" in out
        assert "builtin/session-end (95%)" in out
        assert "no builtin match" in out

    def test_demo_restores_logger_level(self) -> None:
        """The targeted logger silencing must be undone after the demo."""
        import logging

        unified = logging.getLogger("vibesop.core.routing.unified")
        saved_before = unified.level
        runner = QuickstartRunner()
        fake_router = MagicMock()
        fake_router.route.return_value = {"skill_id": "", "confidence": 0.0}
        with patch(
            "vibesop.core.routing.lightweight_api.LightweightRouter",
            return_value=fake_router,
        ):
            runner._run_route_demo(self._config())
        assert unified.level == saved_before

    def test_demo_survives_router_exception(self, capsys) -> None:
        """A routing error degrades to 'no builtin match', never a crash."""
        runner = QuickstartRunner()
        fake_router = MagicMock()
        fake_router.route.side_effect = RuntimeError("boom")
        with patch(
            "vibesop.core.routing.lightweight_api.LightweightRouter",
            return_value=fake_router,
        ):
            runner._run_route_demo(self._config())
        out = capsys.readouterr().out
        assert out.count("no builtin match") == 3
