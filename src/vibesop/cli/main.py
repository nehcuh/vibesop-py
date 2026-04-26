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
from typing import TYPE_CHECKING, Any

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
from vibesop.cli.orchestration_report import render_orchestration_result
from vibesop.cli.render import (
    render_compact_orchestration,
    render_fallback_panel,
    render_match_panel,
    render_no_match,
)
from vibesop.cli.routing_report import render_routing_report
from vibesop.cli.subcommands import register
from vibesop.core.routing import UnifiedRouter

if TYPE_CHECKING:
    from vibesop.core.models import OrchestrationResult

app = typer.Typer(
    name="vibe",
    help="VibeSOP - AI-powered workflow SOP",
    no_args_is_help=True,
)
console = Console()

# Register subcommands
app.add_typer(plan_cmd.app, name="plan")
app.add_typer(matcher_cmd.app, name="matcher")
app.add_typer(deviation_cmd.app, name="deviation")
app.add_typer(badges_cmd.app, name="badges")
app.add_typer(market_cmd.app, name="market")
app.add_typer(skill_cmd.app, name="skill")
app.add_typer(snapshot_cmd.app, name="snapshot")


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
    slash: bool = typer.Option(False, "--slash", help="Treat query as a quick command (e.g., --slash '/vibe-help')"),
    validate: bool = typer.Option(False, "--validate", "-V", help="Validate routing configuration"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full routing decision tree with per-layer details"),
    explain: bool = typer.Option(False, "--explain", "-e", help="Alias for --verbose (backward compatibility)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt (alias for confirmation_mode=never)"),
    no_session: bool = typer.Option(False, "--no-session", help="Disable session-state-aware routing for this query"),
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
            console.print(json.dumps({"success": result.success, "message": result.message, "command": result.command}, indent=2))
        elif result.success:
            console.print(f"[bold green]✓[/bold green] {result.message}")
        else:
            console.print(f"[bold yellow]⚠[/bold yellow] {result.message}")
        raise typer.Exit(0 if result.success else 1)

    interceptor = IntentInterceptor()
    decision = interceptor.should_intercept(query)

    if decision.mode == InterceptionMode.SLASH_COMMAND:
        executor = SlashCommandExecutor()
        result = executor.execute(decision)

        if json_output:
            import json
            console.print(json.dumps({"success": result.success, "message": result.message}, indent=2))
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

    # Use live progress display for interactive non-verbose, non-json mode
    use_live_progress = not verbose and not json_output and sys.stdin.isatty()

    if use_live_progress:
        from vibesop.cli.progress import LiveOrchestrationCallbacks
        with LiveOrchestrationCallbacks(console=console) as callbacks:
            result = router.orchestrate(query, context=context, callbacks=callbacks)
    else:
        result = router.orchestrate(query, context=context)

    # --verbose mode: show full decision tree and exit
    if verbose:
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

    # Default: show compact summary directly from OrchestrationResult
    render_compact_orchestration(result, console=console)

    # Handle result with unified confirmation flow
    if result.mode.value == "orchestrated" and result.execution_plan:
        _handle_orchestrated_result(result, router, yes, json_output, console)
        return

    # Handle single-skill result
    _handle_single_result(result, router, yes, json_output, validate, console)


@app.command()
def orchestrate(
    query: str = typer.Argument(..., help="Multi-intent query to orchestrate into sub-tasks"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full decomposition and planning details"),
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
        console.print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
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
        console.print(json.dumps(
            {"query": query, "sub_tasks": [{"intent": t.intent, "query": t.query} for t in sub_tasks]},
            indent=2,
            ensure_ascii=False,
        ))
    else:
        if not sub_tasks:
            console.print("[yellow]No sub-tasks detected — query appears to be single intent.[/yellow]")
            return
        console.print(f"[bold]Decomposed '{query}' into {len(sub_tasks)} sub-tasks:[/bold]\n")
        for i, task in enumerate(sub_tasks, 1):
            console.print(f"  {i}. [cyan]{task.intent}[/cyan] — {task.query}")


def _edit_execution_plan(
    result: Any,
    console: Console,
) -> bool:
    """Interactive execution plan editor.

    Returns True if plan was modified, False otherwise.
    """
    plan = result.execution_plan
    if plan is None or not plan.steps:
        console.print("[yellow]No steps to edit.[/yellow]")
        return False

    steps = list(plan.steps)
    while True:
        console.print("\n[bold]✏️  Edit Execution Plan[/bold]\n")
        for i, step in enumerate(steps, 1):
            marker = "  "
            console.print(f"  {marker}{i}. {step.skill_id} — {step.intent}")

        action = questionary.select(
            "Choose an action:",
            choices=[
                questionary.Choice("↑ Move step up", value="up"),
                questionary.Choice("↓ Move step down", value="down"),
                questionary.Choice("✗ Remove step", value="remove"),
                questionary.Choice("✓ Done editing", value="done"),
                questionary.Choice("↩️  Cancel", value="cancel"),
            ],
        ).ask()

        if action in ("done", None):
            if not steps:
                console.print("[yellow]⚠️  Plan has no steps. Edit cancelled.[/yellow]")
                return False
            plan.steps = steps
            # Re-number steps
            for i, step in enumerate(steps, 1):
                step.step_number = i
            console.print("[green]✓ Plan updated[/green]")
            return True
        elif action == "cancel":
            console.print("[dim]Edit cancelled.[/dim]")
            return False
        elif action == "up":
            idx = questionary.select(
                "Select step to move up:",
                choices=[
                    questionary.Choice(f"{s.step_number}. {s.skill_id}", value=i)
                    for i, s in enumerate(steps)
                ],
            ).ask()
            if idx is not None and idx > 0:
                steps[idx - 1], steps[idx] = steps[idx], steps[idx - 1]
        elif action == "down":
            idx = questionary.select(
                "Select step to move down:",
                choices=[
                    questionary.Choice(f"{s.step_number}. {s.skill_id}", value=i)
                    for i, s in enumerate(steps)
                ],
            ).ask()
            if idx is not None and idx < len(steps) - 1:
                steps[idx + 1], steps[idx] = steps[idx], steps[idx + 1]
        elif action == "remove":
            idx = questionary.select(
                "Select step to remove:",
                choices=[
                    questionary.Choice(f"{s.step_number}. {s.skill_id}", value=i)
                    for i, s in enumerate(steps)
                ],
            ).ask()
            if idx is not None and len(steps) > 1:
                removed = steps.pop(idx)
                console.print(f"[dim]Removed step: {removed.skill_id}[/dim]")
            elif idx is not None:
                console.print("[yellow]Cannot remove the last step.[/yellow]")


def _handle_orchestrated_result(
    result: Any,
    router: Any,
    yes: bool,
    json_output: bool,
    console: Console,
) -> None:
    """Handle multi-step orchestration result with confirmation."""
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

        choice = questionary.select(
            "How would you like to proceed?",
            choices=choices,
        ).ask()

        if choice == "edit":
            modified = _edit_execution_plan(result, console)
            if modified:
                # Re-render after edit
                render_orchestration_result(result, console=console)
                # Ask for confirmation again
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
            # Switch to single-skill mode
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

    # Save plan to tracker
    from vibesop.core.orchestration import PlanTracker
    tracker = PlanTracker(storage_dir=Path.cwd() / ".vibe")
    if plan:
        tracker.create_plan(plan)

    if json_output:
        import json
        console.print(json.dumps(result.to_dict(), indent=2))
    else:
        render_orchestration_result(result, console=console)
        console.print("\n[dim]Plan saved. Track with:[/dim] [bold]vibe plan status[/bold]")

        # Generate and display execution summary
        if plan:
            from vibesop.core.orchestration import generate_execution_summary
            summary = generate_execution_summary(plan)
            console.print("\n[bold]Execution Summary:[/bold]")
            console.print(summary)

        # Collect user feedback for continuous improvement
        if sys.stdin.isatty() and not json_output:
            _collect_feedback(result, router, console)


def _collect_feedback(
    result: OrchestrationResult,
    router: Any,
    console: Console,
) -> None:
    """Collect user satisfaction feedback after orchestration.

    Routes feedback into PreferenceBooster for closed-loop improvement.
    """
    try:
        feedback = questionary.select(
            "Did this decomposition match your intent?",
            choices=[
                questionary.Choice("👍 Yes, perfect", value="yes"),
                questionary.Choice("🤔 Mostly, but could be improved", value="partial"),
                questionary.Choice("👎 No, wrong decomposition", value="no"),
                questionary.Choice("Skip", value="skip"),
            ],
        ).ask()

        if feedback == "skip":
            return

        satisfied = feedback == "yes"
        partial = feedback == "partial"

        # Record feedback to analytics
        from vibesop.core.analytics import AnalyticsStore
        store = AnalyticsStore()
        records = store.list_records(limit=1)
        if records:
            record = records[0]
            record.user_satisfied = satisfied
            record.user_modified = partial
            store.record(record)

        # Closed loop: feed positive feedback into PreferenceBooster
        if satisfied and result.execution_plan:
            import contextlib
            for step in result.execution_plan.steps:
                with contextlib.suppress(Exception):
                    router.record_selection(step.skill_id, result.original_query, was_helpful=True)

        if not satisfied:
            console.print("[dim]Thanks for the feedback. We'll use this to improve routing.[/dim]")
            record_deviation = questionary.confirm(
                "Would you like to record this as a routing deviation for analysis?",
                default=False,
            ).ask()
            if record_deviation:
                console.print("[dim]Use: vibe deviation record \"<query>\" \"<skill>\" <confidence> \"<layer>\"[/dim]")
    except Exception:
        pass


def _needs_confirmation(
    result: Any,
    router: Any,
    yes: bool,
    json_output: bool,
    validate: bool = False,
    is_orchestrated: bool = False,
) -> bool:
    """Determine if user confirmation is needed for a routing result.

    Unified confirmation check for both single-skill and orchestrated results.

    Args:
        result: The routing result (single or orchestrated)
        router: The router instance
        yes: If True, skip confirmation
        json_output: If True, skip confirmation (machine-readable output)
        validate: If True, skip confirmation (validation mode)
        is_orchestrated: If True, this is an orchestrated result

    Returns:
        True if user confirmation is needed
    """
    # Skip if explicitly requested or non-interactive
    if yes or json_output or validate:
        return False

    confirmation_mode = router._config.confirmation_mode

    # Skip if confirmation disabled or not in a TTY
    if confirmation_mode == "never" or not sys.stdin.isatty():
        return False

    # For orchestrated results, confirm unless all steps are high confidence
    if is_orchestrated:
        if confirmation_mode == "ambiguous_only" and result.execution_plan:
            all_confident = all(
                step.confidence >= router._config.auto_select_threshold
                for step in result.execution_plan.steps
                if hasattr(step, "confidence")
            )
            return not all_confident
        return True

    # For single results, skip if high confidence and mode is 'ambiguous_only'
    return not (
        confirmation_mode == "ambiguous_only"
        and result.primary
        and result.primary.confidence >= router._config.auto_select_threshold
    )


def _run_confirmation_flow(
    result: Any,
    console: Console,
) -> None:
    """Interactive confirmation: confirm / alternative / skip."""
    from vibesop.core.models import RoutingResult
    routing_result = RoutingResult(
        primary=result.primary,
        alternatives=result.alternatives,
        routing_path=result.routing_path,
        layer_details=result.layer_details,
        query=result.original_query,
        duration_ms=result.duration_ms,
    )
    render_routing_report(routing_result, console=console)

    choices = [
        questionary.Choice("✅ Confirm selected skill", value="confirm"),
        questionary.Choice("🔀 Choose a different skill", value="alternative"),
        questionary.Choice("📝 Skip skill, use raw LLM", value="skip"),
    ]
    choice = questionary.select("How would you like to proceed?", choices=choices).ask()

    if choice == "alternative" and result.alternatives:
        alt_choices = [
            questionary.Choice(
                f"{alt.skill_id} ({alt.confidence:.0%} via {alt.layer.value})"
                f"{(' — ' + alt.description[:40]) if alt.description else ''}",
                value=alt.skill_id,
            )
            for alt in result.alternatives[:5]
        ]
        alt_choices.append(questionary.Choice("↩️  Back", value="back"))
        alt_id = questionary.select("Select a skill:", choices=alt_choices).ask()

        if alt_id == "back":
            pass
        elif alt_id:
            for alt in result.alternatives:
                if alt.skill_id == alt_id:
                    result.primary = alt
                    break
    elif choice == "skip":
        result.primary = None


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
    if _needs_confirmation(result, router, yes, json_output, validate=validate, is_orchestrated=False):
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
        console.print(json.dumps(routing_result.to_dict(), indent=2))
        return

    if result.primary is None:
        render_no_match(result, console)
    elif result.primary.layer.value == "fallback_llm":
        render_fallback_panel(result, console)
    else:
        render_match_panel(result, console)

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
            return False, f"{healthy}/{total} packs healthy, {critical} critical ({total_skills} skills)"
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
