"""Tests for PackInstaller."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vibesop.installer.pack_installer import PackInstaller
from vibesop.security.skill_auditor import PackAuditResult


@contextmanager
def _allow_local_build():
    """Mock the F-03 interactive gate so tests can exercise local build execution."""
    with (
        patch("vibesop.installer.pack_installer.sys.stdin.isatty", return_value=True),
        patch("vibesop.installer.pack_installer.Confirm.ask", return_value=True),
    ):
        yield


def _clean_pack_audit() -> PackAuditResult:
    """Helper: a passing pre-install audit result for use in tests that mock
    SkillSecurityAuditor. Returns no critical/high threats so the install
    proceeds past the pre-audit gate introduced in v7.0.1."""
    return PackAuditResult(is_safe=True, files_scanned=1)


class TestPackInstaller:
    """Test PackInstaller functionality."""

    def test_install_unknown_pack(self) -> None:
        """Installing an unknown pack without URL should fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])
            success, msg = installer.install_pack("unknown-pack")
            assert success is False
            assert "Unknown pack" in msg

    def test_install_pack_with_url(self) -> None:
        """Installing a pack from a direct URL should succeed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[Path("skills/test/SKILL.md")],
                )
                mock_analyzer.git_clone.return_value = True
                mock_cls.return_value = mock_analyzer

                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = Path(tmpdir) / "test-pack"
                    planner_cls.return_value.plan.return_value = mock_plan

                    success, msg = installer.install_pack(
                        "test-pack", "https://example.com/test-pack"
                    )

            assert success is True
            assert "Installed test-pack" in msg
            mock_analyzer.git_clone.assert_called_once()

    def test_install_pack_analysis_errors(self) -> None:
        """Installation should fail when repository analysis returns errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=["Network unreachable"],
                    skill_files=[],
                )
                mock_cls.return_value = mock_analyzer

                success, msg = installer.install_pack("test-pack", "https://example.com/test-pack")

            assert success is False
            assert "Network unreachable" in msg

    def test_install_pack_no_skills_found(self) -> None:
        """Installation should fail when no SKILL.md files are found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[],
                )
                mock_cls.return_value = mock_analyzer

                success, msg = installer.install_pack("test-pack", "https://example.com/test-pack")

            assert success is False
            assert "No SKILL.md files found" in msg

    def test_install_pack_clone_failure(self) -> None:
        """Installation should fail when git clone fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = PackInstaller(external_paths=[Path(tmpdir)])

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[Path("skills/test/SKILL.md")],
                )
                mock_analyzer.git_clone.return_value = False
                mock_cls.return_value = mock_analyzer

                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = Path(tmpdir) / "test-pack"
                    planner_cls.return_value.plan.return_value = mock_plan

                    success, msg = installer.install_pack(
                        "test-pack", "https://example.com/test-pack"
                    )

            assert success is False
            assert "Failed to clone" in msg

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_install_pack_security_audit(self, mock_auditor_cls: Any) -> None:
        """Installed skills should be security audited."""
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
        mock_auditor_cls.return_value = mock_auditor

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test-pack"

            installer = PackInstaller(external_paths=[Path(tmpdir)])

            def _mock_clone(url: str, dest: Path) -> bool:
                """Simulate git clone by creating the skill file."""
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")
                return True

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[target_path / "SKILL.md"],
                )
                mock_analyzer.git_clone.side_effect = _mock_clone
                mock_cls.return_value = mock_analyzer

                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = target_path
                    planner_cls.return_value.plan.return_value = mock_plan

                    success, msg = installer.install_pack(
                        "test-pack", "https://example.com/test-pack"
                    )

            assert success is True
            assert "PASS" in msg
            mock_auditor.audit_skill_file.assert_called_once()

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_install_pack_with_build_sh(self, mock_auditor_cls: Any) -> None:
        """Pack with BUILD.sh should run build and report output."""
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
        mock_auditor_cls.return_value = mock_auditor

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test-pack"

            installer = PackInstaller(
                external_paths=[Path(tmpdir)],
                sandbox_builds=False,
                allow_unsafe_build=True,
            )

            def _mock_clone(url: str, dest: Path) -> bool:
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text("# Test\n", encoding="utf-8")
                (dest / "BUILD.sh").write_text("#!/bin/sh\necho 'built'", encoding="utf-8")
                return True

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[target_path / "SKILL.md"],
                    setup_scripts=["BUILD.sh"],
                )
                mock_analyzer.git_clone.side_effect = _mock_clone
                mock_cls.return_value = mock_analyzer

                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = target_path
                    planner_cls.return_value.plan.return_value = mock_plan

                    with _allow_local_build():
                        success, msg = installer.install_pack(
                            "test-pack", "https://example.com/test-pack"
                        )

            assert success is True
            assert "Build:" in msg
            assert "BUILD.sh" in msg or "built" in msg

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_install_pack_without_build_script(self, mock_auditor_cls: Any) -> None:
        """Pack without build script should not report Build line."""
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
        mock_auditor_cls.return_value = mock_auditor

        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "test-pack"

            installer = PackInstaller(external_paths=[Path(tmpdir)])

            def _mock_clone(url: str, dest: Path) -> bool:
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text("# Test\n", encoding="utf-8")
                return True

            with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = MagicMock(
                    errors=[],
                    skill_files=[target_path / "SKILL.md"],
                    setup_scripts=[],
                )
                mock_analyzer.git_clone.side_effect = _mock_clone
                mock_cls.return_value = mock_analyzer

                with patch("vibesop.installer.pack_installer.InstallPlanner") as planner_cls:
                    mock_plan = MagicMock()
                    mock_plan.target_path = target_path
                    planner_cls.return_value.plan.return_value = mock_plan

                    success, msg = installer.install_pack(
                        "test-pack", "https://example.com/test-pack"
                    )

            assert success is True
            assert "Build:" not in msg


