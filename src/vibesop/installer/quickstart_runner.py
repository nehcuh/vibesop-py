# pyright: reportMissingTypeArgument=false
"""Quickstart runner for interactive installation.

This module provides an interactive wizard for setting up
VibeSOP configuration.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from vibesop.installer.init_support import InitSupport
from vibesop.installer.installer import VibeSOPInstaller

console = Console()


@dataclass
class QuickstartConfig:
    """Configuration from quickstart wizard.

    Attributes:
        platform: Selected platform
        install_integrations: Whether to install integrations
        install_hooks: Whether to install hooks
        project_path: Project root path
        global_install: Whether this is a global install
    """

    platform: str
    install_integrations: bool | None
    install_hooks: bool | None
    project_path: Path
    global_install: bool


class QuickstartRunner:
    """Interactive quickstart wizard.

    Guides users through the setup process with
    interactive questions and recommendations.

    Example:
        >>> runner = QuickstartRunner()
        >>> result = runner.run()
        >>> print(f"Setup complete: {result['success']}")
    """

    def __init__(self) -> None:
        """Initialize the quickstart runner."""
        self._supported_platforms = {
            "claude-code": "Claude Code CLI",
            "kimi-cli": "Kimi Code CLI",
            "opencode": "OpenCode CLI",
        }

        from vibesop.core.skills.external_loader import ExternalSkillLoader

        self._available_integrations = {
            name: desc
            for name, desc in [
                ("gstack", "Virtual engineering team skills"),
                ("superpowers", "General-purpose productivity skills"),
            ]
            if name in ExternalSkillLoader.TRUSTED_PACKS
        }

    def run(self, project_path: Path | None = None) -> dict[str, Any]:
        """Run the interactive quickstart wizard.

        Args:
            project_path: Project root (None = current directory)

        Returns:
            Dictionary with setup results
        """
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

            # Step 1: Determine project path
            if project_path is None:
                project_path = Path.cwd()
            else:
                project_path = project_path.expanduser().resolve()

            console.print(f"📁 Project Path: {project_path}")
            console.print()

            # Step 2: Ask about install type
            config = self._ask_install_type(project_path)
            result["config"] = config

            # Step 3: Select platform
            if config.platform == "ask":
                config.platform = self._ask_platform()
            console.print()

            # Step 4: Ask about integrations
            if config.install_integrations is None:
                config.install_integrations = self._ask_yes_no(
                    "Install skill pack integrations (gstack, superpowers)?",
                    default=True,
                )
            console.print()

            # Step 5: Ask about hooks
            if config.install_hooks is None:
                config.install_hooks = self._ask_yes_no(
                    "Install platform hooks?",
                    default=True,
                )
            console.print()

            # Step 6: Show summary
            self._show_summary(config)
            console.print()

            # Step 7: Confirm
            if not self._ask_yes_no("Proceed with installation?", default=True):
                console.print("Installation cancelled.")
                return result

            # Step 8: Execute installation
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
                self._show_next_steps(config)

        except KeyboardInterrupt:
            console.print("\n\nInstallation cancelled by user.")
            result["errors"].append("User cancelled")
        except Exception as e:
            result["errors"].append(f"Setup failed: {e}")

        return result

    def _ask_install_type(self, project_path: Path) -> QuickstartConfig:
        """Ask about installation type.

        Args:
            project_path: Project root path

        Returns:
            QuickstartConfig with initial settings
        """
        console.print("What would you like to set up?")
        console.print("1. Global configuration for Claude Code/Kimi CLI/OpenCode")
        console.print("2. Project-specific configuration")
        console.print()

        choice = self._ask_choice(
            "Choose installation type",
            options=["1", "2"],
            default="1",
        )

        if choice == "1":
            # Global install
            return QuickstartConfig(
                platform="ask",  # Will ask later
                install_integrations=True,
                install_hooks=True,
                project_path=Path.home(),  # Global config
                global_install=True,
            )
        else:
            # Project install
            return QuickstartConfig(
                platform="ask",
                install_integrations=False,  # Usually not for projects
                install_hooks=False,
                project_path=project_path,
                global_install=False,
            )

    def _ask_platform(self) -> str:
        """Ask user to select platform.

        Returns:
            Selected platform identifier
        """
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
        """Ask a yes/no question.

        Args:
            question: Question text
            default: Default answer

        Returns:
            True for yes, False for no
        """
        default_str = "Y/n" if default else "y/N"
        prompt = f"{question} [{default_str}]: "

        while True:
            response = input(prompt).strip().lower()

            if not response:
                return default

            if response in ["y", "yes"]:
                return True
            elif response in ["n", "no"]:
                return False

            console.print("Please answer 'yes' or 'no'")

    def _ask_choice(self, question: str, options: list[str], default: str) -> str:
        """Ask user to choose from options.

        Args:
            question: Question text
            options: List of valid options
            default: Default option

        Returns:
            Selected option
        """
        prompt = f"{question} [{'/'.join(options)}]: "

        while True:
            response = input(prompt).strip()

            if not response:
                return default

            if response in options:
                return response

            console.print(f"Please choose one of: {'/'.join(options)}")

    def _show_summary(self, config: QuickstartConfig) -> None:
        """Show installation summary.

        Args:
            config: QuickstartConfig
        """
        console.print("┌─ Installation Summary ─────────────────────┐")
        console.print(f"│ Platform: {config.platform:<20} │")
        console.print(f"│ Type: {'Global' if config.global_install else 'Project':<20} │")
        console.print(f"│ Integrations: {'Yes' if config.install_integrations else 'No':<20} │")
        console.print(f"│ Hooks: {'Yes' if config.install_hooks else 'No':<20} │")
        console.print(f"│ Location: {config.project_path!s:<20} │")
        console.print("└──────────────────────────────────────────┘")

    def _execute_installation(self, config: QuickstartConfig) -> bool:
        """Execute the installation.

        Args:
            config: QuickstartConfig

        Returns:
            True if successful, False otherwise
        """
        try:
            # Step 1: Initialize project
            if not config.global_install:
                init_support = InitSupport()
                init_result = init_support.init_project(
                    config.project_path,
                    config.platform,
                )

                if not init_result["success"]:
                    console.print(f"❌ Initialization failed: {init_result['errors']}")
                    return False

                console.print("✓ Project initialized")

            # Step 2: Install configuration
            installer = VibeSOPInstaller()
            if config.global_install:
                install_target: Path | None = None
            else:
                install_target = config.project_path / ".vibe" / "dist" / config.platform
            install_result = installer.install(
                config.platform,
                install_target,
                force=False,
            )

            if not install_result["success"]:
                console.print(f"❌ Configuration installation failed: {install_result['errors']}")
                return False

            console.print("✓ Configuration installed")

            # Step 3: Install integrations (if requested)
            if config.install_integrations:
                for integration in ["gstack", "superpowers"]:
                    self._install_integration(integration, config.platform)
            else:
                console.print("⊘ Integrations skipped")

            # Step 4: Install hooks (if requested)
            if config.install_hooks:
                hooks_install_target = (
                    Path.home() / ".claude" if config.global_install else install_target
                )
                hooks_result = installer.install(config.platform, hooks_install_target)
                hooks_installed = sum(
                    1 for v in hooks_result.get("hooks_installed", {}).values() if v
                )
                total_hooks = len(hooks_result.get("hooks_installed", {}))

                if hooks_installed > 0:
                    console.print(f"✓ Hooks installed: {hooks_installed}/{total_hooks}")
                else:
                    console.print("⊘ No hooks available for this platform")
            else:
                console.print("⊘ Hooks skipped")

            return True

        except Exception as e:
            console.print(f"❌ Installation failed: {e}")
            return False

    def _install_integration(self, integration: str, _platform: str) -> None:
        """Install a skill pack integration.

        Args:
            integration: Integration name (gstack, superpowers)
            _platform: Target platform (unused, kept for signature compatibility)
        """
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

    def _show_next_steps(self, config: QuickstartConfig) -> None:
        """Show next steps after installation.

        Args:
            config: QuickstartConfig
        """
        console.print("\n[bold]📚 Next Steps:[/bold]\n")

        # Platform to output directory mapping
        platform_dirs = {
            "claude-code": "~/.claude",
            "kimi-cli": "~/.kimi",
            "opencode": "~/.config/opencode",
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
        else:
            console.print("1. Review .vibe/ directory")
            console.print("2. Add skills to .vibe/skills/")
            console.print("3. Run: [cyan]vibe build[/cyan]")
            console.print('4. Run: [cyan]vibe route "your query"[/cyan] to test')

        console.print("\n[bold yellow]⚠️  LLM Configuration Required[/bold yellow]")
        console.print(
            "   VibeSOP runs as a CLI subprocess and [bold]cannot reuse your Agent's LLM[/bold]."
        )
        console.print("   Configure a separate LLM for semantic routing:")
        console.print("   [dim]  export ANTHROPIC_API_KEY=\"sk-ant-...\"  # or OPENAI_API_KEY[/dim]")
        console.print("   [dim]  # or local Ollama (zero cost):[/dim]")
        console.print("   [dim]  export VIBE_LLM_PROVIDER=ollama[/dim]")
        console.print("   [dim]  ollama pull qwen3:35b-a3b-mlx && ollama serve[/dim]")

        console.print("\n[bold]📖 Documentation:[/bold]")
        console.print("   - Quick Start: README.md")
        console.print("   - Architecture: ARCHITECTURE.md")
        console.print("   - Contributing: CONTRIBUTING.md")
