# pyright: ignore[reportPossiblyUnboundVariable, reportUnnecessaryComparison]
"""Discovery commands: suggestions, recommended, featured, create."""

from pathlib import Path

import questionary
import typer
from rich.console import Console

from vibesop.core.skills import SkillManager

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
        console.print(f"[green]✓[/green] Dismissed [bold]{count}[/bold] pending suggestions.")
        return

    pending = collector.get_pending()
    if not pending:
        console.print(
            "[dim]No pending skill suggestions. Keep working — VibeSOP learns from your workflows![/dim]"
        )
        stats = collector.get_stats()
        if stats["created"] > 0:
            console.print(
                f"[dim]{stats['created']} skill(s) created from suggestions so far.[/dim]"
            )
        return

    console.print(
        f"\n[bold]💡 Pending Skill Suggestions[/bold] [dim]({len(pending)} total)[/dim]\n"
    )

    for i, s in enumerate(pending, 1):
        steps_str = " → ".join(s.pattern_steps[:5])
        if len(s.pattern_steps) > 5:
            steps_str += f" → ... (+{len(s.pattern_steps) - 5} more)"
        tags_str = f" [dim]{', '.join(s.context_tags)}[/dim]" if s.context_tags else ""

        console.print(
            f"[bold cyan]{i}.[/bold cyan] [bold]{s.suggested_name}[/bold] (confidence: {s.confidence:.0%})"
        )
        console.print(f"    Pattern: {steps_str}")
        console.print(
            f"    Occurrences: {s.occurrences} times, {s.success_rate:.0%} success{tags_str}"
        )
        console.print(f"    ID: [dim]{s.id}[/dim]")
        console.print()

    console.print("[bold]Actions:[/bold]")
    console.print("  [green]vibe skills create --from-suggestion <id>[/green] — Create skill")
    console.print("  [dim]vibe skills suggestions --dismiss[/dim] — Dismiss all")
    console.print()


def recommended(
    collaborative: bool = typer.Option(
        False, "--collaborative", "-c", help="Show collaborative filtering recommendations"
    ),
    install: bool = typer.Option(False, "--install", "-i", help="Install all recommended skills"),
) -> None:
    """Show personalized skill recommendations.

    Recommends skills based on your project's tech stack and
    what other users with similar setups have installed.

    \b
    Examples:
        # Stack-based recommendations
        vibe skills recommended

        # Collaborative filtering
        vibe skills recommended --collaborative

        # Install all in one go
        vibe skills recommended --install
    """
    from vibesop.core.skills.recommender import SkillRecommender

    recommender = SkillRecommender()

    if collaborative:
        recs = recommender.recommend_collaborative()
        title = "Collaborative Recommendations"
    else:
        stack_recs = recommender.recommend_for_project()
        missing_recs = recommender.detect_missing_skills()
        recs = stack_recs + [
            r for r in missing_recs if r.skill_id not in {s.skill_id for s in stack_recs}
        ]
        title = "Recommended for This Project"

    if not recs:
        console.print(
            "[dim]No recommendations available. You might have all essential skills installed![/dim]"
        )
        return

    from rich.table import Table

    table = Table(title=title)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Skill", style="cyan")
    table.add_column("Reason", style="dim")
    table.add_column("Status", justify="center")

    for i, r in enumerate(recs, 1):
        status_str = "[green]installed[/green]" if r.installed else "[yellow]not installed[/yellow]"
        table.add_row(str(i), r.skill_id, r.reason, status_str)

    console.print(table)

    uninstalled = [r for r in recs if not r.installed]
    if uninstalled:
        console.print(f"\n[bold]{len(uninstalled)}[/bold] skill(s) not installed.")
        if install:
            for r in uninstalled:
                try:
                    from vibesop.installer.pack_installer import PackInstaller

                    installer = PackInstaller()
                    installer.install_skill_from_github(r.skill_id)
                    console.print(f"[green]✓[/green] Installed: {r.skill_id}")
                except Exception as e:
                    console.print(f"[red]✗[/red] {r.skill_id}: {e}")
        else:
            console.print("[dim]Run with --install to install all recommendations.[/dim]")


