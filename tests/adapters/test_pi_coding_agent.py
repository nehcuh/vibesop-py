"""Tests for PiCodingAgentAdapter skill render boundary (B1 corrective).

Real public ``render_config`` counterexamples (no mocked render/content
lookups): a symlinked skills ROOT must be refused before any mkdir touches
the central install; a legal per-skill symlink must keep its
skip-central-rewrite contract; a legal missing-source fallback must render
(R3 signature contract).
"""

from pathlib import Path

import pytest

from vibesop.adapters.models import Manifest, ManifestMetadata
from vibesop.adapters.pi_coding_agent import PiCodingAgentAdapter
from vibesop.spec import SkillSpec

CENTRAL_CONTENT = "# Central Install\n\nprecious central content — do not touch\n"
PROJECT_BODY = "# Demo\n\nPROJECT_ONLY_BODY\n"


def _manifest(skill_id: str = "demo") -> Manifest:
    return Manifest(
        metadata=ManifestMetadata(platform="pi"),
        skills=[
            SkillSpec(
                id=skill_id,
                name="Demo",
                description="Demo skill",
                trigger_when="testing",
            )
        ],
    )


def _seed_project(tmp_path: Path, skill_id: str = "demo") -> Path:
    """Project with real, discoverable skill content."""
    project_root = tmp_path / "proj"
    name_only = skill_id.split("/", 1)[1] if "/" in skill_id else skill_id
    skill_dir = project_root / "skills" / name_only
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(PROJECT_BODY, encoding="utf-8")
    return project_root


class TestRenderAncestorSymlinkRefused:
    """R1/R2 counterexamples: ``skills/`` root replaced by a symlink into a
    central install. The render must fail safe BEFORE any mkdir — the
    central install must not gain directories, content, or markers.
    """

    def test_refuses_before_creating_central_dir(
        self, tmp_path: Path, symlink_supported: bool
    ) -> None:
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")

        project_root = _seed_project(tmp_path)
        central = tmp_path / "central"
        central.mkdir()
        output_dir = project_root / ".pi"
        output_dir.mkdir(parents=True)
        (output_dir / "skills").symlink_to(central, target_is_directory=True)

        adapter = PiCodingAgentAdapter(project_root=project_root)
        result = adapter.render_config(_manifest(), output_dir)

        assert not result.success
        assert any("symlink" in e.lower() or "traversal" in e.lower() for e in result.errors), (
            f"expected a symlink/traversal refusal, got: {result.errors}"
        )
        assert not (central / "demo").exists(), (
            "render must validate the skills root BEFORE mkdir — no central dir may appear"
        )
        assert not (central / ".vibe-manifest.json").exists()

    def test_existing_central_content_untouched(
        self, tmp_path: Path, symlink_supported: bool
    ) -> None:
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")

        project_root = _seed_project(tmp_path)
        central_demo = tmp_path / "central" / "demo"
        central_demo.mkdir(parents=True)
        (central_demo / "SKILL.md").write_text(CENTRAL_CONTENT, encoding="utf-8")

        output_dir = project_root / ".pi"
        output_dir.mkdir(parents=True)
        (output_dir / "skills").symlink_to(central_demo.parent, target_is_directory=True)

        adapter = PiCodingAgentAdapter(project_root=project_root)
        result = adapter.render_config(_manifest(), output_dir)

        assert not result.success
        assert (central_demo / "SKILL.md").read_text(encoding="utf-8") == CENTRAL_CONTENT, (
            "render must not rewrite the central install through a symlinked skills root"
        )
        assert not (central_demo / ".vibe-manifest.json").exists(), (
            "ownership marker must not penetrate into the central install"
        )


class TestRenderPerSkillSymlinkPreserved:
    """Legal contract (D02): a pre-existing per-skill symlink into a central
    install with real content must survive the render — no central rewrite,
    no central marker, idempotent second render.
    """

    def test_per_skill_link_kept_and_central_untouched(
        self, tmp_path: Path, symlink_supported: bool
    ) -> None:
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")

        project_root = _seed_project(tmp_path)
        central_demo = tmp_path / "central" / "demo"
        central_demo.mkdir(parents=True)
        (central_demo / "SKILL.md").write_text(CENTRAL_CONTENT, encoding="utf-8")

        output_dir = project_root / ".pi"
        skill_dir = output_dir / "skills" / "demo"
        skill_dir.parent.mkdir(parents=True)
        skill_dir.symlink_to(central_demo, target_is_directory=True)

        adapter = PiCodingAgentAdapter(project_root=project_root)
        result = adapter.render_config(_manifest(), output_dir)

        assert result.success, f"render failed: {result.errors}"
        assert skill_dir.is_symlink(), "per-skill platform link must be preserved"
        assert skill_dir.resolve() == central_demo.resolve()
        assert (central_demo / "SKILL.md").read_text(encoding="utf-8") == CENTRAL_CONTENT
        assert not (central_demo / ".vibe-manifest.json").exists()

        # Second render is idempotent: same link, central install untouched.
        result2 = adapter.render_config(_manifest(), output_dir)
        assert result2.success, f"second render failed: {result2.errors}"
        assert skill_dir.is_symlink()
        assert (central_demo / "SKILL.md").read_text(encoding="utf-8") == CENTRAL_CONTENT
        assert not (central_demo / ".vibe-manifest.json").exists()


class TestRenderLegalPaths:
    """R3 regression + plain legal renders through the public entry point."""

    def test_legal_real_content_renders(self, tmp_path: Path) -> None:
        project_root = _seed_project(tmp_path)
        output_dir = project_root / ".pi"

        adapter = PiCodingAgentAdapter(project_root=project_root)
        result = adapter.render_config(_manifest(), output_dir)

        assert result.success, f"render failed: {result.errors}"
        rendered = output_dir / "skills" / "demo" / "SKILL.md"
        assert rendered.exists()
        # The render path wrote the real project content (not a stub).
        assert "PROJECT_ONLY_BODY" in rendered.read_text(encoding="utf-8")

    def test_legal_missing_source_fallback_renders(self, tmp_path: Path) -> None:
        """R3: fallback must accept the caller-threaded base_dir keyword and
        still produce the generated skill doc for a declared-but-unavailable
        skill (no project source, no central link)."""
        project_root = tmp_path / "proj"
        project_root.mkdir()
        output_dir = project_root / ".pi"

        adapter = PiCodingAgentAdapter(project_root=project_root)
        result = adapter.render_config(
            _manifest(skill_id="b1-unique-missing-source-20261009"), output_dir
        )

        assert result.success, f"fallback render failed: {result.errors}"
        rendered = output_dir / "skills" / "b1-unique-missing-source-20261009" / "SKILL.md"
        assert rendered.exists()
        content = rendered.read_text(encoding="utf-8")
        assert "b1-unique-missing-source-20261009" in content
