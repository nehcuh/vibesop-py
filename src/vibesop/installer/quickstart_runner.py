# pyright: reportMissingTypeArgument=false
"""Quickstart runner for interactive installation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from vibesop.installer.init_support import InitSupport
from vibesop.installer.installer import VibeSOPInstaller

console = Console()


@dataclass
class QuickstartConfig:
    platform: str
    install_integrations: bool | None
    install_hooks: bool | None
    project_path: Path
    global_install: bool


class QuickstartRunner:
    """Interactive quickstart wizard."""

    def __init__(self) -> None:
        self._supported_platforms = {
            p["name"]: p["description"] for p in VibeSOPInstaller().list_platforms()
        }

        from vibesop.core.skills.external_loader import ExternalSkillLoader

        self._available_integrations = {
            name: desc
            for name, desc in [
                ("superpowers", "General-purpose productivity skills"),
                ("omx", "oh-my-codex — autonomous agent skills"),
                ("mattpocock", "Matt Pocock's TypeScript/production skills"),
            ]
            if name in ExternalSkillLoader.TRUSTED_PACKS
        }

    def run(
        self,
        project_path: Path | None = None,
        platform: str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "config": None,
            "steps_completed": [],
            "errors": [],
        }

        try:
            console.print("╔════════════════════════════════════════════════════╗")
            console.print("║     VibeSOP Quickstart Wizard                      ║")
            console.print("╚════════════════════════════════════════════════════╝")
            console.print()

            if project_path is None:
                project_path = Path.cwd()
            else:
                project_path = project_path.expanduser().resolve()

            console.print(f"📁 Project Path: {project_path}")
            console.print()

            config = self._ask_install_type(project_path)
            result["config"] = config

            if platform:
                if platform not in self._supported_platforms:
                    msg = (
                        f"Unknown platform: {platform}. "
                        f"Supported: {', '.join(self._supported_platforms)}"
                    )
                    console.print(f"❌ {msg}")
                    result["errors"].append(msg)
                    return result
                config.platform = platform
            elif config.platform == "ask":
                config.platform = self._ask_platform()
            console.print()

            if config.install_integrations is None:
                config.install_integrations = self._ask_yes_no(
                    "Install skill pack integrations (superpowers, omx)?",
                    default=True,
                )
            console.print()

            if config.install_hooks is None:
                config.install_hooks = self._ask_yes_no("Install platform hooks?", default=True)
            console.print()

            self._show_summary(config)
            console.print()

            if not self._ask_yes_no("Proceed with installation?", default=True):
                console.print("Installation cancelled.")
                return result

            result["success"] = self._execute_installation(config)
            result["steps_completed"] = [
                "platform_selection",
                "integration_selection",
                "hook_selection",
            ]

            if result["success"]:
                console.print()
                console.print("✅ Installation complete!")
                console.print()
                self._run_route_demo(config)
                self._show_next_steps(config)

        except KeyboardInterrupt:
            console.print("\n\nInstallation cancelled by user.")
            result["errors"].append("User cancelled")
        except Exception as e:
            result["errors"].append(f"Setup failed: {e}")

        return result

    def _ask_install_type(self, project_path: Path) -> QuickstartConfig:
        console.print("What would you like to set up?")
        console.print("1. Global configuration for Claude Code/Grok Build/Kimi CLI/OpenCode/Pi")
        console.print("2. Project-specific configuration")
        console.print()

        choice = self._ask_choice("Choose installation type", options=["1", "2"], default="1")

        if choice == "1":
            return QuickstartConfig(
                platform="ask",
                # Third-party packs (superpowers/omx) are opt-in, not a default:
                # keep the default install license-clean and self-contained.
                install_integrations=False,
                install_hooks=True,
                project_path=Path.home(),
                global_install=True,
            )
        return QuickstartConfig(
            platform="ask",
            install_integrations=False,
            install_hooks=False,
            project_path=project_path,
            global_install=False,
        )

    def _ask_platform(self) -> str:
        console.print("Select your platform:")
        platforms = list(self._supported_platforms.keys())
        for i, (plat_id, plat_name) in enumerate(self._supported_platforms.items(), 1):
            console.print(f"{i}. {plat_id} - {plat_name}")

        console.print()
        choice = self._ask_choice(
            "Select platform",
            options=[str(i) for i in range(1, len(platforms) + 1)],
            default="1",
        )
        return platforms[int(choice) - 1]

    def _ask_yes_no(self, question: str, default: bool = False) -> bool:
        default_str = "Y/n" if default else "y/N"
        prompt = f"{question} [{default_str}]: "

        while True:
            response = input(prompt).strip().lower()
            if not response:
                return default
            if response in ("y", "yes"):
                return True
            if response in ("n", "no"):
                return False
            console.print("Please answer 'yes' or 'no'")

    def _ask_choice(self, question: str, options: list[str], default: str) -> str:
        prompt = f"{question} [{'/'.join(options)}]: "

        while True:
            response = input(prompt).strip()
            if not response:
                return default
            if response in options:
                return response
            console.print(f"Please choose one of: {'/'.join(options)}")

    def _show_summary(self, config: QuickstartConfig) -> None:
        platform_name = self._supported_platforms.get(config.platform, config.platform)
        console.print("┌─ Installation Summary ─────────────────────┐")
        console.print(f"│ Platform: {platform_name:<20} │")
        console.print(f"│ Type: {'Global' if config.global_install else 'Project':<20} │")
        console.print(f"│ Integrations: {'Yes' if config.install_integrations else 'No':<20} │")
        console.print(f"│ Hooks: {'Yes' if config.install_hooks else 'No':<20} │")
        console.print(f"│ Location: {config.project_path!s:<20} │")
        console.print("└──────────────────────────────────────────┘")

    def _execute_installation(self, config: QuickstartConfig) -> bool:
        try:
            from vibesop.installer.init_support import _ensure_global_config

            _ensure_global_config(config.platform, {"created_files": []})

            if not config.global_install:
                init_support = InitSupport()
                init_result = init_support.init_project(config.project_path, config.platform)
                if not init_result["success"]:
                    console.print(f"❌ Initialization failed: {init_result['errors']}")
                    return False
                console.print("✓ Project initialized")

            installer = VibeSOPInstaller()
            if config.global_install:
                install_target: Path | None = None
            else:
                install_target = config.project_path / ".vibe" / "dist" / config.platform
            install_result = installer.install(config.platform, install_target, force=False)

            if not install_result["success"]:
                console.print(f"❌ Configuration installation failed: {install_result['errors']}")
                return False
            console.print("✓ Configuration installed")

            if config.install_integrations:
                for integration in self._available_integrations:
                    self._install_integration(integration, config.platform)
                self._sync_platform_symlinks(config.platform)
            else:
                console.print("⊘ Integrations skipped")

            # installer.install() already deploys hooks (shell via HookInstaller,
            # JSON via the platform adapter). A second install() hits
            # _is_configured and reports zero hooks — "No hooks available"
            # even when claude-code/grok-build hooks were just written.
            if config.install_hooks:
                hooks_installed_list = install_result.get("hooks_installed") or []
                hooks_installed = (
                    len(hooks_installed_list)
                    if isinstance(hooks_installed_list, list)
                    else sum(1 for v in hooks_installed_list.values() if v)
                )
                total_hooks = len(hooks_installed_list)
                if hooks_installed > 0:
                    console.print(f"✓ Hooks installed: {hooks_installed}/{total_hooks}")
                else:
                    console.print("⊘ No hooks available for this platform")
            else:
                console.print("⊘ Hooks skipped")

            from vibesop.core.skills.indexer import SkillIndexer
            from vibesop.llm.factory import create_provider

            def _llm_factory() -> Any:
                return create_provider()

            indexer = SkillIndexer(project_root=config.project_path, llm_factory=_llm_factory)

            if config.global_install:
                console.print("\n[bold cyan]🔍 Building global skill index...[/bold cyan]")
                indexer.build_index(scope="global", show_progress=True)
            else:
                if not indexer.global_index_path.exists():
                    console.print("\n[bold cyan]🔍 Building global skill index...[/bold cyan]")
                    indexer.build_index(scope="global", show_progress=True)
                console.print("\n[bold cyan]🔍 Building project skill index...[/bold cyan]")
                indexer.build_index(scope="project", show_progress=True)

            return True

        except Exception as e:
            console.print(f"❌ Installation failed: {e}")
            return False

    def _install_integration(self, integration: str, _platform: str) -> None:
        try:
            from vibesop.installer.pack_installer import PackInstaller

            installer = PackInstaller()
            success, msg = installer.install_pack(integration)
            if success:
                console.print(f"[green]✓[/green] {integration} installed")
            else:
                console.print(f"[yellow]⊘[/yellow] {integration} installation failed: {msg}")
        except Exception as e:
            console.print(f"[yellow]⊘[/yellow] {integration} installation failed: {e}")

    def _sync_platform_symlinks(self, platform: str) -> None:
        from vibesop.core.skills.storage import SkillStorage
        from vibesop.installer.pack_installer import PackInstaller

        storage = SkillStorage()
        platform_dir = storage.PLATFORM_SKILLS_DIRS.get(platform)
        if not platform_dir:
            return

        platform_dir.mkdir(parents=True, exist_ok=True)

        installer = PackInstaller()
        total = 0
        for pack_name in self._available_integrations:
            central_path = Path.home() / ".config" / "skills" / pack_name
            if not central_path.exists():
                continue
            try:
                total += installer.create_skill_symlinks(central_path, platform_dir, pack_name)
            except OSError:
                try:
                    total += installer._copy_skill_dirs(central_path, platform_dir, pack_name)
                except Exception as copy_err:
                    console.print(
                        f"  [yellow]⊘[/yellow] {pack_name}: copy fallback failed: {copy_err}"
                    )

        if total > 0:
            console.print(f"  Synced {total} skill(s) to {platform}")

    def _run_route_demo(self, config: QuickstartConfig) -> None:
        """Keyless routing demo — first value moment before any configuration.

        LightweightRouter does keyword/scenario routing only (no LLM, no API
        key), so the demo works on a fresh install. Queries are verified
        against the builtin pool: slash-list and session-end both hit.
        """
        import contextlib
        import logging

        from vibesop.core.routing.lightweight_api import LightweightRouter

        console.print("[bold cyan]🧭 Routing demo (no API key required)[/bold cyan]")
        console.print("   Watch natural language match skills:\n")
        router = LightweightRouter(project_root=config.project_path)
        # The no-prompt_builder constructor warning targets LLM-triage callers;
        # this demo never reaches AI triage, so silence that one logger.
        unified_logger = logging.getLogger("vibesop.core.routing.unified")
        saved_level = unified_logger.level
        unified_logger.setLevel(logging.ERROR)
        try:
            for query in ("show me all the skills", "wrap up the session", "今天就到这里，收工"):
                try:
                    result = router.route(query)
                except Exception:
                    result = {}
                skill = result.get("skill_id") or ""
                confidence = result.get("confidence") or 0.0
                if skill and not skill.startswith("fallback"):
                    console.print(
                        f'   vibe route "{query}" → [green]{skill}[/green] ({confidence:.0%})'
                    )
                else:
                    console.print(f'   vibe route "{query}" → [yellow]no builtin match[/yellow]')
        finally:
            with contextlib.suppress(Exception):
                unified_logger.setLevel(saved_level)
        console.print()

    def _show_next_steps(self, config: QuickstartConfig) -> None:
        console.print("\n[bold]📚 Next Steps:[/bold]\n")

        platform_dirs = {
            "claude-code": "~/.claude",
            "kimi-cli": "~/.kimi-code",
            "opencode": "~/.config/opencode",
            "pi": "~/.pi/agent",
            "grok-build": "~/.grok",
        }

        if config.global_install:
            output_dir = platform_dirs.get(config.platform)
            if output_dir:
                console.print(
                    f"1. Run: [cyan]vibe build {config.platform} --output {output_dir}[/cyan]"
                )
            else:
                console.print(f"1. Run: [cyan]vibe build {config.platform}[/cyan]")
            console.print('2. Run: [cyan]vibe route "your query"[/cyan] to find skills')
            console.print("3. Run: [cyan]vibe skills list[/cyan] to see available skills")
            console.print(
                "4. Later, add community packs: [cyan]vibe install superpowers[/cyan]"
            )
        else:
            console.print("1. Review .vibe/ directory")
            console.print("2. Add skills to .vibe/skills/")
            console.print("3. Run: [cyan]vibe build[/cyan]")
            console.print('4. Run: [cyan]vibe route "your query"[/cyan] to test')

        console.print("\n[bold yellow]⚙️  LLM Configuration[/bold yellow]")
        console.print(
            "   Default config created at [cyan]~/.vibe/config.toml[/cyan] with Ollama as provider."
        )
        console.print("   Edit this file to switch provider (Anthropic, OpenAI, DeepSeek, etc.):")
        console.print()
        console.print("   [dim]  [llm][/dim]")
        console.print('   [dim]  provider = "anthropic"[/dim]')
        console.print('   [dim]  model = "claude-sonnet-4-6-20250514"[/dim]')
        console.print('   [dim]  api_key = "sk-..."[/dim]')

        console.print("\n[bold]📖 Documentation:[/bold]")
        console.print("   - Quick Start: README.md")
        console.print("   - Architecture: ARCHITECTURE.md")
        console.print("   - Contributing: CONTRIBUTING.md")