def create(
    name: str | None = typer.Option(None, help="Skill name (kebab-case)"),
    description: str | None = typer.Option(None, help="What this skill does"),
    from_template: str | None = typer.Option(None, "--from", help="Base on existing skill"),
    from_suggestion: str | None = typer.Option(
        None,
        "--from-suggestion",
        help="Create from auto-detected pattern (use 'vibe skills suggestions' to list)",
    ),
    namespace: str = typer.Option("custom", help="Skill namespace"),
    interactive: bool = typer.Option(True, help="Use interactive wizard"),
) -> None:
    """Create a new skill from natural language, template, or auto-detected pattern.

    \b
    Examples:
        # Interactive wizard
        vibe skills create

        # Create from existing skill template
        vibe skills create --from gstack/review --name my-review

        # Create from auto-detected pattern
        vibe skills create --from-suggestion sug_abc123

        # Non-interactive
        vibe skills create --name security-audit --description "Scan for vulnerabilities"
    """
    manager = SkillManager()

    if from_suggestion:
        _create_from_suggestion(from_suggestion)
        return

    if from_template:
        template_info = manager.get_skill_info(from_template)
        if not template_info:
            console.print(f"[red]✗ Template skill not found: {from_template}[/red]")
            raise typer.Exit(1)

        if not name:
            name = questionary.text(
                "New skill name:",
                default=f"my-{from_template.split('/')[-1]}",
            ).ask()
            if not name:
                console.print("[yellow]Cancelled.[/yellow]")
                return

        skill_dir = Path.cwd() / ".vibe" / "skills" / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        template_path = template_info.get("source_file")
        if template_path:
            template_text = Path(template_path).read_text()
            new_text = template_text.replace(
                f"id: {from_template}", f"id: {namespace}/{name}"
            ).replace(f"name: {from_template.split('/')[-1]}", f"name: {name}")
            if description:
                # YAML-safe the description (handle [, {, :, etc.)
                from vibesop.adapters._shared import _yaml_dquote

                safe_desc = _yaml_dquote(description)
                old_desc = template_info.get("description", "")
                old_desc_alt = _yaml_dquote(old_desc) if old_desc else None
                # Try quoted first, then bare
                replaced = new_text.replace(
                    f"description: {old_desc}",
                    f"description: {safe_desc}",
                )
                if replaced == new_text and old_desc_alt and old_desc_alt != f'"{old_desc}"':
                    replaced = new_text.replace(
                        f"description: {old_desc_alt}",
                        f"description: {safe_desc}",
                    )
                new_text = replaced
            (skill_dir / "SKILL.md").write_text(new_text)
        else:
            _generate_skill_md(skill_dir, name, description or f"{name} skill", namespace)

        console.print(f"[green]✓ Created skill from template:[/green] {skill_dir}")
        console.print("[dim]Next steps:[/dim]")
        console.print(f"  1. Edit {skill_dir}/SKILL.md")
        console.print(f"  2. Run [bold]vibe skills validate {namespace}/{name}[/bold]")
        console.print(f"  3. Run [bold]vibe skills enable {namespace}/{name}[/bold]")
        return

    keywords: str | None = None

    if interactive and not name:
        console.print("[bold]✨ Skill Creation Wizard[/bold]\n")
        name = questionary.text(
            "Skill name (kebab-case):",
            validate=lambda t: bool(t) or "Name is required",
        ).ask()
        if not name:
            console.print("[yellow]Cancelled.[/yellow]")
            return

        description = questionary.text(
            "What does this skill do?",
            default=description or "",
        ).ask()

        keywords = questionary.text(
            "Trigger keywords (comma-separated):",
        ).ask()

        namespace = (
            questionary.text(
                "Namespace:",
                default=namespace,
            ).ask()
            or namespace
        )

    if not name:
        console.print("[red]✗ Skill name is required[/red]")
        raise typer.Exit(1)

    skill_dir = Path.cwd() / ".vibe" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    _generate_skill_md(
        skill_dir,
        name,
        description or f"{name} skill",
        namespace,
        keywords=keywords if interactive else None,
    )

    console.print(f"[green]✓ Created skill:[/green] {skill_dir}")
    console.print("[dim]Next steps:[/dim]")
    console.print(f"  1. Edit {skill_dir}/SKILL.md")
    console.print(f"  2. Run [bold]vibe skills validate {namespace}/{name}[/bold]")
    console.print(f"  3. Run [bold]vibe skills enable {namespace}/{name}[/bold]")


