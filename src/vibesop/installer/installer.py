"""VibeSOP configuration installer."""

import shutil
from pathlib import Path
from typing import Any


class VibeSOPInstaller:
    """Installs VibeSOP configurations for different platforms."""

    def __init__(self) -> None:
        self._platforms: dict[str, dict[str, Any]] = {
            "claude-code": {
                "config_dir": Path.home() / ".claude",
                "description": "Claude Code CLI",
            },
            "kimi-cli": {
                "config_dir": Path.home() / ".kimi-code",
                "description": "Kimi Code CLI",
            },
            "opencode": {
                "config_dir": Path.home() / ".config" / "opencode",
                "description": "OpenCode CLI",
            },
            "pi": {
                "config_dir": Path.home() / ".pi" / "agent",
                "description": "Pi Coding Agent",
            },
        }

    def install(
        self,
        platform: str,
        config_dir: Path | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "platform": platform,
            "config_dir": None,
            "files_created": [],
            "errors": [],
            "warnings": [],
        }

        try:
            if platform not in self._platforms:
                result["errors"].append(f"Unknown platform: {platform}")
                return result

            target_dir = (
                config_dir if config_dir is not None else self._platforms[platform]["config_dir"]
            ).expanduser()
            result["config_dir"] = str(target_dir)

            if not force and self._is_configured(target_dir):
                result["warnings"].append(
                    f"Configuration already exists in {target_dir}. Use --force to overwrite."
                )
                result["success"] = True
                return result

            from vibesop.builder import ConfigRenderer, QuickBuilder
            from vibesop.core.skills import SkillStorage
            from vibesop.hooks import HookInstaller

            manifest = QuickBuilder.default(platform=platform)

            renderer = ConfigRenderer(project_root=self._get_project_root())
            render_result = renderer.render_config_only(manifest, target_dir)

            if not render_result.success:
                result["errors"].extend(render_result.errors)
                return result

            result["files_created"] = [str(f) for f in render_result.files_created]

            storage = SkillStorage()
            installed, linked, messages = storage.sync_project_skills(
                project_root=self._get_project_root(),
                platform=platform,
                force=force,
            )
            result["skills_installed"] = installed
            result["skills_linked"] = linked
            result["skill_messages"] = messages

            hook_installer = HookInstaller()
            hook_results = hook_installer.install_hooks(platform, target_dir)

            installed_hooks = [name for name, status in hook_results.items() if status]
            failed_hooks = [name for name, status in hook_results.items() if not status]

            if installed_hooks:
                result["hooks_installed"] = installed_hooks
            if failed_hooks:
                result["warnings"].append(f"Failed to install hooks: {', '.join(failed_hooks)}")

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Installation failed: {e}")

        return result

    def uninstall(
        self,
        platform: str,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "platform": platform,
            "files_removed": [],
            "errors": [],
        }

        try:
            if platform not in self._platforms:
                result["errors"].append(f"Unknown platform: {platform}")
                return result

            target_dir = (
                config_dir if config_dir is not None else self._platforms[platform]["config_dir"]
            ).expanduser()

            from vibesop.hooks import HookInstaller

            hook_installer = HookInstaller()
            hook_installer.uninstall_hooks(platform, target_dir)

            if not target_dir.exists():
                result["errors"].append(f"Configuration directory not found: {target_dir}")
                return result

            for file_path in [
                target_dir / "CLAUDE.md",
                target_dir / "config.toml",
                target_dir / "config.yaml",
                target_dir / "settings.json",
                target_dir / "rules",
                target_dir / "docs",
                target_dir / "hooks",
            ]:
                if file_path.exists():
                    if file_path.is_dir():
                        shutil.rmtree(file_path)
                    else:
                        file_path.unlink()
                    result["files_removed"].append(str(file_path))

            result["success"] = True

        except Exception as e:
            result["errors"].append(f"Uninstallation failed: {e}")

        return result

    def verify(
        self,
        platform: str,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "platform": platform,
            "installed": False,
            "config_valid": False,
            "hooks_installed": {},
            "issues": [],
        }

        try:
            target_dir: Path | None = None
            if config_dir is None:
                platform_info = self._platforms.get(platform)
                if platform_info is not None:
                    target_dir = platform_info.get("config_dir")
            else:
                target_dir = config_dir

            if not target_dir:
                result["issues"].append(f"Unknown platform: {platform}")
                return result

            target_dir = target_dir.expanduser()

            if not self._is_configured(target_dir):
                result["issues"].append(f"Not configured in {target_dir}")
                return result

            result["installed"] = True

            result["issues"].extend(self._verify_config_files(platform, target_dir))
            result["config_valid"] = len(result["issues"]) == 0

            from vibesop.hooks import HookInstaller

            hook_installer = HookInstaller()
            result["hooks_installed"] = hook_installer.verify_hooks(platform, target_dir)

        except Exception as e:
            result["issues"].append(f"Verification failed: {e}")

        return result

    def list_platforms(self) -> list[dict[str, str]]:
        return [
            {"name": name, "description": cfg["description"], "config_dir": str(cfg["config_dir"])}
            for name, cfg in self._platforms.items()
        ]

    def _get_project_root(self) -> Path:
        current = Path.cwd()
        for path in [current, current / "src", Path(__file__).parent.parent.parent]:
            if (path / "core" / "skills").exists():
                return path.resolve()
        return Path().resolve()

    def _is_configured(self, config_dir: Path) -> bool:
        if not config_dir.exists():
            return False
        return any(
            f.exists()
            for f in [
                config_dir / "CLAUDE.md",
                config_dir / "config.yaml",
                config_dir / "settings.json",
                config_dir / "config.toml",
            ]
        )

    def _verify_config_files(self, platform: str, config_dir: Path) -> list[str]:
        issues: list[str] = []

        if platform == "claude-code":
            claude_md = config_dir / "CLAUDE.md"
            if not claude_md.exists():
                issues.append("CLAUDE.md not found")
            elif (
                "# VibeSOP" not in claude_md.read_text()
                and "## VibeSOP" not in claude_md.read_text()
            ):
                issues.append("CLAUDE.md missing VibeSOP configuration")
        elif platform == "kimi-cli":
            if not (config_dir / "config.toml").exists():
                issues.append("config.toml not found")
        elif platform == "opencode":
            if not (config_dir / "config.yaml").exists():
                issues.append("config.yaml not found")
        elif platform == "pi":
            if not (config_dir / "AGENTS.md").exists():
                issues.append("AGENTS.md not found")

        return issues