class TestSkillSymlinks:
    """Tests for create_skill_symlinks and _copy_skill_dirs."""

    def test_create_skill_symlinks_flat_layout(self, tmp_path):
        """Skill symlinks are created with correct flattened names for flat layout."""
        from vibesop.installer.pack_installer import PackInstaller

        # Create a mock pack structure
        central = tmp_path / "central"
        pack = central / "testpack"
        review_dir = pack / "review"
        review_dir.mkdir(parents=True)
        (review_dir / "SKILL.md").write_text(
            "---\nname: review\ndescription: Review code changes\n---\n# Test skill",
            encoding="utf-8",
        )
        qa_dir = pack / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "SKILL.md").write_text(
            "---\nname: qa\ndescription: QA test the application\n---\n# QA skill",
            encoding="utf-8",
        )

        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        try:
            count = installer.create_skill_symlinks(pack, platform, "testpack")
        except OSError:
            # Fallback for Windows without symlink privileges
            count = installer._copy_skill_dirs(pack, platform, "testpack")

        assert count == 2

    def test_copy_skill_dirs_writes_ownership_marker(self, tmp_path):
        """Copied skill dirs get .vibe-manifest.json so clean_orphan_skills
        can reclaim them later."""
        import json

        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        pack = central / "testpack"
        skill_dir = pack / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: review\ndescription: Review code changes\n---\n# Test skill",
            encoding="utf-8",
        )

        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        count = installer._copy_skill_dirs(pack, platform, "testpack")

        assert count == 1
        marker = platform / "testpack-review" / ".vibe-manifest.json"
        assert marker.exists(), "pack copy must write the ownership marker"
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data["source"]["type"] == "pack-copy"

    def test_copy_skill_dirs_preserves_source_marker(self, tmp_path):
        """A marker already present in central storage is kept as-is."""
        central = tmp_path / "central"
        pack = central / "testpack"
        skill_dir = pack / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: review\ndescription: Review code changes\n---\n# Test skill",
            encoding="utf-8",
        )
        (skill_dir / ".vibe-manifest.json").write_text(
            '{"id": "review", "source": {"type": "local"}}', encoding="utf-8"
        )

        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        installer._copy_skill_dirs(pack, platform, "testpack")

        marker = platform / "testpack-review" / ".vibe-manifest.json"
        assert marker.read_text(encoding="utf-8") == (
            '{"id": "review", "source": {"type": "local"}}'
        ), "source marker must be preserved"


