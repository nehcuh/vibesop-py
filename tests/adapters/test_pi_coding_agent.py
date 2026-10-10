"""Tests for PiCodingAgentAdapter skill render boundary (B1 corrective).

Real public ``render_config`` counterexamples (no mocked render/content
lookups): a symlinked skills ROOT must be refused before any mkdir touches
the central install; a legal per-skill symlink must keep its
skip-central-rewrite contract; a legal missing-source fallback must render
(R3 signature contract).
"""

import os
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


class TestRenderCopyFallbackWithoutSymlinkCapability:
    """W1 (Windows qualification): public ``render_config`` with the symlink
    capability probe forced False (unprivileged Windows) must take the REAL
    product copy fallback — actual directory (never a link), provenance and
    ownership markers, flattened name boundary, central source untouched,
    idempotent re-render.

    Honest boundary: capability=False lane only; it does NOT replace the
    malicious-symlink refusals above (those stay gated on
    ``symlink_supported`` because they need real symlinks).
    """

    def test_copy_fallback_real_dir_and_central_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json

        monkeypatch.setattr("vibesop.utils.symlinks.can_create_dir_symlink", lambda _: False)

        skill_id = "w1glm-20261009/demo"
        central_demo = tmp_path / "central" / "demo"
        central_demo.mkdir(parents=True)
        (central_demo / "SKILL.md").write_text(CENTRAL_CONTENT, encoding="utf-8")

        project_root = tmp_path / "proj"
        project_root.mkdir()
        output_dir = project_root / ".pi"

        manifest = Manifest(
            metadata=ManifestMetadata(platform="pi"),
            skills=[
                SkillSpec(
                    id=skill_id,
                    name="Demo",
                    description="Demo skill",
                    trigger_when="testing",
                    metadata={"source_path": str(central_demo)},
                )
            ],
        )
        adapter = PiCodingAgentAdapter(project_root=project_root)
        result = adapter.render_config(manifest, output_dir)

        assert result.success, f"copy-fallback render failed: {result.errors}"
        skill_dir = output_dir / "skills" / "w1glm-20261009-demo"

        assert skill_dir.is_dir()
        assert not skill_dir.is_symlink()
        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == CENTRAL_CONTENT

        copy_marker = skill_dir / ".vibe-copy-source"
        assert copy_marker.is_file()
        assert Path(copy_marker.read_text(encoding="utf-8").strip()) == central_demo.resolve()
        owner = json.loads((skill_dir / ".vibe-manifest.json").read_text(encoding="utf-8"))
        assert owner["id"] == skill_id
        assert owner["source"]["type"] == "pack-copy"

        # Name boundary: exactly the flattened dir, no nested namespace dir.
        assert sorted(p.name for p in (output_dir / "skills").iterdir()) == [skill_dir.name]

        assert (central_demo / "SKILL.md").read_text(encoding="utf-8") == CENTRAL_CONTENT
        assert not (central_demo / ".vibe-manifest.json").exists()

        result2 = adapter.render_config(manifest, output_dir)
        assert result2.success, f"second render failed: {result2.errors}"
        assert skill_dir.is_dir()
        assert not skill_dir.is_symlink()
        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == CENTRAL_CONTENT
        assert (central_demo / "SKILL.md").read_text(encoding="utf-8") == CENTRAL_CONTENT
        assert not (central_demo / ".vibe-manifest.json").exists()


class TestNamespaceRewriteThroughPerSkillLink:
    """M1: the pi namespace rewrite through a legal per-skill dir symlink must
    materialize a private copy of the ENTIRE central skill dir (auxiliary
    pack files included), rewrite the name in the copy, and leave the central
    install untouched. Writing only SKILL.md silently drops references/ and
    scripts/ from the platform tree.
    """

    def test_namespaced_copy_keeps_auxiliary_files(
        self, tmp_path: Path, symlink_supported: bool
    ) -> None:
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")

        skill_id = "nspack-20261010/demo"
        central_skill = tmp_path / "central" / "demo"
        (central_skill / "references").mkdir(parents=True)
        (central_skill / "SKILL.md").write_text(
            "---\nname: demo\ndescription: Central pack skill\n---\n# Pack Demo\n",
            encoding="utf-8",
        )
        (central_skill / "references" / "ref.md").write_text(
            "AUXILIARY_REFERENCE\n", encoding="utf-8"
        )

        project_root = tmp_path / "proj"
        project_root.mkdir()
        output_dir = project_root / ".pi"
        skill_dir = output_dir / "skills" / "nspack-20261010-demo"
        skill_dir.parent.mkdir(parents=True)
        skill_dir.symlink_to(central_skill, target_is_directory=True)

        manifest = Manifest(
            metadata=ManifestMetadata(platform="pi"),
            skills=[
                SkillSpec(
                    id=skill_id,
                    name="Demo",
                    description="Demo skill",
                    trigger_when="testing",
                    metadata={"source_path": str(central_skill)},
                )
            ],
        )
        adapter = PiCodingAgentAdapter(project_root=project_root)
        result = adapter.render_config(manifest, output_dir)

        assert result.success, f"namespaced render failed: {result.errors}"
        assert skill_dir.is_dir() and not skill_dir.is_symlink(), (
            "the link must be replaced by a private real directory"
        )
        assert (skill_dir / "references" / "ref.md").read_text(encoding="utf-8") == (
            "AUXILIARY_REFERENCE\n"
        ), "auxiliary pack files must survive the namespaced copy"
        rendered = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "name: nspack-20261010-demo" in rendered
        assert (central_skill / "SKILL.md").read_text(encoding="utf-8") == (
            "---\nname: demo\ndescription: Central pack skill\n---\n# Pack Demo\n"
        ), "central install content must stay untouched"


