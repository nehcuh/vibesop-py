"""End-to-end test for third-party skill pack installation and routing.

This test verifies the complete lifecycle of a third-party skill pack:
1. Create a mock third-party skill pack as a local git repository
2. Install it via PackInstaller
3. Discover it via ExternalSkillLoader
4. Route queries to it via UnifiedRouter

This specifically validates that the dynamic namespace discovery in
CandidatePrefilter works for newly installed third-party packs,
eliminating the hardcoded NAMESPACE_KEYWORDS limitation.
"""

import subprocess
import tempfile
from pathlib import Path

from vibesop.core.routing.unified import UnifiedRouter
from vibesop.core.skills.external_loader import ExternalSkillLoader
from vibesop.installer.pack_installer import PackInstaller


class TestThirdPartySkillPack:
    """Test installing and routing to a third-party skill pack."""

    def _create_mock_git_repo(self, repo_dir: Path) -> None:
        """Initialize a git repo with a custom skill pack."""
        skill_dir = repo_dir / "skills" / "my-audit"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "id: my-audit\n"
            "name: My Audit\n"
            "description: Custom security audit workflow for third-party validation\n"
            "namespace: awesome-skills\n"
            "tags: [audit, security, custom]\n"
            "trigger_when: When user asks for a custom security audit\n"
            "---\n"
            "\n"
            "# My Audit Skill\n"
            "\n"
            "This is a custom third-party skill.\n"
        )

        (repo_dir / "README.md").write_text("# Awesome Skills\n\nA third-party skill pack.\n")

        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

    def test_install_and_route_third_party_pack(self) -> None:
        """Test that a third-party pack can be installed, discovered, and routed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_dir = tmpdir_path / "awesome-skills-repo"

            home_dir = tmpdir_path
            config_skills = home_dir / ".config" / "skills"
            config_skills.mkdir(parents=True)

            # 1. Create mock third-party git repository
            self._create_mock_git_repo(repo_dir)

            # 2. Install the pack to our isolated temp directory
            installer = PackInstaller(external_paths=[config_skills])
            success, msg = installer.install_pack(
                "awesome-skills",
                f"file://{repo_dir}",
            )
            assert success is True, f"Install failed: {msg}"

            # 3. Verify ExternalSkillLoader discovers the new skill
            loader = ExternalSkillLoader(external_paths=[config_skills])
            skills = loader.discover_all()
            skill_key = "awesome-skills/my-audit"
            assert skill_key in skills, (
                f"Skill '{skill_key}' not found. Discovered: {list(skills.keys())}"
            )

            skill = skills[skill_key]
            assert skill.base_metadata.namespace == "awesome-skills"
            assert skill.is_safe is True

            # 4. Verify UnifiedRouter can route queries to the third-party skill.
            # UnifiedRouter creates its own SkillLoader -> ExternalSkillLoader internally,
            # so we temporarily override the class-level EXTERNAL_PATHS to point to our
            # isolated temp directory. This ensures the router discovers the third-party
            # pack without polluting the real filesystem.
            project_root = Path(__file__).parent.parent.parent
            router = UnifiedRouter(project_root=project_root)

            original_paths = list(ExternalSkillLoader.EXTERNAL_PATHS)
            ExternalSkillLoader.EXTERNAL_PATHS = [config_skills]
            try:
                router.reload_candidates()
                result = router.route("run my custom security audit")
            finally:
                ExternalSkillLoader.EXTERNAL_PATHS = original_paths

            assert result.primary is not None, f"No routing match. Path: {result.routing_path}"
            assert result.primary.skill_id == "awesome-skills/my-audit", (
                f"Expected 'awesome-skills/my-audit', got {result.primary.skill_id}"
            )
            assert result.primary.source == "external"