def _create_from_suggestion(suggestion_id: str) -> None:
    from vibesop.core.skills.suggestion_collector import SkillSuggestionCollector
    from vibesop.core.skills.understander import SkillAutoConfigurator, understand_skill_from_file

    collector = SkillSuggestionCollector()
    suggestion = collector.get(suggestion_id)

    if not suggestion:
        console.print(f"[red]✗ Suggestion not found: {suggestion_id}[/red]")
        console.print("[dim]Run `vibe skills suggestions` to see available suggestions.[/dim]")
        raise typer.Exit(1)

    if suggestion.status == "created":
        console.print(
            f"[yellow]⚠ Suggestion already created as skill: {suggestion.skill_id}[/yellow]"
        )
        return

    console.print("\n[bold]✨ Creating skill from pattern...[/bold]")
    console.print(f"  Name: [cyan]{suggestion.suggested_name}[/cyan]")
    console.print(f"  Pattern: [dim]{' → '.join(suggestion.pattern_steps)}[/dim]")
    console.print(
        f"  Confidence: {suggestion.confidence:.0%} ({suggestion.occurrences} occurrences)"
    )

    skill_dir = Path.cwd() / ".vibe" / "skills" / suggestion.suggested_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    steps_md = "\n".join(f"   - {step}" for step in suggestion.pattern_steps)
    tags_str = ", ".join(suggestion.context_tags) or "workflow, auto-generated"
    # YAML-safe: wrap description in double quotes
    safe_desc = suggestion.suggested_description.replace("\\", "\\\\").replace('"', '\\"')
    content = f"""---
id: custom/{suggestion.suggested_name}
name: {suggestion.suggested_name}
description: "{safe_desc}"
tags: [{tags_str}]
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
vibe route "your query related to {" → ".join(suggestion.pattern_steps[:3])}"
```
"""
    (skill_dir / "SKILL.md").write_text(content)
    console.print(f"[green]✓[/green] SKILL.md created: {skill_dir}/SKILL.md")

    try:
        config = understand_skill_from_file(skill_dir, scope="project")
        configurator = SkillAutoConfigurator()
        configurator.save_config(config, Path.cwd() / ".vibe" / "skills")

        console.print(
            f"[green]✓[/green] Auto-analyzed: category={config.category}, priority={config.priority}"
        )
        console.print(f"  Routing patterns: {len(config.routing_patterns)} generated")
    except Exception as e:
        console.print(f"[yellow]⚠ Auto-config skipped: {e}[/yellow]")

    skill_id = f"custom/{suggestion.suggested_name}"
    collector.mark_created(suggestion.id, skill_id)
    console.print(f"[green]✓[/green] Registered as: [bold]{skill_id}[/bold]")

    console.print('\n[dim]Next: `vibe route "your query"` will now match this skill[/dim]')


def _generate_skill_md(
    skill_dir: Path,
    name: str,
    description: str,
    namespace: str,
    keywords: str | None = None,
) -> None:
    tags = ""
    if keywords:
        tag_list = [k.strip() for k in keywords.split(",") if k.strip()]
        tags = f"\ntags: [{', '.join(tag_list)}]"

    content = f"""---
id: {namespace}/{name}
name: {name}
description: "{description}"{tags}
intent: general
namespace: {namespace}
version: 1.0.0
type: prompt
---

# {name.replace("-", " ").title()}

## Overview

{description}

## Workflow

1. Step one
2. Step two
3. Step three

## Usage

```bash
vibe route "your query here"
```
"""
    (skill_dir / "SKILL.md").write_text(content)


def featured(
    stack: str | None = typer.Option(
        None, "--stack", "-s", help="Filter by tech stack (python, typescript, etc.)"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    install: bool = typer.Option(  # noqa: ARG001  # Typer CLI option (framework-passed)
        False, "--install", "-i", help="Install all featured skills for stack"
    ),
) -> None:
    """Browse the curated featured skills registry.

    Shows high-quality, community-curated skills organized by tech stack.
    Use --stack to filter by your project's primary language.

    Examples:
        vibe skills featured                   # All featured skills
        vibe skills featured --stack python    # Python-specific
        vibe skills featured --stack typescript --install
    """
    from vibesop.core.skills.featured_registry import FeaturedRegistry

    registry = FeaturedRegistry()

    if stack:
        skills = registry.for_stack(stack)
        title = f"Featured Skills for [cyan]{stack.title()}[/cyan]"
    else:
        skills = registry.skills
        title = "All Featured Skills"

    if json_output:
        import json

        console.print(json.dumps([s.to_dict() for s in skills], indent=2, ensure_ascii=False))
        return

    if not skills:
        console.print(f"[dim]No featured skills found for stack '{stack}'.[/dim]")
        stacks = registry.stacks_available()
        console.print(f"[dim]Available stacks: {', '.join(stacks) if stacks else 'none'}[/dim]")
        return

    from rich.table import Table

    table = Table(title=title)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Skill", style="cyan")
    table.add_column("Rating", justify="center")
    table.add_column("Stacks", style="dim")
    table.add_column("Description", max_width=50, style="dim")

    for i, s in enumerate(skills, 1):
        rating_style = (
            "green" if s.quality_rating >= 0.85 else "yellow" if s.quality_rating >= 0.7 else "dim"
        )
        rating_str = f"[{rating_style}]{s.quality_rating:.0%}[/{rating_style}]"
        stacks_str = ", ".join(s.stacks[:3]) if s.stacks else "any"
        table.add_row(
            str(i),
            s.skill_id,
            rating_str,
            stacks_str,
            s.description[:80],
        )

    console.print()
    console.print(table)
    console.print()
    console.print(f"[dim]{len(skills)} featured skills shown.[/dim]")

    if stack:
        console.print(
            f"[dim]Install with:[/dim] [cyan]vibe skills featured --stack {stack} --install[/cyan]"
        )
    else:
        stacked = registry.stacks_available()
        if stacked:
            console.print(f"[dim]Filter by stack: {', '.join(stacked[:8])}[/dim]")
    console.print()
