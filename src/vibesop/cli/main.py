"""VibeSOP CLI - Main entry point.

Built with Typer for modern CLI UX.

Note: v4.1.0 removed the `execute` command and `--run` flag from `route`.
Skills should be executed by AI Agents (Claude Code, OpenCode), not VibeSOP.
VibeSOP is a routing engine, not an executor.
"""

from __future__ import annotations

import importlib.util
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
    market_cmd,
    matcher_cmd,
    plan_cmd,
    skill_cmd,
    snapshot_cmd,
)
from vibesop.cli.commands.status_cmd import status as status_command
from vibesop.cli.confirmation import _needs_confirmation, _run_confirmation_flow
from vibesop.cli.feedback import _collect_feedback
from vibesop.cli.orchestration_report import render_orchestration_result
from vibesop.cli.plan_editor import _edit_execution_plan
from vibesop.cli.render import (
    render_compact_orchestration,
    render_fallback_panel,
    render_match_panel,
    render_no_match,
)
from vibesop.cli.routing_report import render_routing_report
from vibesop.cli.subcommands import register
from vibesop.core.routing import UnifiedRouter

app = typer.Typer(
    name="vibe",
    help="VibeSOP - AI-powered workflow SOP",
    no_args_is_help=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def _default_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", help="Show version and exit"
    ),
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
app.add_typer(skill_cmd.app, name="skill")
app.add_typer(snapshot_cmd.app, name="snapshot")


@app.command()
def status(
    no_color: bool = typer.Option(
        False, "--no-color", help="Disable colored output"
    ),
) -> None:
    """Show a unified snapshot of your VibeSOP skill ecosystem."""
    status_command(no_color=no_color)