class TestFallbackKeepsLegalPerSkillLink:
    """L1: the no-content fallback must keep a pre-existing legal per-skill
    symlink (same skip-rewrite semantics as the main render path) instead of
    tripping the write-time leaf-link refusal and aborting the render."""

    def test_fallback_preserves_legal_leaf_link(
        self, tmp_path: Path, symlink_supported: bool
    ) -> None:
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")

        central_demo = tmp_path / "central" / "demo"
        central_demo.mkdir(parents=True)
        (central_demo / "SKILL.md").write_text(CENTRAL_CONTENT, encoding="utf-8")

        project_root = tmp_path / "proj"
        project_root.mkdir()
        output_dir = project_root / ".pi"
        skill_dir = output_dir / "skills" / "l1lone-20261010"
        skill_dir.parent.mkdir(parents=True)
        skill_dir.symlink_to(central_demo, target_is_directory=True)

        adapter = PiCodingAgentAdapter(project_root=project_root)
        result = adapter.render_config(_manifest(skill_id="l1lone-20261010"), output_dir)

        assert result.success, f"fallback render must keep the legal link: {result.errors}"
        assert skill_dir.is_symlink(), "legal per-skill link must be preserved"
        assert (central_demo / "SKILL.md").read_text(encoding="utf-8") == CENTRAL_CONTENT


class TestNamespaceRewriteRollback:
    """M1 round-2: a failed staged copy must leave the original legal link
    intact and remove the staging dir; a successful swap leaves a 0755 dir."""

    def _stage_namespaced_link(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        central_skill = tmp_path / "central" / "demo"
        central_skill.mkdir(parents=True)
        (central_skill / "SKILL.md").write_text(
            "---\nname: demo\ndescription: Central pack skill\n---\n# Pack Demo\n",
            encoding="utf-8",
        )
        output_dir = tmp_path / "proj" / ".pi"
        skill_dir = output_dir / "skills" / "nspack-rb-demo"
        skill_dir.parent.mkdir(parents=True)
        skill_dir.symlink_to(central_skill, target_is_directory=True)
        return skill_dir, central_skill, output_dir

    def test_failed_copy_preserves_original_link(
        self, tmp_path: Path, symlink_supported: bool, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")

        skill_dir, central_skill, output_dir = self._stage_namespaced_link(tmp_path)
        adapter = PiCodingAgentAdapter(project_root=tmp_path / "proj")
        skill = SkillSpec(
            id="nspack-rb/demo",
            name="Demo",
            description="Demo skill",
            trigger_when="testing",
        )

        def _boom(*args, **kwargs):
            raise OSError("simulated copy failure")

        monkeypatch.setattr("vibesop.adapters.pi_coding_agent.shutil.copytree", _boom)
        with pytest.raises(OSError, match="simulated copy failure"):
            adapter._namespace_skill_name(skill, skill_dir, base_dir=output_dir)

        assert skill_dir.is_symlink(), "failed copy must leave the original link intact"
        assert skill_dir.resolve() == central_skill.resolve()
        leftovers = [
            p for p in skill_dir.parent.iterdir() if p.name.startswith(".nspack-rb-demo.copy-")
        ]
        assert leftovers == [], f"staging dir must be cleaned on failure: {leftovers}"

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission semantics")
    def test_successful_swap_leaves_0755_dir(self, tmp_path: Path, symlink_supported: bool) -> None:
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        import stat as stat_mod

        skill_dir, _central_skill, output_dir = self._stage_namespaced_link(tmp_path)
        adapter = PiCodingAgentAdapter(project_root=tmp_path / "proj")
        skill = SkillSpec(
            id="nspack-rb/demo",
            name="Demo",
            description="Demo skill",
            trigger_when="testing",
        )

        adapter._namespace_skill_name(skill, skill_dir, base_dir=output_dir)

        assert skill_dir.is_dir() and not skill_dir.is_symlink()
        mode = stat_mod.S_IMODE(skill_dir.stat().st_mode)
        assert mode == 0o755, f"mkdtemp's 0700 must not leak into the render tree: {oct(mode)}"
