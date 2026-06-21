# pyright: ignore[reportPossiblyUnboundVariable, reportUnnecessaryComparison]
"""Quality commands: report, feedback, skill_optimize, rate, ratings."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.skills.evaluator import RoutingEvaluator

console = Console()


def report(
    grade: str | None = typer.Option(
        None,
        "--grade",
        "-g",
        help="Filter by grade (A, B, C, D, F)",
    ),
    suggest_removal: bool = typer.Option(
        False,
        "--suggest-removal",
        help="Show only skills recommended for removal (grade F)",
    ),
) -> None:
    """Show skill quality report with grades.

    \b
    Examples:
        # Show all skills with grades
        vibe skills report

        # Show only skills needing attention
        vibe skills report --grade D

        # Show skills recommended for removal
        vibe skills report --suggest-removal
    """
    from rich.table import Table

    evaluator = RoutingEvaluator()
    all_evals = evaluator.evaluate_all_skills()

    if not all_evals:
        console.print("[yellow]No evaluation data available.[/yellow]")
        console.print("[dim]Use skills to generate feedback data.[/dim]")
        raise typer.Exit(0)

    filtered = list(all_evals.values())
    if suggest_removal:
        filtered = [e for e in filtered if e.grade == "F"]
    elif grade:
        filtered = [e for e in filtered if e.grade == grade.upper()]

    if not filtered:
        console.print("[dim]No skills match the filter criteria.[/dim]")
        raise typer.Exit(0)

    filtered.sort(key=lambda e: e.quality_score, reverse=True)

    table = Table(title="Skill Quality Report")
    table.add_column("Skill", style="cyan")
    table.add_column("Grade", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Routes", justify="right")
    table.add_column("Success", justify="right")
    table.add_column("User Score", justify="right")
    table.add_column("Routing Impact", justify="center")

    grade_colors = {
        "A": "green",
        "B": "green",
        "C": "yellow",
        "D": "yellow",
        "F": "red",
    }
    grade_icons = {
        "A": "✅",
        "B": "✅",
        "C": "✓",
        "D": "⚠️",
        "F": "🗑️",
    }
    impact_map = {
        "A": "[green]+0.05 boost[/green]",
        "B": "[green]+0.02 boost[/green]",
        "C": "[dim]no change[/dim]",
        "D": "[yellow]-0.02 demote[/yellow]",
        "F": "[red]-0.05 demote[/red]",
    }

    for evaluation in filtered:
        color = grade_colors.get(evaluation.grade, "dim")
        icon = grade_icons.get(evaluation.grade, "")
        impact = impact_map.get(evaluation.grade, "—")
        if evaluation.total_routes < 3:
            impact = "[dim]insufficient data[/dim]"
        table.add_row(
            evaluation.skill_id,
            f"[{color}]{evaluation.grade}[/{color}] {icon}",
            f"{evaluation.quality_score:.0%}",
            str(evaluation.total_routes),
            f"{evaluation.success_rate:.0%}" if evaluation.total_routes > 0 else "—",
            f"{evaluation.user_score:.2f}",
            impact,
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(filtered)} skills[/dim]")
    console.print("[dim]Routing impact only applies when total_routes >= 3[/dim]")


def feedback(
    skill_id: str = typer.Option(..., "--skill", "-s", help="Skill ID"),
    query: str = typer.Option(..., "--query", "-q", help="Original user query"),
    helpful: str | None = typer.Option(
        None,
        "--helpful",
        "-h",
        help="Was the skill helpful? (yes/no)",
    ),
    success: str | None = typer.Option(
        None,
        "--success",
        help="Did execution succeed? (yes/no)",
    ),
    execution_time: float | None = typer.Option(
        None,
        "--time",
        "-t",
        help="Execution time in milliseconds",
    ),
    notes: str | None = typer.Option(
        None,
        "--notes",
        "-n",
        help="Optional notes",
    ),
) -> None:
    """Record post-execution feedback for a skill.

    \b
    Examples:
        # Mark a skill as helpful
        vibe skills feedback --skill gstack/review --query "review code" --helpful yes

        # Report execution failure with notes
        vibe skills feedback --skill gstack/review --query "review code" --success no --notes "missed edge case"
    """
    from vibesop.core.feedback import ExecutionFeedbackCollector

    collector = ExecutionFeedbackCollector()

    was_helpful = None
    if helpful is not None:
        was_helpful = helpful.lower() in ("yes", "true", "1", "y")

    execution_success = None
    if success is not None:
        execution_success = success.lower() in ("yes", "true", "1", "y")

    collector.collect(
        skill_id=skill_id,
        query=query,
        was_helpful=was_helpful,
        execution_success=execution_success,
        execution_time_ms=execution_time,
        notes=notes,
    )

    console.print(f"[green]✓ Feedback recorded for '{skill_id}'[/green]")
    if was_helpful is not None:
        icon = "👍" if was_helpful else "👎"
        console.print(f"  [dim]Helpful: {icon}[/dim]")
    if execution_success is not None:
        icon = "✅" if execution_success else "❌"
        console.print(f"  [dim]Execution: {icon}[/dim]")

    from vibesop.core.badges import BadgeTracker, get_badge_display

    tracker = BadgeTracker()
    new_badges = tracker.check_feedback_event()
    for badge in new_badges:
        meta = get_badge_display(badge.type)
        console.print()
        console.print(f"[bold yellow]{meta['icon']}  New Badge: {meta['title']}[/bold yellow]")
        console.print(f"   [dim]{meta['description']}[/dim]")


def skill_optimize(
    skill_id: str = typer.Argument(..., help="Skill ID to analyze (e.g., 'gstack/investigate')"),
    min_confidence: float = typer.Option(
        0.6, "--min-confidence", "-c", help="Minimum confidence for actionable suggestions"
    ),
    n: int = typer.Option(5, "--top", "-n", help="Number of keyword suggestions"),
) -> None:
    """Suggest trigger keyword improvements based on routing feedback.

    Analyzes feedback records where this skill was the correct answer
    but wasn't routed, and extracts candidate keywords from the queries.

    Examples:
        vibe skill optimize gstack/investigate
        vibe skill optimize superpowers/architect --top 10
    """
    try:
        from vibesop.core.feedback import FeedbackCollector
    except ImportError as err:
        console.print("[yellow]Feedback system not available[/yellow]")
        raise typer.Exit(1) from err

    collector = FeedbackCollector()
    mismatches = collector.get_top_mismatches(top_n=100)

    candidate_queries: list[str] = []
    for m in mismatches:
        if m["actual_skill"] == skill_id and m["avg_confidence"] >= min_confidence:
            candidate_queries.extend(m["example_queries"])

    if not candidate_queries:
        console.print(f"[dim]No feedback data found for {skill_id} as correct skill[/dim]")
        console.print("[dim]Use `vibe feedback record` to collect routing feedback first[/dim]")
        raise typer.Exit(0)

    import re
    from collections import Counter

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
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "it",
        "they",
        "them",
        "this",
        "that",
        "these",
        "those",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "from",
        "by",
        "about",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "and",
        "but",
        "or",
        "not",
        "no",
        "if",
        "then",
        "else",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "now",
        "up",
        "out",
        "help",
    }

    word_counts: Counter[str] = Counter()
    for query in candidate_queries:
        words = re.findall(r"\w+", query.lower())
        for word in words:
            if word not in stop_words and len(word) > 2:
                word_counts[word] += 1

    top_keywords = word_counts.most_common(n)
    if not top_keywords:
        console.print("[dim]No meaningful keywords extracted from feedback[/dim]")
        raise typer.Exit(0)

    console.print()
    console.print(
        Panel(
            f"[bold]Keyword Suggestions for [cyan]{skill_id}[/cyan][/bold]\n"
            f"[dim]Based on {len(candidate_queries)} feedback records[/dim]",
            border_style="blue",
        )
    )

    table = Table(title="Suggested Keywords")
    table.add_column("#", style="dim")
    table.add_column("Keyword", style="cyan")
    table.add_column("Frequency", style="green")
    table.add_column("Action", style="yellow")

    for i, (word, count) in enumerate(top_keywords, 1):
        table.add_row(str(i), word, str(count), "Consider adding as trigger")

    console.print(table)
    console.print()
    console.print(
        "[dim]To add a keyword: add it to the skill's trigger_when field in registry.yaml[/dim]"
    )


def rate(
    skill_id: str = typer.Argument(..., help="Skill ID to rate"),
    score: int = typer.Argument(..., help="Rating score (1-5)"),
    review: str | None = typer.Option(None, "--review", "-r", help="Optional text review"),
) -> None:
    """Rate a skill (1-5 stars) with optional review.

    \b
    Examples:
        # Rate a skill 5 stars
        vibe skills rate gstack/review 5

        # Rate with review
        vibe skills rate gstack/review 4 --review "Good but slow"
    """
    from vibesop.core.skills.ratings import SkillRatingStore

    if not 1 <= score <= 5:
        console.print("[red]✗ Score must be 1-5[/red]")
        raise typer.Exit(1)

    store = SkillRatingStore()
    store.rate(skill_id, score, review or "")

    stars = "⭐" * score + "☆" * (5 - score)
    avg = store.get_avg_score(skill_id)
    count = store.get_count(skill_id)
    console.print(f"[green]✓[/green] Rated {skill_id}: {stars}")
    console.print(f"  Average: {avg:.1f}/5 ({count} review(s))")
    if review:
        console.print(f"  Review: [dim]{review}[/dim]")


def ratings(
    skill_id: str | None = typer.Argument(None, help="Skill ID or omit for top-rated"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of top skills to show"),
) -> None:
    """View skill ratings and reviews.

    \b
    Examples:
        # Show ratings for a specific skill
        vibe skills ratings gstack/review

        # Show top-rated skills
        vibe skills ratings
    """
    from vibesop.core.skills.ratings import SkillRatingStore

    store = SkillRatingStore()

    if skill_id:
        ratings_list = store.get_ratings(skill_id)
        avg = store.get_avg_score(skill_id)

        if not ratings_list:
            console.print(f"[dim]No ratings yet for {skill_id}[/dim]")
            console.print(f"[dim]Rate it: vibe skills rate {skill_id} 5[/dim]")
            return

        stars = "⭐" * round(avg or 0) + "☆" * (5 - round(avg or 0))
        console.print(
            f"\n[bold]{skill_id}[/bold] — {stars} {avg:.1f}/5 ({len(ratings_list)} reviews)\n"
        )

        for r in sorted(ratings_list, key=lambda x: x.created_at, reverse=True)[:10]:
            stars_str = "⭐" * r.score
            review_text = f"[dim]— {r.review}[/dim]" if r.review else ""
            console.print(f"  {stars_str} {review_text}")
            console.print(f"  [dim]{r.created_at[:10]}[/dim]")
    else:
        top = store.get_top_rated(limit=limit)
        if not top:
            console.print(
                "[dim]No ratings yet. Rate your skills with: vibe skills rate <id> <1-5>[/dim]"
            )
            return

        console.print("\n[bold]Top Rated Skills[/bold]\n")
        for i, (sid, score, count) in enumerate(top, 1):
            stars = "⭐" * round(score) + "☆" * (5 - round(score))
            console.print(
                f"  {i:2}. [cyan]{sid}[/cyan] {stars} {score:.1f}/5 ([dim]{count} reviews[/dim])"
            )
