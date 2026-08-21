# pyright: ignore[reportMissingParameterType]
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
    vibe skill cleanup [--auto] [--dry-run]
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.cli.commands.cleanup_cmd import cleanup
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
        "[cyan]vibe market search <query>[/cyan] [dim]— find skills on GitHub[/dim]\n"
        "[cyan]vibe skill cleanup[/cyan]         [dim]— review and prune stale skills[/dim]\n"
        "[cyan]vibe skill enable/disable[/cyan]  [dim]— toggle skills on/off[/dim]\n"
        "[cyan]vibe skill stale[/cyan]           [dim]— detailed health analysis[/dim]"
    )

    console.print(
        Panel(actions, title="[bold]Quick Actions[/bold]", border_style="cyan", box=ROUNDED)
    )

    console.print()
    console.print(
        "[dim]Also try:[/dim] [cyan]vibe status[/cyan] [dim]for full ecosystem health[/dim]"
    )
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
    _audit_skill_or_exit(skill_path)

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
    _install_skill_or_exit(skill_path, scope, force=force)

    if auto_config:
        console.print("\n[dim]Phase 5: Auto-configuring with LLM understanding...[/dim]")
        _auto_configure_skill_with_llm(metadata, scope, skill_source)
    else:
        console.print("\n[dim]Phase 5: Manual configuration[/dim]")
        _manual_configure_skill(metadata, scope)

    console.print("\n[dim]Phase 6: Verifying...[/dim]")
    indexed = _verify_and_sync(metadata.id, scope)

    console.print("\n[bold green]✨ Installation complete![/bold green]")
    if indexed:
        ready_line = f"[bold]{metadata.name}[/bold] is now ready to use!"
    else:
        # Honest fallback (M7): without the semantic index entry the skill
        # is invisible to the SEMANTIC_INDEX routing layer — don't claim
        # "ready to use" until `vibe skills index` has run.
        ready_line = (
            f"[bold]{metadata.name}[/bold] is installed.\n"
            f"[yellow]Run [cyan]vibe skills index[/cyan] before it can be "
            f"semantically routed.[/yellow]"
        )
    console.print(
        Panel(
            f"{ready_line}\n\n"
            f"[dim]Test it with:[/dim]\n"
            f'  [cyan]vibe route "{metadata.trigger_when or "test query"}"[/cyan]\n\n'
            f"[dim]View details:[/dim]\n"
            f"  [cyan]vibe skills info {metadata.id}[/cyan]",
            border_style="green",
        )
    )


def _audit_skill_or_exit(skill_path: Path) -> None:
    """Security audit — Phase 2 of ``vibe skill add``.

    Extracted (M12 M5) so ``vibe skill promote --activate`` runs the
    EXACT same audit instead of a copy. Raises ``typer.Exit(1)`` on
    critical risk or declined warnings.
    """
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


def _install_skill_or_exit(skill_path: Path, scope: str, *, force: bool) -> str:
    """Install into the scope's skills root — Phase 4 of ``vibe skill add``.

    Extracted (M12 M5) so ``vibe skill promote --activate`` registers via
    the EXACT same installer path (``~/.vibe/skills`` for global, legacy
    migration included) instead of a copy. Returns the installed path;
    raises ``typer.Exit(1)`` on install failure.
    """
    from vibesop.installer.skill_installer import SkillInstaller

    installer = SkillInstaller()

    project_path = _install_root(scope)
    if scope == "global":
        _migrate_legacy_global_skills(Path.home())
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

    for warning in install_result["warnings"]:
        console.print(f"[yellow]⚠ {warning}[/yellow]")
    console.print(f"[green]✓ Installed to:[/green] {install_result['installed_path']}")
    return str(install_result["installed_path"])


def _install_root(scope: str) -> Path:
    """Install root passed to SkillInstaller for the given scope.

    The installer appends ``.vibe/skills`` to this root, so ``global``
    must be the home directory itself: ``~/.vibe/skills/<id>`` is the
    unified global location — it is in ``ExternalSkillLoader``'s search
    paths and matches the `vibe skill promote` activate hints. (An
    earlier version passed ``~/.vibe`` here, producing the doubled,
    undiscoverable ``~/.vibe/.vibe/skills/<id>``.)
    """
    return Path() if scope == "project" else Path.home()


