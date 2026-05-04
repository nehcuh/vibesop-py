"""Slash command registry for VibeSOP."""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vibesop.core.routing import UnifiedRouter

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def _extract_query_and_flags(
    args: tuple[str, ...],
    flag_names: set[str] | None = None,
) -> tuple[str, dict[str, str | bool]]:
    flag_names = flag_names or set()
    query_parts: list[str] = []
    flags: dict[str, str | bool] = {}
    skip_next = False

    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue

        if arg.startswith("--"):
            if arg in flag_names and i + 1 < len(args):
                flags[arg] = args[i + 1]
                skip_next = True
            else:
                flags[arg] = True
            continue

        query_parts.append(arg)

    return " ".join(query_parts), flags


@dataclass
class SlashCommand:
    """Definition of a slash command."""

    name: str
    description: str
    handler: Callable[..., tuple[bool, str]]
    args_schema: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    requires_confirmation: bool = False

    def validate_args(self, args: list[str]) -> tuple[bool, str]:
        if not self.args_schema:
            return True, ""

        # Check for unknown flags
        known_flags = {arg for arg in self.args_schema if arg.startswith("--")}
        for arg in args:
            if arg.startswith("--") and arg not in known_flags:
                return False, f"Unknown flag: {arg}. Available: {', '.join(sorted(known_flags))}"

        # Check required positional arguments
        positional_schemas = [s for s in self.args_schema if not s.startswith("--")]
        positional_args = [a for a in args if not a.startswith("--")]

        if positional_schemas and not positional_args:
            return False, f"Missing required argument: <{positional_schemas[0]}>"

        return True, ""

    def generate_help(self) -> str:
        lines = [f"Usage: {self.name}"]

        if self.args_schema:
            args_str = " ".join(self.args_schema)
            lines[0] += f" {args_str}"

        lines.append("")
        lines.append(self.description)

        if self.examples:
            lines.append("")
            lines.append("Examples:")
            for example in self.examples:
                lines.append(f"  {example}")

        return "\n".join(lines)


