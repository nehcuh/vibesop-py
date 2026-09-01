"""Tests for best-effort oh-my-codex CLI companion."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from vibesop.constants import TRUSTED_PACKS
from vibesop.installer.omx_cli import ensure_omx_cli, is_omx_pack


class TestIsOmxPack:
    def test_name_omx(self) -> None:
        assert is_omx_pack("omx") is True

    def test_name_superpowers(self) -> None:
        assert is_omx_pack("superpowers") is False

    def test_trusted_url(self) -> None:
        assert is_omx_pack("other", TRUSTED_PACKS["omx"]) is True

    def test_unrelated_url(self) -> None:
        assert is_omx_pack("other", "https://example.com/skills") is False


class TestEnsureOmxCli:
    def test_present_skips_npm(self) -> None:
        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=["/usr/bin/omx"]),
            patch("vibesop.installer.omx_cli.subprocess.run") as mock_run,
        ):
            result = ensure_omx_cli()
        assert result.status == "present"
        assert result.omx_path == "/usr/bin/omx"
        assert "already" in result.detail.lower()
        mock_run.assert_not_called()

    def test_no_npm_skips(self) -> None:
        with (
            patch("vibesop.installer.omx_cli.shutil.which", return_value=None),
            patch("vibesop.installer.omx_cli.subprocess.run") as mock_run,
        ):
            result = ensure_omx_cli()
        assert result.status == "skipped_no_npm"
        assert "npm install -g oh-my-codex" in result.detail
        mock_run.assert_not_called()

    def test_npm_success_installs(self) -> None:
        omx_hits = {"n": 0}

        def _which(name: str) -> str | None:
            if name == "npm":
                return "/usr/local/bin/npm"
            if name == "omx":
                omx_hits["n"] += 1
                return "/usr/local/bin/omx" if omx_hits["n"] > 1 else None
            return None

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "added 1 package"
        completed.stderr = ""
        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=_which),
            patch("vibesop.installer.omx_cli.subprocess.run", return_value=completed) as mock_run,
        ):
            result = ensure_omx_cli()
        assert result.status == "installed"
        assert result.omx_path == "/usr/local/bin/omx"
        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert cmd[0] == "/usr/local/bin/npm"
        assert cmd[1:3] == ["install", "-g"]
        assert "oh-my-codex" in cmd
        assert mock_run.call_args.kwargs["timeout"] == 180.0

    def test_npm_nonzero_fails_without_raising(self) -> None:
        completed = MagicMock()
        completed.returncode = 1
        completed.stdout = ""
        completed.stderr = "EACCES\npermission denied\n"

        def _which(name: str) -> str | None:
            return None if name == "omx" else "/usr/bin/npm"

        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=_which),
            patch("vibesop.installer.omx_cli.subprocess.run", return_value=completed),
        ):
            result = ensure_omx_cli()
        assert result.status == "failed"
        assert "npm install -g oh-my-codex" in result.detail
        assert "permission denied" in result.detail

    def test_timeout_fails_without_raising(self) -> None:
        def _which(name: str) -> str | None:
            return None if name == "omx" else "/usr/bin/npm"

        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=_which),
            patch(
                "vibesop.installer.omx_cli.subprocess.run",
                side_effect=subprocess.TimeoutExpired("npm", 180),
            ),
        ):
            result = ensure_omx_cli()
        assert result.status == "failed"
        assert "timed out" in result.detail.lower()
        assert "npm install -g oh-my-codex" in result.detail

    def test_npm_success_but_omx_missing_from_path(self) -> None:
        def _which(name: str) -> str | None:
            if name == "npm":
                return "/usr/local/bin/npm"
            return None

        install = MagicMock()
        install.returncode = 0
        install.stdout = "added 1 package"
        install.stderr = ""

        prefix = MagicMock()
        prefix.returncode = 0
        prefix.stdout = "/opt/npm-global\n"
        prefix.stderr = ""

        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=_which),
            patch(
                "vibesop.installer.omx_cli.subprocess.run",
                side_effect=[install, prefix],
            ) as mock_run,
        ):
            result = ensure_omx_cli()
        assert result.status == "failed"
        assert result.omx_path is None
        assert "/opt/npm-global/bin" in result.detail
        assert "npm install -g oh-my-codex" in result.detail
        assert mock_run.call_args_list[0].kwargs["encoding"] == "utf-8"
        assert mock_run.call_args_list[0].kwargs["errors"] == "replace"

    def test_unexpected_exception_fails_without_raising(self) -> None:
        def _which(name: str) -> str | None:
            return None if name == "omx" else "/usr/bin/npm"

        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=_which),
            patch(
                "vibesop.installer.omx_cli.subprocess.run",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = ensure_omx_cli()
        assert result.status == "failed"
        assert "boom" in result.detail
        assert "npm install -g oh-my-codex" in result.detail

    def test_keyboard_interrupt_fails_without_raising(self) -> None:
        def _which(name: str) -> str | None:
            return None if name == "omx" else "/usr/bin/npm"

        with (
            patch("vibesop.installer.omx_cli.shutil.which", side_effect=_which),
            patch(
                "vibesop.installer.omx_cli.subprocess.run",
                side_effect=KeyboardInterrupt(),
            ),
        ):
            result = ensure_omx_cli()
        assert result.status == "failed"
        assert "npm install -g oh-my-codex" in result.detail
