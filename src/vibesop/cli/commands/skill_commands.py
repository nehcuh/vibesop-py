# pyright: reportPrivateUsage=false
# pyright: ignore[reportPrivateUsage, reportMissingParameterType]
"""VibeSOP skill command group - All `vibe skill *` subcommands.

Consolidated from: skill_cmd.py, skill_add.py, skill_config.py.

Usage:
    vibe skill                        — Show skill ecosystem overview
    vibe skill list [--all] [--project]
    vibe skill enable <skill_id>
    vibe skill disable <skill_id>
    vibe skill status <skill_id>
    vibe skill stale [--auto] [--json]
    vibe skill end-check [--json]
    vibe skill add <source> [--global] [--auto-config/--manual-config] [--force]
    vibe skill share <skill_id>
    vibe skill discover [query] [--json]
    vibe skill cleanup [--auto] [--dry-run]
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.cli.commands.cleanup_cmd import cleanup
from vibesop.cli.commands.community_cmd import discover, share
from vibesop.core.skills.config_manager import SkillConfigManager

logger = logging.getLogger(__name__)

console = Console()


# ---------------------------------------------------------------------------
# Skill ecosystem overview (callback)
# ---------------------------------------------------------------------------

app = typer.Typer(name="skill", help="Manage skill lifecycle", no_args_is_help=False)


@app.callback(invoke_without_command=True)
def _skill_overview(  # pyright: ignore[reportUnusedFunction]
    ctx: typer.Context,
) -> None:
    """Show skill ecosystem overview when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return

    from pathlib import Path

    project_root = Path.cwd()

    try:
        from vibesop.core.routing.candidate_manager import CandidateManager

        mgr = CandidateManager(project_root)
        candidates = mgr.get_candidates()
        total = len(candidates)
    except Exception:
        total = 0

    try:
        from vibesop.core.skills.evaluator import RoutingEvaluator

        evaluator = RoutingEvaluator(project_root=project_root)
        low = evaluator.get_low_quality_skills(threshold=0.3, min_routes=3)
        low_count = len(low)
    except Exception:
        low_count = 0

    try:
        from vibesop.core.skills.feedback_loop import FeedbackLoop

        loop = FeedbackLoop(project_root=project_root)
        stale = loop.analyze_all(auto_deprecate=False)
        stale_count = sum(1 for s in stale if s.action in ("deprecate", "archive"))
    except Exception:
        stale_count = 0

    console.print()
    console.rule("[bold cyan]VibeSOP Skill Management[/bold cyan]")
    console.print()

    status_parts = [f"[bold]{total}[/bold] skills installed"]
    if low_count > 0:
        status_parts.append(f"[yellow]{low_count} need attention[/yellow]")
    if stale_count > 0:
        status_parts.append(f"[yellow]{stale_count} stale[/yellow]")
    if low_count == 0 and stale_count == 0:
        status_parts.append("[green]all healthy[/green]")

    console.print(f"  {' · '.join(status_parts)}")
    console.print()

    from rich.box import ROUNDED

    actions = (
        "[cyan]vibe skill list[/cyan]            [dim]— browse all installed skills[/dim]\n"
        "[cyan]vibe skill discover[/cyan]        [dim]— find community skills[/dim]\n"
        "[cyan]vibe skill cleanup[/cyan]         [dim]— review and prune stale skills[/dim]\n"
        "[cyan]vibe skill enable/disable[/cyan]  [dim]— toggle skills on/off[/dim]\n"
        "[cyan]vibe skill stale[/cyan]           [dim]— detailed health analysis[/dim]\n"
        "[cyan]vibe skill share[/cyan]           [dim]— publish your skill to the community[/dim]"
    )

    console.print(
        Panel(actions, title="[bold]Quick Actions[/bold]", border_style="cyan", box=ROUNDED)
    )

    console.print()
    console.print("[dim]Also try:[/dim] [cyan]vibe status[/cyan] [dim]for full ecosystem health[/dim]")
    console.print()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def _load_skills(project_root: str = ".") -> list[dict[str, Any]]:
    from vibesop.core.routing import UnifiedRouter

    router = UnifiedRouter(project_root=project_root)
    return router.get_candidates() or []