# -- Core routing commands --


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
) -> None:
    """Route a query to the appropriate skill using unified routing.

    VibeSOP is a routing engine - it tells you which skill to use,
    but does not execute skills. Use your AI Agent (Claude Code, OpenCode)
    to execute the recommended skill.

    By default, VibeSOP asks for confirmation before selecting a skill.
    Set routing.confirmation_mode to 'never' for automatic selection,
    or use --yes to skip once.

    Use --verbose to inspect the full routing decision tree.
    Use --slash to invoke a quick command explicitly (e.g., --slash '/vibe-help').
    """
    from pathlib import Path

    # -- Route through IntentInterceptor to respect full Agent Runtime logic --
    from vibesop.agent.runtime import IntentInterceptor, InterceptionMode, SlashCommandExecutor
    from vibesop.core.routing import RoutingConfig, UnifiedRouter

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
                print(json.dumps({"success": result.success, "message": result.message}, indent=2, ensure_ascii=False))
            elif result.success:
                console.print(f"[bold green]✓[/bold green] {result.message}")
            else:
                console.print(f"[bold yellow]⚠[/bold yellow] {result.message}")
            raise typer.Exit(0 if result.success else 1)

    # Set up router with optional overrides
    routing_kwargs: dict[str, Any] = {}
    if min_confidence is not None:
        routing_kwargs["min_confidence"] = min_confidence
    if no_session:
        routing_kwargs["session_aware"] = False
    if strategy is not None:
        routing_kwargs["default_strategy"] = strategy

    if routing_kwargs:
        config = RoutingConfig(**routing_kwargs)
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
    else:
        router = UnifiedRouter(project_root=Path.cwd())

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

    # Merge --explain alias into verbose flag for backward compatibility
    verbose = verbose or explain

    # Determine transparency mode: config value or CLI flags
    # --quiet forces compact; --verbose forces full even if config says compact
    router_config = router._config
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

    if use_live_progress:
        from vibesop.cli.progress import LiveOrchestrationCallbacks

        with LiveOrchestrationCallbacks(console=console) as callbacks:
            result = router.orchestrate(query, context=context, callbacks=callbacks)
    else:
        result = router.orchestrate(query, context=context)

    # JSON output mode: skip all Rich rendering, write structured result to stdout
    if json_output:
        import json

        print(json.dumps(result.to_dict(), indent=2, default=str, ensure_ascii=False))
        raise typer.Exit(0 if result.has_match else 1)

    # Full transparency: show routing decision tree (default)
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
        raise typer.Exit(0)

    # Compact mode: show compact summary only
    render_compact_orchestration(result, console=console)

    # Handle result with unified confirmation flow
    if result.mode.value == "orchestrated" and result.execution_plan:
        _handle_orchestrated_result(result, router, yes, execute, json_output, console)
        return

    # Handle single-skill result
    _handle_single_result(result, router, yes, json_output, validate, console)


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
        router = UnifiedRouter(project_root=Path.cwd(), config=config)
    else:
        router = UnifiedRouter(project_root=Path.cwd())

    context = RoutingContext()
    if conversation_id:
        context.conversation_id = conversation_id
    else:
        import hashlib

        project_hash = hashlib.sha256(str(Path.cwd()).encode()).hexdigest()[:8]
        context.conversation_id = f"cli-{project_hash}"

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

    router = UnifiedRouter(project_root=Path.cwd())
    llm = getattr(router, "_llm", None)
    decomposer = TaskDecomposer(llm_client=llm)
    sub_tasks = decomposer.decompose(query)

    if json_output:
        import json

        console.print(
            json.dumps(
                {
                    "query": query,
                    "sub_tasks": [{"intent": t.intent, "query": t.query} for t in sub_tasks],
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
            console.print(f"  {i}. [cyan]{task.intent}[/cyan] — {task.query}")


def _handle_orchestrated_result(
    result: Any,
    router: Any,
    yes: bool,
    execute: bool,
    json_output: bool,
    console: Console,
) -> None:
    """Handle multi-step orchestration result with confirmation.

    When --execute is passed, after confirmation the CLI enters
    interactive step-by-step execution mode.
    """
    plan = result.execution_plan

    # Use unified confirmation check
    if _needs_confirmation(result, router, yes, json_output, is_orchestrated=True):
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

        # Add execute option when --execute flag is active
        if execute and sys.stdin.isatty():
            choices.insert(1, questionary.Choice("▶️  Execute plan step-by-step", value="execute"))

        choice = questionary.select(
            "How would you like to proceed?",
            choices=choices,
        ).ask()

        if choice == "edit":
            modified = _edit_execution_plan(result, console)
            if modified:
                render_orchestration_result(result, console=console)
                confirm = questionary.confirm(
                    "Proceed with updated plan?",
                    default=True,
                ).ask()
                if not confirm:
                    console.print("[dim]Plan editing cancelled.[/dim]")
                    return
            else:
                return
        elif choice == "single" and result.single_fallback:
            console.print(
                Panel(
                    f"[bold green]✅ Matched:[/bold green] {result.single_fallback.skill_id}\n"
                    f"[dim]Confidence:[/dim] {result.single_fallback.confidence:.0%}",
                    title="[bold]Single Skill Fallback[/bold]",
                    border_style="blue",
                )
            )
            return
        elif choice == "skip":
            console.print("[dim]Skipped. Using raw LLM.[/dim]")
            return
        elif choice == "execute":
            if plan:
                _execute_plan_interactive(result, console)
            return

    # --execute mode without confirmation prompt (--yes passed)
    if execute and plan:
        _execute_plan_interactive(result, console)
        return

    # Save plan to tracker
    from vibesop.core.orchestration import PlanTracker

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
    """Enter interactive step-by-step execution mode.

    For each step in the orchestration plan:
    1. Display the step's instruction with embedded SKILL.md content
    2. Present a prompt with the full step context
    3. Wait for user/agent confirmation of completion
    4. Save the step output for downstream steps
    5. Automatically generate the next step's prompt with upstream context
    """
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
    """Render validation output and exit."""
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
) -> None:
    """Handle single-skill routing result."""
    # Validation mode
    if validate:
        _render_validation(result, router, console)

    # Confirmation flow (unified check)
    if _needs_confirmation(
        result, router, yes, json_output, validate=validate, is_orchestrated=False
    ):
        _run_confirmation_flow(result, console)

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

        if result.primary is None:
            render_no_match(result, console)
        elif result.primary.layer.value == "fallback_llm":
            render_fallback_panel(result, console)
        else:
            render_match_panel(result, console)

    # Post-route retention check (every 20 routes)
    _check_stale_skills_post_route()


def _check_stale_skills_post_route() -> None:
    """Check for stale skills every N routes and prompt user if needed."""
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
    except Exception:
        pass


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
    if os.getenv("ANTHROPIC_API_KEY"):
        return True, "Anthropic (API key found)"
    if os.getenv("OPENAI_API_KEY"):
        return True, "OpenAI (API key found)"
    if os.getenv("KIMI_API_KEY"):
        return True, "Kimi / Moonshot (API key found)"
    return False, "No API key found (set ANTHROPIC_API_KEY, OPENAI_API_KEY, or KIMI_API_KEY)"


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
            verify_result: dict[str, Any] = installer.verify(platform_name)  # type: ignore[reportUnknownVariableType]
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


# Register all subcommands
register(app)

if __name__ == "__main__":
    app()
