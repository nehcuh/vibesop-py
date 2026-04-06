# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false, reportUnknownParameterType=false
"""Quickstart runner for interactive installation.

This module provides an interactive wizard for setting up
VibeSOP configuration.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vibesop.installer.init_support import InitSupport
from vibesop.installer.installer import VibeSOPInstaller


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
            "opencode": "OpenCode CLI",
        }

        self._available_integrations = {
            "gstack": "Virtual engineering team skills",
            "superpowers": "General-purpose productivity skills",
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
            print("╔════════════════════════════════════════════════════╗")
            print("║     VibeSOP Quickstart Wizard                      ║")
            print("╚════════════════════════════════════════════════════╝")
            print()

            # Step 1: Determine project path
            if project_path is None:
                project_path = Path.cwd()
            else:
                project_path = project_path.expanduser().resolve()

            print(f"📁 Project Path: {project_path}")
            print()

            # Step 2: Ask about install type
            config = self._ask_install_type(project_path)
            result["config"] = config

            # Step 3: Select platform
            if config.platform == "ask":
                config.platform = self._ask_platform()
            print()

            # Step 4: Ask about integrations
            if config.install_integrations is None:
                config.install_integrations = self._ask_yes_no(
                    "Install skill pack integrations (gstack, superpowers)?",
                    default=True,
                )
            print()

            # Step 5: Ask about hooks
            if config.install_hooks is None:
                config.install_hooks = self._ask_yes_no(
                    "Install platform hooks?",
                    default=True,
                )
            print()

            # Step 6: Show summary
            self._show_summary(config)
            print()

            # Step 7: Confirm
            if not self._ask_yes_no("Proceed with installation?", default=True):
                print("Installation cancelled.")
                return result

            # Step 8: Execute installation
            result["success"] = self._execute_installation(config)
            result["steps_completed"] = [
                "platform_selection",
                "integration_selection",
                "hook_selection",
            ]

            if result["success"]:
                print()
                print("✅ Installation complete!")
                print()
                self._show_next_steps(config)

        except KeyboardInterrupt:
            print("\n\nInstallation cancelled by user.")
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
        print("What would you like to set up?")
        print("1. Global configuration for Claude Code/OpenCode")
        print("2. Project-specific configuration")
        print()

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
        print("Select your platform:")
        platforms = list(self._supported_platforms.keys())
        for i, (plat_id, plat_name) in enumerate(self._supported_platforms.items(), 1):
            print(f"{i}. {plat_id} - {plat_name}")

        print()
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

            print("Please answer 'yes' or 'no'")

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

            print(f"Please choose one of: {'/'.join(options)}")

    def _show_summary(self, config: QuickstartConfig) -> None:
        """Show installation summary.

        Args:
            config: QuickstartConfig
        """
        print("┌─ Installation Summary ─────────────────────┐")
        print(f"│ Platform: {config.platform:<20} │")
        print(f"│ Type: {'Global' if config.global_install else 'Project':<20} │")
        print(f"│ Integrations: {'Yes' if config.install_integrations else 'No':<20} │")
        print(f"│ Hooks: {'Yes' if config.install_hooks else 'No':<20} │")
        print(f"│ Location: {config.project_path!s:<20} │")
        print("└──────────────────────────────────────────┘")

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
                    print(f"❌ Initialization failed: {init_result['errors']}")
                    return False

                print("✓ Project initialized")

            # Step 2: Install configuration
            installer = VibeSOPInstaller()
            install_result = installer.install(
                config.platform,
                config.project_path,
                force=False,
            )

            if not install_result["success"]:
                print(f"❌ Configuration installation failed: {install_result['errors']}")
                return False

            print("✓ Configuration installed")

            # Step 3: Install integrations (if requested)
            if config.install_integrations:
                for integration in ["gstack", "superpowers"]:
                    self._install_integration(integration, config.platform)
            else:
                print("⊘ Integrations skipped")

            # Step 4: Install hooks (if requested)
            if config.install_hooks:
                hooks_result = installer.verify(config.platform, config.project_path)
                hooks_installed = sum(
                    1 for v in hooks_result.get("hooks_installed", {}).values() if v
                )
                total_hooks = len(hooks_result.get("hooks_installed", {}))

                if hooks_installed > 0:
                    print(f"✓ Hooks installed: {hooks_installed}/{total_hooks}")
                else:
                    print("⊘ No hooks available for this platform")
            else:
                print("⊘ Hooks skipped")

            return True

        except Exception as e:
            print(f"❌ Installation failed: {e}")
            return False

    def _install_integration(self, integration: str, platform: str) -> None:
        """Install a skill pack integration.

        Args:
            integration: Integration name (gstack, superpowers)
            platform: Target platform
        """
        try:
            if integration == "gstack":
                from vibesop.installer.gstack_installer import GstackInstaller

                installer = GstackInstaller()
                result = installer.install(platform)

                if result["success"]:
                    print(f"✓ {integration} installed")
                else:
                    print(f"⊘ {integration} installation failed: {result['errors']}")

        except Exception as e:
            print(f"⊘ {integration} installation failed: {e}")

    def _show_next_steps(self, config: QuickstartConfig) -> None:
        """Show next steps after installation.

        Args:
            config: QuickstartConfig
        """
        print("📚 Next Steps:")
        print()

        if config.global_install:
            print("1. Restart your terminal/editor")
            print("2. Run: vibe doctor")
        else:
            print("1. Review .vibe/ directory")
            print("2. Add skills to .vibe/skills/")
            print("3. Run: vibe build")

        print()
        print("📖 Documentation:")
        print("   - CLI Reference: docs/CLI_REFERENCE.md")
        print("   - Project Status: docs/PROJECT_STATUS.md")
        print()