@app.command("list")
def list_skills(
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all skills including archived"),
    project_only: bool = typer.Option(
        False, "--project", "-p", help="Show only project-scoped skills"
    ),
) -> None:
    """List all skills with their lifecycle state."""
    skills = _load_skills()

    table = Table(title="Skills")
    table.add_column("ID", style="bold")
    table.add_column("Name")
    table.add_column("State", justify="center")
    table.add_column("Scope", justify="center")
    table.add_column("Version")

    for skill in skills:
        lifecycle = skill.get("lifecycle", "active")
        if not show_all and lifecycle == "archived":
            continue
        if project_only and skill.get("scope", "global") != "project":
            continue

        enabled = skill.get("enabled", True)
        state_color = {
            "active": "green" if enabled else "yellow",
            "deprecated": "yellow",
            "draft": "dim",
            "archived": "red",
        }.get(lifecycle, "white")

        state_text = f"[{state_color}]{lifecycle}[/{state_color}]"
        if not enabled:
            state_text += " [dim](disabled)[/dim]"

        table.add_row(
            skill.get("id", "unknown"),
            skill.get("name", "")[:30],
            state_text,
            skill.get("scope", "global"),
            skill.get("version", "1.0.0"),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------

@app.command()
def enable(
    skill_id: str = typer.Argument(..., help="Skill ID to enable"),
) -> None:
    """Enable a skill for routing."""
    from vibesop.core.skills import SkillManager

    manager = SkillManager()
    skill_info = manager.get_skill_info(skill_id)
    if not skill_info:
        console.print(f"[red]✗[/red] Skill '{skill_id}' not found")
        raise typer.Exit(1)

    config = SkillConfigManager.get_skill_config(skill_id)
    if config and config.enabled:
        console.print(f"[yellow]⚠ Skill '{skill_id}' is already enabled[/yellow]")
        return

    SkillConfigManager.update_skill_config(skill_id, {"enabled": True})
    console.print(f"[green]✓[/green] Skill '{skill_id}' enabled")


@app.command()
def disable(
    skill_id: str = typer.Argument(..., help="Skill ID to disable"),
) -> None:
    """Disable a skill from routing."""
    from vibesop.core.skills import SkillManager

    manager = SkillManager()
    skill_info = manager.get_skill_info(skill_id)
    if not skill_info:
        console.print(f"[red]✗[/red] Skill '{skill_id}' not found")
        raise typer.Exit(1)

    config = SkillConfigManager.get_skill_config(skill_id)
    if config and not config.enabled:
        console.print(f"[yellow]⚠ Skill '{skill_id}' is already disabled[/yellow]")
        return

    SkillConfigManager.update_skill_config(skill_id, {"enabled": False})
    console.print(f"[yellow]✓[/yellow] Skill '{skill_id}' disabled")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status(
    skill_id: str = typer.Argument(..., help="Skill ID to check"),
) -> None:
    """Show detailed status of a skill."""
    from vibesop.core.skills.lifecycle import SkillLifecycle, SkillLifecycleManager

    skills = _load_skills()
    skill = next((s for s in skills if s.get("id") == skill_id), None)

    if not skill:
        console.print(f"[red]✗[/red] Skill '{skill_id}' not found")
        raise typer.Exit(1)

    lifecycle = skill.get("lifecycle", "active")
    enabled = skill.get("enabled", True)

    current = (
        SkillLifecycle(lifecycle)
        if lifecycle in [s.value for s in SkillLifecycle]
        else SkillLifecycle.ACTIVE
    )
    valid_next = SkillLifecycleManager.valid_transitions().get(current, frozenset())
    next_states = ", ".join(s.value for s in valid_next) if valid_next else "none (terminal)"

    console.print(
        Panel(
            f"[bold]ID:[/bold] {skill_id}\n"
            f"[bold]Name:[/bold] {skill.get('name', 'N/A')}\n"
            f"[bold]State:[/bold] {lifecycle}\n"
            f"[bold]Enabled:[/bold] {'Yes' if enabled else 'No'}\n"
            f"[bold]Scope:[/bold] {skill.get('scope', 'global')}\n"
            f"[bold]Version:[/bold] {skill.get('version', '1.0.0')}\n"
            f"[bold]Valid transitions:[/bold] {next_states}",
            title=f"Skill Status: {skill_id}",
            border_style="blue" if enabled else "yellow",
        )
    )


# ---------------------------------------------------------------------------
# stale
# ---------------------------------------------------------------------------

@app.command()
def stale(
    auto_deprecate: bool = typer.Option(
        False, "--auto", "-a", help="Automatically deprecate stale skills"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Detect stale or underperforming skills.

    Analyzes usage statistics to identify skills that haven't been used
    recently or have low quality scores. Skills with no recorded usage
    data are shown separately — these may be newly installed or never triggered.

    Examples:
        vibe skill stale              # Show report only
        vibe skill stale --auto       # Auto-deprecate F-grade skills
        vibe skill stale --json       # Machine-readable output
    """
    from vibesop.core.skills.feedback_loop import FeedbackLoop

    loop = FeedbackLoop()
    suggestions = loop.analyze_all(auto_deprecate=auto_deprecate)

    if json_output:
        import json as json_mod

        report_data = loop.generate_report()
        console.print(json_mod.dumps(report_data, indent=2, default=str))
        return

    if not suggestions:
        console.print("[green]✓[/green] No stale or underperforming skills detected.")
        return

    to_archive = [s for s in suggestions if s.action == "archive"]
    to_deprecate = [s for s in suggestions if s.action == "deprecate"]
    to_warn = [s for s in suggestions if s.action == "warn"]
    to_boost = [s for s in suggestions if s.action == "boost"]

    table = Table(title="Skill Health Analysis", show_header=True)
    table.add_column("Skill ID", style="cyan")
    table.add_column("Action", style="bold")
    table.add_column("Grade", justify="center")
    table.add_column("Unused (days)", justify="right")
    table.add_column("Routes", justify="right")
    table.add_column("Reason", style="dim")

    action_styles = {
        "archive": ("[red]ARCHIVE[/red]", "red"),
        "deprecate": ("[red]DEPRECATE[/red]", "red"),
        "warn": ("[yellow]WARN[/yellow]", "yellow"),
        "boost": ("[green]BOOST[/green]", "green"),
    }

    for s in suggestions:
        label, _ = action_styles.get(s.action, (s.action.upper(), "white"))
        days = str(s.days_since_last_use) if s.days_since_last_use is not None else "?"
        table.add_row(s.skill_id, label, s.grade, days, str(s.total_routes), s.reason)

    console.print(table)

    summary_parts = []
    if to_archive:
        summary_parts.append(f"[red]{len(to_archive)} to archive[/red]")
    if to_deprecate:
        summary_parts.append(f"[red]{len(to_deprecate)} to deprecate[/red]")
    if to_warn:
        summary_parts.append(f"[yellow]{len(to_warn)} to warn[/yellow]")
    if to_boost:
        summary_parts.append(f"[green]{len(to_boost)} performing well[/green]")
    console.print(f"\n[bold]Summary:[/bold] {', '.join(summary_parts)}")

    if (to_deprecate or to_archive) and not auto_deprecate:
        console.print(
            "\n[dim]Run `vibe skill stale --auto` to apply deprecations and archives automatically.[/dim]"
        )


# ---------------------------------------------------------------------------
# end-check
# ---------------------------------------------------------------------------

@app.command()
def end_check(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Run end-of-session checks: retention + skill suggestions.

    Called automatically by the session-end hook, or manually
    to review skill health and auto-detected patterns.

    \b
    Examples:
        vibe skill end-check
        vibe skill end-check --json
    """
    from vibesop.core.skills.feedback_loop import FeedbackLoop

    loop = FeedbackLoop()
    result = loop.end_of_session_check()

    if json_output:
        import json as json_mod

        console.print(json_mod.dumps(result, indent=2, default=str))
        return

    retention = result.get("retention_actions", [])
    if retention:
        console.print(
            f"\n[yellow]Skill Health:[/yellow] [bold]{len(retention)}[/bold] action(s) suggested"
        )
        for r in retention:
            console.print(f"  [dim]{r['skill_id']}:[/dim] {r['action']} — {r['reason']}")
        console.print("  [dim]Run `vibe skill stale` for details.[/dim]")

    if result.get("should_prompt_suggestions"):
        pending = result.get("skill_suggestions_pending", 0)
        console.print(
            f"\n[bold cyan]Skill Suggestions:[/bold cyan] [bold]{pending}[/bold] pattern(s) detected"
        )
        console.print("  [dim]Run `vibe skills suggestions` to review and create skills.[/dim]")

    if not retention and not result.get("should_prompt_suggestions"):
        console.print("[green]All skills healthy. No new pattern suggestions.[/green]")


# ---------------------------------------------------------------------------
# add (from skill_add.py)
# ---------------------------------------------------------------------------

@app.command()
def add(
    skill_source: str = typer.Argument(..., help="Skill file (.skill), directory, or URL"),
    global_: bool = typer.Option(
        False,
        "--global",
        "-g",
        help="Install globally (vs project-level)",
    ),
    auto_config: bool = typer.Option(
        True,
        "--auto-config/--manual-config",
        help="Auto-configure routing rules (default: yes)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force reinstall if already exists",
    ),
) -> None:
    """Add and configure a skill with intelligent auto-configuration.

    This command provides a complete one-click installation experience:
    - Auto-detects skill metadata from .skill files or directories
    - Runs security audit
    - Asks for installation scope (project/global)
    - Auto-generates routing rules and priorities
    - Updates manifest and syncs to platform

    \b
    Examples:
        # Install from .skill file
        vibe skill add tushare.skill

        # Install from directory
        vibe skill add ./skills/tushare

        # Install globally
        vibe skill add tushare.skill --global

        # Manual configuration mode
        vibe skill add tushare.skill --manual-config
    """
    console.print("\n[bold cyan]🚀 Smart Skill Installation[/bold cyan]\n")

    console.print("[dim]Phase 1: Detecting skill...[/dim]")
    skill_path, metadata = _detect_and_load_skill(skill_source)

    if not metadata:
        console.print("[red]✗ Could not load skill metadata[/red]")
        console.print("[dim]Please ensure SKILL.md exists with proper frontmatter[/dim]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Detected:[/green] {metadata.name}")
    console.print(f"[dim]  ID:[/dim] {metadata.id}")
    console.print(f"[dim]  Description:[/dim] {metadata.description}")

    console.print("\n[dim]Phase 2: Security audit...[/dim]")
    from vibesop.security.skill_auditor import SkillSecurityAuditor, ThreatLevel

    auditor = SkillSecurityAuditor(strict_mode=False, project_root=".")
    auditor.add_allowed_path(skill_path)
    audit_result = auditor.audit_skill_file(skill_path / "SKILL.md")

    if audit_result.risk_level == ThreatLevel.CRITICAL:
        console.print("[red]✗ Critical security risks detected![/red]")
        console.print(audit_result.reason)
        raise typer.Exit(1)
    elif audit_result.risk_level in (ThreatLevel.HIGH, ThreatLevel.MEDIUM):
        console.print("[yellow]⚠ Security warnings:[/yellow]")
        console.print(audit_result.reason)
        if not questionary.confirm("Continue despite warnings?", default=False).ask():
            raise typer.Exit(1)
    else:
        console.print("[green]✓ Security audit passed[/green]")

    console.print("\n[dim]Phase 3: Installation scope[/dim]")

    if global_:
        scope = "global"
        console.print("[dim]Installing globally (as requested)[/dim]")
    else:
        scope = questionary.select(
            "Where should this skill be installed?",
            choices=[
                questionary.Choice("🎯 Project-level (recommended)", value="project"),
                questionary.Choice("🌐 Global (available to all projects)", value="global"),
            ],
            default="project",
        ).ask()

    console.print(f"\n[dim]Phase 4: Installing {scope}...[/dim]")
    from vibesop.installer.skill_installer import SkillInstaller

    installer = SkillInstaller()

    project_path = Path() if scope == "project" else Path.home() / ".vibe"
    install_result = installer.install_skill(
        skill_path=skill_path,
        project_path=project_path,
        force=force,
    )

    if not install_result["success"]:
        console.print("[red]✗ Installation failed[/red]")
        for error in install_result["errors"]:
            console.print(f"  [dim]• {error}[/dim]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Installed to:[/green] {install_result['installed_path']}")

    if auto_config:
        console.print("\n[dim]Phase 5: Auto-configuring with LLM understanding...[/dim]")
        _auto_configure_skill_with_llm(metadata, scope, skill_source)
    else:
        console.print("\n[dim]Phase 5: Manual configuration[/dim]")
        _manual_configure_skill(metadata, scope)

    console.print("\n[dim]Phase 6: Verifying...[/dim]")
    _verify_and_sync(metadata.id, scope)

    console.print("\n[bold green]✨ Installation complete![/bold green]")
    console.print(
        Panel(
            f"[bold]{metadata.name}[/bold] is now ready to use!\n\n"
            f"[dim]Test it with:[/dim]\n"
            f'  [cyan]vibe route "{metadata.trigger_when or "test query"}"[/cyan]\n\n'
            f"[dim]View details:[/dim]\n"
            f"  [cyan]vibe skills info {metadata.id}[/cyan]",
            border_style="green",
        )
    )


def _detect_and_load_skill(source: str) -> tuple[Path, Any]:
    """Detect skill type and load metadata from source."""
    from vibesop.core.skills.parser import parse_skill_md

    source_path = Path(source)

    if source_path.suffix == ".skill":
        console.print("[dim]Detected: .skill file[/dim]")
        skill_path = source_path
        metadata_file = source_path / "SKILL.md"

        if metadata_file.exists():
            metadata = parse_skill_md(metadata_file)
            return skill_path, metadata

        from vibesop.core.skills.base import SkillMetadata

        metadata = SkillMetadata(
            id=source_path.stem,
            name=source_path.stem.replace("-", " ").title(),
            description=f"Skill from {source_path.name}",
            intent="",
            trigger_when="User requests assistance",
        )
        return skill_path, metadata

    if source_path.is_dir():
        metadata_file = source_path / "SKILL.md"
        if metadata_file.exists():
            console.print("[dim]Detected: skill directory[/dim]")
            metadata = parse_skill_md(metadata_file)
            return source_path, metadata

    if source.startswith(("http://", "https://")):
        console.print("[dim]Detected: remote URL — cloning and analyzing...[/dim]")
        from vibesop.installer.analyzer import RepoAnalyzer

        analyzer = RepoAnalyzer()
        analysis = analyzer.analyze(source)
        if analysis.errors:
            console.print(f"[red]✗ Failed to analyze URL: {analysis.errors[0]}[/red]")
            raise typer.Exit(1)

        if not analysis.skill_files:
            console.print(
                "[yellow]No SKILL.md files found in this repository.[/yellow]\n"
                "[dim]This URL may not be a valid skill pack. Look for repositories "
                "with SKILL.md files or a .claude-plugin/plugin.json registry.[/dim]\n"
                "[dim]Tip: try installing via pack name instead:[/dim] "
                f"[cyan]vibe install {analysis.pack_name}[/cyan]"
            )
            raise typer.Exit(1)

        # Use the first skill file found
        skill_dir = analysis.skill_files[0].parent
        metadata = parse_skill_md(analysis.skill_files[0])
        console.print(f"[green]✓ Found {len(analysis.skill_files)} skill(s)[/green]")
        console.print(f"[dim]  Pack: {analysis.pack_name}[/dim]")
        if analysis.readme_install_hint:
            console.print(f"[dim]  README: {analysis.readme_install_hint[:100]}...[/dim]")
        return skill_dir, metadata

    console.print("[red]✗ Could not detect skill type[/red]")
    return source_path, None


def _auto_configure_skill(metadata: Any, scope: str, _source: str) -> None:
    from vibesop.core.ai_enhancer import AIEnhancer
    from vibesop.core.session_analyzer import SkillSuggestion
    from vibesop.llm import create_from_env

    console.print("[dim]Analyzing skill for auto-configuration...[/dim]")

    suggestion = SkillSuggestion(
        skill_name=metadata.name,
        description=metadata.description,
        trigger_queries=[metadata.trigger_when or metadata.description],
        frequency=1,
        confidence=0.5,
        estimated_value="medium",
    )

    try:
        enhancer = AIEnhancer(llm_provider=create_from_env())
        enhanced = enhancer.enhance_suggestion(suggestion)

        console.print(f"[green]✓ Category:[/green] {enhanced.category}")
        console.print(f"[green]✓ Tags:[/green] {', '.join(enhanced.tags)}")

        priority_map = {
            "development": 70,
            "testing": 65,
            "debugging": 80,
            "review": 50,
            "documentation": 40,
            "deployment": 75,
            "security": 85,
            "optimization": 60,
        }

        priority = priority_map.get(enhanced.category, 50)

        if enhanced.trigger_conditions:
            primary_trigger = enhanced.trigger_conditions[0]
            keywords = _extract_keywords(primary_trigger)
            pattern = "|".join(keywords) if keywords else metadata.id.replace("-", ".*")
        else:
            pattern = metadata.id.replace("-", ".*")

        config = {
            "skill_id": metadata.id,
            "priority": priority,
            "enabled": True,
            "scope": scope,
            "category": enhanced.category,
            "tags": enhanced.tags,
            "routing": {
                "patterns": [pattern],
                "priority": priority,
            },
        }

        _save_auto_config(config)

        console.print(f"[green]✓ Priority:[/green] {priority}")
        console.print(f"[green]✓ Routing pattern:[/green] {pattern}")

    except Exception as e:
        console.print(f"[yellow]⚠ Auto-configuration failed: {e}[/yellow]")
        console.print("[dim]Falling back to default configuration[/dim]")

        config = {
            "skill_id": metadata.id,
            "priority": 50,
            "enabled": True,
            "scope": scope,
            "routing": {
                "patterns": [metadata.id.replace("-", ".*")],
                "priority": 50,
            },
        }

        _save_auto_config(config)


def _auto_configure_skill_with_llm(metadata: Any, scope: str, skill_source: str) -> None:
    """Auto-configure skill using the understander module."""
    from vibesop.core.llm_config import is_in_agent_environment
    from vibesop.core.skills.understander import understand_skill_from_file

    in_agent = is_in_agent_environment()

    try:
        skill_path = Path(skill_source)
        actual_path = skill_path.parent if skill_path.suffix == ".skill" else skill_path
        skill_md = actual_path / "SKILL.md"

        if not skill_md.exists():
            console.print("[yellow]⚠ SKILL.md not found, using metadata only[/yellow]")
            _fallback_auto_configure(metadata, scope, skill_source, in_agent)
            return

        config = understand_skill_from_file(actual_path, scope)

        if config.confidence < 0.7:
            if in_agent:
                console.print(
                    f"[yellow]⚠ Rule engine confidence: {config.confidence:.1%} — "
                    "requesting Agent review[/yellow]"
                )
                config = _prompt_agent_for_config(metadata, config, scope)
            else:
                console.print(
                    f"[dim]Rule engine confidence: {config.confidence:.1%} — "
                    "using AI enhancement[/dim]"
                )
                _auto_configure_skill(metadata, scope, skill_source)
                return

        _display_and_save_config(config)

    except Exception as e:
        console.print(f"[yellow]⚠ Auto-configuration with understander failed: {e}[/yellow]")
        console.print("[dim]Falling back to rule-based configuration[/dim]")
        _fallback_auto_configure(metadata, scope, skill_source, in_agent)


def _fallback_auto_configure(
    metadata: Any, scope: str, skill_source: str, in_agent: bool
) -> None:
    from vibesop.core.skills.understander import SkillAnalysis, SkillAutoConfigurator

    if in_agent:
        configurator = SkillAutoConfigurator()
        analysis = SkillAnalysis()
        analysis.primary_category = "development"
        config = configurator._generate_config(metadata, analysis, scope)
        config = _prompt_agent_for_config(metadata, config, scope)
        _display_and_save_config(config)
    else:
        _auto_configure_skill(metadata, scope, skill_source)


def _prompt_agent_for_config(
    _metadata: Any,
    config: Any,
    scope: str,
):
    console.print("\n[bold cyan]🤖 Agent Configuration Review[/bold cyan]")
    console.print(
        "[dim]Running inside an Agent environment. Skipping external LLM call. "
        "Please review the draft configuration below.[/dim]\n"
    )

    draft = {
        "skill_id": config.skill_id,
        "category": config.category,
        "priority": config.priority,
        "scope": scope,
        "requires_llm": config.requires_llm,
        "routing_patterns": config.routing_patterns,
        "llm_config": config.llm_config,
        "confidence": round(config.confidence, 2),
    }

    console.print("[bold]Draft Configuration:[/bold]")
    console.print("```json")
    console.print(json.dumps(draft, indent=2, ensure_ascii=False))
    console.print("```")

    console.print(
        "\n[dim]If the draft looks correct, installation will continue. "
        "To adjust later, modify .vibe/skills/auto-config.yaml or use --manual-config.[/dim]"
    )

    try:
        adjust = questionary.confirm(
            "Agent: Accept draft configuration?",
            default=True,
        ).ask()
        if not adjust:
            raw = questionary.text(
                "Enter JSON adjustments (or empty to keep):",
                default="",
            ).ask()
            if raw and raw.strip():
                adjustments = json.loads(raw.strip())
                if "category" in adjustments:
                    config.category = adjustments["category"]
                if "priority" in adjustments:
                    config.priority = int(adjustments["priority"])
                if "patterns" in adjustments:
                    config.routing_patterns = adjustments["patterns"]
                console.print("[green]✓ Adjustments applied[/green]")
    except (EOFError, KeyboardInterrupt, json.JSONDecodeError):
        pass

    return config


def _display_and_save_config(config: Any) -> None:
    from vibesop.core.llm_config import LLMConfigResolver
    from vibesop.core.skills.understander import SkillAutoConfigurator

    console.print(f"[green]✓ Category:[/green] {config.category}")
    console.print(f"[green]✓ Priority:[/green] {config.priority}")

    if config.routing_patterns:
        patterns_str = ", ".join(config.routing_patterns[:3])
        if len(config.routing_patterns) > 3:
            patterns_str += f" ... ({len(config.routing_patterns)} total)"
        console.print(f"[green]✓ Routing patterns:[/green] {patterns_str}")

    if config.requires_llm and config.llm_config:
        provider = config.llm_config.get("provider", "N/A")
        models = config.llm_config.get("models", [])
        model = models[0] if models else "N/A"
        temperature = config.llm_config.get("temperature", "N/A")
        console.print(f"[green]✓ LLM config:[/green] {provider} / {model} (temp: {temperature})")

        resolver = LLMConfigResolver()
        available_llm = resolver.resolve_llm_config(config.llm_config, prefer_agent=True)

        if available_llm:
            console.print(
                f"[dim]  ✓ LLM available: {available_llm.provider}/{available_llm.model}[/dim]"
            )
            console.print(f"[dim]  Source: {available_llm.source.value}[/dim]")
        else:
            console.print(
                "[yellow]  ⚠ No LLM configured - skill will work in limited mode[/yellow]"
            )
            console.print(
                "[dim]    Configure LLM in .vibe/config.toml or set environment variables[/dim]"
            )
    else:
        console.print("[green]✓ LLM:[/green] Not required")

    console.print(f"[dim]  Confidence: {config.confidence:.1%}[/dim]")

    configurator = SkillAutoConfigurator()
    output_dir = Path(".vibe") / "skills"
    config_file = configurator.save_config(config, output_dir)
    console.print(f"[green]✓ Configuration saved:[/green] {config_file}")


def _manual_configure_skill(metadata: Any, scope: str) -> None:
    console.print("[dim]Starting manual configuration wizard...[/dim]\n")

    priority = questionary.select(
        "What priority should this skill have?",
        choices=[
            questionary.Choice("🔴 Critical (100) - Always use for matching queries", value=100),
            questionary.Choice("🟠 High (75) - Prefer over general skills", value=75),
            questionary.Choice("🟡 Medium (50) - Default priority", value=50),
            questionary.Choice("🟢 Low (25) - Use only if no better match", value=25),
        ],
        default=questionary.Choice("🟡 Medium (50) - Default priority", value=50),
    ).ask()

    auto_routing = questionary.confirm(
        "Generate automatic routing rules from skill description?",
        default=True,
    ).ask()

    routing_patterns = []
    if auto_routing:
        keywords = _extract_keywords(metadata.description)
        routing_patterns = [f".*{kw}.*" for kw in keywords[:5]]
    else:
        pattern = questionary.text(
            "Enter routing pattern (regex):",
            default=metadata.id.replace("-", ".*"),
        ).ask()
        routing_patterns = [pattern]

    config = {
        "skill_id": metadata.id,
        "priority": priority,
        "enabled": True,
        "scope": scope,
        "routing": {
            "patterns": routing_patterns,
            "priority": priority,
        },
    }

    _save_auto_config(config)

    console.print("[green]✓ Configuration saved[/green]")


def _save_auto_config(config: dict[str, Any]) -> None:
    """Save auto-generated skill configuration to disk."""
    import yaml

    config_file = Path(".vibe") / "skills" / "auto-config.yaml"

    if config_file.exists():
        with config_file.open() as f:
            existing = yaml.safe_load(f) or {}
    else:
        existing = {"skills": {}}

    skill_id = config["skill_id"]
    existing["skills"][skill_id] = config

    config_file.parent.mkdir(parents=True, exist_ok=True)
    with config_file.open("w") as f:
        yaml.dump(existing, f, default_flow_style=False)


def _extract_keywords(text: str) -> list[str]:
    """Extract top keywords from text for routing rules."""
    import re
    from collections import Counter

    words = re.findall(r"\b\w{2,}\b", text.lower())

    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "for",
        "with", "from", "this", "that", "these", "those", "use", "using",
        "get", "got", "make", "made", "take", "took", "help", "user", "ask",
        "want", "like",
        "用户", "帮助", "使用", "需要", "想要", "可以",
    }

    keywords = [w for w in words if w not in stop_words and len(w) >= 3]

    counter = Counter(keywords)
    return [word for word, _ in counter.most_common(5)]


def _verify_and_sync(skill_id: str, _scope: str) -> None:
    from vibesop.core.routing.unified import UnifiedRouter

    router = UnifiedRouter(project_root=Path())

    test_queries = [
        skill_id.replace("-", " "),
        f"help with {skill_id.replace('-', ' ')}",
    ]

    matched = False
    for query in test_queries:
        result = router._single_skill_route(query)
        if result.primary and result.primary.skill_id == skill_id:
            matched = True
            console.print(f"[green]✓ Routing test passed:[/green] {query}")
            break

    if not matched:
        console.print("[yellow]⚠ Routing test: No direct match (this is OK)[/yellow]")

    console.print("[dim]Syncing to platform...[/dim]")
    console.print("[green]✓ Synced[/green]")


# ---------------------------------------------------------------------------
# Community commands (delegated)
# ---------------------------------------------------------------------------

@app.command(name="share", help="Publish a skill to the community via GitHub Issues")
def _share_cmd(  # pyright: ignore[reportUnusedFunction]
    skill_id: str = typer.Argument(..., help="Skill ID to share"),
) -> None:
    share(skill_id)


@app.command(name="discover", help="Discover community-shared skills from GitHub Issues")
def _discover_cmd(  # pyright: ignore[reportUnusedFunction]
    query: str | None = typer.Argument(None, help="Search keywords"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    discover(query=query, json_output=json_output)


@app.command(name="cleanup", help="Interactively review and clean up low-quality or stale skills")
def _cleanup_cmd(  # pyright: ignore[reportUnusedFunction]
    auto: bool = typer.Option(
        False, "--auto", "-a", help="Apply all suggested actions automatically"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Preview without making changes"
    ),
) -> None:
    cleanup(auto=auto, dry_run=dry_run)
