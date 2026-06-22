"""VibeSOP CLI - Main entry point.

Built with Typer for modern CLI UX.

VibeSOP is a Skill Operating System (SkillOS) that manages the full lifecycle
of AI development skills: discovery → installation → routing → orchestration →
evaluation → retention/deprecation. Simple tasks are handled end-to-end by
VibeSOP (route → inject → guide execution); complex tasks are delegated to
AI Agents (Claude Code, Cursor, OpenCode).

Note: v4.1.0 removed the `execute` CLI command — skill execution is the
responsibility of AI Agents. VibeSOP provides lightweight guided execution
for task orchestration, not full skill execution.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any

import questionary
import typer
from rich.console import Console
from rich.panel import Panel

from vibesop import __version__
from vibesop.cli.commands import (
    badges_cmd,
    deviation_cmd,
    instinct_cmd,
    loop_cmd,
    market_cmd,
    matcher_cmd,
    plan_cmd,
    prompt_chain_cmd,
    snapshot_cmd,
    sync_cmd,
    trace_cmd,
    workflows_cmd,
)
from vibesop.cli.commands import trust as trust_module
from vibesop.cli.commands.status_cmd import status as status_command
from vibesop.cli.confirmation import _needs_confirmation, _run_confirmation_flow
from vibesop.cli.feedback import _collect_feedback
from vibesop.cli.orchestration_report import render_orchestration_result
from vibesop.cli.plan_editor import _edit_execution_plan
from vibesop.cli.render import (
    render_compact_orchestration,
)
from vibesop.cli.routing_report import render_routing_report
from vibesop.cli.subcommands import register
from vibesop.core.routing import UnifiedRouter


def _wire_defaults() -> None:
    """Composition root: wire concrete implementations into core abstractions."""
    from vibesop.core.skills.executor import ExternalSkillExecutor
    from vibesop.core.skills.external_loader import ExternalSkillLoader
    from vibesop.core.skills.storage import SkillStorage
    from vibesop.security import PathSafety, SkillSecurityAuditor

    SkillStorage.set_default_path_safety(PathSafety())
    ExternalSkillLoader.set_default_auditor_factory(
        lambda strict, root: SkillSecurityAuditor(strict_mode=strict, project_root=root),
    )
    ExternalSkillExecutor.set_default_auditor_factory(
        lambda root: SkillSecurityAuditor(project_root=root),
    )


_wire_defaults()

logger = logging.getLogger(__name__)


def _build_llm_factory() -> Any:
    """Create an LLM factory callable for injection into UnifiedRouter.

    Composition root: this is the only place that imports vibesop.llm.
    Returns a callable that, when invoked, produces a configured LLM provider.
    """

    def factory() -> Any:
        from vibesop.core.llm_config import VibeSOPConfigManager
        from vibesop.llm.factory import create_provider

        llm_config = VibeSOPConfigManager.get_llm_config()
        if llm_config and llm_config.api_key:
            return create_provider(
                provider=llm_config.provider,
                api_key=llm_config.api_key,
                base_url=llm_config.api_base,
            )
        return create_provider()

    return factory


def _build_prompt_builder() -> Any:
    """Create a prompt builder callable for injection into UnifiedRouter."""

    def builder(query: str, skills_summary: str, version: str) -> str:
        from vibesop.llm.triage_prompts import TriagePromptRegistry

        return TriagePromptRegistry.render(
            query=query,
            skills_summary=skills_summary,
            version=version,
        )

    return builder


app = typer.Typer(
    name="vibe",
    help="VibeSOP - AI-powered workflow SOP",
    no_args_is_help=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def _default_callback(  # pyright: ignore[reportUnusedFunction]
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit"),
) -> None:
    """VibeSOP — AI-powered skill operating system for developers."""
    if version:
        console.print(f"VibeSOP v{__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        status_command()


# Register subcommands
app.add_typer(plan_cmd.app, name="plan")
app.add_typer(matcher_cmd.app, name="matcher")
app.add_typer(deviation_cmd.app, name="deviation")
app.add_typer(badges_cmd.app, name="badges")
app.add_typer(market_cmd.app, name="market")
app.add_typer(snapshot_cmd.app, name="snapshot")
app.add_typer(trace_cmd.app, name="trace")
app.add_typer(sync_cmd.app, name="sync-registry")
app.add_typer(workflows_cmd.app, name="workflows")
app.add_typer(instinct_cmd.app, name="instinct")
app.add_typer(prompt_chain_cmd.app, name="prompt-chain")
app.add_typer(loop_cmd.app, name="loop")
app.command(name="trust")(trust_module.trust)


@app.command()
def status(
    no_color: bool = typer.Option(False, "--no-color", help="Disable colored output"),
) -> None:
    """Show a unified snapshot of your VibeSOP skill ecosystem."""
    status_command(no_color=no_color)


# -- Core routing commands --


def _print_fallback(query: str, reason: str, *, json_output: bool) -> None:
    """Print a fallback response when the interceptor declines routing."""
    if json_output:
        import json

        print(
            json.dumps(
                {
                    "intercepted": False,
                    "query": query,
                    "reason": reason,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        console.print(f"[dim]{reason} — passing query to agent.[/dim]")


def _copy_context(base: Any | None) -> Any:
    """Return a shallow copy of a RoutingContext, preserving all fields."""
    import dataclasses

    from vibesop.core.matching import RoutingContext

    if base is None:
        return RoutingContext()
    copied = dataclasses.replace(base)
    # Ensure mutable metadata is not shared between contexts.
    copied.metadata = dict(copied.metadata)
    return copied


def _build_single_agent_context(
    context: Any | None,
    decision: Any,
) -> Any:
    """Build a RoutingContext enriched with role/skill isolation for SINGLE_AGENT."""
    from vibesop.core.orchestration.role_templates import ORCHESTRATOR_PROMPT, ROLE_PROMPTS

    analysis = decision.analysis
    if not analysis or not analysis.suggested_roles:
        return context

    role_id = analysis.suggested_roles[0]
    skills = analysis.per_agent_skills.get(role_id, [])
    role_ctx = {
        "role": role_id,
        "role_prompt": ROLE_PROMPTS.get(role_id, ORCHESTRATOR_PROMPT),
        "allowed_skills": skills,
        "interception_mode": "single_agent",
    }
    enriched = _copy_context(context)
    enriched.interception_mode = "single_agent"
    enriched.role_context = role_ctx
    # First-class field (preferred by readers post-v7.0.3):
    enriched.intent_analysis = analysis.to_dict()
    # Legacy backchannel (kept for any reader that has not yet migrated):
    enriched.metadata.update(
        {
            "intent_analysis": analysis.to_dict(),
            "_interception_mode": "single_agent",
        }
    )
    return enriched


def _build_multi_agent_squad_context(
    context: Any | None,
    decision: Any,
) -> Any:
    """Build a RoutingContext carrying intent analysis for MULTI_AGENT_SQUAD."""
    analysis = decision.analysis
    enriched = _copy_context(context)
    enriched.interception_mode = "multi_agent_squad"
    if analysis is not None:
        # First-class field (preferred by readers post-v7.0.3):
        enriched.intent_analysis = analysis.to_dict()
        # Legacy backchannel (kept for any reader that has not yet migrated):
        enriched.metadata.update(
            {
                "intent_analysis": analysis.to_dict(),
                "_interception_mode": "multi_agent_squad",
            }
        )
    return enriched


@app.command()
def route(
    query: str = typer.Argument(..., help="Natural language query to route"),
    min_confidence: float | None = typer.Option(
        None,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold (0.0-1.0)",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    slash: bool = typer.Option(
        False, "--slash", help="Treat query as a quick command (e.g., --slash '/vibe-help')"
    ),
    validate: bool = typer.Option(False, "--validate", "-V", help="Validate routing configuration"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show full routing decision tree (now the default)"
    ),
    explain: bool = typer.Option(
        False, "--explain", "-e", help="Alias for --verbose (backward compatibility)"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress routing decision tree, show compact summary only"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt (alias for confirmation_mode=never)"
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        "-x",
        help="Enter interactive step-by-step execution mode after plan confirmation",
    ),
    no_session: bool = typer.Option(
        False, "--no-session", help="Disable session-state-aware routing for this query"
    ),
    trace: bool = typer.Option(
        False, "--trace", help="Enable per-layer routing trace (inspired by SkillTree)"
    ),
    agents: str | None = typer.Option(
        None,
        "--agents",
        help="Comma-separated agent pool for orchestration (claude-code,opencode,kimi-cli,cursor)",
    ),
    strategy: str | None = typer.Option(
        None,
        "--strategy",
        "-s",
        help="Force execution strategy: auto, sequential, parallel, hybrid",
    ),
    conversation_id: str | None = typer.Option(
        None,
        "--conversation",
        "-C",
        help="Conversation ID for multi-turn context (auto-generated if omitted)",
    ),
    pattern: str | None = typer.Option(
        None,
        "--pattern",
        "-p",
        help="Force workflow pattern: sequential, parallel, fan_out, adversarial, prompt_chain",
    ),
    verify: bool = typer.Option(
        False,
        "--verify",
        help="Enable adversarial verification for execution steps",
    ),
    strictness: str = typer.Option(
        "standard",
        "--strictness",
        help="Verification strictness: lenient, standard, strict",
    ),
    output_dir: str | None = typer.Option(
        None,
        "--output-dir",
        "-O",
        help="Output directory for prompt chain files (default: .vibe/prompts)",
    ),
    minimal: bool = typer.Option(
        False,
        "--minimal",
        "-m",
        help="Minimal JSON output for sub-agent consumption (requires --json)",
    ),
) -> None:
    """Route a query to the appropriate skill using unified orchestration.

    Detects single vs. multi-intent queries automatically. For multi-intent
    queries, decomposes into sub-tasks and builds an execution plan.
    For single-intent queries, routes to the best matching skill directly.

    VibeSOP is a Skill Operating System (SkillOS) — it manages the full
    lifecycle of skills: discovers, routes, orchestrates, evaluates, and
    retains or deprecates. Skill execution is delegated to your AI Agent
    (Claude Code, Cursor, OpenCode).

    By default, VibeSOP asks for confirmation before selecting a skill.
    Set routing.confirmation_mode to 'never' for automatic selection,
    or use --yes to skip once.

    Use --verbose to inspect the full routing decision tree.
    Use --slash to invoke a quick command explicitly (e.g., --slash '/vibe-help').
    """
    from pathlib import Path

    # -- Route through IntentInterceptor to respect full Agent Runtime logic --
    from vibesop.agent.runtime import IntentInterceptor, InterceptionMode, SlashCommandExecutor

    # When --slash is explicitly passed, treat as a CLI quick command
    if slash:
        executor = SlashCommandExecutor()
        if query.strip().startswith("/vibe-"):
            result = executor.execute_query(query)
        else:
            console.print("[bold red]✗[/bold red] Quick commands must start with /vibe-")
            raise typer.Exit(1)

        if json_output:
            import json

            console.print(
                json.dumps(
                    {
                        "success": result.success,
                        "message": result.message,
                        "command": result.command,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        elif result.success:
            console.print(f"[bold green]✓[/bold green] {result.message}")
        else:
            console.print(f"[bold yellow]⚠[/bold yellow] {result.message}")
        raise typer.Exit(0 if result.success else 1)

    interceptor = IntentInterceptor()
    decision = interceptor.should_intercept(query)

    if decision.mode == InterceptionMode.SLASH_COMMAND:
        # /vibe-route, /slash-route, /vibe-orchestrate, /orchestrate:
        # strip the prefix and let the underlying query go through the normal
        # routing pipeline so the full RoutingResult/OrchestrationResult is
        # available for structured output (--json, hook additionalContext).
        import re

        _route_like_re = re.compile(
            r'^/(?:vibe-route|slash-route|vibe-orchestrate|orchestrate)\s+["\']?(.+?)["\']?\s*$',
            re.DOTALL,
        )
        route_match = _route_like_re.match(query.strip())
        if route_match:
            query = route_match.group(1).strip()
        else:
            # Other slash commands (/vibe-help, /vibe-list, /vibe-install, etc.)
            executor = SlashCommandExecutor()
            result = executor.execute(decision)

            if json_output:
                import json

                # Use print() instead of console.print() to avoid Rich's line wrapping
                # which would break JSON structure with unescaped newlines
                print(
                    json.dumps(
                        {"success": result.success, "message": result.message},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            elif result.success:
                console.print(f"[bold green]✓[/bold green] {result.message}")
            else:
                console.print(f"[bold yellow]⚠[/bold yellow] {result.message}")
            raise typer.Exit(0 if result.success else 1)

    # Phase 2.3: CLI now uses AgentRuntime components (interceptor, presenter,
    # injector) while retaining direct UnifiedRouter access for detailed
    # OrchestrationResult handling (routing paths, layer details, execution plans).

    from vibesop.agent.runtime import AgentRuntime

    runtime = AgentRuntime(project_root=Path.cwd())
    # Inject LLM factory for AI triage (same as before)
    runtime.router.set_llm_factory(_build_llm_factory())

    # Apply CLI overrides to the underlying router config
    router = runtime.router._router
    if min_confidence is not None:
        router.routing_config = router.routing_config.model_copy(
            update={"min_confidence": min_confidence}
        )
    if no_session:
        router.routing_config = router.routing_config.model_copy(update={"session_aware": False})
    if strategy is not None:
        router.routing_config = router.routing_config.model_copy(
            update={"default_strategy": strategy}
        )

    # Enable routing trace if --trace flag is set
    if trace:
        router.enable_trace()

    # Build routing context with conversation ID for multi-turn support
    from vibesop.core.matching import RoutingContext

    context = RoutingContext()
    if conversation_id:
        context.conversation_id = conversation_id
    elif not no_session:
        # Auto-generate conversation ID from project path for continuity
        import hashlib

        project_hash = hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:8]
        context.conversation_id = f"cli-{project_hash}"

    # Apply workflow pattern and verification hints
    if pattern:
        context.strategy_hint = f"workflow_pattern:{pattern}"
    if verify:
        context.strategy_hint = f"{context.strategy_hint or ''} verify:{strictness}".strip()

    # Merge --explain alias into verbose flag for backward compatibility
    verbose = verbose or explain

    # Determine transparency mode: config value or CLI flags
    # --quiet forces compact; --verbose forces full even if config says compact
    router_config = router.routing_config
    transparency_mode = (
        "full"
        if verbose
        else "compact"
        if quiet
        else (
            router_config.transparency
            if router_config and hasattr(router_config, "transparency")
            else "full"
        )
    )

    # Use live progress display for interactive non-verbose, non-json mode
    use_live_progress = not verbose and not json_output and sys.stdin.isatty()

    # Phase 6: dispatch by interception mode
    if not decision.should_route:
        _print_fallback(query, decision.reason, json_output=json_output)
        raise typer.Exit(0)

    if decision.mode == InterceptionMode.SINGLE:
        routing_result = router.route(decision.query, context=context)
        result = router._to_orchestration_result(routing_result, decision.query)
    elif decision.mode == InterceptionMode.SINGLE_AGENT:
        enriched_ctx = _build_single_agent_context(context, decision)
        routing_result = router.route(decision.query, context=enriched_ctx)
        result = router._to_orchestration_result(routing_result, decision.query)
    elif decision.mode == InterceptionMode.MULTI_AGENT_SQUAD:
        enriched_ctx = _build_multi_agent_squad_context(context, decision)
        if use_live_progress:
            from vibesop.cli.progress import LiveOrchestrationCallbacks

            with LiveOrchestrationCallbacks(console=console) as callbacks:
                result = router.orchestrate(
                    decision.query, context=enriched_ctx, callbacks=callbacks
                )
        else:
            result = router.orchestrate(decision.query, context=enriched_ctx)
    elif decision.mode == InterceptionMode.ORCHESTRATE:
        if use_live_progress:
            from vibesop.cli.progress import LiveOrchestrationCallbacks

            with LiveOrchestrationCallbacks(console=console) as callbacks:
                result = router.orchestrate(decision.query, context=context, callbacks=callbacks)
        else:
            result = router.orchestrate(decision.query, context=context)
    # Unknown mode: fall back to orchestration for backward compatibility
    elif use_live_progress:
        from vibesop.cli.progress import LiveOrchestrationCallbacks

        with LiveOrchestrationCallbacks(console=console) as callbacks:
            result = router.orchestrate(decision.query, context=context, callbacks=callbacks)
    else:
        result = router.orchestrate(decision.query, context=context)

    # Phase 4: render Agent Squad summary when the plan contains a squad
    squad_already_rendered = False
    squad = _extract_squad_from_result(result)
    if squad is not None and not json_output:
        console.print(_format_squad_summary(squad, decision.analysis))
        squad_already_rendered = True

    # JSON output mode: skip all Rich rendering, write structured result to stdout
    if json_output:
        import json

        if minimal:
            # Minimal output for sub-agent consumption
            from vibesop.core.routing.lightweight_api import LightweightRouter

            # Re-use the orchestration result directly
            minimal_result = LightweightRouter._format_result(result)
            print(json.dumps(minimal_result, ensure_ascii=False))
        else:
            print(json.dumps(result.to_dict(), indent=2, default=str, ensure_ascii=False))
        # In JSON mode: exit 0 for successful routing (caller inspects has_match field).
        # A completed routing attempt is not an error even when no match found.
        raise typer.Exit(0)

    # Full transparency: show routing decision tree (default)
    already_rendered = squad_already_rendered
    if transparency_mode == "full":
        if result.mode.value == "single":
            from vibesop.core.models import RoutingResult

            routing_result = RoutingResult(
                primary=result.primary,
                alternatives=result.alternatives,
                routing_path=result.routing_path,
                layer_details=result.layer_details,
                query=result.original_query,
                duration_ms=result.duration_ms,
            )
            render_routing_report(routing_result, console=console, context=context)
        else:
            render_orchestration_result(result, console=console)
        already_rendered = True
    else:
        # Compact mode: show compact summary only
        render_compact_orchestration(result, console=console)

    # Show trace summary if --trace flag was used
    if trace and router.tracer.enabled:
        recent = router.tracer.list_traces(limit=1)
        if recent:
            t = recent[0]
            trace_id = t.get("trace_id", "")
            trace_file = Path.cwd() / ".vibe" / "traces" / f"{trace_id}.json"
            console.print()
            console.print("[bold cyan]🔍 Routing Trace[/bold cyan] [dim](SkillTree mode)[/dim]")
            console.print(f"  Trace ID: [cyan]{trace_id}[/cyan]")
            console.print(f"  Layers: [bold]{t.get('layer_count', 0)}[/bold] attempted")
            console.print(f"  Saved: [dim]{trace_file}[/dim]")
            console.print("  [dim]View full trace:[/dim] [cyan]vibe trace show {trace_id}[/cyan]")
            console.print()

    # Handle result with unified confirmation flow
    if result.mode.value == "orchestrated" and result.execution_plan:
        # Prompt chain generation (--pattern prompt_chain or auto-detected)
        plan = result.execution_plan
        from vibesop.core.models import WorkflowPattern

        if plan.workflow_pattern == WorkflowPattern.PROMPT_CHAIN or (
            pattern and pattern == "prompt_chain"
        ):
            _handle_prompt_chain_output(
                result,
                json_output,
                console,
                output_dir=output_dir,
            )
            return

        _handle_orchestrated_result(
            result,
            router,
            yes,
            execute,
            json_output,
            console,
            already_rendered=already_rendered,
            squad=squad,
        )
        return

    # Handle single-skill result
    _handle_single_result(
        result,
        router,
        yes,
        json_output,
        validate,
        console,
        already_rendered=already_rendered,
    )


@app.command()
def orchestrate(
    query: str = typer.Argument(..., help="Multi-intent query to orchestrate into sub-tasks"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show full decomposition and planning details"
    ),
    strategy: str | None = typer.Option(
        None,
        "--strategy",
        "-s",
        help="Force execution strategy: auto, sequential, parallel, hybrid",
    ),
    conversation_id: str | None = typer.Option(
        None,
        "--conversation",
        "-C",
        help="Conversation ID for multi-turn context",
    ),
    pattern: str | None = typer.Option(
        None,
        "--pattern",
        "-p",
        help="Force workflow pattern: sequential, parallel, fan_out, adversarial",
    ),
    verify: bool = typer.Option(
        False,
        "--verify",
        help="Enable adversarial verification for execution steps",
    ),
    strictness: str = typer.Option(
        "standard",
        "--strictness",
        help="Verification strictness: lenient, standard, strict",
    ),
) -> None:
    """Orchestrate a complex query into an execution plan.

    Detects multiple intents, decomposes the query, and generates
    a serial/parallel execution strategy.

    This is an explicit entry point for orchestration mode.
    For simple queries, use `vibe route` instead.
    """
    from pathlib import Path

    from vibesop.core.matching import RoutingContext
    from vibesop.core.routing import RoutingConfig, UnifiedRouter

    routing_kwargs: dict[str, Any] = {}
    if strategy is not None:
        routing_kwargs["default_strategy"] = strategy

    if routing_kwargs:
        config = RoutingConfig(**routing_kwargs)
        router = UnifiedRouter(
            project_root=Path.cwd(),
            config=config,
            llm_factory=_build_llm_factory(),
            prompt_builder=_build_prompt_builder(),
        )
    else:
        router = UnifiedRouter(
            project_root=Path.cwd(),
            llm_factory=_build_llm_factory(),
            prompt_builder=_build_prompt_builder(),
        )

    context = RoutingContext()
    if conversation_id:
        context.conversation_id = conversation_id
    else:
        import hashlib

        project_hash = hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:8]
        context.conversation_id = f"cli-{project_hash}"

    if pattern:
        context.strategy_hint = f"workflow_pattern:{pattern}"
    if verify:
        context.strategy_hint = f"{context.strategy_hint or ''} verify:{strictness}".strip()

    result = router.orchestrate(query, context=context)

    if json_output:
        import json

        print(json.dumps(result.model_dump(mode="json"), indent=2, default=str, ensure_ascii=False))
    elif verbose:
        render_orchestration_result(result, console=console)
    else:
        render_compact_orchestration(result, console=console)


@app.command()
def decompose(
    query: str = typer.Argument(..., help="Query to decompose into sub-tasks"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Decompose a query into sub-tasks without routing.

    Shows the detected intents and proposed sub-tasks,
    but does not match them to skills or build an execution plan.
    """
    from pathlib import Path

    from vibesop.core.orchestration import TaskDecomposer
    from vibesop.core.routing import UnifiedRouter

    router = UnifiedRouter(
        project_root=Path.cwd(),
        llm_factory=_build_llm_factory(),
        prompt_builder=_build_prompt_builder(),
    )
    decomposer = TaskDecomposer(llm_client=router.llm)
    skills = router.build_decomposition_skills(query=query)
    sub_tasks = decomposer.decompose(query, skills=skills)

    if json_output:
        import json

        console.print(
            json.dumps(
                {
                    "query": query,
                    "sub_tasks": [
                        {
                            "intent": t.intent,
                            "query": t.query,
                            "skill_id": t.skill_id,
                        }
                        for t in sub_tasks
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        if not sub_tasks:
            console.print(
                "[yellow]No sub-tasks detected — query appears to be single intent.[/yellow]"
            )
            return
        console.print(f"[bold]Decomposed '{query}' into {len(sub_tasks)} sub-tasks:[/bold]\n")
        for i, task in enumerate(sub_tasks, 1):
            skill_hint = f" → [magenta]{task.skill_id}[/magenta]" if task.skill_id else ""
            console.print(f"  {i}. [cyan]{task.intent}[/cyan] — {task.query}{skill_hint}")


def _handle_prompt_chain_output(
    result: Any,
    json_output: bool,
    console: Console,
    output_dir: str | None = None,
) -> None:
    """Generate and write prompt chain files for PROMPT_CHAIN pattern."""
    from vibesop.core.models import WorkflowPattern
    from vibesop.core.orchestration.prompt_chain_generator import PromptChainGenerator

    plan = result.execution_plan
    if not plan:
        console.print("[yellow]No execution plan available for prompt chain generation.[/yellow]")
        return

    # Override pattern if forced via --pattern flag
    if plan.workflow_pattern != WorkflowPattern.PROMPT_CHAIN:
        plan.workflow_pattern = WorkflowPattern.PROMPT_CHAIN

    target_dir = output_dir or ".vibe/prompts"

    generator = PromptChainGenerator(output_dir=target_dir)
    prompt_files = generator.generate(plan)

    if not prompt_files:
        console.print(
            "[yellow]Task does not require prompt chain (complexity too low). "
            "Using normal routing.[/yellow]"
        )
        return

    written = generator.write_files(prompt_files)

    if json_output:
        import json

        output = {
            "pattern": "prompt_chain",
            "plan_id": plan.plan_id,
            "total_phases": len(prompt_files),
            "output_dir": target_dir,
            "files": [
                {"phase": pf.phase, "filename": pf.filename, "path": str(p)}
                for pf, p in zip(prompt_files, written)
            ],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    # Rich display
    skill_count = len({s.skill_id for s in plan.steps})
    console.print()
    console.print(
        Panel(
            f"[bold]Complexity[/bold]    multi_agent\n"
            f"[bold]Pattern[/bold]       PROMPT_CHAIN\n"
            f"[bold]Skills[/bold]        {skill_count} ({', '.join(sorted({s.skill_id for s in plan.steps}))})\n"
            f"[bold]Output[/bold]        {target_dir} ({len(prompt_files)} files)",
            title="[bold cyan]🔍 Routing Summary[/bold cyan]",
            border_style="cyan",
        )
    )

    console.print()
    console.print("[bold]📋 Prompt Chain Generated[/bold]")
    for pf in prompt_files:
        phase_label = "Final" if pf.phase == -1 else f"Phase {pf.phase}"
        console.print(f"  {phase_label}: {pf.name} → {target_dir}/{pf.filename}")

    console.print()
    console.print("[bold green]⏩ 请在 Claude Code 中按顺序执行：[/bold green]")
    first_file = next((p for p in written if "phase-0" in p.name), written[0] if written else None)
    if first_file:
        console.print(f"   cat {first_file} | pbcopy")
        console.print("   # 然后粘贴到 Claude Code")


def _handle_orchestrated_result(
    result: Any,
    router: Any,
    yes: bool,
    execute: bool,
    json_output: bool,
    console: Console,
    already_rendered: bool = False,
    squad: Any | None = None,
) -> None:
    plan = result.execution_plan

    # 1. Confirmation flow (when needed)
    confirmed = _orchestration_confirmation_flow(
        result,
        yes,
        execute,
        json_output,
        console,
        router,
        already_rendered=already_rendered,
        squad=squad,
    )
    if not confirmed:
        return

    # 2. Interactive execution (--execute flag)
    if execute and plan:
        _execute_plan_interactive(result, console)
        return

    # 3. Post-processing: save plan, render output, collect feedback
    _orchestration_post_process(result, router, json_output, console)


def _orchestration_confirmation_flow(
    result: Any,
    yes: bool,
    execute: bool,
    json_output: bool,
    console: Console,
    router: Any,
    already_rendered: bool = False,
    squad: Any | None = None,
) -> bool:
    """Interactive confirmation for orchestrated result."""
    plan = result.execution_plan

    if not _needs_confirmation(result, router, yes, json_output, is_orchestrated=True):
        return True

    if not already_rendered:
        render_orchestration_result(result, console=console)

    choices = [
        questionary.Choice("✅ Confirm execution plan", value="confirm"),
        questionary.Choice("✏️  Edit steps", value="edit"),
        questionary.Choice(
            f"🔀 Use single skill: {result.single_fallback.skill_id if result.single_fallback else 'none'}",
            value="single",
        ),
        questionary.Choice("📝 Skip skills, use raw LLM", value="skip"),
    ]

    if squad is not None:
        choices = [
            questionary.Choice("✅ Execute squad", value="confirm"),
            questionary.Choice("✏️  Edit squad", value="edit"),
            questionary.Choice(
                f"🔀 Switch to single agent: {result.single_fallback.skill_id if result.single_fallback else 'none'}",
                value="single",
            ),
            questionary.Choice("📝 Skip", value="skip"),
        ]

    if execute and sys.stdin.isatty():
        choices.insert(1, questionary.Choice("▶️  Execute plan step-by-step", value="execute"))

    choice = questionary.select("How would you like to proceed?", choices=choices).ask()

    if choice == "edit":
        modified = _edit_execution_plan(result, console)
        if modified:
            render_orchestration_result(result, console=console)
            if not questionary.confirm("Proceed with updated plan?", default=True).ask():
                console.print("[dim]Plan editing cancelled.[/dim]")
                return False
            return True
        return False
    elif choice == "single" and result.single_fallback:
        console.print(
            Panel(
                f"[bold green]✅ Matched:[/bold green] {result.single_fallback.skill_id}\n"
                f"[dim]Confidence:[/dim] {result.single_fallback.confidence:.0%}",
                title="[bold]Single Skill Fallback[/bold]",
                border_style="blue",
            )
        )
        return False
    elif choice == "skip":
        console.print("[dim]Skipped. Using raw LLM.[/dim]")
        return False
    elif choice == "execute" and plan:
        _execute_plan_interactive(result, console)
        return False

    return True


def _orchestration_post_process(
    result: Any,
    router: Any,
    json_output: bool,
    console: Console,
) -> None:
    from pathlib import Path

    from vibesop.core.orchestration import PlanTracker

    plan = result.execution_plan
    tracker = PlanTracker(storage_dir=Path.cwd() / ".vibe")
    if plan:
        tracker.create_plan(plan)

    if json_output:
        import json

        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        render_orchestration_result(result, console=console)
        console.print("\n[dim]Plan saved. Track with:[/dim] [bold]vibe plan status[/bold]")

        if plan:
            from vibesop.core.orchestration import generate_execution_summary

            summary = generate_execution_summary(plan)
            console.print("\n[bold]Execution Summary:[/bold]")
            console.print(summary)

        if sys.stdin.isatty() and not json_output:
            _collect_feedback(result, router, console)


def _execute_plan_interactive(result: Any, console: Console) -> None:
    """Enter interactive step-by-step execution mode."""
    plan = result.execution_plan
    if not plan:
        console.print("[yellow]No execution plan available.[/yellow]")
        return

    from pathlib import Path

    from vibesop.agent.runtime.context_injector import StepContextInjector
    from vibesop.agent.runtime.plan_executor import PlanExecutor

    executor = PlanExecutor(project_root=Path.cwd())
    manifest = executor.build_manifest(plan)
    injector = StepContextInjector(project_root=Path.cwd())

    # Save plan and generate sequence file
    from vibesop.core.orchestration import PlanTracker

    tracker = PlanTracker(storage_dir=Path.cwd() / ".vibe")
    tracker.create_plan(plan)
    seq_file = injector.build_sequence_file(manifest)

    console.print(
        f"\n[bold green]▶ Execution Mode[/bold green] — Plan: [cyan]{plan.plan_id}[/cyan]"
    )
    console.print(f"[dim]Sequence file: {seq_file}[/dim]")
    console.print()

    step_outputs: dict[int, str] = {}

    for _step_index, step in enumerate(manifest.steps):
        step_num = step.step_number

        # Build context with upstream step outputs
        enriched_input = step.input_context
        for dep_num, dep_summary in sorted(step_outputs.items()):
            if dep_num < step_num:
                enriched_input = enriched_input or ""
                enriched_input += f"\n步骤 {dep_num} 的输出:\n{dep_summary}"

        console.print(f"{'─' * 60}")
        console.print(
            f"[bold]Step {step_num}/{manifest.total_steps}[/bold]: "
            f"[cyan]{step.skill_id}[/cyan] — {step.skill_name}"
        )
        console.print(f"[dim]{step.instruction}[/dim]")
        console.print()

        # Display embedded skill content
        if step.skill_content:
            console.print("[bold]Skill Content (SKILL.md):[/bold]")
            content_preview = step.skill_content[:800]
            if len(step.skill_content) > 800:
                content_preview += f"\n... ({len(step.skill_content) - 800} more chars)"
            console.print(Panel(content_preview, border_style="dim"))

        # Display upstream context if present
        if enriched_input:
            console.print("[bold]Input Context:[/bold]")
            console.print(Panel(enriched_input, border_style="blue"))

        console.print(
            f"[bold yellow]Completion marker:[/bold yellow] "
            f"[green]`<!-- {step.completion_marker} -->`[/green]"
        )
        console.print()

        # Non-interactive mode — just display and move on
        if not sys.stdin.isatty():
            console.print(
                "[dim](Non-interactive mode — skipping step confirmation. "
                "Run in a TTY for step-by-step execution.)[/dim]"
            )
            continue

        # Wait for completion confirmation
        choice = questionary.select(
            f"Step {step_num}/{manifest.total_steps} — {step.skill_id}",
            choices=[
                questionary.Choice("✅ Completed — proceed to next step", value="done"),
                questionary.Choice("⏭️  Skip this step", value="skip"),
                questionary.Choice("⏸️  Pause (exit execution mode)", value="pause"),
            ],
        ).ask()

        if choice == "skip":
            console.print(f"[dim]Step {step_num} skipped.[/dim]")
            continue
        elif choice == "pause":
            console.print(
                f"[dim]Execution paused at step {step_num}/{manifest.total_steps}. "
                f"Resume with: vibe plan status[/dim]"
            )
            break

        # Collect step output summary
        if sys.stdin.isatty():
            summary = questionary.text(
                f"Summary of step {step_num} output (or leave blank):",
            ).ask()
            if summary:
                injector.save_step_output(
                    plan_id=manifest.plan_id,
                    step_number=step_num,
                    summary=summary.strip(),
                    full_output=summary.strip(),
                    skill_id=step.skill_id,
                    marker=step.completion_marker,
                )
                step_outputs[step_num] = summary.strip()
                console.print(f"[green]✔ Step {step_num} output saved.[/green]")

        console.print()

    # Final summary
    console.print(f"{'═' * 60}")
    console.print("[bold green]Execution Complete[/bold green]")
    completed = len(step_outputs)
    console.print(f"Steps: {completed}/{manifest.total_steps} completed")
    console.print()

    if completed > 0:
        final_summary = injector.build_final_summary(manifest.plan_id, manifest)
        console.print(final_summary)
        console.print(f"\n[dim]All outputs saved to: .vibe/plans/{manifest.plan_id}/[/dim]")


def _render_validation(result: Any, router: Any, console: Console) -> None:
    console.print(f"\n[bold cyan]✓ Route Validation[/bold cyan]\n{'=' * 40}\n")
    caps = router.get_capabilities()
    console.print("[dim]Router capabilities:[/dim]")
    console.print(f"  Matchers: {len(caps['matchers'])}")
    for matcher_info in caps["matchers"]:
        console.print(f"    - {matcher_info['layer']}: {matcher_info['matcher']}")

    config = caps.get("config", {})
    console.print("\n[dim]Configuration:[/dim]")
    console.print(f"  min_confidence: {config.get('min_confidence', 0.3)}")
    console.print(f"  auto_select_threshold: {config.get('auto_select_threshold', 0.6)}")
    console.print(f"  enable_embedding: {config.get('enable_embedding', False)}")

    console.print(f"\n[bold]Testing query:[/bold] {result.original_query}\n")
    if result.primary is not None:
        console.print(f"  Primary: {result.primary.skill_id} ({result.primary.confidence:.0%})")
        console.print(f"  Layer: {result.primary.layer.value}")
    else:
        console.print("  [yellow]No match found[/yellow]")

    if result.alternatives:
        console.print("\n[bold]Alternatives:[/bold]")
        for i, alt in enumerate(result.alternatives[:5], 1):
            desc = f" — {alt.description[:50]}" if alt.description else ""
            console.print(f"  {i}. {alt.skill_id} - {alt.confidence:.0%}{desc}")

    console.print("\n[green]✓ Validation complete[/green]")
    raise typer.Exit(0)


def _handle_single_result(
    result: Any,
    router: Any,
    yes: bool,
    json_output: bool,
    validate: bool,
    console: Console,
    already_rendered: bool = False,
) -> None:
    if validate:
        _render_validation(result, router, console)

    # Confirmation flow (unified check)
    if _needs_confirmation(
        result, router, yes, json_output, validate=validate, is_orchestrated=False
    ):
        _run_confirmation_flow(result, console, already_rendered=already_rendered)

    # Output rendering
    if json_output:
        from vibesop.core.models import RoutingResult

        routing_result = RoutingResult(
            primary=result.primary,
            alternatives=result.alternatives,
            routing_path=result.routing_path,
            layer_details=result.layer_details,
            query=result.original_query,
            duration_ms=result.duration_ms,
        )
        import json

        print(json.dumps(routing_result.to_dict(), indent=2, ensure_ascii=False))
        return

    # Post-route retention check (every 20 routes)
    _check_stale_skills_post_route()


def _check_stale_skills_post_route() -> None:
    import json
    from pathlib import Path

    counter_file = Path.cwd() / ".vibe" / "routing_counter.json"
    counter: dict[str, Any] = {}
    if counter_file.exists():
        try:
            counter = json.loads(counter_file.read_text())
        except (json.JSONDecodeError, OSError):
            counter = {}

    routes_since = counter.get("routes_since_last_check", 0) + 1
    counter["routes_since_last_check"] = routes_since
    check_interval = counter.get("check_interval", 20)
    counter["check_interval"] = check_interval

    counter_file.parent.mkdir(parents=True, exist_ok=True)
    counter_file.write_text(json.dumps(counter, indent=2))

    if routes_since < check_interval:
        return

    try:
        from vibesop.core.skills.feedback_loop import FeedbackLoop

        loop = FeedbackLoop()
        suggestions = loop.analyze_all()
        critical = [s for s in suggestions if s.action in ("deprecate", "archive")]

        if critical:
            console.print()
            console.print(
                f"[yellow]💡 Tip:[/yellow] You have [bold]{len(critical)}[/bold] unused or "
                f"low-quality skills. Run [bold]vibe skill stale[/bold] to review."
            )
            console.print()

        counter["routes_since_last_check"] = 0
        counter_file.write_text(json.dumps(counter, indent=2))
    except Exception as e:
        logger.warning("Unhandled error: %s", e)


@app.command()
def doctor() -> None:
    """Check environment and configuration."""
    console.print("[bold]🔍 Checking VibeSOP environment...[/bold]\n")

    checks = [
        ("Python version", _check_python_version()),
        ("Dependencies", _check_dependencies()),
        ("Configuration", _check_config()),
        ("LLM Provider", _check_llm_provider()),
        ("Platform Integrations", _check_integrations()),
        ("Hook Status", _check_hooks()),
        ("Skill Health", _check_skill_health()),
    ]

    for name, (status, message) in checks:
        icon = (
            "✅" if status else "⚠️ " if name in ["Platform Integrations", "Hook Status"] else "❌"
        )
        color = (
            "green"
            if status
            else "yellow"
            if name in ["Platform Integrations", "Hook Status"]
            else "red"
        )
        console.print(f"{icon} [{color}]{name}[/{color}]: {message}")

    all_ok = all(status for status, _ in checks)
    if all_ok:
        console.print("\n[bold green]✨ All checks passed![/bold green]")
        raise typer.Exit(0)
    else:
        console.print("\n[bold red]⚠️  Some checks failed. Please fix the issues above.[/bold red]")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    console.print(
        Panel(
            f"[bold]VibeSOP[/bold] Python Edition\n\n"
            f"Version: {__version__}\n"
            f"Python: 3.12+\n"
            f"Pydantic: v2",
            title="[bold]Version Information[/bold]",
            border_style="blue",
        )
    )


@app.command()
def record(
    skill_id: str = typer.Argument(..., help="Skill ID that was selected"),
    query: str = typer.Argument(..., help="Original user query"),
    helpful: bool = typer.Option(True, "--helpful/--not-helpful", "-h/-H"),
) -> None:
    """Record a skill selection for preference learning."""
    router = UnifiedRouter()
    router.record_selection(skill_id, query, was_helpful=helpful)

    if helpful:
        console.print(f"[green]✓[/green] Recorded selection: [bold]{skill_id}[/bold]")
    else:
        console.print(
            f"[yellow]✓[/yellow] Recorded selection: [bold]{skill_id}[/bold] (not helpful)"
        )
    console.print("   This will improve future recommendations.")


@app.command("route-stats")
def route_stats() -> None:
    """Show routing statistics."""
    router = UnifiedRouter()
    stats = router.get_stats()

    console.print("[bold]📊 Routing Statistics[/bold]\n")
    total_routes = stats["total_routes"]
    console.print(f"Total routes: {total_routes}")

    if isinstance(total_routes, int) and total_routes > 0:
        console.print("\n[bold]Layer Distribution:[/bold]")
        layer_dist = stats["layer_distribution"]
        if isinstance(layer_dist, dict):
            for layer, count in layer_dist.items():
                pct = count / total_routes * 100
                console.print(f"  • {layer}: {count} ({pct:.0f}%)")

    console.print(f"\nCache: {stats.get('cache_dir', 'N/A')}")


@app.command("preferences")
def preferences() -> None:
    """Show preference learning statistics."""
    router = UnifiedRouter()
    stats = router.get_preference_stats()

    console.print("[bold]📊 Preference Learning Statistics[/bold]\n")
    console.print(f"Total selections: {stats['total_selections']}")
    console.print(f"Helpful rate: {stats['helpful_rate']:.1%}")
    console.print(f"Unique skills: {stats['unique_skills']}")

    top_skills = stats.get("top_skills")
    if isinstance(top_skills, list) and top_skills:
        console.print("\n[bold]Top Skills:[/bold]")
        for skill_id, count in top_skills[:5]:
            console.print(f"  • {skill_id}: {count} selections")

    console.print(f"\nStorage: {stats['storage_path']}")


@app.command("top-skills")
def top_skills(
    limit: int = typer.Option(5, "--limit", "-l", min=1, max=10),
) -> None:
    """Show most preferred skills."""
    router = UnifiedRouter()
    top = router.get_top_skills(limit=limit, min_selections=1)

    console.print(f"[bold]🏆 Top {len(top)} Preferred Skills[/bold]\n")
    for i, pref in enumerate(top, 1):
        bar_length = int(pref.score * 20)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        console.print(
            f"{i}. [bold cyan]{pref.skill_id}[/bold cyan]\n"
            f"   Score: [green]{pref.score:.1%}[/green]  "
            f"[dim]{bar}[/dim]\n"
            f"   Selected: {pref.selection_count}x  "
            f"Helpful: {pref.helpful_count}x"
        )


# -- Health check helpers --


def _check_python_version() -> tuple[bool, str]:
    version = sys.version_info
    if version >= (3, 12):
        return True, f"{version.major}.{version.minor}.{version.micro}"
    return False, f"{version.major}.{version.minor} (requires 3.12+)"


def _check_dependencies() -> tuple[bool, str]:
    missing: list[str] = []
    for module in ("pydantic", "typer", "rich"):
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    if missing:
        return False, f"Missing: {', '.join(missing)}"
    return True, "All dependencies installed"


def _check_config() -> tuple[bool, str]:
    config_dir = Path.cwd() / ".vibe"
    if config_dir.exists():
        return True, f"Found at {config_dir}"
    return False, "No .vibe directory found"


def _check_llm_provider() -> tuple[bool, str]:
    from vibesop.llm.models import (
        ANTHROPIC_DEFAULT_MODEL,
        OPENAI_DEFAULT_MODEL,
        PROVIDER_DEFAULT_MODELS,
        validate_provider_model,
    )

    # provider -> (env var holding its key, default model to validate)
    candidates = [
        ("anthropic", "ANTHROPIC_API_KEY", ANTHROPIC_DEFAULT_MODEL),
        ("openai", "OPENAI_API_KEY", OPENAI_DEFAULT_MODEL),
        ("deepseek", "DEEPSEEK_API_KEY", PROVIDER_DEFAULT_MODELS.get("deepseek", "")),
        ("kimi", "KIMI_API_KEY", PROVIDER_DEFAULT_MODELS.get("kimi", "")),
        ("zhipu", "ZHIPU_API_KEY", PROVIDER_DEFAULT_MODELS.get("zhipu", "")),
    ]
    for provider, key_env, model in candidates:
        key = os.getenv(key_env)
        if not key:
            continue
        # Best-effort live validation against the provider's /models catalog.
        # Fail-safe: a network/error skip never fails the check; only a confirmed
        # "model not in catalog" does (catches stale/hallucinated model IDs).
        ok, detail = validate_provider_model(provider, model, key)
        return ok, f"{provider.capitalize()} (key found; model {model!r}: {detail})"
    return (
        False,
        "No API key found (set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
        "DEEPSEEK_API_KEY, KIMI_API_KEY, or ZHIPU_API_KEY)",
    )


def _check_integrations() -> tuple[bool, str]:
    try:
        from vibesop.integrations import IntegrationManager

        manager = IntegrationManager()
        installed = manager.get_installed_integrations()
        total = len(manager.list_integrations())
        if installed:
            names = [info.name for info in installed]
            return True, f"{len(installed)}/{total} installed ({', '.join(names)})"
        return False, f"No integrations installed (0/{total})"
    except Exception as e:
        return False, f"Failed to check: {e}"


def _check_skill_health() -> tuple[bool, str]:
    try:
        from vibesop.integrations.health_monitor import SkillHealthMonitor

        monitor = SkillHealthMonitor()
        summary = monitor.get_health_summary()
        total = summary.get("total", 0)
        healthy = summary.get("healthy", 0)
        critical = summary.get("critical", 0)
        total_skills = summary.get("total_skills", 0)

        if critical > 0:
            return (
                False,
                f"{healthy}/{total} packs healthy, {critical} critical ({total_skills} skills)",
            )
        if healthy == 0 and total == 0:
            return False, "No skill packs detected"
        return True, f"{healthy}/{total} packs healthy ({total_skills} skills)"
    except Exception as e:
        return False, f"Failed to check: {e}"


def _check_hooks() -> tuple[bool, str]:
    try:
        from vibesop.installer import VibeSOPInstaller

        installer = VibeSOPInstaller()
        platforms = installer.list_platforms()
        results: list[str] = []
        for platform_info in platforms:
            platform_name: str = platform_info["name"]
            verify_result: dict[str, Any] = installer.verify(platform_name)
            if verify_result["installed"]:
                hooks_status: dict[str, Any] = verify_result.get("hooks_installed", {})
                hook_count = sum(1 for s in hooks_status.values() if s)
                total_hooks = len(hooks_status)
                results.append(f"{platform_name}: {hook_count}/{total_hooks}")
            else:
                results.append(f"{platform_name}: not installed")
        if results:
            return any("installed" not in r for r in results), "; ".join(results)
        return False, "No platforms checked"
    except Exception as e:
        return False, f"Failed to check: {e}"


# ── Phase 4: Agent Squad CLI helpers ─────────────────────────────────────────


def _extract_squad_from_result(result: Any) -> Any | None:
    """Return AgentSquad from an OrchestrationResult if present."""
    plan = getattr(result, "execution_plan", None)
    if plan is None:
        return None
    squad_data = plan.metadata.get("agent_squad") if hasattr(plan, "metadata") else None
    if not squad_data:
        return None
    from vibesop.core.models import AgentSquad

    return AgentSquad(**squad_data)


def _format_squad_summary(squad: Any, analysis: Any | None = None) -> str:
    """Format a human-readable Agent Squad summary for CLI output."""
    from vibesop.core.orchestration.agent_squad_composer import ROLE_METADATA

    role_icons = {
        "architect": "🏗️",
        "implementer": "💻",
        "reviewer": "👁️",
        "red_team": "🛡️",
        "debater": "⚡",
        "tester": "🧪",
        "orchestrator": "🎯",
        "documenter": "📝",
        "operator": "🚀",
    }

    lines: list[str] = []

    # Semantic analysis header
    if analysis is not None:
        lines.append("\n🔍 Semantic Analysis")
        lines.append("─────────────────────────────")
        lines.append(f"Mode         {getattr(analysis, 'complexity', 'unknown').upper()}")
        lines.append(f"Complexity   {getattr(analysis, 'complexity', 'unknown')}")
        lines.append(f"Confidence   {int(getattr(analysis, 'confidence', 0.0) * 100)}%")
        lines.append("")

    # Squad roster
    lines.append("🤖 Agent Squad")
    lines.append("─────────────────────────────")

    step_by_role: dict[str, Any] = {}
    for step in squad.steps:
        step_by_role[step.role_id] = step

    for role in squad.roles:
        icon = role_icons.get(role.role_id, "🤖")
        meta = ROLE_METADATA.get(role.role_id, {})
        name = meta.get("name", role.role_id)
        step = step_by_role.get(role.role_id)
        platform = step.agent_platform if step else "claude-code"
        skills = ", ".join(step.skill_ids[:3]) if step and step.skill_ids else "-"

        lines.append(f"  {icon}  {name} → {platform}")
        lines.append(f"     Skills: {skills}")

    # Protocol & rounds
    lines.append("")
    lines.append(f"🔄 Protocol: {squad.collaboration_protocol}")
    order_names = [
        step_by_role[rid].role_id if rid in step_by_role else rid for rid in squad.execution_order
    ]
    lines.append(f"   Round 1: {' → '.join(order_names)} → review")
    lines.append(f"   Max Rounds: {squad.max_rounds}")
    lines.append("")

    return "\n".join(lines)


# Register all subcommands
register(app)

if __name__ == "__main__":
    app()
