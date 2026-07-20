"""Skill pack installer for third-party skill packs."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path
from typing import Any, ClassVar, Literal

from rich.console import Console
from rich.prompt import Confirm

from vibesop.constants import TRUSTED_PACKS
from vibesop.core.skills.storage import SkillStorage, write_copy_source_marker
from vibesop.installer.analyzer import RepoAnalyzer, parse_github_url
from vibesop.installer.planner import InstallPlanner
from vibesop.security import SkillSecurityAuditor
from vibesop.utils.helpers import safe_rmtree as _safe_rmtree
from vibesop.utils.pack_name import sanitize_pack_name

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
        sandbox_builds: bool = True,
        allow_unsafe_build: bool = False,
    ):
        if external_paths is not None:
            self.central_storage = central_storage or external_paths[0]
            self.platform_paths = platform_paths or external_paths[1:]
        else:
            self.central_storage = central_storage or self.CENTRAL_STORAGE
            self.platform_paths = platform_paths or self.PLATFORM_PATHS.copy()

        self._strict_mode = strict_mode
        self._sandbox_builds = sandbox_builds
        self._allow_unsafe_build = allow_unsafe_build
        # Project root anchors project-scope installs (``.vibe/skills/``) and
        # the auditor's allowed paths. Defaults to the current directory,
        # matching how the CLI commands resolve the "current project".
        self._project_root = (
            Path(project_root).resolve() if project_root is not None else Path.cwd()
        )
        self._auditor = SkillSecurityAuditor(
            strict_mode=strict_mode,
            project_root=self._project_root,
        )
        self.central_storage.mkdir(parents=True, exist_ok=True)
        self._auditor.add_allowed_path(self.central_storage)
        for path in self.platform_paths:
            if path.exists():
                self._auditor.add_allowed_path(path)

    @property
    def project_root(self) -> Path:
        """The project root anchoring project-scope installs (``.vibe/skills/``)."""
        return self._project_root

    @classmethod
    def compute_pack_hash(cls, pack_name: str, central_storage: Path | None = None) -> str:
        """Return the sha256 content hash of an installed pack, or ''."""
        sanitize_pack_name(pack_name)
        base = central_storage or cls.CENTRAL_STORAGE
        candidate = base / pack_name
        if candidate.exists() and candidate.is_dir():
            from vibesop.utils.marker_files import MarkerFileManager

            return MarkerFileManager().calculate_checksum(candidate)
        return ""

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
        upgrade: bool = False,
        scope: Literal["global", "project"] = "global",
    ) -> tuple[bool, str]:
        """Install a skill pack from a trusted name or Git URL.

        Args:
            scope: ``"global"`` installs to the central storage
                (``~/.config/skills/<pack>``) with platform symlinks and a
                global index rebuild. ``"project"`` installs to
                ``<project_root>/.vibe/skills/<pack>/`` — discovered by
                ``SkillLoader`` as project-level skills — and runs the exact
                same security chain (pre-install audit, F-02 pack-lock,
                F-03 build gate); only platform symlinks and the global index
                rebuild are skipped.
        """
        from datetime import UTC, datetime

        from vibesop.core.exceptions import PackIntegrityError
        from vibesop.core.skills.pack_lock import PackLock, PackLockStore
        from vibesop.installer.analyzer import capture_rev
        from vibesop.utils.marker_files import MarkerFileManager

        pack_url = pack_url or TRUSTED_PACKS.get(pack_name)
        if not pack_url:
            return False, f"Unknown pack: {pack_name}"

        analyzer = RepoAnalyzer()
        analysis = analyzer.analyze(pack_url, pack_name)

        if analysis.errors:
            return False, analysis.errors[0]

        if not analysis.skill_files:
            return False, f"No SKILL.md files found in {pack_name} repository"

        install_base = (
            self.central_storage if scope == "global" else self._project_root / ".vibe" / "skills"
        )
        planner = InstallPlanner(base_target=install_base)
        plan = planner.plan(analysis)

        try:
            target_path = plan.target_path

            if target_path.exists() and any(target_path.iterdir()):
                if upgrade:
                    # F-02: --upgrade re-clones to accept a changed pack.
                    _safe_rmtree(target_path)
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    installed_skill_files = list(target_path.rglob("SKILL.md"))
                    if installed_skill_files:
                        audit_results = self._audit_skills(
                            installed_skill_files, pack_name=pack_name
                        )
                        symlink_results = (
                            self._create_symlinks(pack_name, platforms) if scope == "global" else []
                        )
                        msg = self._build_install_msg(
                            pack_name,
                            installed_skill_files,
                            audit_results,
                            symlink_results,
                            already_installed=True,
                        )
                        if scope == "global":
                            self._rebuild_global_index(pack_name)
                        return True, msg

            target_path.mkdir(parents=True, exist_ok=True)

            repo_url, _ = parse_github_url(pack_url)
            clone_ok = analyzer.git_clone(repo_url, target_path)
            if not clone_ok:
                return False, f"Failed to clone {repo_url} to {target_path}"

            # F-02: capture the commit SHA BEFORE removing .git (rev-parse needs
            # the object database), then remove .git and compute a deterministic
            # content checksum of the checked-out tree. Verify against the prior
            # install's lock to reject force-pushes / tampered packs unless --upgrade.
            commit_sha = capture_rev(target_path)

            git_dir = target_path / ".git"
            if git_dir.exists():
                _safe_rmtree(git_dir)

            content_sha256 = MarkerFileManager().calculate_checksum(target_path)
            if not upgrade:
                existing = PackLockStore().get(pack_name)
                if existing is not None and (
                    existing.commit_sha != commit_sha or existing.content_sha256 != content_sha256
                ):
                    _safe_rmtree(target_path)
                    raise PackIntegrityError(
                        pack_name=pack_name,
                        old=existing.commit_sha[:8] or existing.content_sha256[:8],
                        new=commit_sha[:8] or content_sha256[:8],
                    )

            # Pre-install audit: scan ALL files (incl. BUILD.sh / setup.sh /
            # package.json scripts) BEFORE any build script is executed.
            # This closes the RCE where a malicious pack's BUILD.sh runs with
            # local privileges before the audit ever sees it.
            pre_audit = self._auditor.audit_pack_files(target_path, pack_name=pack_name)
            if pre_audit.has_critical:
                _safe_rmtree(target_path)
                return False, f"Pack rejected (pre-install CRITICAL): {pre_audit.summary}"
            if pre_audit.has_high:
                _safe_rmtree(target_path)
                return False, f"Pack rejected (HIGH risk, untrusted): {pre_audit.summary}"

            # Run build with sandbox preference. Falls back to local only when
            # no container runtime exists; otherwise runs in an isolated
            # --network=none container so the build script cannot exfiltrate.
            build_output = self._run_post_install(
                target_path,
                analysis,
                sandbox=self._sandbox_builds,
                allow_unsafe_build=self._allow_unsafe_build,
                pre_audit_summary=pre_audit.summary,
            )

            installed_skill_files = list(target_path.rglob("SKILL.md"))
            audit_results = self._audit_skills(
                installed_skill_files, pack_name=pack_name, pack_path=target_path
            )
            # Project-scope installs stay inside .vibe/skills/ (discovered by
            # SkillLoader directly) — no platform symlinks, no global index.
            symlink_results = (
                self._create_symlinks(pack_name, platforms) if scope == "global" else []
            )

            msg = self._build_install_msg(
                pack_name,
                installed_skill_files,
                audit_results,
                symlink_results,
                target_path=target_path,
                build_output=build_output,
                pre_audit_summary=pre_audit.summary,
                pre_audit_files=pre_audit.files_scanned,
            )
            if scope == "global":
                self._rebuild_global_index(pack_name)
            # F-02: record the lock so future installs verify against this commit.
            # Non-fatal — a lock-write failure degrades to "no lock" (next install
            # is treated as fresh), never undoes a successful install.
            try:
                PackLockStore().write(
                    PackLock(
                        pack_name=pack_name,
                        source_url=repo_url,
                        commit_sha=commit_sha,
                        content_sha256=content_sha256,
                        installed_at=datetime.now(UTC).isoformat(),
                    )
                )
            except OSError as e:
                logger.warning("Install succeeded but failed to write pack lock: %s", e)
            return True, msg

        except PackIntegrityError:
            raise  # F-02: propagate to the CLI (actionable, not a generic install error)
        except Exception as e:
            return False, f"Failed to install {pack_name}: {e}"

    def _audit_skills(
        self,
        skill_files: list[Path],
        pack_name: str | None = None,
        pack_path: Path | None = None,
    ) -> list[str]:
        results = []
        for skill_file in skill_files:
            audit = self._auditor.audit_skill_file(
                skill_file, pack_name=pack_name, pack_path=pack_path
            )
            results.append(f"{skill_file.parent.name}: {'PASS' if audit.is_safe else 'WARN'}")
        return results

    def _build_install_msg(
        self,
        pack_name: str,
        skill_files: list[Path],
        audit_results: list[str],
        symlink_results: list[tuple[str, str]],
        already_installed: bool = False,
        target_path: Path | None = None,
        build_output: str = "",
        pre_audit_summary: str | None = None,
        pre_audit_files: int = 0,
    ) -> str:
        parts: list[str] = []

        if already_installed:
            parts.append(f"Already installed: {pack_name} ({len(skill_files)} skills)")
        else:
            location = target_path or (self.central_storage / pack_name)
            parts.append(f"Installed {pack_name} to {location}")
            parts.append(f"Skills found: {len(skill_files)}")

        if pre_audit_summary is not None:
            parts.append(f"Pre-audit ({pre_audit_files} files): {pre_audit_summary}")
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

    def _run_post_install(
        self,
        target_path: Path,
        _analysis: object,
        *,
        sandbox: bool = False,
        allow_unsafe_build: bool | None = None,
        pre_audit_summary: str = "",
    ) -> str:
        """Run post-install build scripts for template-based skill packs.

        Args:
            target_path: Cloned pack root directory.
            _analysis: Reserved for future use (currently introspected for
                pack-level metadata).
            sandbox: When True, prefer running build inside an ephemeral
                ``--network=none`` container so the script cannot exfiltrate.
                Falls back to local execution only if ``allow_unsafe_build``
                is also True; otherwise the build is skipped with a notice.
            allow_unsafe_build: Explicit opt-in for local execution when no
                container runtime is available. If omitted, the instance's
                ``_allow_unsafe_build`` setting is used.
            pre_audit_summary: Human-readable summary from the pre-install
                security audit, shown during the interactive confirmation for
                local build fallback (F-03).
        """
        if allow_unsafe_build is None:
            allow_unsafe_build = self._allow_unsafe_build
        build_scripts = [".vibesop-build", "BUILD.sh", "setup.sh"]
        script_path: Path | None = next(
            (target_path / s for s in build_scripts if (target_path / s).exists()),
            None,
        )

        has_bun_fallback = (
            script_path is None
            and (target_path / "package.json").exists()
            and shutil.which("bun") is not None
        )
        if has_bun_fallback:
            logger.info(
                "No build script found, falling back to bun for %s "
                "(will execute gen:skill-docs from package.json)",
                target_path,
            )
        has_build = script_path is not None or has_bun_fallback

        if not has_build:
            return ""

        if sandbox:
            runtime = self._detect_container_runtime()
            if runtime is not None and script_path is not None:
                return self._run_build_in_container(target_path, script_path, runtime)
            # No container runtime available: fall through to the local-execution
            # gate below (same path as sandbox=False with allow_unsafe_build=True).

        if not allow_unsafe_build:
            return (
                "BUILD skipped (no container runtime available; "
                "pass allow_unsafe_build=True to override)"
            )

        # F-03: local build execution is an explicitly opted-in escape hatch.
        # Require an interactive TTY, disclose the audit summary + script content,
        # and obtain explicit user confirmation. Non-interactive contexts fail-closed
        # so CI/automation cannot be tricked into executing fetched, unsigned scripts.
        if not sys.stdin.isatty():
            return (
                "BUILD skipped (allow_unsafe_build=True but no interactive "
                "TTY available; local execution of fetched scripts is "
                "disabled in non-interactive contexts)"
            )
        if not self._confirm_unsafe_build(target_path, script_path, pre_audit_summary):
            return "BUILD skipped (user declined local execution)"

        return self._run_build_local(target_path, script_path)

    @staticmethod
    def _detect_container_runtime() -> str | None:
        """Return the first available container runtime, or None.

        Order matches prompt_chain/validator.py convention so the two
        sandboxes share detection logic.
        """
        for tool in ("orbstack", "docker", "lima"):
            if shutil.which(tool):
                return tool
        return None

    @staticmethod
    def _run_build_in_container(
        target_path: Path,
        script_path: Path,
        runtime: str,  # noqa: ARG004  # passed by callers; runtime_bin fixed (dead-ternary collapsed)
    ) -> str:
        """Run a build script in an ephemeral, network-blocked container.

        Security properties:
        - ``--network=none`` blocks egress even if the script tries curl|sh.
        - ``--read-only`` mount of the source tree: the script can read its
          own files but cannot persist backdoors into the pack directory.
        - 60s timeout, 512 MB memory cap, 0.5 CPU: contains runaway builds.
        """
        import subprocess

        # Reject symlinks that escape the pack directory, matching the local
        # execution gate in ``_confirm_unsafe_build``.
        try:
            script_path.resolve().relative_to(target_path.resolve())
        except ValueError:
            return f"{script_path.name} blocked: resolves outside the pack directory"

        image = "ubuntu:22.04"
        # All three supported runtimes accept the docker-CLI shape for our
        # purposes (orbstack via docker-compat, lima via its docker wrapper).
        # We use the docker CLI regardless and let the runtime shim translate.
        runtime_bin = "docker"
        cmd = [
            runtime_bin,
            "run",
            "--rm",
            "-v",
            f"{target_path}:/work:ro",
            "-w",
            "/work",
            "--network",
            "none",
            "--memory",
            "512m",
            "--cpus",
            "0.5",
            image,
            "/bin/sh",
            script_path.name,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            return f"{script_path.name} sandbox error: {e}"

        if result.returncode == 0:
            return f"{script_path.name} OK (sandboxed, network blocked)"
        return f"{script_path.name} blocked/failed in sandbox: {result.stderr.strip()[:80]}"

    @staticmethod
    def _confirm_unsafe_build(
        target_path: Path,
        script_path: Path | None,
        pre_audit_summary: str,
    ) -> bool:
        """Interactive confirmation before locally executing a fetched build script.

        Returns True only when the user explicitly confirms after seeing the
        audit summary and the script content (F-03).
        """
        console.print("\n[bold yellow]⚠ Security warning[/bold yellow]")
        console.print(
            "No container runtime was found and [bold]allow_unsafe_build=True[/bold] "
            "was requested. VibeSOP is about to execute a fetched, unsigned build "
            "script on this machine with your user privileges."
        )
        console.print(f"Pack directory: {target_path}", markup=False)
        if pre_audit_summary:
            console.print(f"Pre-install audit: {pre_audit_summary}", markup=False)
        if script_path is not None:
            # Reject symlinks that escape the pack directory — they could point
            # to arbitrary sensitive files on disk.
            try:
                script_path.resolve().relative_to(target_path.resolve())
            except ValueError:
                console.print(
                    "[red]Build script resolves outside the pack directory; "
                    "refusing to display or execute it.[/red]"
                )
                return False
            console.print(f"\nScript to execute: {script_path}", markup=False)
            try:
                content = script_path.read_text(encoding="utf-8", errors="replace")
                console.print("\n[dim]--- script start ---[/dim]")
                console.print(content, markup=False)
                console.print("[dim]--- script end ---[/dim]\n")
            except OSError as e:
                console.print(f"[dim]Could not read script content: {e}[/dim]\n")
        return Confirm.ask(
            "Do you want to execute this script locally?",
            default=False,
        )

    @staticmethod
    def _run_build_local(
        target_path: Path,
        script_path: Path | None,
    ) -> str:
        """Legacy local execution path. Retained as opt-in fallback."""
        import subprocess

        if script_path is None:
            # Bun fallback for template-based packs without a shell script.
            if (target_path / "package.json").exists() and shutil.which("bun"):
                try:
                    result = subprocess.run(
                        ["bun", "run", "gen:skill-docs"],
                        cwd=target_path,
                        capture_output=True,
                        text=True,
                        timeout=60,
                        check=False,
                    )
                    if result.returncode == 0:
                        return "bun run gen:skill-docs OK"
                    return f"bun build failed: {result.stderr.strip()[:80]}"
                except (subprocess.TimeoutExpired, OSError) as e:
                    return f"bun build error: {e}"
            return ""

        # Reject symlinks that escape the pack directory before mutating or
        # executing the script.
        try:
            script_path.resolve().relative_to(Path(target_path).resolve())
        except ValueError:
            return f"{script_path.name} blocked (resolves outside pack directory)"
        script_path.chmod(0o755)
        try:
            result = subprocess.run(
                [str(script_path)],
                cwd=target_path,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
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
        safe_name = sanitize_pack_name(pack_name)
        central_path = self.central_storage / safe_name

        if not central_path.exists():
            return results

        platforms_to_link = platforms or list(storage.PLATFORM_SKILLS_DIRS.keys())

        for platform in platforms_to_link:
            if platform not in storage.PLATFORM_SKILLS_DIRS:
                results.append((platform, "Unknown platform"))
                continue

            platform_dir = storage.PLATFORM_SKILLS_DIRS[platform]

            from vibesop.utils.symlinks import can_create_dir_symlink

            if not can_create_dir_symlink(platform_dir):
                logger.info(
                    "symlinks unsupported under %s, copying %s instead",
                    platform_dir,
                    safe_name,
                )
            else:
                try:
                    platform_dir.mkdir(parents=True, exist_ok=True)
                    skill_count = self.create_skill_symlinks(central_path, platform_dir, safe_name)
                    results.append((platform, f"Linked to {platform} ({skill_count} skills)"))
                    continue
                except OSError as e:
                    logger.info(
                        "symlink creation failed for %s, falling back to copy: %s",
                        platform,
                        e,
                    )

            try:
                skill_count = self._copy_skill_dirs(central_path, platform_dir, safe_name)
                results.append(
                    (
                        platform,
                        f"Copied to {platform} ({skill_count} skills, symlinks not supported)",
                    )
                )
            except Exception as copy_err:
                results.append((platform, f"Failed: {copy_err}"))

        return results

    @staticmethod
    def _flatten_skill_name(pack_name: str, rel_path: str) -> str:
        if str(rel_path) == ".":
            return pack_name
        # rel_path comes from Path.relative_to() — native separators, i.e.
        # backslashes on Windows. Normalize before flattening, otherwise the
        # "flat" name still contains path segments and symlink/copy targets
        # end up in non-existent nested directories (WinError 3).
        return pack_name + "-" + str(rel_path).replace("\\", "/").replace("/", "-")

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

    @staticmethod
    def _parse_skill_name(skill_file: Path) -> str | None:
        """Extract the frontmatter ``name:`` of a SKILL.md.

        Returns ``None`` if the file has no frontmatter, no ``name`` key, or
        the value is not a non-empty string.
        """
        try:
            content = skill_file.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None
            import yaml as _yaml

            fm = _yaml.safe_load(parts[1])
            if not isinstance(fm, dict):
                return None
            name = fm.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
            return None
        except Exception:
            return None

    def _collect_existing_skill_names(self, platform_dir: Path) -> dict[str, Path]:
        """Map existing skill ``name:`` → symlink path in ``platform_dir``.

        Walks existing entries (typically symlinks from prior installs) and
        reads each target's SKILL.md frontmatter. Used to skip cross-pack
        duplicates that point to the same logical skill.
        """
        seen: dict[str, Path] = {}
        if not platform_dir.exists():
            return seen
        for entry in platform_dir.iterdir():
            try:
                if entry.is_symlink():
                    target = entry.resolve()
                elif entry.is_dir():
                    target = entry
                else:
                    continue
                skill_md = target / "SKILL.md"
                if not skill_md.is_file():
                    continue
                name = self._parse_skill_name(skill_md)
                if name and name not in seen:
                    seen[name] = entry
            except OSError:
                continue
        return seen

    def create_skill_symlinks(
        self,
        central_path: Path,
        platform_dir: Path,
        pack_name: str,
        dedupe_by_name: bool = True,
    ) -> int:
        count = 0
        existing_names: dict[str, Path] = (
            self._collect_existing_skill_names(platform_dir) if dedupe_by_name else {}
        )
        for skill_file in central_path.rglob("SKILL.md"):
            if not self._is_valid_skill(skill_file):
                logger.warning("Skipping empty/invalid skill: %s", skill_file)
                continue
            skill_dir = skill_file.parent
            rel_path = skill_dir.relative_to(central_path)
            flat_name = self._flatten_skill_name(pack_name, str(rel_path))
            link_path = platform_dir / flat_name

            if dedupe_by_name:
                skill_name = self._parse_skill_name(skill_file)
                if skill_name and skill_name in existing_names:
                    logger.info(
                        "Skipping duplicate skill %s (name=%r already at %s)",
                        skill_file,
                        skill_name,
                        existing_names[skill_name],
                    )
                    continue

            if link_path.exists():
                if link_path.is_symlink():
                    if link_path.resolve() == skill_dir.resolve():
                        count += 1
                        continue
                    link_path.unlink()
                elif link_path.is_dir():
                    _safe_rmtree(link_path)
                else:
                    link_path.unlink()

            link_path.symlink_to(skill_dir, target_is_directory=True)
            if dedupe_by_name:
                skill_name = self._parse_skill_name(skill_file)
                if skill_name and skill_name not in existing_names:
                    existing_names[skill_name] = link_path
            count += 1

        return count

    def _copy_skill_dirs(
        self,
        central_path: Path,
        platform_dir: Path,
        pack_name: str,
        dedupe_by_name: bool = True,
    ) -> int:
        count = 0
        existing_names: dict[str, Path] = (
            self._collect_existing_skill_names(platform_dir) if dedupe_by_name else {}
        )
        for skill_file in central_path.rglob("SKILL.md"):
            if not self._is_valid_skill(skill_file):
                logger.warning("Skipping empty/invalid skill: %s", skill_file)
                continue
            skill_dir = skill_file.parent
            rel_path = skill_dir.relative_to(central_path)
            flat_name = self._flatten_skill_name(pack_name, str(rel_path))
            dest_path = platform_dir / flat_name

            if dedupe_by_name:
                skill_name = self._parse_skill_name(skill_file)
                if skill_name and skill_name in existing_names:
                    logger.info(
                        "Skipping duplicate skill %s (name=%r already at %s)",
                        skill_file,
                        skill_name,
                        existing_names[skill_name],
                    )
                    continue

            if dest_path.exists():
                if dest_path.is_symlink() or dest_path.is_file():
                    dest_path.unlink()
                elif dest_path.is_dir():
                    _safe_rmtree(dest_path)

            shutil.copytree(skill_dir, dest_path)
            write_copy_source_marker(dest_path, skill_dir)
            if dedupe_by_name:
                skill_name = self._parse_skill_name(skill_file)
                if skill_name and skill_name not in existing_names:
                    existing_names[skill_name] = dest_path
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
                pack_name=pack_name,
                pack_storage=self.central_storage,
                show_progress=False,
            )
            if result.success:
                logger.info(
                    "Global index updated for pack %s: %d skills", pack_name, result.indexed_count
                )
            else:
                detail = "; ".join(result.errors) if result.errors else "unknown"
                logger.warning("Global index update for %s had issues: %s", pack_name, detail)
                console.print(
                    f"\n[yellow]⚠ Index update for '{pack_name}' had issues:[/yellow] {detail}\n{recovery_hint}"
                )
        except Exception as e:
            logger.warning("Global index update for %s failed (non-fatal): %s", pack_name, e)
            console.print(
                f"\n[yellow]⚠ Index update for '{pack_name}' failed:[/yellow] {e}\n{recovery_hint}"
            )