class TestPostInstallHook:
    """Tests for _run_post_install build script detection and execution."""

    def test_symlinked_build_script_outside_pack_rejected(self, tmp_path, symlink_supported):
        """A BUILD.sh symlink pointing outside the pack must not be executed."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("sensitive data", encoding="utf-8")
        (pack_dir / "BUILD.sh").symlink_to(secret)

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())
        # The confirmation gate should reject the symlink and decline execution.
        assert "declined" in result.lower()

    def test_build_sh_executed(self, tmp_path):
        """BUILD.sh is detected and executed."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "BUILD.sh").write_text("#!/bin/sh\necho 'built'", encoding="utf-8")

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())
        assert "BUILD.sh" in result

    def test_vibesop_build_priority(self, tmp_path):
        """.vibesop-build takes priority over BUILD.sh."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / ".vibesop-build").write_text("#!/bin/sh\necho 'vibesop'", encoding="utf-8")
        (pack_dir / "BUILD.sh").write_text("#!/bin/sh\necho 'build'", encoding="utf-8")

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())
        assert "vibesop-build" in result

    def test_package_json_bun_fallback_failure_is_not_success(self, tmp_path, monkeypatch):
        """A failing bun fallback is a required-build failure, not a success string.

        Evidence limit: the raw native Windows log only shows this test DID
        NOT RAISE (no ``shutil.which`` result was captured), so the old
        fixture's extensionless ``#!/bin/sh`` PATH stub never engaging the
        bun fallback is a PLAUSIBLE INFERENCE — CreateProcess cannot execute
        such a stub (WinError 193) — not an observation. Discovery is
        therefore controlled for the literal name ``"bun"`` only; everything
        else defers to the real ``shutil.which``. The recorded production argv
        ``["bun", "run", "gen:skill-docs"]`` is then executed as a REAL child
        (``sys.executable``) that exits 1 with ``bun-failed`` on stderr, and
        the genuine ``CompletedProcess`` is handed back to production. The
        confirmation gate, has_bun_fallback detection, and the exception path
        all run unmodified.
        """
        from vibesop.installer.pack_installer import PackBuildError, PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "package.json").write_text(
            '{"scripts":{"gen:skill-docs":"echo skills"}}', encoding="utf-8"
        )
        # Real file on disk anchoring the controlled discovery result.
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        bun = bin_dir / "bun"
        bun.write_text("#!/bin/sh\necho bun-failed >&2\nexit 1\n", encoding="utf-8")
        bun.chmod(0o755)
        # Real child: always exits nonzero with bun-failed stderr, so unknown
        # or unexpected fixture arguments can never fake a successful build.
        child = tmp_path / "bun-child.py"
        child.write_text(
            "import sys\nsys.stderr.write('bun-failed\\n')\nraise SystemExit(1)\n",
            encoding="utf-8",
        )
        real_which = shutil.which
        real_run = subprocess.run
        recorded: dict[str, Any] = {}

        def _which(cmd: str, *args: Any, **kwargs: Any) -> str | None:
            if cmd == "bun":
                return os.fspath(bun)
            return real_which(cmd, *args, **kwargs)

        def _run(cmd: Any, *args: Any, **kwargs: Any) -> Any:
            argv = list(cmd) if isinstance(cmd, (list, tuple)) else None
            if argv and argv[0] == "bun":
                recorded["argv"] = argv
                recorded["cwd"] = kwargs.get("cwd")
                recorded["kwargs"] = dict(kwargs)
                return real_run([sys.executable, os.fspath(child)], *args, **kwargs)
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(shutil, "which", _which)
        monkeypatch.setattr(subprocess, "run", _run)

        # The TTY/confirmation gate, has_bun_fallback detection, and the
        # exception path all run through production code inside this block.
        with _allow_local_build(), pytest.raises(PackBuildError, match="bun") as excinfo:
            installer._run_post_install(pack_dir, object())

        # Original complete argv and invocation contract, recorded before the
        # child rewrite and asserted against production's exact call.
        assert recorded["argv"] == ["bun", "run", "gen:skill-docs"]
        assert recorded["cwd"] == pack_dir
        bun_kwargs = recorded["kwargs"]
        assert bun_kwargs["cwd"] == pack_dir
        assert bun_kwargs["timeout"] == 60
        assert bun_kwargs["capture_output"] is True
        assert bun_kwargs["text"] is True
        assert bun_kwargs["check"] is False
        # Real child outcome: nonzero exit plus its stderr flowed through the
        # production failure formatting.
        assert "bun-failed" in str(excinfo.value)

    def test_setup_sh_executed(self, tmp_path):
        """setup.sh is also detected as a build script."""
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        (pack_dir / "setup.sh").write_text("#!/bin/sh\necho 'setup'", encoding="utf-8")

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())
        assert "setup.sh" in result

    def test_local_build_nonzero_failure_propagates_stderr(self, tmp_path):
        """A real local build exiting nonzero raises PackBuildError with its stderr.

        Runs the actual production subprocess (direct exec on POSIX; the
        discovered POSIX shell on Windows). No mocking at the test layer.
        """
        from vibesop.installer.pack_installer import PackBuildError, PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        # newline="\n": Git Bash must not see CRLF-translated redirects/exits
        # when this test runs natively on Windows.
        (pack_dir / "BUILD.sh").write_text(
            "#!/bin/sh\necho local-build-boom >&2\nexit 3\n", encoding="utf-8", newline="\n"
        )

        with _allow_local_build(), pytest.raises(PackBuildError) as excinfo:
            installer._run_post_install(pack_dir, object())

        assert "BUILD.sh failed" in str(excinfo.value)
        assert "local-build-boom" in str(excinfo.value)

    def test_local_build_succeeds_in_pack_dir_with_spaces(self, tmp_path):
        """A pack directory containing spaces still executes the build script.

        Spaces exercise argv quoting through the real production subprocess on
        every platform (direct exec on POSIX, interpreter argv on Windows).
        """
        from vibesop.installer.pack_installer import PackInstaller

        installer = PackInstaller(external_paths=[tmp_path], allow_unsafe_build=True)
        pack_dir = tmp_path / "pack with spaces"
        pack_dir.mkdir()
        # newline="\n": Git Bash must not see CRLF-translated redirect targets
        # when this test runs natively on Windows.
        (pack_dir / "BUILD.sh").write_text(
            "#!/bin/sh\necho 'spaced build' > 'spaced out.txt'\n",
            encoding="utf-8",
            newline="\n",
        )

        with _allow_local_build():
            result = installer._run_post_install(pack_dir, object())

        assert result == "BUILD.sh OK"
        assert (pack_dir / "spaced out.txt").read_text(encoding="utf-8").strip() == ("spaced build")

    def test_create_skill_symlinks_root_skill_md(self, tmp_path):
        """Root-level SKILL.md is symlinked using pack_name as the flat name."""
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        pack = central / "testpack"
        pack.mkdir(parents=True)
        (pack / "SKILL.md").write_text(
            "---\nname: testpack\ndescription: Root level test pack skill\n---\n# Pack manifest",
            encoding="utf-8",
        )

        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        try:
            count = installer.create_skill_symlinks(pack, platform, "testpack")
        except OSError:
            # Fallback for Windows without symlink privileges
            count = installer._copy_skill_dirs(pack, platform, "testpack")

        assert count == 1


# The build script below is Python source: production never inspects script
# contents, so the interpreter these simulations discover can be a real child
# (``sys.executable``) that runs it on every host and records the exact argv
# the OS was handed. POSIX-shell semantics stay covered by the real
# ``#!/bin/sh`` tests above and are NOT re-verified here.
_PY_BUILD_CHILD = """\
import json
import os
import sys