class SlashCommandRegistry:
    """Registry of all slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}

    def register(self, command: SlashCommand) -> None:
        self._commands[command.name] = command
        logger.debug(f"Registered slash command: {command.name}")

    def get(self, name: str) -> SlashCommand | None:
        return self._commands.get(name)

    def list_commands(self) -> list[SlashCommand]:
        return list(self._commands.values())

    def parse(self, user_input: str) -> tuple[str | None, list[str]]:
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
        self._router: UnifiedRouter | None = None
        self._setup_handlers()

    @property
    def router(self) -> UnifiedRouter:
        if self._router is None:
            self._router = UnifiedRouter(project_root=self.project_root)
        return self._router

    def _setup_handlers(self) -> None:
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

        # Validate arguments against schema
        is_valid, error_msg = command.validate_args(args)
        if not is_valid:
            help_text = command.generate_help()
            return False, f"{error_msg}\n\n{help_text}"

        logger.info(f"Executing slash command: {cmd_name} with args: {args}")
        return command.handler(*args)

    def _handle_route(self, *args: str) -> tuple[bool, str]:
        if not args:
            return False, "Usage: /vibe-route <query> [--explain] [--strategy <strategy>]"

        query, flags = _extract_query_and_flags(args, {"--strategy"})
        if not query:
            return False, "Please provide a query"

        explain = flags.get("--explain", False)
        strategy = flags.get("--strategy")

        try:
            from vibesop.core.matching import RoutingContext

            context = RoutingContext()
            if strategy and isinstance(strategy, str):
                context.strategy_hint = strategy

            result = self.router.orchestrate(query, context=context)

            if explain:
                from rich.console import Console

                from vibesop.cli.routing_report import render_routing_report

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

        except (OSError, ValueError, RuntimeError) as e:
            logger.error(f"Route command failed: {e}")
            return False, f"Routing failed: {e}"

    def _handle_install(self, *args: str) -> tuple[bool, str]:
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
            return installer.install_pack(pack_name=pack_name, platforms=platforms)
        except (OSError, ValueError, RuntimeError) as e:
            logger.error(f"Install command failed: {e}")
            return False, f"Installation failed: {e}"

    def _handle_analyze(self, *args: str) -> tuple[bool, str]:
        deep = "--deep" in args

        try:
            from vibesop.core.project_analyzer import ProjectAnalyzer

            analyzer = ProjectAnalyzer(self.project_root)
            profile = analyzer.analyze()
            result: dict[str, Any] = {
                "project_type": profile.project_type,
                "tech_stack": profile.tech_stack,
            }
            if deep:
                result["file_count"] = getattr(profile, "file_count", None)
                result["code_lines"] = getattr(profile, "code_lines", None)

            msg = f"Project type: {result.get('project_type') or 'Unknown'}\n"
            tech_stack = result.get("tech_stack", [])
            msg += f"Tech stack: {', '.join(tech_stack) if tech_stack else 'Not detected'}\n"

            if deep:
                file_count = result.get("file_count")
                code_lines = result.get("code_lines")
                if file_count is not None:
                    msg += f"Files: {file_count}\n"
                if code_lines is not None:
                    msg += f"Code lines: {code_lines}\n"

            return True, msg
        except (OSError, ValueError, RuntimeError) as e:
            logger.error(f"Analyze command failed: {e}")
            return False, f"Analysis failed: {e}"

    def _handle_evaluate(self, *args: str) -> tuple[bool, str]:
        skill_id = None
        if "--skill" in args:
            idx = args.index("--skill")
            if idx + 1 < len(args):
                skill_id = args[idx + 1]

        try:
            from vibesop.core.skills.evaluator import RoutingEvaluator

            evaluator = RoutingEvaluator(project_root=self.project_root)
            if skill_id:
                evaluation = evaluator.evaluate_skill(skill_id)
                if evaluation:
                    return (
                        True,
                        f"Skill: {skill_id}\n"
                        f"Grade: {evaluation.grade}\n"
                        f"Quality: {evaluation.quality_score:.0%}\n"
                        f"Total uses: {evaluation.total_routes}",
                    )
                return False, f"No evaluation data for {skill_id}"

            all_evals = evaluator.evaluate_all_skills()
            if not all_evals:
                return True, "No evaluation data yet"

            msg = "Skill Evaluation Summary:\n"
            for sid, ev in all_evals.items():
                msg += f"  {sid}: {ev.grade} ({ev.quality_score:.0%})\n"
            return True, msg
        except (OSError, ValueError, RuntimeError) as e:
            logger.error(f"Evaluate command failed: {e}")
            return False, f"Evaluation failed: {e}"

    def _handle_orchestrate(self, *args: str) -> tuple[bool, str]:
        if not args:
            return (
                False,
                "Usage: /vibe-orchestrate <query> [--strategy <sequential|parallel|hybrid>]",
            )

        query, flags = _extract_query_and_flags(args, {"--strategy"})
        if not query:
            return False, "Please provide a query"

        strategy = flags.get("--strategy")

        try:
            from vibesop.core.matching import RoutingContext

            context = RoutingContext()
            if strategy and isinstance(strategy, str):
                context.strategy_hint = strategy

            result = self.router.orchestrate(query, context=context)

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
        except (OSError, ValueError, RuntimeError) as e:
            logger.error(f"Orchestrate command failed: {e}")
            return False, f"Orchestration failed: {e}"

    def _handle_list(self, *args: str) -> tuple[bool, str]:
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
        except (OSError, ValueError, RuntimeError) as e:
            logger.error(f"List command failed: {e}")
            return False, f"Failed to list: {e}"

    def _handle_help(self, *args: str) -> tuple[bool, str]:
        # Check if user wants help for a specific command
        if args and args[0].startswith("/vibe-"):
            cmd = self._registry.get(args[0])
            if cmd:
                return True, cmd.generate_help()
            return False, f"Unknown command: {args[0]}"

        msg = "VibeSOP Slash Commands:\n\n"
        for cmd in self._registry.list_commands():
            msg += f"  {cmd.name}\n"
            msg += f"    {cmd.description}\n"
            if cmd.examples:
                msg += f"    Example: {cmd.examples[0]}\n"
            msg += "\n"

        msg += "Use /vibe-help <command> for detailed usage.\n"
        msg += "Example: /vibe-help /vibe-route"
        return True, msg