def _migrate_legacy_global_skills(home: Path) -> None:
    """Move skills from the legacy doubled path into ``~/.vibe/skills/``.

    Older versions installed ``--global`` skills to
    ``~/.vibe/.vibe/skills/<id>``, which no discovery path reads — those
    installs are invisible. Defensive: skills are moved (never deleted
    before the move succeeds); on a name conflict the legacy copy is
    left in place with a warning; non-directory entries (e.g. the legacy
    registry.yaml) are left untouched.
    """
    import shutil

    legacy_dir = home / ".vibe" / ".vibe" / "skills"
    if not legacy_dir.is_dir():
        return

    target_dir = home / ".vibe" / "skills"
    moved = 0
    for child in sorted(legacy_dir.iterdir()):
        if not child.is_dir():
            continue
        dest = target_dir / child.name
        if dest.exists():
            console.print(
                f"[yellow]⚠ Skipping legacy global skill '{child.name}': "
                f"{dest} already exists — remove the legacy copy at {child} "
                f"manually if unwanted[/yellow]"
            )
            continue
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(dest))
            moved += 1
        except OSError as e:
            console.print(
                f"[yellow]⚠ Could not migrate legacy global skill '{child.name}': {e}[/yellow]"
            )

    if moved:
        console.print(
            f"[dim]Migrated {moved} skill(s) from legacy "
            f"~/.vibe/.vibe/skills/ to ~/.vibe/skills/[/dim]"
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

        from vibesop.spec.models import SkillSpec

        metadata = SkillSpec(
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


def _fallback_auto_configure(metadata: Any, scope: str, skill_source: str, in_agent: bool) -> None:
    from vibesop.core.skills.understander import SkillAnalysis, SkillAutoConfigurator

    if in_agent:
        configurator = SkillAutoConfigurator()
        analysis = SkillAnalysis()
        analysis.primary_category = "development"
        config = configurator.generate_config(metadata, analysis, scope)
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
        with config_file.open(encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    else:
        existing = {"skills": {}}

    skill_id = config["skill_id"]
    existing["skills"][skill_id] = config

    config_file.parent.mkdir(parents=True, exist_ok=True)
    with config_file.open("w", encoding="utf-8") as f:
        yaml.dump(existing, f, default_flow_style=False)


def _extract_keywords(text: str) -> list[str]:
    """Extract top keywords from text for routing rules."""
    import re
    from collections import Counter

    words = re.findall(r"\b\w{2,}\b", text.lower())

    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "for",
        "with",
        "from",
        "this",
        "that",
        "these",
        "those",
        "use",
        "using",
        "get",
        "got",
        "make",
        "made",
        "take",
        "took",
        "help",
        "user",
        "ask",
        "want",
        "like",
        "用户",
        "帮助",
        "使用",
        "需要",
        "想要",
        "可以",
    }

    keywords = [w for w in words if w not in stop_words and len(w) >= 3]

    counter = Counter(keywords)
    return [word for word, _ in counter.most_common(5)]


def _verify_and_sync(skill_id: str, scope: str) -> bool:
    """Smoke-test routing, then incrementally index the newly added skill.

    Returns True when the skill's profile was merged into the semantic
    index (SEMANTIC_INDEX layer); False when indexing was skipped or
    failed (no LLM configured, analysis failed) — the caller must then
    say ``vibe skills index`` is still required instead of claiming the
    skill is "ready to use" (M7 skill add activation breakpoint).
    """
    from vibesop.core.routing.unified import UnifiedRouter

    router = UnifiedRouter(project_root=Path())

    test_queries = [
        skill_id.replace("-", " "),
        f"help with {skill_id.replace('-', ' ')}",
    ]

    matched = False
    for query in test_queries:
        result = router.route_single(query)
        if result.primary and result.primary.skill_id == skill_id:
            matched = True
            console.print(f"[green]✓ Routing test passed:[/green] {query}")
            break

    if not matched:
        console.print("[yellow]⚠ Routing test: No direct match (this is OK)[/yellow]")

    indexed = _index_newly_added_skill(skill_id, scope)

    console.print("[dim]Syncing to platform...[/dim]")
    console.print("[green]✓ Synced[/green]")
    return indexed


def _index_newly_added_skill(skill_id: str, scope: str) -> bool:
    """Incrementally index ONE newly installed skill into the semantic index.

    Analyzes just the new skill (one LLM call + one embedding) and merges
    its profile into the matching index layer — project index for project
    installs, global index otherwise. A full ``build_index`` is
    deliberately avoided: it would re-walk every discovered skill and
    re-write whole layers, far too slow for an install path.

    Scope note: ``vibe skill add --global`` installs to
    ``~/.vibe/skills/<id>`` (see ``_install_root``), which IS in
    ``ExternalSkillLoader``'s search paths, so incremental indexing
    applies to both scopes. A global skill can still be undiscoverable
    here when the external audit gate rejects it — in that case the
    degrade message points to ``vibe skills index --scope global``.

    Uses SkillIndexer's single-skill building blocks — no public
    single-skill API exists and the indexer is outside this change's
    edit scope. Best-effort: degrades to False (never raises) when no
    LLM is configured or analysis fails, so installation itself never
    fails because the optional index step couldn't run.
    """
    try:
        from vibesop.core.llm_config import LLMConfigResolver
        from vibesop.core.skills.indexer import SkillIndexer
        from vibesop.core.skills.loader import SkillLoader
        from vibesop.llm.factory import create_provider
        from vibesop.utils.file_lock import cross_process_lock

        cfg = LLMConfigResolver().get_llm_for_understanding()
        if not cfg or not cfg.provider:
            console.print(
                "[dim]No LLM configured — skipping semantic indexing "
                "(run `vibe skills index` later)[/dim]"
            )
            return False

        indexer = SkillIndexer(
            project_root=Path(),
            llm_factory=lambda: create_provider(
                provider=cfg.provider,
                api_key=cfg.api_key,
                base_url=cfg.api_base,
            ),
        )
        llm = indexer._get_llm()
        if llm is None:
            return False

        loaded = SkillLoader(project_root=Path()).get_skill(skill_id)
        if loaded is None:
            if scope == "global":
                # Global installs land in ~/.vibe/skills/ (in the external
                # search paths) — reaching this branch means discovery
                # failed anyway (e.g. external audit gate), so point at
                # the global-scope index rebuild.
                console.print(
                    f"[yellow]⚠ Skill '{skill_id}' is not discoverable by "
                    f"SkillLoader — run `vibe skills index --scope global` "
                    f"to make it semantically routable.[/yellow]"
                )
            else:
                console.print(
                    f"[dim]Skill '{skill_id}' not yet discoverable — "
                    "skipping semantic indexing "
                    "(run `vibe skills index` later)[/dim]"
                )
            return False

        console.print("[dim]Indexing new skill (incremental, single skill)...[/dim]")
        profile = indexer._analyze_skill(loaded, llm)
        if profile is None:
            return False
        indexer._compute_embeddings({skill_id: profile})

        layer = "project" if scope == "project" else "global"
        index_path = indexer.project_index_path if layer == "project" else indexer.global_index_path
        # gate7 claude NIT-1 / gate7b pi NIT-5: the load→merge→save
        # read-modify-write runs under a cross-process sidecar lock,
        # mutex'd against concurrent `skill add` runs AND the save phase
        # of `vibe skills index` — build_index takes the same sidecar
        # (names must match, ``{index_path}.lock``, or the locks don't
        # exclude each other). The index is RE-READ inside the lock —
        # merging into a dict read before acquiring it would defeat the
        # lock entirely. Caveat: a full rebuild still last-writer-wins
        # over an earlier incremental merge (its profiles are computed
        # outside the lock); the lock excludes interleaved/clobbering
        # writes, not stale ones.
        lock_path = Path(f"{index_path}.lock")
        try:
            with cross_process_lock(lock_path):
                existing = indexer._load_single_index(index_path)
                existing[skill_id] = profile
                indexer._save_index(existing, scope=layer)
        except OSError as e:  # lock file unavailable / IO error → degrade
            logger.debug("Incremental indexing lock/IO failed for %s: %s", skill_id, e)
            console.print(
                "[yellow]⚠ Semantic indexing failed — "
                "run `vibe skills index` to enable semantic routing[/yellow]"
            )
            return False
        console.print(f"[green]✓ Indexed into {layer} semantic index[/green]")
        return True
    except Exception as e:  # indexing is best-effort; never fail the install
        logger.debug("Incremental indexing failed for %s: %s", skill_id, e)
        console.print(
            "[yellow]⚠ Semantic indexing failed — "
            "run `vibe skills index` to enable semantic routing[/yellow]"
        )
        return False


@app.command(name="cleanup", help="Interactively review and clean up low-quality or stale skills")
def _cleanup_cmd(  # pyright: ignore[reportUnusedFunction]
    auto: bool = typer.Option(
        False, "--auto", "-a", help="Apply all suggested actions automatically"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without making changes"),
) -> None:
    cleanup(auto=auto, dry_run=dry_run)


# ---------------------------------------------------------------------------
# W4: task-memory-loop candidates (scan / candidates / promote / dismiss)
# ---------------------------------------------------------------------------


_GLOBAL_OBSERVABILITY_DIR = Path.home() / ".vibe" / "observability"

_CandidateStoreScope = Literal["project", "global"]


def _get_candidate_store(scope: _CandidateStoreScope = "project") -> ClusterCandidateStore:
    """Resolve the ClusterCandidateStore for the requested scope.

    - ``project`` (default): ``<cwd>/.vibe/observability/cluster_candidates.jsonl``
      — mirrors ReflectionStore and SpanWriter conventions.
    - ``global``: ``~/.vibe/observability/cluster_candidates.jsonl`` —
      W5.2 cross-project candidates land here so they're visible from any
      cwd. Path is NOT under ``ExternalSkillLoader.EXTERNAL_PATHS`` (which
      includes ``~/.vibe/skills/``, not ``~/.vibe/observability/``) —
      drafts stay outside discovery roots (W4 未审不注入 invariant).

    Tests patch this helper (or ``_GLOBAL_OBSERVABILITY_DIR``) to redirect.
    """
    storage_dir = (
        Path.cwd() / ".vibe" / "observability" if scope == "project" else _GLOBAL_OBSERVABILITY_DIR
    )
    return ClusterCandidateStore(storage_dir=storage_dir)


def _slugify(text: str, max_len: int = 50) -> str:
    """Make a URL-safe skill slug from arbitrary text.

    Used to derive a ``skill_id`` from a candidate's representative
    query when the user runs ``promote`` without specifying one.
    """
    slug = "".join(c if c.isalnum() or c in "-/" else "-" for c in text.lower())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:max_len] or "candidate"


# Miss-knob defaults track the calibrated constants in skill_promote so a
# re-calibration touches one place (gate17b pi nit — the gold knobs above
# keep their pre-existing literal defaults).
from vibesop.core.observability import skill_promote as _sp  # noqa: E402

_MISS_COSINE_THRESHOLD_DEFAULT = _sp.MISS_COSINE_THRESHOLD
_MISS_MIN_PAIRS_DEFAULT = _sp.MISS_RECURRENCE_MIN_PAIRS
_MISS_MIN_DAYS_DEFAULT = _sp.MISS_RECURRENCE_MIN_DAYS


@app.command(name="scan-candidates")
def scan_candidates_cmd(  # pyright: ignore[reportUnusedFunction]
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Classify clusters without writing to the pool"
    ),
    min_cluster_size: int = typer.Option(
        3, "--min-cluster-size", help="Min spans per cluster to qualify (>=1)"
    ),
    min_gold_rate: float = typer.Option(
        0.60, "--min-gold-rate", help="Stable candidate threshold (0.0-1.0)"
    ),
    limit: int = typer.Option(100, "--limit", help="Number of recent spans to scan (>=1)"),
    days: int | None = typer.Option(
        None,
        "--days",
        "-d",
        help=(
            "Best-effort look-back window in days (default: no filter). "
            "Spans with missing/malformed timestamps are kept regardless. "
            "Recommended: 7-30."
        ),
    ),
    miss_cosine_threshold: float = typer.Option(
        _MISS_COSINE_THRESHOLD_DEFAULT,
        "--miss-cosine-threshold",
        help=(
            "Cosine threshold for miss-vs-miss soft-merge clustering "
            "(0.0-1.0, default from MISS_COSINE_THRESHOLD — calibrated on "
            "hand-labelled dogfood miss pairs; miss-vs-miss is a different "
            "distribution from the gold-neighbour 0.80)."
        ),
    ),
    miss_min_pairs: int = typer.Option(
        _MISS_MIN_PAIRS_DEFAULT,
        "--miss-min-pairs",
        help="Min distinct (task_key, natural-day) pairs for miss_recurrence admission (>=1)",
    ),
    miss_min_days: int = typer.Option(
        _MISS_MIN_DAYS_DEFAULT,
        "--miss-min-days",
        help="Min distinct natural days for miss_recurrence admission (>=1, conjunctive)",
    ),
    cross_project: bool = typer.Option(
        False,
        "--cross-project",
        help=(
            "Scan spans across all pool members (W5.2). "
            "Candidates land in the global store at ~/.vibe/observability/. "
            "Register pool members first via `vibe pool add <path>`."
        ),
    ),
) -> None:
    """Cluster recent spans → populate the skill-candidate pool.

    Trigger (W4 design, reviewer Q1): clusters with span_count ≥
    --min-cluster-size AND gold_rate ≥ --min-gold-rate become stable
    candidates. Clusters with gold_rate < 0.30 become unstable
    (diagnosis bucket; reviewer Q2). In-between gold_rates are silent
    skip.

    Idempotent: re-scanning the same spans refreshes counts but does
    not duplicate rows. TTL-expired pending rows are pruned at start.

    ``--days`` (W5.0.B): restricts the scan to spans emitted within the
    last N days. Without this, the scan covers all history since project
    inception. Time filter applies AFTER ``query_recent(limit=)`` returns
    the most recent ``limit`` spans — so the actual scanned set is
    "min(limit, spans_younger_than_days)". Filter reads ``started_at``
    (real production schema); malformed timestamps are kept rather than
    dropped (see recall._filter_recent rationale).

    ``--cross-project`` (W5.2): unions spans from every pool member's
    ``spans.jsonl``. Cross-project clusters (queries that recur across
    multiple projects) only surface via this flag — the default scan
    reads only local spans. Candidates land in the global store so
    they're visible from any cwd.

    ``--miss-cosine-threshold`` / ``--miss-min-pairs`` / ``--miss-min-days``
    (M12 M2, gate17 claude nit 3): the miss_recurrence admission knobs —
    miss clusters are admitted on distinct (task_key, natural-day) pairs
    AND distinct days (conjunction), clustered with a miss-vs-miss cosine
    threshold. These wire straight onto ``scan_candidates`` kwargs; they
    do NOT affect gold-cluster admission (that's --min-cluster-size /
    --min-gold-rate).
    """
    # Validate CLI arg bounds (grok P1: prior version accepted any int/float).
    if min_cluster_size < 1:
        console.print(f"[red]✗[/red] --min-cluster-size must be >=1, got {min_cluster_size}")
        raise typer.Exit(1)
    if not (0.0 <= min_gold_rate <= 1.0):
        console.print(f"[red]✗[/red] --min-gold-rate must be in [0.0, 1.0], got {min_gold_rate}")
        raise typer.Exit(1)
    if limit < 1:
        console.print(f"[red]✗[/red] --limit must be >=1, got {limit}")
        raise typer.Exit(1)
    if days is not None and days < 1:
        console.print(f"[red]✗[/red] --days must be >=1, got {days}")
        raise typer.Exit(1)
    if not (0.0 <= miss_cosine_threshold <= 1.0):
        console.print(
            f"[red]✗[/red] --miss-cosine-threshold must be in [0.0, 1.0], got {miss_cosine_threshold}"
        )
        raise typer.Exit(1)
    if miss_min_pairs < 1:
        console.print(f"[red]✗[/red] --miss-min-pairs must be >=1, got {miss_min_pairs}")
        raise typer.Exit(1)
    if miss_min_days < 1:
        console.print(f"[red]✗[/red] --miss-min-days must be >=1, got {miss_min_days}")
        raise typer.Exit(1)

    from vibesop.core.instinct.learner import InstinctLearner
    from vibesop.core.observability.embedding import get_embedding_cache
    from vibesop.core.observability.recall import _filter_recent
    from vibesop.core.observability.skill_promote import (
        DEFAULT_UNSTABLE_GOLD_RATE,
        MAX_PENDING,
        MAX_PENDING_UNSTABLE,
        scan_candidates,
    )
    from vibesop.core.observability.span_writer import SpanWriter

    if cross_project:
        from vibesop.cli.commands.pool_cmd import collect_pool_spans

        spans, aliases_with_data = collect_pool_spans(limit=limit)
        if not aliases_with_data:
            console.print(
                "[red]✗[/red] No pool members with spans found. "
                "Add with: [cyan]vibe pool add <path>[/cyan]"
            )
            raise typer.Exit(1)
        scope_msg = f"cross-project ({len(aliases_with_data)} pool member(s))"
    else:
        spans = SpanWriter().query_recent(limit=limit)
        scope_msg = "project"

    if days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        spans = _filter_recent(spans, cutoff)

    learner = InstinctLearner()
    cache = get_embedding_cache()
    store = _get_candidate_store(scope="global" if cross_project else "project")

    summary = scan_candidates(
        spans,
        learner,
        store,
        cache=cache,
        min_cluster_size=min_cluster_size,
        min_gold_rate=min_gold_rate,
        unstable_gold_rate=DEFAULT_UNSTABLE_GOLD_RATE,
        miss_cosine_threshold=miss_cosine_threshold,
        miss_min_pairs=miss_min_pairs,
        miss_min_days=miss_min_days,
        dry_run=dry_run,
    )

    mode = "[dim]DRY-RUN[/dim] " if dry_run else ""
    console.print(
        f"[green]✓[/green] {mode}Scanned {summary.clusters_seen} cluster(s) "
        f"→ {summary.promoted_count} stable, {summary.unstable_count} unstable"
    )
    # pi gate17 BLOCK-1: embedding degradation must be LOUD, not a per-query
    # warning — otherwise clustering silently degrades to hard task_id
    # grouping (the M0 fastembed-model-name incident proved this failure
    # mode is invisible without an explicit marker).
    if getattr(summary, "embedding_degraded", False):
        console.print(
            "[bold yellow]⚠ embedding 不可用：soft-merge 未生效，"
            "簇仅按 task_id 硬分组（降级模式）[/bold yellow]"
        )
    # pi gate17 BLOCK-2: silent-churn detection fields — computed by the
    # scan but previously never displayed. gate17b claude nit 2: surface
    # cap-refusals too, not just via logger.
    miss_line = (
        f"  [dim]miss pool: {summary.miss_pool_size} span(s) → "
        f"{summary.miss_admitted_count} miss_recurrence candidate(s) admitted"
    )
    if getattr(summary, "miss_rejected_count", 0):
        # F-a: refusal is at the STABLE-class cap (the unstable bucket no
        # longer blocks miss admissions) — say the class explicitly.
        miss_line += f" ({summary.miss_rejected_count} refused: stable pool at cap)"
    console.print(miss_line + "[/dim]")
    # F-a: unstable-bucket churn visibility (per-class refusal count).
    if getattr(summary, "unstable_refused_count", 0):
        console.print(
            f"  [dim]unstable diagnosis bucket full — "
            f"{summary.unstable_refused_count} row(s) refused at cap "
            f"{MAX_PENDING_UNSTABLE}[/dim]"
        )
    # gate21 pi NIT-4: stable-class refusals, symmetric with the above.
    if getattr(summary, "stable_refused_count", 0):
        console.print(
            f"  [dim]stable pool full — "
            f"{summary.stable_refused_count} gold candidate(s) refused at cap "
            f"{MAX_PENDING}[/dim]"
        )
    # M12 M4 item (done in M5, file-ownership): per-layer miss share.
    # Current route-span producers don't emit a layer field, so real data
    # buckets into "unknown" — rendered as-is (honest degradation).
    if summary.miss_share_by_layer:
        share = ", ".join(
            f"{layer} {fraction:.0%}" for layer, fraction in summary.miss_share_by_layer.items()
        )
        console.print(f"  [dim]miss share by layer: {share}[/dim]")
    if summary.pruned_count:
        console.print(f"  [dim]pruned {summary.pruned_count} TTL-expired row(s)[/dim]")
    if summary.capped:
        console.print(
            "  [yellow]⚠ hard cap reached — review backlog or dismiss to make room[/yellow]"
        )
    # gate21 (claude NIT-3 = pi NIT-1): ONE unlocked read, classified in
    # memory — two separate pending_count() calls can snapshot different
    # file states under a concurrent writer and render an inconsistent
    # (theoretically negative) unstable count.
    all_pending = store.list_pending(include_unstable=True)
    stable_pending = sum(1 for r in all_pending if not r.is_unstable)
    unstable_pending = len(all_pending) - stable_pending
    console.print(
        f"  [dim]scope: {scope_msg} | "
        f"pool: {stable_pending} stable pending (cap {MAX_PENDING}), "
        f"{unstable_pending} unstable (cap {MAX_PENDING_UNSTABLE}) "
        f"(use `vibe skill candidates` to review)[/dim]"
    )


def _resolve_project_alias(project_id: str) -> str:
    """Map an absolute-path project_id to a pool alias (W5.2).

    Spans store ``project_id = str(Path.cwd().resolve())`` (W5.0).
    Pool entries store ``path`` (which may be relative or absolute) +
    ``alias``. We resolve both sides and match.

    Falls back to the basename if no pool entry matches (so the column
    stays readable even when projects aren't registered).
    """
    from vibesop.cli.commands.pool_cmd import load_pool

    try:
        target = Path(project_id).resolve()
    except (OSError, ValueError):
        return Path(project_id).name or project_id[:8]

    for entry in load_pool().get("projects", []):
        entry_path = Path(entry.get("path", ""))
        try:
            if entry_path.resolve() == target:
                return entry.get("alias") or entry_path.name
        except (OSError, ValueError):
            continue

    return target.name or project_id[:8]


def _format_projects_column(project_distribution: dict[str, int]) -> str:
    """Render project_distribution as a compact comma-separated alias list."""
    if not project_distribution:
        return "[dim]—[/dim]"
    parts = [
        f"{_resolve_project_alias(pid)}×{count}"
        for pid, count in sorted(project_distribution.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return ", ".join(parts)


def _merge_dedup_candidates(
    project_rows: list[ClusterCandidate],
    global_rows: list[ClusterCandidate],
) -> list[ClusterCandidate]:
    """Merge project + global candidates by cluster_id.

    When the same ``cluster_id`` exists in both stores, the record with
    larger ``len(project_distribution)`` wins (more heterogeneous view
    is strictly more informative — captures cross-project state the
    per-project scan can't see).

    Stable-sort by ``(gold_rate, span_count)`` desc to match
    ``ClusterCandidateStore.list_pending`` ordering.
    """
    by_id: dict[str, ClusterCandidate] = {}
    for row in (*project_rows, *global_rows):
        existing = by_id.get(row.cluster_id)
        if existing is None:
            by_id[row.cluster_id] = row
            continue
        # Prefer more-heterogeneous record (brief v2 §7 Q1).
        if len(row.project_distribution) > len(existing.project_distribution):
            by_id[row.cluster_id] = row
    return sorted(
        by_id.values(),
        key=lambda r: (r.gold_rate, r.span_count),
        reverse=True,
    )


@app.command(name="candidates")
def candidates_cmd(  # pyright: ignore[reportUnusedFunction]
    unstable: bool = typer.Option(
        False, "--unstable", help="Show only unstable candidates (gold_rate<0.30)"
    ),
    include_unstable: bool = typer.Option(
        False,
        "--include-unstable",
        help="Show stable AND unstable candidates in one list (default: stable only)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
    cross_project_only: bool = typer.Option(
        False,
        "--cross-project-only",
        help="Show only candidates from the global (cross-project) store (W5.2).",
    ),
) -> None:
    """List pending skill candidates from the pool.

    Default: stable candidates sorted by gold_rate desc. Use
    ``--unstable`` for the diagnosis bucket only (gold_rate<0.30,
    sorted asc). Use ``--include-unstable`` to see both in one list.

    W5.2: reads from BOTH the project store (``<cwd>/.vibe/observability/``)
    AND the global store (``~/.vibe/observability/``). Cross-project
    candidates are tagged ``[XP]`` (short for "cross-project"; chosen for
    column width — the full label would force Rich to wrap the table).
    Use ``--cross-project-only`` to filter to global store rows only.
    """
    import json as _json
    from datetime import UTC, datetime

    project_store = _get_candidate_store(scope="project")
    global_store = _get_candidate_store(scope="global")

    def _select(store: ClusterCandidateStore) -> list[ClusterCandidate]:
        if unstable:
            return store.list_unstable()
        elif include_unstable:
            return store.list_pending(include_unstable=True)
        return store.list_pending()

    project_rows = [] if cross_project_only else _select(project_store)
    global_rows = _select(global_store)
    rows = _merge_dedup_candidates(project_rows, global_rows)

    if json_output:
        now = datetime.now(UTC)
        payload = [
            {
                "cluster_id": r.cluster_id,
                "task_ids": r.task_ids,
                "queries": r.queries,
                "span_count": r.span_count,
                "gold_rate": round(r.gold_rate, 4),
                "is_unstable": r.is_unstable,
                "is_cross_project": r.is_cross_project,
                # Privacy: basenames only, collision-suffixed. The table
                # view already redacts via _format_projects_column; JSON
                # consumers (dashboards, CI logs) get the same treatment
                # so absolute filesystem paths never leave the user's
                # machine via --json (omx-code-review HIGH #2, brief v2
                # §6 P-5).
                "project_distribution": dedupe_project_distribution(r.project_distribution),
                "ttl_days_left": max(
                    0,
                    int((r.ttl_expires_at - now).total_seconds() // 86400)
                    if r.ttl_expires_at
                    else 0,
                ),
                "core_steps": r.core_steps,
                "status": r.status,
            }
            for r in rows
        ]
        console.print(_json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not rows:
        label = "unstable " if unstable else ("cross-project " if cross_project_only else "")
        console.print(f"[dim]No {label}candidates in pool[/dim]")
        return

    title = "Unstable candidates" if unstable else "Skill candidates"
    table = Table(title=title)
    table.add_column("ID", style="bold", max_width=30, no_wrap=False)
    table.add_column("Representative query", max_width=40)
    table.add_column("Spans", justify="right")
    table.add_column("Gold%", justify="right")
    table.add_column("Bucket", justify="center")
    table.add_column("Projects", max_width=30)
    table.add_column("TTL", justify="right")
    table.add_column("Core steps")

    now = datetime.now(UTC)
    for r in rows:
        days_left = (
            int((r.ttl_expires_at - now).total_seconds() // 86400) if r.ttl_expires_at else 0
        )
        bucket = "[red]unstable[/red]" if r.is_unstable else "[green]stable[/green]"
        ttl_color = "green" if days_left > 7 else "yellow" if days_left > 1 else "red"
        core_str = ", ".join(r.core_steps[:3])
        if len(r.core_steps) > 3:
            core_str += f", +{len(r.core_steps) - 3}"
        # First query, truncated for the table column. Pi P1: gives the
        # user a semantic anchor instead of an opaque hash.
        query_str = (r.queries[0] if r.queries else "")[:40]
        # Cross-project tag on the ID column for visual scannability.
        # Tag is short ("[XP]") so it survives Rich's narrow-table truncation.
        id_str = r.cluster_id[:8]
        if r.is_cross_project:
            id_str = f"[cyan][XP][/cyan] {id_str}"
        table.add_row(
            id_str,
            query_str or "[dim]—[/dim]",
            str(r.span_count),
            f"{r.gold_rate * 100:.0f}%",
            bucket,
            _format_projects_column(r.project_distribution),
            f"[{ttl_color}]{days_left}d[/{ttl_color}]",
            core_str or "[dim]—[/dim]",
        )

    console.print(table)
    # pi re-review M5: in-product legend for the [XP] tag + Projects column
    # format. Only printed when at least one row in the current listing is
    # cross-project (avoids noise for the common single-project case).
    has_xp = any(r.is_cross_project for r in rows)
    if has_xp:
        console.print(
            "[dim][XP] = cross-project cluster (spans sourced from ≥2 pool "
            "members). Projects column shows alias × span count.[/dim]"
        )
    console.print(
        "\n[dim]Next: `vibe skill promote <id>` to draft SKILL.md, "
        "or `vibe skill dismiss <id>` to reject.[/dim]"
    )


@app.command(name="promote")
def promote_cmd(  # pyright: ignore[reportUnusedFunction]
    cluster_id: str = typer.Argument(..., help="Cluster ID from `vibe skill candidates`"),
    scope: Literal["project", "global"] = typer.Option(
        "project",
        "--scope",
        help=(
            "Draft destination: 'project' writes to <cwd>/.vibe/observability/skill_drafts/ "
            "(default); 'global' writes to ~/.vibe/observability/skill_drafts/ (W5.2). "
            "Global drafts are visible from any cwd but still require explicit "
            "activation — drafts are NEVER auto-discovered."
        ),
    ),
    activate: bool = typer.Option(
        False,
        "--activate",
        help=(
            "Register the skill into routing in one step (M12 M5). Refused "
            "unless the draft was edited since generation (content-hash "
            "guard) or --force is passed. Global scope additionally requires "
            "cross-project evidence (or --force) AND an interactive privacy "
            "confirmation (always, even with --force)."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help=(
            "Bypass the edit guard (and the global cross-project evidence "
            "requirement). With --activate it is also forwarded to the "
            "installer as a forced reinstall when the skill is already "
            "installed (gate18 claude NIT-1). It never skips the global "
            "privacy confirmation."
        ),
    ),
) -> None:
    """Promote a candidate → draft SKILL.md + flip status.

    The drafted SKILL.md is written to
    ``.vibe/observability/skill_drafts/<id>/`` (project scope, default) or
    ``~/.vibe/observability/skill_drafts/<id>/`` (global scope, W5.2) —
    paths that ``CandidateManager`` does NOT auto-discover. To inject the
    skill into routing, either edit the draft and re-run with
    ``--activate`` (M12 M5), or copy the draft into the appropriate
    ``skills/`` dir and run ``vibe skill add <path>``. This is the literal
    "未审不注入" guarantee (W4 review P0 — prior version wrote under
    ``.vibe/skills/`` which IS auto-discovered).

    M12 M5 edit guard: the sha256 of the freshly generated draft is
    recorded on the candidate (``draft_sha256``). ``--activate`` compares
    the CURRENT file hash — identical means no human edit happened and
    activation is refused (mtime checks are spoofable by whitespace-only
    edits; content hash is not). The hash is recorded only when this run
    freshly writes the draft — a re-promote over an existing (possibly
    edited) draft does NOT re-baseline the guard. Legacy candidates
    (promoted before M5, no recorded hash) require ``--force``.

    W5.2: For cross-project clusters, the candidate is loaded from the
    global store; promote with ``--scope global`` to keep the draft
    visible across all projects. ``--scope project`` on a cross-project
    cluster is allowed (permissive policy) but emits a warning — the
    drafted SKILL.md will contain queries from multiple projects.
    """
    # W5.2 omx-code-review ARCHITECT #2: --scope is AUTHORITATIVE for
    # store selection. The prior logic picked "more heterogeneous" even
    # when the user explicitly asked for project scope — that could flip
    # the GLOBAL store's status while the draft landed in project drafts,
    # making the row appear "promoted" to other pool members who never
    # opted in. Now: try the requested scope's store first; fall back to
    # the other store ONLY if the cluster isn't in the requested one
    # (with a visible hint so the user sees the redirect).
    primary_store = _get_candidate_store(scope=scope)
    fallback_scope: _CandidateStoreScope = "global" if scope == "project" else "project"
    fallback_store = _get_candidate_store(scope=fallback_scope)
    candidate = primary_store.get(cluster_id)
    store = primary_store
    if candidate is None:
        fallback = fallback_store.get(cluster_id)
        if fallback is not None:
            candidate = fallback
            store = fallback_store
            console.print(
                f"[dim]Cluster '{cluster_id}' found in {fallback_scope} store; "
                f"flipping that store's status. Draft still lands at --scope {scope} "
                f"(per user request).[/dim]"
            )

    if candidate is None:
        console.print(f"[red]✗[/red] Cluster '{cluster_id}' not in pool")
        raise typer.Exit(1)

    if candidate.status == "dismissed":
        console.print(
            f"[yellow]⚠ Cluster '{cluster_id}' is dismissed — "
            "dismiss is sticky; cannot promote.[/yellow]"
        )
        raise typer.Exit(1)

    # W5.2 Task 3.2: permissive policy. Cross-project cluster + project
    # scope → loud warning (user opted into permissive redaction; this
    # is the safeguard per brief v2 §7a A2). Cross-project + global is
    # the natural fit → mild info line.
    if candidate.is_cross_project and scope == "project":
        projects_summary = _format_projects_column(candidate.project_distribution)
        console.print(
            f"[yellow]⚠ Cross-project cluster[/yellow] ({projects_summary}) "
            f"promoted to [bold]project[/bold] scope. "
            f"SKILL.md will contain queries from multiple projects — "
            f"review before activating."
        )
    elif candidate.is_cross_project and scope == "global":
        console.print(
            f"[dim]Cross-project cluster → global drafts ({len(candidate.project_distribution)} projects).[/dim]"
        )

    # Derive skill_id with cluster_id prefix (pi P1: avoids collision
    # when two clusters share a first query — both would slug to the
    # same custom/<slug> and silently no-op on second promote).
    base_query = candidate.queries[0] if candidate.queries else "candidate"
    skill_id = f"custom/{_slugify(base_query)}-{cluster_id[:8]}"

    # W4.E: materialize SKILL.md draft outside discovery paths.
    # W5.2: --scope global routes to ~/.vibe/observability/skill_drafts/.
    drafts_root = (
        Path.cwd() / ".vibe" / "observability" / "skill_drafts"
        if scope == "project"
        else _GLOBAL_OBSERVABILITY_DIR / "skill_drafts"
    )
    # M12 M5: record the draft content hash ONLY when this run freshly
    # writes the draft. materialize_candidate never overwrites an
    # existing draft, so a re-promote over an edited draft must not
    # re-baseline the edit guard (passing None leaves the recorded hash
    # untouched — see ClusterCandidateStore.promote). gate18 pi NIT-2:
    # freshness comes from MaterializeResult.fresh, decided inside
    # materialize_candidate's locked check+write — no racy pre-check here.
    materialized = materialize_candidate(candidate, skill_id, drafts_root=drafts_root, scope=scope)
    skill_path = materialized.path
    draft_sha256 = (
        hashlib.sha256(skill_path.read_bytes()).hexdigest() if materialized.fresh else None
    )

    # Flip store status (idempotent on already-promoted rows).
    # Promote the store that actually holds the candidate.
    store.promote(cluster_id, skill_id, draft_sha256=draft_sha256)
    # Reload so _activate_promoted_draft sees the hash recorded above
    # (get() returns a fresh parse; the pre-promote object is stale).
    candidate = store.get(cluster_id) or candidate

    console.print(f"[green]✓[/green] Promoted '{cluster_id}' → skill_id={skill_id}")
    console.print(f"  [dim]draft:[/dim] {skill_path}")
    if scope == "global":
        console.print(
            f"  [dim]activate:[/dim] copy to ~/.vibe/skills/{skill_id}/ and run "
            f"`vibe skill add ~/.vibe/skills/{skill_id}`"
        )
    else:
        console.print(
            f"  [dim]activate:[/dim] copy to .vibe/skills/{skill_id}/ and run "
            f"`vibe skill add .vibe/skills/{skill_id}`"
        )
    # M7: `vibe skill add` now incrementally indexes the installed skill,
    # so no separate full rebuild is needed when an LLM is configured.
    console.print(
        "  [dim]index:[/dim] `vibe skill add` indexes the skill incrementally "
        "(needs a configured LLM); otherwise run `vibe skills index`"
    )
    console.print("  [dim]review checklist before activating:[/dim]")
    console.print(
        "    [dim]1. rewrite name/description into intent keywords "
        "(the draft name is a placeholder)[/dim]"
    )
    console.print(
        "    [dim]2. confirm the example queries are a single workflow — "
        "split the draft if they aren't[/dim]"
    )
    console.print("    [dim]3. spell out when this skill should NOT be used[/dim]")

    if activate:
        _activate_promoted_draft(
            candidate,
            skill_id,
            skill_path,
            scope,
            force=force,
        )


def _print_promoted_not_activated() -> None:
    """gate18 pi residual-1: clarify post-refusal state — the candidate
    was already flipped to promoted (draft written) before the guard
    chain ran; refusal only blocks REGISTRATION, nothing entered routing."""
    console.print(
        "  [dim]note: the candidate is now 'promoted' (draft written) but NOT "
        "registered — nothing entered routing.[/dim]"
    )


def _activate_promoted_draft(
    candidate: ClusterCandidate,
    skill_id: str,
    skill_path: Path,
    scope: _CandidateStoreScope,
    *,
    force: bool,
) -> None:
    """``promote --activate`` (M12 M5): edit-guarded one-step registration.

    Guard chain (design v3 数据流 M5 — 消解「--activate 与无人工确认不
    激活」的自相矛盾):

    1. Draft file missing → refuse.
    2. ``draft_sha256`` is None (legacy pre-M5 candidate) → refuse unless
       ``--force``, with an honest message.
    3. Current draft hash == recorded hash (never edited) → refuse unless
       ``--force``. The refusal points at the review checklist printed by
       ``promote_cmd`` above.
    4. Global scope: requires cross-project evidence
       (``is_cross_project``) OR ``--force``; AND an interactive privacy
       confirmation (``typer.confirm(default=False)``) — ALWAYS, even
       with ``--force`` (privacy boundary: 默认 N 显式确认).

    Registration reuses the exact ``vibe skill add`` path:
    ``_detect_and_load_skill`` → ``_audit_skill_or_exit`` →
    ``_install_skill_or_exit`` → ``_auto_configure_skill_with_llm`` →
    ``_verify_and_sync``. Nothing is duplicated.
    """
    console.print("\n[dim]--activate: checking edit guard...[/dim]")

    if not skill_path.exists():
        console.print(
            f"[red]✗[/red] Draft file missing: {skill_path}\n"
            "  [dim]Re-run `vibe skill promote` (without --activate) to regenerate it.[/dim]"
        )
        _print_promoted_not_activated()
        raise typer.Exit(1)

    current_sha256 = hashlib.sha256(skill_path.read_bytes()).hexdigest()
    if candidate.draft_sha256 is None:
        if not force:
            # gate18 pi NIT-1: the prior message suggested re-running
            # promote to record the hash — a dead end (materialize keeps
            # the existing draft, so no hash is ever recorded). The two
            # paths that actually work are --force, or delete + fresh
            # re-promote.
            console.print(
                "[red]✗[/red] Activation refused: no draft hash recorded for this "
                "candidate (promoted before the M5 edit guard existed), so "
                "substantive editing cannot be verified.\n"
                "  [dim]Two working paths: (a) pass --force to bypass the guard; or "
                "(b) delete the draft directory shown above and re-run "
                "`vibe skill promote` — a freshly generated draft records the "
                "baseline hash; then edit it and activate. (Re-running promote "
                "alone keeps the existing draft and never records a hash.)[/dim]"
            )
            _print_promoted_not_activated()
            raise typer.Exit(1)
        console.print(
            "[yellow]⚠ --force: no recorded draft hash (legacy candidate) — "
            "edit guard bypassed.[/yellow]"
        )
    elif current_sha256 == candidate.draft_sha256:
        if not force:
            console.print(
                "[red]✗[/red] Activation refused: the draft is byte-identical to "
                "the generated version — no human edit detected.\n"
                "  [dim]Edit the draft per the review checklist above, then "
                "re-run with --activate — or pass --force to bypass.[/dim]"
            )
            _print_promoted_not_activated()
            raise typer.Exit(1)
        console.print(
            "[yellow]⚠ --force: draft unchanged since generation — edit guard bypassed.[/yellow]"
        )
    else:
        console.print("[green]✓[/green] Draft edited since generation (content hash differs)")

    if scope == "global":
        if not candidate.is_cross_project and not force:
            console.print(
                "[red]✗[/red] Global activation refused: this candidate has no "
                "cross-project evidence ([XP]).\n"
                "  [dim]Global skills affect every project — promote a "
                "cross-project cluster, or pass --force to override.[/dim]"
            )
            _print_promoted_not_activated()
            raise typer.Exit(1)
        # Privacy boundary (design v3): explicit confirmation, default N,
        # ALWAYS required for global activation — --force does NOT skip it.
        if not typer.confirm(
            f"Activate '{skill_id}' GLOBALLY (~/.vibe/skills/, visible to all projects)?",
            default=False,
        ):
            console.print("[dim]Aborted — global activation requires explicit confirmation.[/dim]")
            _print_promoted_not_activated()
            raise typer.Exit(1)

    # Registration: the exact `vibe skill add` path (factored phases).
    draft_dir = skill_path.parent
    _, metadata = _detect_and_load_skill(str(draft_dir))
    if not metadata:
        console.print("[red]✗ Could not load skill metadata from the draft[/red]")
        raise typer.Exit(1)

    _audit_skill_or_exit(draft_dir)
    _install_skill_or_exit(draft_dir, scope, force=force)
    _auto_configure_skill_with_llm(metadata, scope, str(draft_dir))
    indexed = _verify_and_sync(metadata.id, scope)

    console.print(f"[bold green]✨ Activated:[/bold green] {skill_id} ({scope})")
    if not indexed:
        console.print(
            "[yellow]Run [cyan]vibe skills index[/cyan] before it can be "
            "semantically routed.[/yellow]"
        )


@app.command(name="dismiss")
def dismiss_cmd(  # pyright: ignore[reportUnusedFunction]
    cluster_id: str = typer.Argument(..., help="Cluster ID to dismiss"),
    reason: str = typer.Option(None, "--reason", help="Why this candidate is rejected (recorded)"),
    scope: _CandidateStoreScope = typer.Option(
        "project",
        "--scope",
        help=(
            "Which store to dismiss from: 'project' (default) or 'global'. "
            "If the cluster isn't in the requested store, VibeSOP falls back "
            "to the other store with a hint (W5.2 pi re-review H1: cross-project "
            "candidates live in global store and would otherwise be undismissable)."
        ),
    ),
) -> None:
    """Dismiss a candidate with optional reason. Status is sticky."""
    # pi re-review H1: mirror promote_cmd's dual-store lookup so cross-project
    # candidates in the global store can actually be dismissed. Prior version
    # hard-coded scope='project' and reported "not in pool" for clusters that
    # visibly appeared in `candidates` listing — user trap.
    primary_store = _get_candidate_store(scope=scope)
    fallback_scope: _CandidateStoreScope = "global" if scope == "project" else "project"
    fallback_store = _get_candidate_store(scope=fallback_scope)
    candidate = primary_store.get(cluster_id)
    store = primary_store
    if candidate is None:
        fallback = fallback_store.get(cluster_id)
        if fallback is not None:
            candidate = fallback
            store = fallback_store
            console.print(
                f"[dim]Cluster '{cluster_id}' found in {fallback_scope} store; "
                f"dismissing there.[/dim]"
            )

    if candidate is None:
        console.print(f"[red]✗[/red] Cluster '{cluster_id}' not in pool")
        raise typer.Exit(1)

    if candidate.status == "promoted":
        console.print(
            f"[yellow]⚠ Cluster '{cluster_id}' is already promoted — "
            "promote is sticky; cannot dismiss.[/yellow]"
        )
        raise typer.Exit(1)

    store.dismiss(cluster_id, reason=reason)
    console.print(f"[green]✓[/green] Dismissed '{cluster_id}'")
    if reason:
        console.print(f"  [dim]reason:[/dim] {reason}")


# Top-level imports for W4 commands. These are scoped to this module's
# end so the existing W0-W3 commands above don't pay the import cost
# unless W4 features are used.
# ---------------------------------------------------------------------------
# M12 M2: unified Discovery queue (vibe skill discover)
# ---------------------------------------------------------------------------
#
# 呈现层合一裁决（m12-product-design.md v3）：用户只面对一个 Discovery
# 队列——本命令组就是候选池（stable/unstable/miss_recurrence 全来源）的
# 统一视图。routing_pending / SkillSuggestionCollector 降为信号源，本里程
# 碑不合并进队列。dismiss 走粘性否定列表（discovery_dismissals.jsonl，
# 不动候选行状态，--all 仍可见），与 `vibe skill dismiss`（翻候选行
# status）是两套机制。
#
# Imports live at the TOP of this section (not module-end like W4): the
# callback's option defaults (DEFAULT_MUTE_DAYS) are evaluated at
# definition time. The discovery module is lightweight (stdlib only).
from vibesop.core.observability.discovery import (  # noqa: E402
    DEFAULT_MUTE_DAYS,
    HISTORY_HIT_THRESHOLD,
    DiscoveryObservationStore,
    DiscoveryRow,
    DiscoverySignalStore,
    build_queue,
    candidate_source,
    cluster_fingerprint,
    count_skill_route_hits,
    threshold_suggestion,
)
from vibesop.core.observability.skill_promote import (  # noqa: E402
    ClusterCandidate,
    ClusterCandidateStore,
    dedupe_project_distribution,
    materialize_candidate,
)

discover_app = typer.Typer(
    name="discover",
    help="Unified Discovery queue — one view over all skill candidates (M12 M2).",
    no_args_is_help=False,
)


def _get_discovery_dir(scope: _CandidateStoreScope = "project") -> Path:
    """Dir holding discovery_dismissals.jsonl / discovery_observations.json.

    Mirrors the candidate-store scoping (project → <cwd>/.vibe/observability,
    global → ~/.vibe/observability). Tests patch this helper to redirect.
    """
    return (
        Path.cwd() / ".vibe" / "observability" if scope == "project" else _GLOBAL_OBSERVABILITY_DIR
    )


def _gather_scoped_candidates() -> dict[str, tuple[_CandidateStoreScope, ClusterCandidate]]:
    """All pending candidates (stable + unstable + all sources), both scopes.

    Dedup by cluster_id preferring the more heterogeneous record (same
    rule as ``_merge_dedup_candidates``), keeping the scope so dismiss /
    mute land in the matching signal store.

    gate18 claude NIT-3: this dedup rule has a deliberate mirror in the
    dashboard read-model (``vibesop.dashboard._discoveries``'s
    ``_load_scoped_candidates``) — the two MUST stay semantically
    identical so CLI and board render the same queue. Change one, change
    the other.
    """
    by_id: dict[str, tuple[_CandidateStoreScope, ClusterCandidate]] = {}
    for scope in ("project", "global"):
        store = _get_candidate_store(scope=scope)  # type: ignore[arg-type]
        for candidate in store.list_pending(include_unstable=True):
            existing = by_id.get(candidate.cluster_id)
            if existing is None or len(candidate.project_distribution) > len(
                existing[1].project_distribution
            ):
                by_id[candidate.cluster_id] = (scope, candidate)  # type: ignore[assignment]
    return by_id


def _discovery_rows(*, observe: bool = True) -> list[DiscoveryRow]:
    """Compose the unified queue: candidates joined with dismiss/mute/cooling.

    Cross-scope wiring (gate17 claude nit 1 / pi nit 3): the union of BOTH
    scopes' dismissed fingerprints and active mutes is fed into every
    ``build_queue`` call, so a candidate dismissed once (in either scope's
    negative list) is treated as dismissed everywhere — same fingerprint,
    one dismissal.
    """
    by_id = _gather_scoped_candidates()
    signal_stores = {
        scope: DiscoverySignalStore(_get_discovery_dir(scope))  # type: ignore[arg-type]
        for scope in ("project", "global")
    }
    dismissed_union: set[str] = set()
    mutes_union: dict[str, datetime] = {}
    for signal_store in signal_stores.values():
        dismissed_union |= signal_store.dismissed_fingerprints()
        mutes_union.update(signal_store.active_mutes())

    rows: list[DiscoveryRow] = []
    for scope in ("project", "global"):
        group = [c for s, c in by_id.values() if s == scope]
        if not group:
            continue
        rows.extend(
            build_queue(
                group,
                signal_stores[scope],
                DiscoveryObservationStore(_get_discovery_dir(scope)),  # type: ignore[arg-type]
                observe=observe,
                extra_dismissed=dismissed_union,
                extra_mutes=mutes_union,
            )
        )
    rows.sort(
        key=lambda r: (r.score, r.candidate.span_count, r.candidate.cluster_id),
        reverse=True,
    )
    return rows


def _discovery_dismiss_total() -> int:
    """Dismiss count across BOTH scopes (gate17 pi nit 8).

    Summed rather than local-only so the one-way-tightening hint uses the
    same cross-scope口径 as ``--history`` — a user dismissing 3 project +
    2 global candidates has still dismissed 5 suggestions.
    """
    return sum(
        DiscoverySignalStore(_get_discovery_dir(scope)).dismiss_count()  # type: ignore[arg-type]
        for scope in ("project", "global")
    )


def _resolve_discovery_candidate(
    cluster_id: str,
) -> tuple[_CandidateStoreScope, ClusterCandidate] | None:
    """Resolve a full or 8-char-prefix cluster_id to (scope, candidate)."""
    by_id = _gather_scoped_candidates()
    exact = by_id.get(cluster_id)
    if exact is not None:
        return exact
    matches = [pair for cid, pair in by_id.items() if cid.startswith(cluster_id)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        console.print(f"[red]✗[/red] Cluster id prefix '{cluster_id}' is ambiguous")
        raise typer.Exit(1)
    return None


def _redact_query(query: str, max_len: int) -> str:
    """Defensive redaction + single-line collapse + truncate for card display.

    Queries are already redacted at the write side (集中脱敏); this is a
    display-side second pass so a hand-edited store file can't leak
    secrets into the terminal.
    """
    from vibesop.utils.redaction import redact_sensitive

    cleaned = " ".join(redact_sensitive(str(query)).split())
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip() + "…"
    return cleaned


def _render_source(row: DiscoveryRow) -> str:
    if row.source == "miss_recurrence":
        return "[magenta]miss×复现[/magenta]"
    return f"gold {row.candidate.gold_rate * 100:.0f}%"


def _render_behavior(row: DiscoveryRow) -> str:
    if row.behavior == "consistent":
        return "[green]consistent[/green]"
    if row.behavior == "unavailable":
        return "[yellow]unavailable[/yellow]"
    return "[dim]未采集[/dim]"


def _render_discovery_list(rows: list[DiscoveryRow], *, show_all: bool) -> None:
    visible = rows if show_all else [r for r in rows if not r.dismissed and not r.muted]
    if not visible:
        if rows:
            console.print(
                "[dim]队列中的候选均已 dismiss/mute —— `vibe skill discover --all` 查看全部。[/dim]"
            )
            return
        console.print("[dim]Discovery 队列暂无候选。[/dim]")
        console.print("候选来自路由数据的自动汇聚，积累方式：")
        console.print("  [dim]1. 正常使用 vibe —— 每次路由都会静默记录观测数据[/dim]")
        console.print(
            "  [dim]2. 定期运行 [cyan]vibe skill scan-candidates --days 7[/cyan] "
            "把复现模式聚成候选[/dim]"
        )
        console.print(
            "  [dim]3. 跨项目复现用 [cyan]vibe skill scan-candidates "
            "--cross-project[/cyan]（先入 pool）[/dim]"
        )
        return

    table = Table(title="Discovery queue" + (" (all)" if show_all else ""))
    table.add_column("ID", style="bold", max_width=20)
    table.add_column("Score", justify="right")
    table.add_column("Pattern", max_width=36)
    table.add_column("Examples", max_width=40)
    table.add_column("Source", justify="right")
    table.add_column("Behavior")
    table.add_column("Age", justify="right")
    if show_all:
        table.add_column("Status")

    for row in rows if show_all else visible:
        candidate = row.candidate
        id_str = candidate.cluster_id[:8]
        if candidate.is_cross_project:
            id_str = f"[cyan][XP][/cyan] {id_str}"
        examples = "\n".join(_redact_query(q, 40) for q in candidate.queries[:3]) or "[dim]—[/dim]"
        age_str = f"{row.age_days}d"
        if row.cooling:
            age_str += "\n[dim]冷却中[/dim]"
        cells = [
            id_str,
            f"{row.score:.2f}",
            _redact_query(candidate.queries[0], 60) if candidate.queries else "[dim]—[/dim]",
            examples,
            _render_source(row),
            _render_behavior(row),
            age_str,
        ]
        if show_all:
            if row.dismissed:
                cells.append("[red]dismissed[/red]")
            elif row.muted and row.mute_expires_at is not None:
                cells.append(f"[yellow]muted → {row.mute_expires_at.date()}[/yellow]")
            else:
                cells.append("[dim]—[/dim]")
        table.add_row(*cells)

    console.print(table)
    if any(r.cooling for r in visible):
        console.print(
            "[dim]「冷却中」= 14 天无新增成员，已降档不再主动提示（新成员出现时自动恢复）。[/dim]"
        )
    console.print(
        "\n[dim]Next: `vibe skill promote <id>` 起草 SKILL.md · "
        "`vibe skill discover dismiss <id>` 否决 · "
        "`vibe skill discover --mute <id>` 静音 14 天 · "
        "`vibe skill discover --history` 闭环记录[/dim]"
    )


def _render_discovery_history() -> None:
    """已闭环记录 + 发现精度 + 提升后命中闭环检查.

    闭环检查数据源：.vibe/analytics.jsonl 的 ExecutionRecord.primary_skill
    （unified router 每次路由自动写入）。instinct/learner 无按 skill 命中
    计数；FeedbackCollector 只记显式反馈——analytics 是唯一自动累计源。
    文件不存在时如实标注「暂无数据源」。
    """
    all_rows: list[ClusterCandidate] = []
    dismiss_total = 0
    for scope in ("project", "global"):
        store = _get_candidate_store(scope=scope)  # type: ignore[arg-type]
        all_rows.extend(store.list_all())
        dismiss_total += DiscoverySignalStore(
            _get_discovery_dir(scope)  # type: ignore[arg-type]
        ).dismiss_count()

    promoted = [r for r in all_rows if r.status == "promoted"]
    store_dismissed = [r for r in all_rows if r.status == "dismissed"]
    dismissed_total = len(store_dismissed) + dismiss_total

    if not promoted and not dismissed_total:
        console.print("[dim]暂无闭环记录（尚无 promoted/dismissed 候选）。[/dim]")
        return

    if promoted:
        table = Table(title="Promoted（已提升）")
        table.add_column("Cluster", style="bold")
        table.add_column("Skill ID", max_width=44)
        table.add_column("Promoted at")
        table.add_column("路由命中闭环", max_width=40)
        analytics_path = Path.cwd() / ".vibe" / "analytics.jsonl"
        for row in promoted:
            skill_id = row.source_skill_id or "—"
            if row.source_skill_id:
                # gate17 pi nit 4: only hits AT/AFTER the promotion count —
                # pre-promotion hits are outside the window.
                hits = count_skill_route_hits(
                    row.source_skill_id, analytics_path, since=row.reviewed_at
                )
                if hits is None:
                    closed = "[dim]暂无数据源（analytics.jsonl 不存在）[/dim]"
                elif hits >= HISTORY_HIT_THRESHOLD:
                    closed = f"[green]✓ 提升后 {hits} 次命中（≥{HISTORY_HIT_THRESHOLD}）[/green]"
                else:
                    closed = f"[yellow]提升后 {hits}/{HISTORY_HIT_THRESHOLD} 次命中[/yellow]"
            else:
                closed = "[dim]无 skill_id 记录[/dim]"
            table.add_row(
                row.cluster_id[:8],
                skill_id,
                row.reviewed_at.date().isoformat() if row.reviewed_at else "—",
                closed,
            )
        console.print(table)
        console.print(
            "[dim]命中按 promote 时记录的 skill_id 匹配；激活时改过名的技能无法关联。[/dim]"
        )
        # gate17 claude nit 9: disclose the counting口径 — cwd project only.
        console.print(
            "[dim]命中口径：仅统计当前项目（cwd）的 analytics.jsonl；"
            "全局 scope 提升在其他项目的命中不计入。[/dim]"
        )

    if store_dismissed or dismiss_total:
        table = Table(title="Dismissed（已否决）")
        table.add_column("Cluster", style="bold")
        table.add_column("Reason", max_width=50)
        table.add_column("Via")
        for row in store_dismissed:
            table.add_row(
                row.cluster_id[:8], row.dismiss_reason or "[dim]—[/dim]", "candidate pool"
            )
        for scope in ("project", "global"):
            signals = DiscoverySignalStore(
                _get_discovery_dir(scope)  # type: ignore[arg-type]
            ).dismissals()
            for signal in signals:
                table.add_row(
                    signal.cluster_id[:8] or signal.fingerprint[:8],
                    signal.reason or "[dim]—[/dim]",
                    f"negative list ({scope})",
                )
        console.print(table)

    total = len(promoted) + dismissed_total
    precision = len(promoted) / total if total else 0.0
    console.print(
        f"\n[bold]发现精度[/bold] promoted/(promoted+dismissed) = "
        f"{len(promoted)}/{total} = [cyan]{precision:.0%}[/cyan]"
    )
    suggestion = threshold_suggestion(dismissed_total)
    if suggestion:
        console.print(f"[yellow]⚠ {suggestion}[/yellow]")


@discover_app.callback(invoke_without_command=True)
def _discover_main(  # pyright: ignore[reportUnusedFunction]
    ctx: typer.Context,
    show_all: bool = typer.Option(
        False, "--all", help="Show dismissed/muted candidates too (default: hidden)"
    ),
    mute: str | None = typer.Option(
        None, "--mute", help="Temporarily mute a candidate by cluster id (auto-restores)"
    ),
    mute_days: int = typer.Option(
        DEFAULT_MUTE_DAYS, "--mute-days", help="Mute duration in days (default 14)"
    ),
    history: bool = typer.Option(
        False, "--history", help="Show closed-loop record + discovery precision"
    ),
) -> None:
    """Unified Discovery queue: one ranked view over all skill candidates.

    Default lists pending candidates sorted by evidence_score (簇规模 /
    distinct task 数 / 来源信号 / 跨项目加权——公式见
    observability.discovery 模块 docstring)。Dismissed 与静音中的候选
    默认隐藏，--all 可见。
    """
    if ctx.invoked_subcommand is not None:
        return
    if mute is not None and history:
        console.print("[red]✗[/red] --mute and --history cannot be combined")
        raise typer.Exit(1)

    if mute is not None:
        if mute_days < 1:
            console.print(f"[red]✗[/red] --mute-days must be >=1, got {mute_days}")
            raise typer.Exit(1)
        resolved = _resolve_discovery_candidate(mute)
        if resolved is None:
            console.print(f"[red]✗[/red] Cluster '{mute}' not in Discovery queue")
            raise typer.Exit(1)
        scope, candidate = resolved
        signal_store = DiscoverySignalStore(_get_discovery_dir(scope))
        signal = signal_store.record_mute(
            cluster_fingerprint(candidate.queries), candidate.cluster_id, days=mute_days
        )
        console.print(
            f"[green]✓[/green] Muted '{candidate.cluster_id[:8]}' until "
            f"{signal.expires_at.date() if signal.expires_at else '?'} "
            f"[dim](不进否定列表，到期自动恢复)[/dim]"
        )
        return

    if history:
        _render_discovery_history()
        return

    _render_discovery_list(_discovery_rows(), show_all=show_all)


@discover_app.command(name="dismiss")
def discover_dismiss_cmd(  # pyright: ignore[reportUnusedFunction]
    cluster_id: str = typer.Argument(..., help="Cluster ID (full or 8-char prefix)"),
    reason: str | None = typer.Option(
        None, "--reason", help="Why this candidate is rejected (recorded in the negative list)"
    ),
) -> None:
    """Dismiss a candidate into the sticky negative list.

    记录到 ``discovery_dismissals.jsonl``（cluster 指纹 + 原因 + 时间）：
    不再主动提示、列表默认隐藏（--all 可见）。不翻候选行状态——与
    `vibe skill dismiss`（candidate pool status）是两套机制。反馈单向
    收紧：dismiss 计数达到阈值时建议上调准入阈值（只建议，不自动改）。
    """
    resolved = _resolve_discovery_candidate(cluster_id)
    if resolved is None:
        console.print(f"[red]✗[/red] Cluster '{cluster_id}' not in Discovery queue")
        raise typer.Exit(1)
    scope, candidate = resolved
    signal_store = DiscoverySignalStore(_get_discovery_dir(scope))
    fingerprint = cluster_fingerprint(candidate.queries)

    # Cross-scope semantics (gate17 claude nit 1): a dismissal in EITHER
    # scope's negative list covers this fingerprint.
    other_scope: _CandidateStoreScope = "global" if scope == "project" else "project"
    other_store = DiscoverySignalStore(_get_discovery_dir(other_scope))
    if (
        fingerprint in signal_store.dismissed_fingerprints()
        or fingerprint in other_store.dismissed_fingerprints()
    ):
        console.print(f"[dim]Cluster '{candidate.cluster_id[:8]}' is already dismissed.[/dim]")
        return

    signal_store.record_dismiss(fingerprint, candidate.cluster_id, reason)
    console.print(f"[green]✓[/green] Dismissed '{candidate.cluster_id[:8]}' (sticky negative list)")
    if reason:
        console.print(f"  [dim]reason:[/dim] {reason}")

    # gate17 pi nit 8 + claude nit 3: count dismissals across BOTH scopes
    # (same口径 as --history), and point at the knobs that actually gate
    # this candidate's admission source.
    suggestion = threshold_suggestion(
        _discovery_dismiss_total(), source=candidate_source(candidate)
    )
    if suggestion:
        console.print(f"[yellow]⚠ {suggestion}[/yellow]")


app.add_typer(discover_app, name="discover")