payload = {
    "interpreter": sys.executable,
    "script_arg": sys.argv[0],
    "extra_args": list(sys.argv[1:]),
    "cwd": os.getcwd(),
}
with open(os.environ["W2_BUILD_RECORD"], "w", encoding="utf-8") as fh:
    json.dump(payload, fh)
"""


def _write_inert_decoy(path: Path) -> Path:
    """A real, selectable file that fails loudly if executed as an interpreter.

    No exec bit on POSIX (EACCES) and not a Win32 application on Windows
    (WinError 193), so wrongly selecting a decoy can only fail the build.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("inert decoy: not a valid executable\n", encoding="utf-8")
    return path


def _write_python_build_script(pack_dir: Path) -> Path:
    script = pack_dir / "BUILD.sh"
    script.write_text(_PY_BUILD_CHILD, encoding="utf-8", newline="\n")
    return script


class TestWindowsLocalBuildInterpreterSeam:
    """SIMULATIONS of the win32 interpreter-selection seam in ``_run_build_local``.

    What stays real: production candidate ordering, resolution, System32
    exclusion, chmod, argv construction, and the ``shell=False`` subprocess —
    the selected interpreter is a real ``sys.executable`` child whose recorded
    argv is asserted in full, and every test below runs on every host
    (no native-Windows skip).

    What is fixture-controlled — and therefore NOT native proof: the platform
    predicate (a module-local ``sys`` shim applied only on POSIX hosts; the
    real ``sys.platform``/``os.name`` are never patched process-wide), the
    discovery probe (``shutil.which`` controlled for the literal names
    ``sh``/``bash``, delegating everything else to the real implementation),
    and the scratch Windows environment. Decoys are inert files: if
    production selected one, the real subprocess would fail (EACCES on POSIX,
    WinError 193 on Windows) and the build could not report success, so a
    passing test is machine evidence the asserted candidate was chosen.
    Native discovery/execution of a real Git Bash ``sh.exe`` and exclusion of
    the real ``C:\\Windows\\System32\\bash.exe`` WSL launcher are covered only
    by the real-shell tests above when they run on a Windows host.
    """

    @staticmethod
    def _stage_win32_seam(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        discovered: dict[str, str | None],
    ) -> None:
        """Point production's win32 branch at a controlled scratch Windows.

        ``discovered`` maps the literal probe names (``sh``, ``bash``) to the
        candidate string production should see, or ``None`` for "not found".
        """
        from types import SimpleNamespace

        import vibesop.installer.pack_installer as pack_installer_module

        fake_root = tmp_path / "fake-win"
        # Uppercase names match production's lookups (case-insensitive on
        # Windows, exact on POSIX simulation hosts).
        monkeypatch.setenv("SYSTEMROOT", str(fake_root / "Windows"))
        monkeypatch.setenv("PROGRAMFILES", str(fake_root / "Program Files"))
        monkeypatch.setenv("PROGRAMFILES(X86)", str(fake_root / "Program Files (x86)"))
        monkeypatch.setenv("LOCALAPPDATA", str(fake_root / "AppData" / "Local"))
        # A PATH pointing nowhere keeps the delegating probe hermetic if
        # production ever queries a name outside ``discovered``.
        monkeypatch.setenv("PATH", str(fake_root / "no-bin-on-path"))
        real_which = shutil.which

        def _which(cmd: str, *args: Any, **kwargs: Any) -> str | None:
            if cmd in discovered:
                return discovered[cmd]
            return real_which(cmd, *args, **kwargs)

        monkeypatch.setattr(shutil, "which", _which)
        if sys.platform != "win32":
            # On POSIX hosts swap ONLY the production module's ``sys`` so its
            # platform predicate reads "win32"; the real ``sys.platform`` and
            # ``os.name`` stay untouched, leaving shutil/pathlib/subprocess in
            # their native POSIX implementations.
            monkeypatch.setattr(pack_installer_module, "sys", SimpleNamespace(platform="win32"))

    @staticmethod
    def _assert_child_argv(record: Path, pack_dir: Path, script: Path) -> None:
        payload = json.loads(record.read_text(encoding="utf-8"))
        # Complete production argv, recorded by the child that was executed:
        # [resolved interpreter, script.as_posix()] and nothing else.
        assert Path(payload["interpreter"]).resolve() == Path(sys.executable).resolve()
        assert payload["script_arg"] == script.as_posix()
        assert payload["extra_args"] == []
        assert Path(payload["cwd"]).resolve() == pack_dir.resolve()

    def test_windows_branch_prefers_sh_candidate(self, tmp_path, monkeypatch):
        """``sh`` wins over equal-presence ``bash`` and Git-install decoys.

        Both lower-priority candidates are selectable inert decoys: a wrong
        priority order would execute one and fail the build.
        """
        from vibesop.installer.pack_installer import PackInstaller

        fake_root = tmp_path / "fake-win"
        decoy_bash = _write_inert_decoy(fake_root / "bin" / "bash")
        _write_inert_decoy(fake_root / "Program Files" / "Git" / "bin" / "bash.exe")
        record = tmp_path / "build-record.json"
        monkeypatch.setenv("W2_BUILD_RECORD", str(record))
        self._stage_win32_seam(
            monkeypatch, tmp_path, {"sh": sys.executable, "bash": str(decoy_bash)}
        )

        pack_dir = tmp_path / "pack with spaces"
        pack_dir.mkdir()
        script = _write_python_build_script(pack_dir)

        assert PackInstaller._run_build_local(pack_dir, script) == "BUILD.sh OK"
        self._assert_child_argv(record, pack_dir, script)

    def test_windows_branch_skips_wsl_launcher_in_system32(self, tmp_path, monkeypatch):
        """A ``System32\\bash.exe`` returned first by discovery is excluded.

        The decoy is a scratch file, not the real WSL launcher; this seam
        verifies production's exclusion logic, not native WSL behavior.
        Had the decoy been selected, executing it would have failed the
        build, so this test cannot pass on a selection regression.
        """
        from vibesop.installer.pack_installer import PackInstaller

        fake_root = tmp_path / "fake-win"
        wsl_decoy = _write_inert_decoy(fake_root / "Windows" / "System32" / "bash.exe")
        record = tmp_path / "build-record.json"
        monkeypatch.setenv("W2_BUILD_RECORD", str(record))
        self._stage_win32_seam(
            monkeypatch, tmp_path, {"sh": str(wsl_decoy), "bash": sys.executable}
        )

        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        script = _write_python_build_script(pack_dir)

        assert PackInstaller._run_build_local(pack_dir, script) == "BUILD.sh OK"
        self._assert_child_argv(record, pack_dir, script)
        assert wsl_decoy.is_file()

    def test_windows_branch_resolves_lexical_alias_of_wsl_launcher(self, tmp_path, monkeypatch):
        """A ``..``-laden spelling of the WSL launcher cannot evade exclusion.

        ``<root>/bin/../Windows/System32/bash.exe`` is lexically outside
        ``<root>/Windows/System32`` yet resolves onto the very same decoy
        file; production must resolve both the candidate and the boundary
        before the exclusion check. Selecting the alias would execute the
        inert decoy and fail the build, so only the resolved exclusion passes.
        """
        from vibesop.installer.pack_installer import PackInstaller

        fake_root = tmp_path / "fake-win"
        wsl_decoy = _write_inert_decoy(fake_root / "Windows" / "System32" / "bash.exe")
        # Every intermediate directory of the alias spelling must exist, or
        # the OS stat would fail and skip the candidate as nonexistent
        # instead of exercising the containment check.
        (fake_root / "bin").mkdir()
        alias = fake_root / "bin" / ".." / "Windows" / "System32" / "bash.exe"
        # Fixture preconditions, machine-checked: the alias spelling evades a
        # lexical prefix test, is a real selectable file, and resolves to the
        # decoy file.
        assert not str(alias).startswith(str(fake_root / "Windows"))
        assert alias.is_file()
        assert alias.resolve() == wsl_decoy.resolve()
        record = tmp_path / "build-record.json"
        monkeypatch.setenv("W2_BUILD_RECORD", str(record))
        self._stage_win32_seam(monkeypatch, tmp_path, {"sh": str(alias), "bash": sys.executable})

        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        script = _write_python_build_script(pack_dir)

        assert PackInstaller._run_build_local(pack_dir, script) == "BUILD.sh OK"
        self._assert_child_argv(record, pack_dir, script)
        assert wsl_decoy.is_file()

    def test_windows_branch_ignores_nonexistent_candidate(self, tmp_path, monkeypatch):
        """A probe result pointing at nothing is skipped, never launched.

        The nonexistent ``sh`` candidate is passed over in favor of an
        existing allowed candidate (the real python child). Launching the
        ghost path would raise FileNotFoundError and fail the build.
        """
        from vibesop.installer.pack_installer import PackInstaller

        ghost = tmp_path / "fake-win" / "bin" / "sh"
        record = tmp_path / "build-record.json"
        monkeypatch.setenv("W2_BUILD_RECORD", str(record))
        self._stage_win32_seam(monkeypatch, tmp_path, {"sh": str(ghost), "bash": sys.executable})

        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        script = _write_python_build_script(pack_dir)

        assert PackInstaller._run_build_local(pack_dir, script) == "BUILD.sh OK"
        self._assert_child_argv(record, pack_dir, script)
        assert not ghost.exists()

    def test_windows_branch_missing_interpreter_fails_closed(self, tmp_path, monkeypatch):
        """No discoverable POSIX shell → PackBuildError, never a silent skip.

        Runs on every host: the probe reports "not found" and the fallback
        roots point into the scratch tree, so production must fail closed
        before any exec (the subprocess is patched to fail the test if
        reached).
        """
        from vibesop.installer.pack_installer import PackBuildError, PackInstaller

        self._stage_win32_seam(monkeypatch, tmp_path, {"sh": None, "bash": None})

        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        script = pack_dir / "BUILD.sh"
        script.write_text("#!/bin/sh\necho 'built'\n", encoding="utf-8")

        with (
            patch("subprocess.run", side_effect=AssertionError("must not execute")),
            pytest.raises(PackBuildError, match="no Windows-native POSIX shell"),
        ):
            PackInstaller._run_build_local(pack_dir, script)
        # The script itself is untouched apart from the pre-execution chmod.
        assert script.read_text(encoding="utf-8") == "#!/bin/sh\necho 'built'\n"

    def test_windows_branch_nonexistent_candidates_fail_closed(self, tmp_path, monkeypatch):
        """Candidates that exist only as spellings fail closed too.

        Every discovery result points at a path that was never created and
        the fallback roots are equally empty: production must skip each ghost
        (never launch it) and refuse the build.
        """
        from vibesop.installer.pack_installer import PackBuildError, PackInstaller

        ghost_sh = tmp_path / "ghosts" / "sh"
        ghost_bash = tmp_path / "ghosts" / "bash"
        self._stage_win32_seam(
            monkeypatch, tmp_path, {"sh": str(ghost_sh), "bash": str(ghost_bash)}
        )

        pack_dir = tmp_path / "pack"
        pack_dir.mkdir()
        script = pack_dir / "BUILD.sh"
        script.write_text("#!/bin/sh\necho 'built'\n", encoding="utf-8")

        with (
            patch("subprocess.run", side_effect=AssertionError("must not execute")),
            pytest.raises(PackBuildError, match="no Windows-native POSIX shell"),
        ):
            PackInstaller._run_build_local(pack_dir, script)
        assert not ghost_sh.exists()
        assert not ghost_bash.exists()


