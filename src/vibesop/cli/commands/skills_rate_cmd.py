"""Skills rating commands — rate skills and view ratings."""

import typer
from rich.console import Console

console = Console()


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
        console.print("[red]\u2717 Score must be 1-5[/red]")
        raise typer.Exit(1)

    store = SkillRatingStore()
    store.rate(skill_id, score, review or "")

    stars = "\u2b50" * score + "\u2606" * (5 - score)
    avg = store.get_avg_score(skill_id)
    count = store.get_count(skill_id)
    console.print(f"[green]\u2713[/green] Rated {skill_id}: {stars}")
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

        stars = "\u2b50" * round(avg or 0) + "\u2606" * (5 - round(avg or 0))
        console.print(
            f"\n[bold]{skill_id}[/bold] \u2014 {stars} {avg:.1f}/5 ({len(ratings_list)} reviews)\n"
        )

        for r in sorted(ratings_list, key=lambda x: x.created_at, reverse=True)[:10]:
            stars_str = "\u2b50" * r.score
            review_text = f"[dim]\u2014 {r.review}[/dim]" if r.review else ""
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
            stars = "\u2b50" * round(score) + "\u2606" * (5 - round(score))
            console.print(
                f"  {i:2}. [cyan]{sid}[/cyan] {stars} {score:.1f}/5 ([dim]{count} reviews[/dim])"
            )


__all__ = ["rate", "ratings"]
