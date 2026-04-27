"""Skills suggestions command — auto-detected skill suggestions from usage patterns."""

from pathlib import Path

import typer
from rich.console import Console

console = Console()


def suggestions(
    dismiss: bool = typer.Option(False, "--dismiss", "-d", help="Dismiss all pending suggestions"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show auto-detected skill suggestions from usage patterns.

    VibeSOP learns from your repeated workflows and suggests creating
    reusable skills. Each suggestion is based on a sequence of tool
    calls you've made successfully at least 5 times.

    \b
    Examples:
        # View pending suggestions
        vibe skills suggestions

        # Dismiss all
        vibe skills suggestions --dismiss

        # Machine-readable output
        vibe skills suggestions --json
    """
    from vibesop.core.skills.suggestion_collector import SkillSuggestionCollector

    collector = SkillSuggestionCollector()

    if json_output:
        import json

        suggestions_data = [s.to_dict() for s in collector.get_pending()]
        console.print(
            json.dumps(
                {"suggestions": suggestions_data, **collector.get_stats()}, indent=2, default=str
            )
        )
        return

    if dismiss:
        count = collector.dismiss_all()
        console.print(f"[green]\u2713[/green] Dismissed [bold]{count}[/bold] pending suggestions.")
        return

    pending = collector.get_pending()
    if not pending:
        console.print(
            "[dim]No pending skill suggestions. Keep working \u2014 VibeSOP learns from your workflows![/dim]"
        )
        stats = collector.get_stats()
        if stats["created"] > 0:
            console.print(
                f"[dim]{stats['created']} skill(s) created from suggestions so far.[/dim]"
            )
        return

    console.print(
        f"\n[bold]\U0001f4a1 Pending Skill Suggestions[/bold] [dim]({len(pending)} total)[/dim]\n"
    )

    for i, s in enumerate(pending, 1):
        steps_str = " \u2192 ".join(s.pattern_steps[:5])
        if len(s.pattern_steps) > 5:
            steps_str += f" \u2192 ... (+{len(s.pattern_steps) - 5} more)"
        tags_str = f" [dim]{', '.join(s.context_tags)}[/dim]" if s.context_tags else ""

        console.print(
            f"[bold cyan]{i}.[/bold cyan] [bold]{s.suggested_name}[/bold cyan] (confidence: {s.confidence:.0%})"
        )
        console.print(f"    Pattern: {steps_str}")
        console.print(
            f"    Occurrences: {s.occurrences} times, {s.success_rate:.0%} success{tags_str}"
        )
        console.print(f"    ID: [dim]{s.id}[/dim]")
        console.print()

    console.print("[bold]Actions:[/bold]")
    console.print("  [green]vibe skills create --from-suggestion <id>[/green] \u2014 Create skill")
    console.print("  [dim]vibe skills suggestions --dismiss[/dim] \u2014 Dismiss all")
    console.print()


def create_from_suggestion(suggestion_id: str) -> None:
    """Create a skill from an auto-detected pattern suggestion."""
    from vibesop.core.skills.suggestion_collector import SkillSuggestionCollector
    from vibesop.core.skills.understander import SkillAutoConfigurator, understand_skill_from_file

    collector = SkillSuggestionCollector()
    suggestion = collector.get(suggestion_id)

    if not suggestion:
        console.print(f"[red]\u2717 Suggestion not found: {suggestion_id}[/red]")
        console.print("[dim]Run `vibe skills suggestions` to see available suggestions.[/dim]")
        raise typer.Exit(1)

    if suggestion.status == "created":
        console.print(
            f"[yellow]\u26a0 Suggestion already created as skill: {suggestion.skill_id}[/yellow]"
        )
        return

    console.print("\n[bold]\u2728 Creating skill from pattern...[/bold]")
    console.print(f"  Name: [cyan]{suggestion.suggested_name}[/cyan]")
    console.print(f"  Pattern: [dim]{' \u2192 '.join(suggestion.pattern_steps)}[/dim]")
    console.print(
        f"  Confidence: {suggestion.confidence:.0%} ({suggestion.occurrences} occurrences)"
    )

    skill_dir = Path.cwd() / ".vibe" / "skills" / suggestion.suggested_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    steps_md = "\n".join(f"   - {step}" for step in suggestion.pattern_steps)
    content = f"""---
id: custom/{suggestion.suggested_name}
name: {suggestion.suggested_name}
description: {suggestion.suggested_description}
tags: [{", ".join(suggestion.context_tags) or "workflow, auto-generated"}]
intent: general
namespace: custom
version: 1.0.0
type: workflow
auto_generated: true
source_suggestion: {suggestion.id}
---

# {suggestion.suggested_name.replace("-", " ").title()}

> Auto-generated from your workflow patterns
> Confidence: {suggestion.confidence:.0%} | Occurrences: {suggestion.occurrences}

## Overview

{suggestion.suggested_description}

## Detected Workflow Steps

{steps_md}

## Usage

This skill was auto-detected from your successful tool call sequences.
Edit this file to add context, refine steps, and improve accuracy.

```bash
vibe route "your query related to {" \u2192 ".join(suggestion.pattern_steps[:3])}"
```
"""
    (skill_dir / "SKILL.md").write_text(content)
    console.print(f"[green]\u2713[/green] SKILL.md created: {skill_dir}/SKILL.md")

    try:
        config = understand_skill_from_file(skill_dir, scope="project")
        configurator = SkillAutoConfigurator()
        configurator.save_config(config, Path.cwd() / ".vibe" / "skills")

        console.print(
            f"[green]\u2713[/green] Auto-analyzed: category={config.category}, priority={config.priority}"
        )
        console.print(f"  Routing patterns: {len(config.routing_patterns)} generated")
    except Exception as e:
        console.print(f"[yellow]\u26a0 Auto-config skipped: {e}[/yellow]")

    skill_id = f"custom/{suggestion.suggested_name}"
    collector.mark_created(suggestion.id, skill_id)
    console.print(f"[green]\u2713[/green] Registered as: [bold]{skill_id}[/bold]")

    console.print('\n[dim]Next: `vibe route "your query"` will now match this skill[/dim]')


__all__ = ["create_from_suggestion", "suggestions"]