class TestSkillNameDedup:
    """Tests for cross-pack deduplication by frontmatter ``name:``."""

    def _make_pack(
        self, central: Path, pack_name: str, skill_name: str, rel: str = "review"
    ) -> Path:
        pack = central / pack_name
        skill_dir = pack / rel
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: A test skill for dedup verification\n---\n# {skill_name}\n",
            encoding="utf-8",
        )
        return pack

    def test_flatten_skill_name_normalizes_separators(self) -> None:
        """rel_path from Path.relative_to() uses native separators — backslashes
        on Windows must flatten too, else the link target lands in a nested
        non-existent directory (WinError 3 on windows-latest CI)."""
        from vibesop.installer.pack_installer import PackInstaller

        assert (
            PackInstaller._flatten_skill_name("packB", "deeply/nested/review")
            == "packB-deeply-nested-review"
        )
        assert (
            PackInstaller._flatten_skill_name("packB", "deeply\\nested\\review")
            == "packB-deeply-nested-review"
        )
        assert PackInstaller._flatten_skill_name("packB", ".") == "packB"

    def test_dedup_skips_same_name_across_packs(self, tmp_path, symlink_supported):
        """Two packs installing a skill with the same ``name:`` → only first lands."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        pack_a = self._make_pack(central, "packA", "shared-skill", rel="review")
        pack_b = self._make_pack(central, "packB", "shared-skill", rel="deeply/nested/review")

        installer = PackInstaller(central_storage=central, platform_paths=[platform])

        count_a = installer.create_skill_symlinks(pack_a, platform, "packA")
        count_b = installer.create_skill_symlinks(pack_b, platform, "packB")

        assert count_a == 1
        assert count_b == 0
        entries = sorted(p.name for p in platform.iterdir())
        assert entries == ["packA-review"]

    def test_dedupe_disabled_installs_both(self, tmp_path, symlink_supported):
        """``dedupe_by_name=False`` preserves the legacy duplicate behavior."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        pack_a = self._make_pack(central, "packA", "shared-skill", rel="review")
        pack_b = self._make_pack(central, "packB", "shared-skill", rel="deeply/nested/review")

        installer = PackInstaller(central_storage=central, platform_paths=[platform])

        count_a = installer.create_skill_symlinks(pack_a, platform, "packA", dedupe_by_name=False)
        count_b = installer.create_skill_symlinks(pack_b, platform, "packB", dedupe_by_name=False)

        assert count_a == 1
        assert count_b == 1
        entries = sorted(p.name for p in platform.iterdir())
        assert entries == ["packA-review", "packB-deeply-nested-review"]

    def test_different_names_both_installed(self, tmp_path, symlink_supported):
        """Distinct ``name:`` values are never deduped."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        pack_a = self._make_pack(central, "packA", "alpha", rel="alpha")
        pack_b = self._make_pack(central, "packB", "beta", rel="beta")

        installer = PackInstaller(central_storage=central, platform_paths=[platform])

        count_a = installer.create_skill_symlinks(pack_a, platform, "packA")
        count_b = installer.create_skill_symlinks(pack_b, platform, "packB")

        assert count_a == 1
        assert count_b == 1
        entries = sorted(p.name for p in platform.iterdir())
        assert entries == ["packA-alpha", "packB-beta"]

    def test_missing_name_field_falls_back_to_path_dedup(self, tmp_path, symlink_supported):
        """A SKILL.md without ``name:`` is not deduped (falls back to path-based logic)."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        from vibesop.installer.pack_installer import PackInstaller

        central = tmp_path / "central"
        platform = tmp_path / "platform"
        platform.mkdir(parents=True)

        # Pack A has a name, pack B does not
        pack_a = central / "packA" / "review"
        pack_a.mkdir(parents=True)
        (pack_a / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: Has a name field\n---\n# alpha\n",
            encoding="utf-8",
        )

        pack_b = central / "packB" / "review"
        pack_b.mkdir(parents=True)
        (pack_b / "SKILL.md").write_text(
            "---\ndescription: No name field here at all\n---\n# beta\n",
            encoding="utf-8",
        )

        installer = PackInstaller(central_storage=central, platform_paths=[platform])
        count_a = installer.create_skill_symlinks(pack_a.parent, platform, "packA")
        count_b = installer.create_skill_symlinks(pack_b.parent, platform, "packB")

        # Both installed because packB has no resolvable name
        assert count_a == 1
        assert count_b == 1
        entries = sorted(p.name for p in platform.iterdir())
        assert entries == ["packA-review", "packB-review"]


