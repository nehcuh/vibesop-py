"""Tests for wheel-bundled data resolution (utils/bundled.py).

Covers the B0.1 packaging fix: pipx/uv-tool installs have no repo checkout,
so core-data readers must fall back to the copies force-included into the
wheel (vibesop/builtin_skills, vibesop/builtin_data/core).
"""

from __future__ import annotations

from pathlib import Path

from vibesop.core.routing.candidate_manager import CandidateManager
from vibesop.utils.bundled import (
    bundled_core_file,
    bundled_path,
    is_vibesop_checkout,
    resolve_builtin_skills_dir,
)


class TestBundledPath:
    def test_bundled_path_returns_package_relative_path(self) -> None:
        import vibesop

        result = bundled_path("builtin_skills")
        assert result == Path(vibesop.__file__).parent / "builtin_skills"


class TestBundledCoreFile:
    def test_repo_checkout_wins_when_present(self, tmp_path: Path) -> None:
        repo_copy = tmp_path / "core" / "registry.yaml"
        repo_copy.parent.mkdir(parents=True)
        repo_copy.write_text("skills: []\n", encoding="utf-8")

        result = bundled_core_file("registry.yaml", tmp_path)

        assert result == repo_copy

    def test_falls_back_to_wheel_bundle_when_repo_missing(self, tmp_path: Path) -> None:
        result = bundled_core_file("registry.yaml", tmp_path)

        assert result == bundled_path("builtin_data", "core", "registry.yaml")
        assert "builtin_data" in result.parts

    def test_no_project_root_uses_bundle(self) -> None:
        result = bundled_core_file("registry.yaml")

        assert result == bundled_path("builtin_data", "core", "registry.yaml")


class TestCandidateManagerSearchPaths:
    def test_wheel_bundled_skills_discovered(self, tmp_path: Path, monkeypatch) -> None:
        """Simulate a pipx install: package lives in site-packages with
        bundled builtin_skills, and no repo checkout exists."""
        import vibesop

        fake_pkg = tmp_path / "site-packages" / "vibesop"
        (fake_pkg / "builtin_skills").mkdir(parents=True)
        fake_init = fake_pkg / "__init__.py"
        fake_init.write_text("", encoding="utf-8")
        monkeypatch.setattr(vibesop, "__file__", str(fake_init))

        manager = CandidateManager(project_root=tmp_path)
        paths = manager._build_search_paths()

        assert fake_pkg / "builtin_skills" in paths

    def test_repo_checkout_skills_still_discovered(self, tmp_path: Path) -> None:
        """In the dev repo the wheel bundle does not exist; the
        src-layout checkout path (<repo>/core/skills) must still be found."""
        manager = CandidateManager(project_root=tmp_path)
        paths = manager._build_search_paths()

        # In the real dev environment exactly one builtin source exists.
        import vibesop

        repo_builtins = Path(vibesop.__file__).parent.parent.parent / "core" / "skills"
        pkg_builtins = bundled_path("builtin_skills")
        assert (repo_builtins in paths) or (pkg_builtins in paths)


class TestResolveBuiltinSkillsDir:
    def test_foreign_core_skills_does_not_shadow_wheel(self, tmp_path: Path, monkeypatch) -> None:
        (tmp_path / "core" / "skills" / "code-review").mkdir(parents=True)
        (tmp_path / "core" / "skills" / "code-review" / "SKILL.md").write_text(
            "# FOREIGN\n", encoding="utf-8"
        )
        fake_pkg = tmp_path / "site-packages" / "vibesop"
        wheel_skill = fake_pkg / "builtin_skills" / "code-review"
        wheel_skill.mkdir(parents=True)
        (wheel_skill / "SKILL.md").write_text("# WHEEL\n", encoding="utf-8")
        (fake_pkg / "__init__.py").write_text("", encoding="utf-8")
        import vibesop

        monkeypatch.setattr(vibesop, "__file__", str(fake_pkg / "__init__.py"))

        resolved = resolve_builtin_skills_dir(tmp_path)
        assert resolved == fake_pkg / "builtin_skills"
        assert not is_vibesop_checkout(tmp_path)

    def test_identified_checkout_wins(self, tmp_path: Path) -> None:
        (tmp_path / "core" / "skills" / "foo").mkdir(parents=True)
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "vibesop"\n', encoding="utf-8")
        assert resolve_builtin_skills_dir(tmp_path) == tmp_path / "core" / "skills"


class TestBuiltinReadersIdentityGated:
    """P1-4 residual readers must go through resolve_builtin_skills_dir.

    grok_build._count_builtin_skills, SkillHealthMonitor builtin fallback,
    and RegistrySync's default skills_dir previously read cwd/project-root
    relative ``core/skills`` — a foreign tree shadowed (or hid) the real
    builtins on uv-tool installs.
    """

    def _fake_wheel(self, tmp_path: Path, monkeypatch) -> Path:
        fake_pkg = tmp_path / "site-packages" / "vibesop"
        wheel_skill = fake_pkg / "builtin_skills" / "code-review"
        wheel_skill.mkdir(parents=True)
        (wheel_skill / "SKILL.md").write_text("# WHEEL\n", encoding="utf-8")
        (fake_pkg / "__init__.py").write_text("", encoding="utf-8")
        import vibesop

        monkeypatch.setattr(vibesop, "__file__", str(fake_pkg / "__init__.py"))
        return fake_pkg

    def test_grok_adapter_counts_wheel_not_foreign_root(self, tmp_path, monkeypatch) -> None:
        from vibesop.adapters.grok_build import GrokBuildAdapter

        fake_pkg = self._fake_wheel(tmp_path, monkeypatch)
        foreign = tmp_path / "foreign-project"
        (foreign / "core" / "skills" / "ghost-skill").mkdir(parents=True)

        adapter = GrokBuildAdapter(project_root=foreign)
        assert adapter._count_builtin_skills() == 1
        assert resolve_builtin_skills_dir(foreign) == fake_pkg / "builtin_skills"

    def test_health_monitor_builtin_fallback_ignores_foreign_root(self, tmp_path, monkeypatch) -> None:
        from vibesop.integrations.health_monitor import SkillHealthMonitor

        self._fake_wheel(tmp_path, monkeypatch)
        foreign = tmp_path / "foreign-project"
        (foreign / "core" / "skills" / "ghost-skill").mkdir(parents=True)
        (foreign / "core" / "skills" / "ghost-skill" / "SKILL.md").write_text(
            "# FOREIGN\n", encoding="utf-8"
        )

        status = SkillHealthMonitor(project_root=foreign).check_local_health("builtin")
        assert status.skills_count == 1
        assert status.name == "builtin"

    def test_registry_sync_default_dir_is_identity_gated(self, tmp_path, monkeypatch) -> None:
        from vibesop.core.skills.registry_sync import RegistrySync

        fake_pkg = self._fake_wheel(tmp_path, monkeypatch)
        sync = RegistrySync()
        assert sync.skills_dir == fake_pkg / "builtin_skills"
