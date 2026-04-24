"""Slash command registry for VibeSOP.

Provides explicit slash commands (e.g., /vibe-route, /vibe-install) that allow
users to directly trigger VibeSOP capabilities even when the AI Agent doesn't
naturally route to them.

Usage:
    /vibe-route "帮我review这段代码"     # Force trigger routing
    /vibe-install gstack                  # Install skill pack
    /vibe-analyze --deep                  # Deep project analysis
    /vibe-evaluate --skill review         # Evaluate skill quality
    /vibe-orchestrate "分析→评审→优化"     # Multi-skill orchestration

Architecture:
    - SlashCommandRegistry: Central registry of all available commands
    - SlashCommandHandler: Executes commands by dispatching to internal APIs
    - Agent Runtime Integration: Interceptor detects /vibe-* prefix and routes
"""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class SlashCommand:
    """Definition of a slash command."""

    name: str
    description: str
    handler: Callable[..., tuple[bool, str]]
    args_schema: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    requires_confirmation: bool = False


class SlashCommandRegistry:
    """Registry of all slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}

    def register(self, command: SlashCommand) -> None:
        """Register a slash command."""
        self._commands[command.name] = command
        logger.debug(f"Registered slash command: {command.name}")

    def get(self, name: str) -> SlashCommand | None:
        """Get a command by name."""
        return self._commands.get(name)

    def list_commands(self) -> list[SlashCommand]:
        """List all registered commands."""
        return list(self._commands.values())

    def parse(self, user_input: str) -> tuple[str | None, list[str]]:
        """Parse user input to extract command and arguments."""
        user_input = user_input.strip()
        if not user_input.startswith("/vibe-"):
            return None, []

        try:
            parts = shlex.split(user_input)
        except ValueError:
            parts = user_input.split()

        if not parts:
            return None, []

        return parts[0], parts[1:]


class SlashCommandHandler:
    """Executes slash commands by dispatching to VibeSOP internal APIs."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._registry = SlashCommandRegistry()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up all command handlers."""
        self._registry.register(
            SlashCommand(
                name="/vibe-route",
                description="Force trigger routing decision with transparency",
                handler=self._handle_route,
                args_schema=["query", "--explain", "--strategy"],
                examples=[
                    '/vibe-route "帮我review这段代码"',
                    '/vibe-route "分析项目架构" --explain',
                ],
            )
        )

        self._registry.register(
            SlashCommand(
                name="/vibe-install",
                description="Install skill pack to central storage with symlinks",
                handler=self._handle_install,
                args_schema=["pack_name", "--platform"],
                examples=["/vibe-install gstack", "/vibe-install superpowers"],
            )
        )

        self._registry.register(
            SlashCommand(
                name="/vibe-analyze",
                description="Deep project architecture and tech stack analysis",
                handler=self._handle_analyze,
                args_schema=["--deep", "--output"],
                examples=["/vibe-analyze", "/vibe-analyze --deep"],
            )
        )

        self._registry.register(
            SlashCommand(
                name="/vibe-evaluate",
                description="Evaluate skill quality and usage statistics",
                handler=self._handle_evaluate,
                args_schema=["--skill", "--report"],
                examples=["/vibe-evaluate", "/vibe-evaluate --skill gstack/review"],
            )
        )

        self._registry.register(
            SlashCommand(
                name="/vibe-orchestrate",
                description="Multi-skill orchestration for complex requests",
                handler=self._handle_orchestrate,
                args_schema=["query", "--strategy"],
                examples=[
                    '/vibe-orchestrate "分析架构→评审代码→提出优化"',
                    '/vibe-orchestrate "review + qa" --strategy parallel',
                ],
            )
        )

        self._registry.register(
            SlashCommand(
                name="/vibe-list",
                description="List installed skills and available packs",
                handler=self._handle_list,
                args_schema=["--installed", "--available"],
                examples=["/vibe-list", "/vibe-list --installed"],
            )
        )

        self._registry.register(
            SlashCommand(
                name="/vibe-help",
                description="Show all available slash commands and usage",
                handler=self._handle_help,
                examples=["/vibe-help"],
            )
        )

    def execute(self, user_input: str) -> tuple[bool, str]:
        """Execute a slash command from user input."""
        cmd_name, args = self._registry.parse(user_input)

        if cmd_name is None:
            return False, "Not a valid VibeSOP slash command"

        command = self._registry.get(cmd_name)
        if command is None:
            available = [cmd.name for cmd in self._registry.list_commands()]
            return (
                False,
                f"Unknown command: {cmd_name}\nAvailable: {', '.join(available)}",
            )

        logger.info(f"Executing slash command: {cmd_name} with args: {args}")
        return command.handler(*args)

    def _handle_route(self, *args: str) -> tuple[bool, str]:
        """Handle /vibe-route command."""
        if not args:
            return False, "Usage: /vibe-route <query> [--explain]"

        explain = "--explain" in args

        # Extract query
        query_parts = []
        skip_next = False
        for i, arg in enumerate(args):
            if skip_next:
                skip_next = False
                continue
            if arg.startswith("--"):
                if arg in ("--strategy",):
                    skip_next = True
                continue
            query_parts.append(arg)

        query = " ".join(query_parts)
        if not query:
            return False, "Please provide a query"

        try:
            from vibesop.core.routing import UnifiedRouter
            from vibesop.core.matching import RoutingContext

            router = UnifiedRouter(project_root=self.project_root)
            context = RoutingContext()
            result = router.route(query, context=context)

            if explain:
                from vibesop.cli.routing_report import render_routing_report
                from rich.console import Console
                console = Console()
                render_routing_report(result, console=console)
                return True, "Routing decision displayed"
            elif result.primary:
                return (
                    True,
                    f"Recommended: {result.primary.skill_id} (confidence: {result.primary.confidence:.0%})",
                )
            else:
                return True, "No matching skill found"

        except Exception as e:
            logger.error(f"Route command failed: {e}")
            return False, f"Routing failed: {e}"

    def _handle_install(self, *args: str) -> tuple[bool, str]:
        """Handle /vibe-install command."""
        if not args:
            return False, "Usage: /vibe-install <pack_name> [--platform <platform>]"

        pack_name = args[0]
        platforms = None
        if "--platform" in args:
            idx = args.index("--platform")
            if idx + 1 < len(args):
                platforms = [args[idx + 1]]

        try:
            from vibesop.installer.pack_installer import PackInstaller
            installer = PackInstaller()
            success, msg = installer.install_pack(pack_name=pack_name, platforms=platforms)
            return success, msg
        except Exception as e:
            logger.error(f"Install command failed: {e}")
            return False, f"Installation failed: {e}"

    def _handle_analyze(self, *args: str) -> tuple[bool, str]:
        """Handle /vibe-analyze command."""
        deep = "--deep" in args

        try:
            from vibesop.core.project_analyzer import ProjectAnalyzer
            analyzer = ProjectAnalyzer(self.project_root)
            profile = analyzer.analyze()

            msg = f"Project type: {profile.project_type or 'Unknown'}\n"
            msg += f"Tech stack: {', '.join(profile.tech_stack) if profile.tech_stack else 'Not detected'}\n"

            if deep:
                msg += f"Files: {profile.file_count}\n"
                msg += f"Code lines: {profile.code_lines}\n"

            return True, msg
        except Exception as e:
            logger.error(f"Analyze command failed: {e}")
            return False, f"Analysis failed: {e}"

    def _handle_evaluate(self, *args: str) -> tuple[bool, str]:
        """Handle /vibe-evaluate command."""
        skill_id = None
        if "--skill" in args:
            idx = args.index("--skill")
            if idx + 1 < len(args):
                skill_id = args[idx + 1]

        try:
            from vibesop.core.skills.evaluator import SkillEvaluator
            evaluator = SkillEvaluator(project_root=self.project_root)

            if skill_id:
                evaluation = evaluator.evaluate_skill(skill_id)
                if evaluation:
                    return (
                        True,
                        f"Skill: {skill_id}\n"
                        f"Grade: {evaluation.grade}\n"
                        f"Success rate: {evaluation.success_rate:.0%}\n"
                        f"Total uses: {evaluation.total_routes}",
                    )
                return False, f"No evaluation data for {skill_id}"

            all_evals = evaluator.evaluate_all()
            if not all_evals:
                return True, "No evaluation data yet"

            msg = "Skill Evaluation Summary:\n"
            for sid, ev in all_evals.items():
                msg += f"  {sid}: {ev.grade} ({ev.quality_score:.0%})\n"
            return True, msg
        except Exception as e:
            logger.error(f"Evaluate command failed: {e}")
            return False, f"Evaluation failed: {e}"

    def _handle_orchestrate(self, *args: str) -> tuple[bool, str]:
        """Handle /vibe-orchestrate command."""
        if not args:
            return False, "Usage: /vibe-orchestrate <query> [--strategy <sequential|parallel|hybrid>]"

        strategy = None
        if "--strategy" in args:
            idx = args.index("--strategy")
            if idx + 1 < len(args):
                strategy = args[idx + 1]

        query_parts = []
        skip_next = False
        for i, arg in enumerate(args):
            if skip_next:
                skip_next = False
                continue
            if arg.startswith("--"):
                if arg == "--strategy":
                    skip_next = True
                continue
            query_parts.append(arg)

        query = " ".join(query_parts)
        if not query:
            return False, "Please provide a query"

        try:
            from vibesop.core.routing import UnifiedRouter
            from vibesop.core.matching import RoutingContext

            router = UnifiedRouter(project_root=self.project_root)
            context = RoutingContext()
            if strategy:
                context.strategy_hint = strategy

            result = router.orchestrate(query, context=context)

            if result.mode.value == "orchestrated" and result.execution_plan:
                msg = f"Execution Plan ({result.execution_plan.mode}):\n"
                for step in result.execution_plan.steps:
                    msg += f"  {step.step_number}. {step.skill_id} — {step.intent}\n"
                return True, msg
            elif result.primary:
                return (
                    True,
                    f"Single skill: {result.primary.skill_id} (confidence: {result.primary.confidence:.0%})",
                )
            return True, "No matching skill found"
        except Exception as e:
            logger.error(f"Orchestrate command failed: {e}")
            return False, f"Orchestration failed: {e}"

    def _handle_list(self, *args: str) -> tuple[bool, str]:
        """Handle /vibe-list command."""
        installed_only = "--installed" in args

        try:
            from vibesop.core.skills.storage import SkillStorage
            storage = SkillStorage()
            skills = storage.list_skills()

            if not skills:
                return True, "No installed skills"

            msg = "Installed Skills:\n"
            for skill_id in skills:
                msg += f"  • {skill_id}\n"

            if not installed_only:
                from vibesop.constants import TRUSTED_PACKS
                msg += "\nAvailable Packs:\n"
                for pack_name in TRUSTED_PACKS:
                    msg += f"  • {pack_name}\n"

            return True, msg
        except Exception as e:
            logger.error(f"List command failed: {e}")
            return False, f"Failed to list: {e}"

    def _handle_help(self, *args: str) -> tuple[bool, str]:
        """Handle /vibe-help command."""
        msg = "VibeSOP Slash Commands:\n\n"
        for cmd in self._registry.list_commands():
            msg += f"  {cmd.name}\n"
            msg += f"    {cmd.description}\n"
            if cmd.examples:
                msg += f"    Example: {cmd.examples[0]}\n"
            msg += "\n"
        return True, msg