class TestProjectScopeInstall:
    """``scope="project"`` installs into ``<project_root>/.vibe/skills/<pack>/``.

    The full security chain (pre-audit, F-02 pack-lock, F-03 build gate) runs
    exactly as for global installs; only platform symlinks and the global
    index rebuild are skipped.
    """

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_project_scope_layout_and_discovery(self, mock_auditor_cls: Any, tmp_path) -> None:
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
        mock_auditor_cls.return_value = mock_auditor

        project_root = tmp_path / "proj"
        central = tmp_path / "central"
        platform = tmp_path / "platform"
        installer = PackInstaller(
            central_storage=central,
            platform_paths=[platform],
            project_root=project_root,
        )

        def _mock_clone(url: str, dest: Path) -> bool:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "SKILL.md").write_text(
                "---\nname: proj-pack\ndescription: A project-scope test skill pack\n---\n# Test\n",
                encoding="utf-8",
            )
            return True

        with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = MagicMock(
                errors=[],
                skill_files=[Path("SKILL.md")],
                pack_name="proj-pack",
                source_url="https://example.com/proj-pack",
                readme_install_hint="",
                setup_scripts=[],
            )
            mock_analyzer.git_clone.side_effect = _mock_clone
            mock_cls.return_value = mock_analyzer

            success, msg = installer.install_pack(
                "proj-pack", "https://example.com/proj-pack", scope="project"
            )

        assert success is True, msg
        pack_dir = project_root / ".vibe" / "skills" / "proj-pack"
        assert (pack_dir / "SKILL.md").is_file()
        assert str(pack_dir) in msg

        # Project scope skips platform symlinks and the central-storage copy.
        assert not (central / "proj-pack").exists()
        assert not platform.exists()

        # F-02: the pack lock is recorded (conftest isolates the lock store).
        from vibesop.core.skills.pack_lock import PackLockStore

        assert PackLockStore().get("proj-pack") is not None

        # The project-level pack is discovered by the skill loader, like any
        # other .vibe/skills/ skill (e.g. instinct-evolved ones).
        from vibesop.core.skills.loader import SkillLoader

        skills = SkillLoader(project_root=project_root, enable_external=False).discover_all()
        assert "proj-pack" in skills
        source_file = skills["proj-pack"].source_file
        assert source_file is not None
        assert ".vibe/skills/proj-pack" in source_file.as_posix()

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_project_scope_already_installed_branch(self, mock_auditor_cls: Any, tmp_path) -> None:
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
        mock_auditor_cls.return_value = mock_auditor

        project_root = tmp_path / "proj"
        installer = PackInstaller(
            central_storage=tmp_path / "central",
            platform_paths=[tmp_path / "platform"],
            project_root=project_root,
        )

        def _mock_clone(url: str, dest: Path) -> bool:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "SKILL.md").write_text(
                "---\nname: proj-pack\ndescription: A project-scope test skill pack\n---\n# Test\n",
                encoding="utf-8",
            )
            return True

        with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = MagicMock(
                errors=[],
                skill_files=[Path("SKILL.md")],
                pack_name="proj-pack",
                source_url="https://example.com/proj-pack",
                readme_install_hint="",
                setup_scripts=[],
            )
            mock_analyzer.git_clone.side_effect = _mock_clone
            mock_cls.return_value = mock_analyzer

            url = "https://example.com/proj-pack"
            first, _ = installer.install_pack("proj-pack", url, scope="project")
            second, msg = installer.install_pack("proj-pack", url, scope="project")

        assert first is True
        assert second is True
        assert "Already installed" in msg
        # The second install short-circuits before re-cloning.
        mock_analyzer.git_clone.assert_called_once()

    @patch("vibesop.installer.pack_installer.SkillSecurityAuditor")
    def test_global_scope_unchanged(self, mock_auditor_cls: Any, tmp_path) -> None:
        """Default scope still installs to central storage."""
        mock_audit = MagicMock()
        mock_audit.is_safe = True
        mock_auditor = MagicMock()
        mock_auditor.audit_skill_file.return_value = mock_audit
        mock_auditor.audit_pack_files.return_value = _clean_pack_audit()
        mock_auditor_cls.return_value = mock_auditor

        central = tmp_path / "central"
        project_root = tmp_path / "proj"
        installer = PackInstaller(
            central_storage=central,
            platform_paths=[tmp_path / "platform"],
            project_root=project_root,
        )

        def _mock_clone(url: str, dest: Path) -> bool:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "SKILL.md").write_text(
                "---\nname: glob-pack\ndescription: A global-scope test skill pack\n---\n# Test\n",
                encoding="utf-8",
            )
            return True

        with patch("vibesop.installer.pack_installer.RepoAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = MagicMock(
                errors=[],
                skill_files=[Path("SKILL.md")],
                pack_name="glob-pack",
                source_url="https://example.com/glob-pack",
                readme_install_hint="",
                setup_scripts=[],
            )
            mock_analyzer.git_clone.side_effect = _mock_clone
            mock_cls.return_value = mock_analyzer

            with patch.object(installer, "_create_symlinks", return_value=[]):
                success, msg = installer.install_pack("glob-pack", "https://example.com/glob-pack")

        assert success is True, msg
        assert (central / "glob-pack" / "SKILL.md").is_file()
        assert not (project_root / ".vibe" / "skills" / "glob-pack").exists()
