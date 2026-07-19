"""Tests for symlink capability probing and the copy fallback path.

Covers ``vibesop.utils.symlinks`` (probe + M5 cache discipline) and the
three production symlink creation sites with ``symlink_to`` mocked to
raise OSError — exercising the Windows copy fallback on any platform
(ROADMAP debt: previously the fallback was untestable on POSIX CI).

M5 discipline: every test in this module runs with a cleared probe
cache (autouse fixture) so cached positives cannot leak between tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock

import pytest

from vibesop.core.skills.storage import COPY_SOURCE_MARKER, SkillStorage
from vibesop.installer.pack_installer import PackInstaller
from vibesop.utils.symlinks import can_create_dir_symlink, clear_cache


@pytest.fixture(autouse=True)
def _clean_probe_cache():
    """M5: tests that mock symlink creation must start with an empty cache."""
    clear_cache()
    yield
    clear_cache()


def _raise_oserror(*_args: object, **_kwargs: object) -> None:
    raise OSError("mocked: symlink privilege not held")


class TestCanCreateDirSymlink:
    """Probe behavior and cache discipline (mocked — platform-independent)."""

    def test_success_is_cached(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[Path, Path]] = []

        def fake_symlink_to(self: Path, target: Path, target_is_directory: bool = False) -> None:
            calls.append((self, target))

        monkeypatch.setattr(Path, "symlink_to", fake_symlink_to)

        assert can_create_dir_symlink(tmp_path) is True
        assert can_create_dir_symlink(tmp_path) is True
        assert len(calls) == 1  # second call served from cache

    def test_failure_is_not_cached(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[Path, Path]] = []

        def fake_symlink_to(self: Path, target: Path, target_is_directory: bool = False) -> None:
            calls.append((self, target))
            raise OSError("transient failure (e.g. Defender)")

        monkeypatch.setattr(Path, "symlink_to", fake_symlink_to)

        assert can_create_dir_symlink(tmp_path) is False
        assert can_create_dir_symlink(tmp_path) is False
        assert len(calls) == 2  # False is never cached — re-probed each call

    def test_clear_cache_forces_reprobe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "symlink_to", lambda *a, **k: None)
        assert can_create_dir_symlink(tmp_path) is True

        clear_cache()
        monkeypatch.setattr(Path, "symlink_to", _raise_oserror)
        assert can_create_dir_symlink(tmp_path) is False

    def test_probe_creates_missing_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "new" / "nested"
        can_create_dir_symlink(target)
        assert target.is_dir()

    def test_real_probe_returns_bool_and_leaves_no_residue(self, tmp_path: Path) -> None:
        result = can_create_dir_symlink(tmp_path)
        assert isinstance(result, bool)
        assert not any(p.name.startswith(".vibesop-symlink-probe") for p in tmp_path.iterdir())


class TestStorageCopyFallback:
    """SkillStorage.link_to_platform: OSError on symlink_to → copy + marker."""

    def test_link_to_platform_falls_back_to_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        central = tmp_path / "central"
        skill_dir = central / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# My Skill", encoding="utf-8")
        platform_dir = tmp_path / "platform"

        monkeypatch.setattr(SkillStorage, "CENTRAL_SKILLS_DIR", central)
        monkeypatch.setattr(SkillStorage, "PLATFORM_SKILLS_DIRS", {"test-platform": platform_dir})
        monkeypatch.setattr(Path, "symlink_to", _raise_oserror)

        storage = SkillStorage(dry_run=False)
        ok, msg = storage.link_to_platform("my-skill", "test-platform")

        assert ok is True
        assert "Copied" in msg
        dest = platform_dir / "my-skill"
        assert not dest.is_symlink()
        assert (dest / "SKILL.md").read_text(encoding="utf-8") == "# My Skill"
        assert (dest / COPY_SOURCE_MARKER).is_file()


class TestPackInstallerCopyFallback:
    """PackInstaller._create_symlinks: OSError on symlink_to → copy + marker."""

    def test_create_symlinks_falls_back_to_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        central = tmp_path / "central"
        pack = central / "testpack"
        skill_dir = pack / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: review\ndescription: Review code changes thoroughly\n---\n# Review",
            encoding="utf-8",
        )
        platform_dir = tmp_path / "platform"

        monkeypatch.setattr(SkillStorage, "PLATFORM_SKILLS_DIRS", {"test-platform": platform_dir})
        monkeypatch.setattr(Path, "symlink_to", _raise_oserror)

        installer = PackInstaller(central_storage=central, platform_paths=[platform_dir])
        results = installer._create_symlinks("testpack", platforms=["test-platform"])

        assert results == [
            ("test-platform", "Copied to test-platform (1 skills, symlinks not supported)")
        ]
        dest = platform_dir / "testpack-review"
        assert not dest.is_symlink()
        assert (dest / "SKILL.md").is_file()
        assert (dest / COPY_SOURCE_MARKER).is_file()


class TestAdapterCopyFallback:
    """PlatformAdapter._render_skill_content: OSError on symlink_to → copy + marker."""

    def test_render_skill_content_falls_back_to_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from vibesop.adapters.claude_code import ClaudeCodeAdapter
        from vibesop.adapters.models import Manifest, ManifestMetadata

        adapter = ClaudeCodeAdapter()
        skill_dir = tmp_path / "output" / "skills" / "gstack-review"
        skill_dir.mkdir(parents=True)

        installed_dir = tmp_path / "installed"
        installed_dir.mkdir(parents=True)
        (installed_dir / "SKILL.md").write_text("# Full Review Skill", encoding="utf-8")

        monkeypatch.setattr(
            "vibesop.adapters._shared.is_pack_installed",
            lambda _: installed_dir,
        )
        monkeypatch.setattr(Path, "symlink_to", _raise_oserror)

        class _Skill:
            id = "gstack/review"
            namespace = "gstack"
            name = "GStack Review"
            description = "Code review"
            version = "1.0"
            skill_type = "standard"
            tags: ClassVar[list[str]] = ["review"]
            trigger_when = "When asked to review code"

        result = MagicMock()
        manifest = Manifest(
            metadata=ManifestMetadata(platform="claude-code", version="1.0"),
            skills=[],
        )

        adapter._render_skill_content(_Skill(), skill_dir, result, manifest=manifest)

        assert not skill_dir.is_symlink()
        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == "# Full Review Skill"
        assert (skill_dir / COPY_SOURCE_MARKER).is_file()
        result.add_file.assert_called()
