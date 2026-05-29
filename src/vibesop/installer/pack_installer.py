"""Skill pack installer for third-party skill packs."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, ClassVar

from rich.console import Console

from vibesop.constants import TRUSTED_PACKS
from vibesop.core.skills.storage import SkillStorage
from vibesop.installer.analyzer import RepoAnalyzer, parse_github_url
from vibesop.installer.planner import InstallPlanner
from vibesop.security import SkillSecurityAuditor

logger = logging.getLogger(__name__)
console = Console()


class PackInstaller:
    """Installer for skill packs from trusted names or Git URLs."""

    CENTRAL_STORAGE: ClassVar[Path] = Path.home() / ".config" / "skills"
    PLATFORM_PATHS: ClassVar[list[Path]] = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".config" / "opencode" / "skills",
        Path.home() / ".kimi" / "skills",
        Path.home() / ".config" / "cursor" / "skills",
    ]

    def __init__(
        self,
        external_paths: list[Path] | None = None,
        central_storage: Path | None = None,
        platform_paths: list[Path] | None = None,
        strict_mode: bool = True,
        project_root: str | Path | None = None,
    ):
        if external_paths is not None:
            self.central_storage = central_storage or external_paths[0]
            self.platform_paths = platform_paths or external_paths[1:]
        else:
            self.central_storage = central_storage or self.CENTRAL_STORAGE
            self.platform_paths = platform_paths or self.PLATFORM_PATHS.copy()

        self._strict_mode = strict_mode
        self._auditor = SkillSecurityAuditor(
            strict_mode=strict_mode,
            project_root=project_root or Path.cwd(),
        )
        self.central_storage.mkdir(parents=True, exist_ok=True)
        self._auditor.add_allowed_path(self.central_storage)
        for path in self.platform_paths:
            if path.exists():
                self._auditor.add_allowed_path(path)

    def install_skill_from_github(self, skill_id: str) -> tuple[bool, str]:
        try:
            return self.install_pack(
                skill_id.split("/", maxsplit=1)[0] if "/" in skill_id else skill_id
            )
        except Exception as e:
            return False, str(e)

    def install_pack(
        self,
        pack_name: str,
        pack_url: str | None = None,
        _version: str | None = None,
        platforms: list[str] | None = None,
    ) -> tuple[bool, str]:
        pack_url = pack_url or TRUSTED_PACKS.get(pack_name)
        if not pack_url:
            return False, f"Unknown pack: {pack_name}"

        analyzer = RepoAnalyzer()
        analysis = analyzer.analyze(pack_url, pack_name)

        if analysis.errors:
            return False, analysis.errors[0]

        if not analysis.skill_files:
            return False, f"No SKILL.md files found in {pack_name} repository"

        planner = InstallPlanner(base_target=self.central_storage)
        plan = planner.plan(analysis)

        try:
            target_path = plan.target_path

            if target_path.exists() and any(target_path.iterdir()):
                installed_skill_files = list(target_path.rglob("SKILL.md"))
                if installed_skill_files:
                    audit_results = self._audit_skills(installed_skill_files)
                    symlink_results = self._create_symlinks(pack_name, platforms)
                    msg = self._build_install_msg(
                        pack_name, installed_skill_files, audit_results,
                        symlink_results, already_installed=True,
                    )
                    self._rebuild_global_index(pack_name)
                    return True, msg

            target_path.mkdir(parents=True, exist_ok=True)

            repo_url, _ = parse_github_url(pack_url)
            clone_ok = analyzer.git_clone(repo_url, target_path)
            if not clone_ok:
                return False, f"Failed to clone {repo_url} to {target_path}"

            git_dir = target_path / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)

            build_output = self._run_post_install(target_path, analysis)

            installed_skill_files = list(target_path.rglob("SKILL.md"))
            audit_results = self._audit_skills(installed_skill_files)
            symlink_results = self._create_symlinks(pack_name, platforms)

            msg = self._build_install_msg(
                pack_name, installed_skill_files, audit_results,
                symlink_results, build_output=build_output,
            )
            self._rebuild_global_index(pack_name)
            return True, msg

        except Exception as e:
            return False, f"Failed to install {pack_name}: {e}"

    def _audit_skills(self, skill_files: list[Path]) -> list[str]:
        results = []
        for skill_file in skill_files:
            audit = self._auditor.audit_skill_file(skill_file)
            results.append(f"{skill_file.parent.name}: {'PASS' if audit.is_safe else 'WARN'}")
        return results

    def _build_install_msg(
        self,
        pack_name: str,
        skill_files: list[Path],
        audit_results: list[str],
        symlink_results: list[tuple[str, str]],
        already_installed: bool = False,
        build_output: str = "",
    ) -> str:
        parts: list[str] = []

        if already_installed:
            parts.append(f"Already installed: {pack_name} ({len(skill_files)} skills)")
        else:
            parts.append(f"Installed {pack_name} to {self.central_storage / pack_name}")
            parts.append(f"Skills found: {len(skill_files)}")

        if audit_results:
            parts.append(f"Audit: {', '.join(audit_results)}")
        if build_output:
            parts.append(f"Build: {build_output}")
        if symlink_results:
            parts.append("Symlinks:")
            for platform, status in symlink_results:
                icon = "✓" if status.startswith(("Linked", "Already")) else "✗"
                parts.append(f"  {icon} {platform}: {status}")

        return "\n".join(parts)

    def _run_post_install(self, target_path: Path, _analysis: object) -> str:
        """Run post-install build scripts for template-based skill packs."""
        import subprocess

        build_scripts = [".vibesop-build", "BUILD.sh", "setup.sh"]
        script_path: Path | None = next(
            (target_path / s for s in build_scripts if (target_path / s).exists()),
            None,
        )

        if script_path is None:
            if (target_path / "package.json").exists() and shutil.which("bun"):
                try:
                    result = subprocess.run(
                        ["bun", "run", "gen:skill-docs"],
                        cwd=target_path, capture_output=True, text=True, timeout=60, check=False,
                    )
                    if result.returncode == 0:
                        return "bun run gen:skill-docs OK"
                    return f"bun build failed: {result.stderr.strip()[:80]}"
                except (subprocess.TimeoutExpired, OSError) as e:
                    return f"bun build error: {e}"
            return ""

        script_path.chmod(0o755)
        try:
            result = subprocess.run(
                [str(script_path)],
                cwd=target_path, capture_output=True, text=True, timeout=120, check=False,
            )
            if result.returncode == 0:
                return f"{script_path.name} OK"
            return f"{script_path.name} failed: {result.stderr.strip()[:80]}"
        except (subprocess.TimeoutExpired, OSError) as e:
            return f"{script_path.name} error: {e}"

    def _create_symlinks(
        self,
        pack_name: str,
        platforms: list[str] | None = None,
    ) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        storage = SkillStorage()
        central_path = self.central_storage / pack_name

        if not central_path.exists():
            return results

        platforms_to_link = platforms or list(storage.PLATFORM_SKILLS_DIRS.keys())

        for platform in platforms_to_link:
            if platform not in storage.PLATFORM_SKILLS_DIRS:
                results.append((platform, "Unknown platform"))
                continue

            platform_dir = storage.PLATFORM_SKILLS_DIRS[platform]

            try:
                platform_dir.mkdir(parents=True, exist_ok=True)
                skill_count = self.create_skill_symlinks(
                    central_path, platform_dir, pack_name
                )
                results.append((platform, f"Linked to {platform} ({skill_count} skills)"))

            except OSError:
                try:
                    skill_count = self._copy_skill_dirs(
                        central_path, platform_dir, pack_name
                    )
                    results.append(
                        (platform, f"Copied to {platform} ({skill_count} skills, symlinks not supported)")
                    )
                except Exception as copy_err:
                    results.append((platform, f"Failed: {copy_err}"))

        return results

    @staticmethod
    def _flatten_skill_name(pack_name: str, rel_path: str) -> str:
        if str(rel_path) == ".":
            return pack_name
        return pack_name + "-" + str(rel_path).replace("/", "-")

    @staticmethod
    def _is_valid_skill(skill_file: Path) -> bool:
        """Check that a SKILL.md has a non-empty description."""
        try:
            content = skill_file.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return False
            parts = content.split("---", 2)
            if len(parts) < 3:
                return False
            import yaml as _yaml
            fm = _yaml.safe_load(parts[1])
            if not isinstance(fm, dict):
                return False
            desc = fm.get("description", "")
            return isinstance(desc, str) and len(desc.strip()) >= 10
        except Exception:
            return False

    def create_skill_symlinks(
        self,
        central_path: Path,
        platform_dir: Path,
        pack_name: str,
    ) -> int:
        count = 0
        for skill_file in central_path.rglob("SKILL.md"):
            if not self._is_valid_skill(skill_file):
                logger.warning("Skipping empty/invalid skill: %s", skill_file)
                continue
            skill_dir = skill_file.parent
            rel_path = skill_dir.relative_to(central_path)
            flat_name = self._flatten_skill_name(pack_name, str(rel_path))
            link_path = platform_dir / flat_name

            if link_path.exists():
                if link_path.is_symlink():
                    if link_path.resolve() == skill_dir.resolve():
                        count += 1
                        continue
                    link_path.unlink()
                elif link_path.is_dir():
                    shutil.rmtree(link_path)
                else:
                    link_path.unlink()

            link_path.symlink_to(skill_dir, target_is_directory=True)
            count += 1

        return count

    def _copy_skill_dirs(
        self,
        central_path: Path,
        platform_dir: Path,
        pack_name: str,
    ) -> int:
        count = 0
        for skill_file in central_path.rglob("SKILL.md"):
            if not self._is_valid_skill(skill_file):
                logger.warning("Skipping empty/invalid skill: %s", skill_file)
                continue
            skill_dir = skill_file.parent
            rel_path = skill_dir.relative_to(central_path)
            flat_name = self._flatten_skill_name(pack_name, str(rel_path))
            dest_path = platform_dir / flat_name

            if dest_path.exists():
                if dest_path.is_symlink() or dest_path.is_file():
                    dest_path.unlink()
                elif dest_path.is_dir():
                    shutil.rmtree(dest_path)

            shutil.copytree(skill_dir, dest_path)
            count += 1

        return count

    def _rebuild_global_index(self, pack_name: str) -> None:
        recovery_hint = "[dim]Run `vibe quickstart` to rebuild the index from scratch.[/dim]"
        try:
            from vibesop.core.skills.indexer import SkillIndexer
            from vibesop.llm.factory import create_provider

            def _llm_factory() -> Any:
                return create_provider()

            indexer = SkillIndexer(project_root=Path.home(), llm_factory=_llm_factory)
            result = indexer.update_global_index_for_pack(
                pack_name=pack_name, pack_storage=self.central_storage, show_progress=False,
            )
            if result.success:
                logger.info("Global index updated for pack %s: %d skills", pack_name, result.indexed_count)
            else:
                detail = "; ".join(result.errors) if result.errors else "unknown"
                logger.warning("Global index update for %s had issues: %s", pack_name, detail)
                console.print(f"\n[yellow]⚠ Index update for '{pack_name}' had issues:[/yellow] {detail}\n{recovery_hint}")
        except Exception as e:
            logger.warning("Global index update for %s failed (non-fatal): %s", pack_name, e)
            console.print(f"\n[yellow]⚠ Index update for '{pack_name}' failed:[/yellow] {e}\n{recovery_hint}")
