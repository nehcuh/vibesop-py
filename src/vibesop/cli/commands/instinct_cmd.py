"""Instinct learning system CLI commands.

Provides:
- vibe instinct learn <pattern> <action> [--context] [--tags]: Record a pattern
- vibe instinct eval: Review and approve detected sequence patterns
- vibe instinct status [--tag]: View all learned instincts
- vibe instinct export [--output]: Export instincts to JSON
- vibe instinct import <file> [--force]: Import instincts from JSON
- vibe instinct evolve [--index]: Upgrade a high-confidence instinct to a formal skill
- vibe instinct pending: List routing-quality pending items (Sprint 1)
- vibe instinct accept <id>: Accept a pending route (write-back success)
- vibe instinct dismiss <id>: Dismiss a pending route (write-back failure)
- vibe instinct stats: Outcome density + pending queue stats
- vibe instinct prune --auto-extracted [--apply]: Remove junk auto_extracted instincts (dry-run by default)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape as rich_escape
from rich.table import Table

logger = logging.getLogger(__name__)


app = typer.Typer(name="instinct", help="Instinct learning system", no_args_is_help=False)
console = Console()


def _get_storage_path() -> Path:
    return Path.cwd() / ".vibe" / "instincts.jsonl"


@app.callback(invoke_without_command=True)
def _instinct_overview(ctx: typer.Context) -> None:  # pyright: ignore[reportUnusedFunction]
    if ctx.invoked_subcommand is not None:
        return

    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    stats = learner.get_stats()
    instincts = learner.get_reliable_instincts()

    console.rule("[bold cyan]Instinct Learning System[/bold cyan]")
    console.print()

    console.print(
        f"  [bold]{stats['total_instincts']}[/bold] total instincts "
        f"([green]{stats['reliable_instincts']}[/green] reliable, "
        f"[yellow]{stats['sequence_candidates']}[/yellow] candidates)"
    )
    console.print()

    if instincts:
        high = [i for i in instincts if i.confidence >= 0.8]
        if high:
            console.print("[bold]High Confidence (>= 0.8):[/bold]")
            for i in high:
                console.print(
                    f"  [cyan]{i.pattern}[/cyan] ({i.confidence:.0%}, {i.total_applications} uses)"
                )

    console.print()
    console.print("[dim]Quick actions:[/dim]")
    console.print("  [cyan]vibe instinct learn[/cyan]    [dim]— record a pattern[/dim]")
    console.print("  [cyan]vibe instinct eval[/cyan]     [dim]— review candidates[/dim]")
    console.print("  [cyan]vibe instinct status[/cyan]   [dim]— view all instincts[/dim]")
    console.print("  [cyan]vibe instinct export[/cyan]   [dim]— backup to JSON[/dim]")
    console.print("  [cyan]vibe instinct import[/cyan]   [dim]— restore from JSON[/dim]")
    console.print("  [cyan]vibe instinct evolve[/cyan]   [dim]— upgrade to skill[/dim]")
    console.print()


@app.command()
def learn(
    pattern: str = typer.Argument(..., help="One-sentence pattern description"),
    action: str = typer.Argument(..., help="What action to take when pattern matches"),
    context: str = typer.Option("", "--context", "-c", help="When this instinct applies"),
    tags: list[str] | None = typer.Option(None, "--tag", "-t", help="Categories (repeatable)"),
    source: str = typer.Option("manual", "--source", "-s", help="Where this instinct came from"),
) -> None:
    """Record a successful workflow pattern as an instinct."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    instinct = learner.learn(
        pattern=pattern,
        action=action,
        context=context,
        tags=tags or [],
        source=source,
    )
    console.print(
        f"[green]Learned:[/green] {instinct.pattern} (id: [dim]{instinct.id[:16]}...[/dim])"
    )


@app.command()
def eval(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Review detected sequence patterns and convert to skill suggestions."""
    from vibesop.core.instinct.learner import InstinctLearner
    from vibesop.core.skills.suggestion_collector import SkillSuggestionCollector

    learner = InstinctLearner(_get_storage_path())
    candidates = learner.get_sequence_candidates()

    if json_output:
        data = {
            "candidates": [
                {
                    "steps": c.steps,
                    "total_count": c.total_count,
                    "success_rate": c.success_rate,
                    "context_tags": c.context_tags,
                }
                for c in candidates
            ],
            "total": len(candidates),
        }
        console.print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    if not candidates:
        console.print("[dim]No pattern candidates ready yet.[/dim]")
        console.print("[dim]Need 5+ occurrences with 80%+ success rate.[/dim]")
        return

    table = Table(title="Pattern Candidates")
    table.add_column("#", style="bold")
    table.add_column("Steps", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Success", justify="right")
    table.add_column("Tags")

    for i, c in enumerate(candidates, 1):
        table.add_row(
            str(i),
            " → ".join(c.steps),
            str(c.total_count),
            f"{c.success_rate:.0%}",
            ", ".join(c.context_tags) if c.context_tags else "-",
        )

    console.print(table)

    if candidates:
        console.print()
        collector = SkillSuggestionCollector()
        for c in candidates:
            try:
                collector.add_from_pattern(c)
                console.print(f"[green]Approved:[/green] {' → '.join(c.steps)}")
            except Exception as e:
                logger.warning("Unhandled error: %s", e)
        pending = collector.get_pending()
        if pending:
            console.print(
                f"[green]✓[/green] [bold]{len(pending)}[/bold] suggestion(s) pending. Run [cyan]vibe skills suggestions[/cyan] to review."
            )


def _pending_store_path() -> Path:
    return Path.cwd() / ".vibe" / "instincts" / "routing_pending.jsonl"


def _apply_accept_writeback(query: str, skill_id: str | None) -> None:
    """Learn + positive outcome + preference (accept path)."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    pattern = query.lower().strip()
    if skill_id:
        instinct = learner.learn(
            pattern=pattern,
            action=f"suggest {skill_id} skill",
            context="routing_pending_accept",
            tags=["routing", "pending_accept"],
            source="routing_pending",
        )
        # learn() merges by id and does NOT re-tag/re-source an existing
        # instinct — a previously auto-minted row would keep
        # source="auto_routing" + the auto_extracted tag, and
        # prune_auto_extracted would delete this human-confirmed instinct
        # (gate8 review: pi reproduction). Stamp the confirmation explicitly.
        if instinct.source == "auto_routing" or "auto_extracted" in instinct.tags:
            instinct.source = "routing_pending"
            instinct.tags = ["routing", "pending_accept"]
            instinct.context = "routing_pending_accept"
            # NOTE (gate8b): learn() has already persisted once above, so a
            # concurrent cross-process prune could still delete the row in the
            # microsecond window before this save() lands. Manual-CLI-only,
            # .bak recovery exists — accepted; the success_count>0 guard in
            # prune closes the window for anything feedback-confirmed.
            learner.save()
        learner.record_outcome_for_query(pattern, success=True)
        try:
            from vibesop.core.optimization import PreferenceBooster

            PreferenceBooster().get_learner().record_selection(skill_id, pattern, was_helpful=True)
        except Exception as exc:
            logger.debug("preference writeback failed: %s", exc)
    else:
        # No skill on accept of no_match without --skill: still mark outcome if known
        learner.record_outcome_for_query(pattern, success=True)


def _apply_dismiss_writeback(query: str, skill_id: str | None) -> None:
    """Negative outcome + preference (dismiss path)."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    pattern = query.lower().strip()
    # Ensure instinct exists so record_outcome is not a silent no-op
    if skill_id:
        learner.learn(
            pattern=pattern,
            action=f"suggest {skill_id} skill",
            context="routing_pending_dismiss",
            tags=["routing", "pending_dismiss"],
            source="routing_pending",
        )
        try:
            from vibesop.core.optimization import PreferenceBooster

            PreferenceBooster().get_learner().record_selection(skill_id, pattern, was_helpful=False)
        except Exception as exc:
            logger.debug("preference dismiss writeback failed: %s", exc)
    learner.record_outcome_for_query(pattern, success=False)


@app.command("pending")
def pending_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="Max items to show"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """List routing-quality pending items (low-conf / no-match) awaiting accept/dismiss.

    Sprint 1 golden path — separate from ``vibe skills suggestions`` (workflow drafts).
    """
    from vibesop.core.instinct.routing_pending import RoutingPendingStore

    store = RoutingPendingStore(_pending_store_path())
    items = store.list_pending(limit=limit)
    stats = store.stats()

    if json_output:
        console.print(
            json.dumps(
                {
                    "items": [i.to_dict() for i in items],
                    "stats": stats,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if not items:
        console.print(
            "[dim]没有待审路由项。低置信 / 未命中路由会自动进入此队列"
            f"（每日最多 {stats['daily_cap']} 条）。[/dim]"
        )
        console.print(
            f"[dim]今日已创建 {stats['created_today']}/{stats['daily_cap']} · "
            f"历史 accept={stats['accepted']} dismiss={stats['dismissed']}[/dim]"
        )
        return

    console.print(
        f"[bold]待审路由[/bold] [dim]({len(items)} pending · "
        f"今日 {stats['created_today']}/{stats['daily_cap']})[/dim]\n"
    )
    for item in items:
        skill = item.skill_id or "（未命中）"
        console.print(
            f"  [cyan]{item.id}[/cyan]  [{item.kind}]  conf={item.confidence:.0%}  "
            f"skill=[magenta]{skill}[/magenta]"
        )
        console.print(f"    [dim]query:[/dim] {item.query[:120]}")
        console.print(f"    [green]{item.reason_zh}[/green]")
        console.print()
    console.print(
        "[dim]操作: [cyan]vibe instinct accept <id>[/cyan]  "
        "或  [cyan]vibe instinct dismiss <id>[/cyan][/dim]"
    )


@app.command("accept")
def accept_cmd(
    item_id: str = typer.Argument(..., help="Pending item id (rp-…)"),
    skill: str | None = typer.Option(
        None,
        "--skill",
        "-s",
        help="Override skill id (required for no_match if item has no skill)",
    ),
) -> None:
    """Accept a pending route: write positive outcome so next route prefers it."""
    from vibesop.core.instinct.routing_pending import RoutingPendingStore

    store = RoutingPendingStore(_pending_store_path())
    item = store.get(item_id)
    if item is None:
        console.print(f"[red]找不到 id={item_id}[/red]")
        raise typer.Exit(1)
    if item.status != "pending":
        console.print(f"[yellow]已是 {item.status}，跳过。[/yellow]")
        raise typer.Exit(1)

    skill_id = skill or item.skill_id
    if not skill_id and item.kind == "no_match":
        console.print("[red]no_match 项需要 --skill <id> 才能 accept（否则不知道该强化谁）。[/red]")
        raise typer.Exit(1)

    resolved = store.accept(item_id)
    if resolved is None:
        console.print("[red]accept 失败（可能已被处理）[/red]")
        raise typer.Exit(1)

    # If --skill override, update the resolved view for writeback
    if skill:
        resolved.skill_id = skill

    _apply_accept_writeback(resolved.query, skill_id)
    console.print(
        f"[green]✓ accepted[/green] {item_id} → skill=[magenta]{skill_id}[/magenta]\n"
        f"[dim]已写入 instinct outcome + preference。下次同类 query 应更准。[/dim]"
    )


@app.command("dismiss")
def dismiss_cmd(
    item_id: str = typer.Argument(..., help="Pending item id (rp-…)"),
) -> None:
    """Dismiss a pending route: negative outcome; suppress re-prompt 24h."""
    from vibesop.core.instinct.routing_pending import RoutingPendingStore

    store = RoutingPendingStore(_pending_store_path())
    item = store.get(item_id)
    if item is None:
        console.print(f"[red]找不到 id={item_id}[/red]")
        raise typer.Exit(1)
    if item.status != "pending":
        console.print(f"[yellow]已是 {item.status}，跳过。[/yellow]")
        raise typer.Exit(1)

    resolved = store.dismiss(item_id)
    if resolved is None:
        console.print("[red]dismiss 失败[/red]")
        raise typer.Exit(1)

    _apply_dismiss_writeback(resolved.query, resolved.skill_id)
    console.print(
        f"[green]✓ dismissed[/green] {item_id}\n"
        f"[dim]已记负反馈；24h 内同 query+skill 不再入队。[/dim]"
    )


@app.command("stats")
def stats_cmd(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Outcome density + routing pending queue stats (Sprint 1 kill-criteria signal)."""
    from vibesop.core.instinct.learner import InstinctLearner
    from vibesop.core.instinct.routing_pending import RoutingPendingStore

    learner = InstinctLearner(_get_storage_path())
    all_instincts = list(learner._instincts.values())
    outcomes = sum(i.success_count + i.failure_count for i in all_instincts)
    successes = sum(i.success_count for i in all_instincts)
    failures = sum(i.failure_count for i in all_instincts)
    with_outcome = sum(1 for i in all_instincts if i.total_applications > 0)

    store = RoutingPendingStore(_pending_store_path())
    pstats = store.stats()

    payload = {
        "instincts_total": len(all_instincts),
        "instincts_with_outcome": with_outcome,
        "outcomes_total": outcomes,
        "outcomes_success": successes,
        "outcomes_failure": failures,
        "routing_pending": pstats,
    }

    if json_output:
        console.print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    console.print("[bold]Instinct / 路由闭环统计[/bold]")
    console.print(f"  instincts: {payload['instincts_total']} (有 outcome: {with_outcome})")
    console.print(f"  outcomes: {outcomes}  (✓ {successes} / ✗ {failures})")
    console.print(
        f"  routing pending: open={pstats['pending']}  "
        f"accept={pstats['accepted']} dismiss={pstats['dismissed']}  "
        f"today={pstats['created_today']}/{pstats['daily_cap']}"
    )
    if outcomes == 0:
        console.print(
            "[yellow]⚠ outcome 密度为 0 — 请 accept/dismiss 待审项，"
            "或确认 replay Y 路径；否则 14 天 kill 会触发。[/yellow]"
        )


@app.command()
def status(
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter instincts by tag"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """View all learned instincts with confidence scores and usage statistics."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    instincts = learner.get_reliable_instincts(tag=tag)

    if json_output:
        data = {
            "total": len(instincts),
            "instincts": [i.to_dict() for i in instincts],
        }
        console.print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    if not instincts:
        console.print(
            "[dim]No reliable instincts yet. Use [cyan]vibe instinct learn[/cyan] to build your knowledge base.[/dim]"
        )
        return

    high = [i for i in instincts if i.confidence >= 0.8]
    mid = [i for i in instincts if 0.6 <= i.confidence < 0.8]
    low = [i for i in instincts if i.confidence < 0.6]

    console.print(f"[bold]Active Instincts:[/bold] [green]{len(instincts)}[/green] total")
    if tag:
        console.print(f"[dim]Filtered by tag: {tag}[/dim]")
    console.print()

    if high:
        console.print("[bold]High Confidence (>= 0.8):[/bold]")
        for i in high:
            console.print(
                f"  [cyan]{i.pattern}[/cyan]\n"
                f"    Action: {i.action}  |  Uses: {i.total_applications}  |  Tags: {', '.join(i.tags) if i.tags else '-'}"
            )
    if mid:
        console.print("\n[bold]Medium Confidence (0.6-0.8):[/bold]")
        for i in mid:
            console.print(f"  [{i.confidence:.0%}] {i.pattern}")
    if low:
        console.print("\n[dim]Low Confidence (<0.6):[/dim]")
        for i in low:
            console.print(f"  [dim][{i.confidence:.0%}] {i.pattern}[/dim]")

    stats = learner.get_stats()
    console.print()
    console.print(
        f"[dim]Total: {stats['total_instincts']} | Candidates: {len(learner.get_sequence_candidates())}[/dim]"
    )


@app.command()
def export(
    output: Path = typer.Option(
        Path("instincts-export.json"),
        "--output",
        "-o",
        help="Output file path",
    ),
    min_confidence: float = typer.Option(
        0.0, "--min-confidence", "-c", help="Minimum confidence filter"
    ),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag"),
) -> None:
    """Export reliable instincts to JSON for backup or team sharing."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    instincts = learner.get_reliable_instincts()

    if min_confidence > 0:
        instincts = [i for i in instincts if i.confidence >= min_confidence]
    if tag:
        instincts = [i for i in instincts if tag.lower() in [t.lower() for t in i.tags]]

    data: dict[str, Any] = {
        "version": "1.0",
        "exported_at": datetime.now().isoformat(),
        "instincts": [i.to_dict() for i in instincts],
    }

    output_path = Path.cwd() / output if not output.is_absolute() else output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    console.print(
        f"[green]Exported[/green] [bold]{len(instincts)}[/bold] instincts to [cyan]{output_path}[/cyan]"
    )


@app.command(name="import")
def import_(
    file: Path = typer.Argument(..., help="Path to the JSON export file"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing instincts with same ID"
    ),
) -> None:
    """Import instincts from a JSON export file (team sharing or backup restore)."""
    from vibesop.core.instinct.learner import Instinct, InstinctLearner

    input_path = file if file.is_absolute() else Path.cwd() / file
    if not input_path.exists():
        console.print(f"[red]✗[/red] File not found: {input_path}")
        raise typer.Exit(1)

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        incoming = [Instinct.from_dict(i) for i in data.get("instincts", [])]
    except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as e:
        console.print(f"[red]✗[/red] Invalid export file: {e}")
        raise typer.Exit(1) from None

    learner = InstinctLearner(_get_storage_path())
    imported = 0
    skipped = 0
    updated = 0

    for instinct in incoming:
        if not learner.has_instinct(instinct.id):
            learner.set_instinct(instinct)
            with learner.storage_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(instinct.to_dict(), default=str) + "\n")
            imported += 1
        elif force:
            learner.set_instinct(instinct)
            updated += 1
        else:
            skipped += 1

    if imported or updated:
        learner.save()

    parts = []
    if imported:
        parts.append(f"[green]{imported}[/green] imported")
    if updated:
        parts.append(f"[yellow]{updated}[/yellow] updated (overwritten)")
    if skipped:
        parts.append(f"[dim]{skipped}[/dim] skipped (duplicates)")
    console.print(f"[bold]Result:[/bold] {', '.join(parts)}")


@app.command()
def evolve(
    index: int = typer.Option(
        0,
        "--index",
        "-i",
        help="Index of the instinct to evolve (use --list to see candidates first)",
    ),
    list_only: bool = typer.Option(
        False, "--list", "-l", help="Only list candidates, don't generate"
    ),
) -> None:
    """Upgrade a high-confidence instinct into a formal VibeSOP skill."""
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    reliable = [
        i
        for i in learner.get_reliable_instincts()
        if i.confidence >= 0.8 and i.total_applications >= 10
    ]

    if not reliable:
        console.print("[yellow]No instincts ready for evolution.[/yellow]")
        console.print("[dim]Need confidence >= 0.8 and 10+ uses.[/dim]")
        return

    if list_only:
        console.print("[bold]Evolution Candidates:[/bold]")
        for j, ins in enumerate(reliable):
            console.print(
                f"  {j}. [cyan]{ins.pattern}[/cyan] ({ins.confidence:.0%}, {ins.total_applications} uses)"
            )
        return

    # Out-of-range index: show the candidate list instead of evolving
    # (note: bare `evolve` uses the --index default of 0 and evolves the
    # first candidate directly; --list is the review-only path)
    if index < 0 or index >= len(reliable):
        console.print("[bold]Evolution Candidates:[/bold]")
        for j, ins in enumerate(reliable):
            console.print(
                f"  {j}. [cyan]{ins.pattern}[/cyan] ({ins.confidence:.0%}, {ins.total_applications} uses)"
            )
        if len(reliable) > 1:
            console.print()
            console.print("[dim]Use --index <N> to pick one, or 0 for the first.[/dim]")
        else:
            console.print()
            console.print("[dim]Use --index 0 to evolve the sole candidate.[/dim]")
        return

    ins = reliable[index]
    skill_id = "custom/" + ins.pattern.lower().replace(" ", "-").replace(",", "")[:50]
    skill_dir = Path.cwd() / ".vibe" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_md = f"""---
id: {skill_id}
name: {skill_id}
description: "{ins.pattern} (evolved from instinct)"
tags: {ins.tags}
intent: workflow
namespace: custom
version: 1.0.0
type: prompt
source: instinct-evolution
instinct_id: {ins.id}
---

# {ins.pattern}

## Overview

Pattern evolved from instinct with {ins.confidence:.0%} confidence ({ins.total_applications} uses).

## When to Apply

{ins.context}

## Steps

When this pattern matches, {ins.action}.

## Metrics

- **Confidence**: {ins.confidence:.0%}
- **Success rate**: {ins.success_rate:.0%} ({ins.success_count}/{ins.total_applications})
- **Evolved from**: instinct #{ins.id[:8]}
"""

    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    console.print(f"[green]Skill created:[/green] {skill_dir}/SKILL.md")
    console.print(f"[green]Skill ID:[/green] [cyan]{skill_id}[/cyan]")
    console.print()
    console.print(
        "[dim]Next: run [cyan]vibe skills suggestions[/cyan] to register it formally.[/dim]"
    )


# ──────────────────────────────────────────────────────────────────
# prune (Tier2 — existing-data hygiene for junk auto_extracted instincts)
# ──────────────────────────────────────────────────────────────────


@app.command("prune")
def prune_cmd(
    auto_extracted: bool = typer.Option(
        False,
        "--auto-extracted",
        help="清理 auto_extracted instinct（路由自动 mint）中质量不达标的条目",
    ),
    apply: bool = typer.Option(False, "--apply", help="真正删除（默认 dry-run，只打印）"),
) -> None:
    """清理质量门控不达标的 auto_extracted instinct（Tier2 存量数据卫生）。

    与路由侧新 mint 使用同一道质量门（低信息 query / 超长 megaprompt）。
    默认 dry-run：只列出将被删除的条目；加 ``--apply`` 才真正删除。
    人工确认的 instinct（pending accept/dismiss、manual）不受影响。
    """
    from vibesop.core.instinct.learner import InstinctLearner

    if not auto_extracted:
        console.print("[yellow]请指定清理范围：--auto-extracted[/yellow]")
        raise typer.Exit(1)

    learner = InstinctLearner(_get_storage_path())
    victims = learner.prune_auto_extracted(dry_run=not apply)

    if not victims:
        console.print("[green]✓[/green] 没有需要清理的 auto_extracted instinct。")
        return

    for v in victims:
        # rich_escape on user-derived pattern text — a pattern containing
        # "[/x]" would otherwise raise MarkupError (after the deletion in
        # --apply mode). Convention: cli/main.py, cli/render.py.
        console.print(f"  [dim]{v.id}[/dim] {rich_escape(v.pattern[:100])}")
    if apply:
        console.print(f"[bold]已删除 {len(victims)} 条[/bold]")
    else:
        console.print(
            f"[bold]将被删除 {len(victims)} 条[/bold] [dim](dry-run：加 --apply 执行)[/dim]"
        )


# ──────────────────────────────────────────────────────────────────
# auto-promote / feedback-collect (Phase D — scheduled loop entry points)
# ──────────────────────────────────────────────────────────────────


def _feedback_watermark_path() -> Path:
    """Per-project watermark tracking which miss-hashes feedback-collect has
    already processed (so re-runs don't double-decay the same cluster)."""
    return Path.cwd() / ".vibe" / "instincts" / "feedback_watermark.json"


def _load_watermark() -> dict[str, None]:
    """Load processed-hash watermark as an insertion-ordered dict.

    Using ``dict[str, None]`` (Python 3.7+ preserves insertion order) gives
    us both O(1) membership tests AND deterministic FIFO trimming — a plain
    ``set`` would lose insertion order and `list(set)[-N:]` would trim
    arbitrarily depending on hash seed (pi Phase D P1-C). Empty dict on
    first run / corruption.
    """
    path = _feedback_watermark_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        hashes = data.get("processed_hashes", [])
        return {h: None for h in hashes if isinstance(h, str)}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load feedback watermark (%s): %s", path, e)
        return {}


def _save_watermark(hashes: dict[str, None]) -> None:
    """Persist watermark atomically. Cap at 10k entries (FIFO trim oldest).

    Uses ``atomic_writer.write_text`` (temp file + rename) so a crash mid-write
    leaves the previous watermark intact rather than a truncated JSON file —
    losing the watermark would cause the next feedback-collect to re-decay
    every previously-processed hash (pi Phase D P1-C).
    """
    from vibesop.utils.atomic_writer import write_text

    path = _feedback_watermark_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # dict preserves insertion order — list(...) gives oldest-first, so
    # [-10000:] keeps the most recent 10k. Re-decaying occasional hashes
    # shed by the cap is harmless (decay is bounded by early-stop at ≤ 0.1).
    trimmed = list(hashes)[-10000:]
    payload = {"processed_hashes": trimmed}
    write_text(path, json.dumps(payload, ensure_ascii=False))


def _add_watermark(watermark: dict[str, None], h: str) -> None:
    """Add hash to watermark preserving insertion order (re-adding moves to end).

    A re-added hash bubbles to the tail so the FIFO trim in ``_save_watermark``
    prefers keeping recently-observed hashes over ancient ones.
    """
    watermark.pop(h, None)
    watermark[h] = None


def _candidate_to_instinct(learner: Any, candidate: Any, source: str) -> Any:
    """Convert a ``SequencePattern`` into a persistent ``Instinct``.

    Why manual construction instead of ``learner.learn(...)``: ``learn`` does
    fuzzy pattern matching and may merge into an existing instinct. For
    auto-promote we want a 1:1 conversion from candidate → instinct, with
    the candidate's success/failure counts preserved verbatim. The learner's
    public ``generate_id`` gives us a deterministic id (same steps → same
    id), so re-running auto-promote on the same candidate is a no-op
    rather than a duplicate.
    """
    from vibesop.core.instinct.learner import Instinct

    pattern = " → ".join(candidate.steps)
    failure_count = max(0, candidate.total_count - candidate.success_count)
    return Instinct(
        id=learner.generate_id(pattern),
        pattern=pattern,
        action=f"Consider this sequence as a repeatable workflow: {pattern}",
        context=", ".join(candidate.context_tags) if candidate.context_tags else "",
        confidence=min(0.95, max(0.5, candidate.success_rate)),
        success_count=candidate.success_count,
        failure_count=failure_count,
        source=source,
        tags=[*candidate.context_tags, "sequence-promoted"],
    )


@app.command("auto-promote")
def auto_promote(
    min_confidence: float = typer.Option(
        0.85, "--min-confidence", help="候选 success_rate 下限（默认 0.85）"
    ),
    min_count: int = typer.Option(5, "--min-count", help="候选 total_count 下限（默认 5）"),
    growth_cap_pct: int = typer.Option(
        20,
        "--growth-cap-pct",
        help=(
            "单次 promote 数量上限 = 当前 instinct 数 × pct%（防失控）。"
            "冷启动（before=0）时强制允许 1 个。"
        ),
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印，不写盘"),
) -> None:
    """把高置信度 sequence 候选提升为持久 instinct（计划 §5d）。

    Growth cap (plan v2 §C)：单次 promote 不超过现有 instinct 数的
    ``growth_cap_pct%``（至少 1 个），避免一次性灌入大量低质 instinct
    污染路由。重跑幂等——同一候选的 id 由 pattern 决定，
    ``set_instinct`` 覆盖写不复制。
    """
    from vibesop.core.instinct.learner import InstinctLearner

    learner = InstinctLearner(_get_storage_path())
    before = len(learner.instincts)
    allowed = max(1, int(before * growth_cap_pct / 100))

    candidates = learner.get_sequence_candidates(min_confidence=min_confidence)
    promoted = 0
    capped = False
    for c in candidates:
        if promoted >= allowed:
            capped = True
            break
        if c.total_count < min_count:
            continue
        instinct = _candidate_to_instinct(learner, c, source="auto-promote")
        if dry_run:
            console.print(
                f"[dim]would promote:[/dim] {instinct.pattern} "
                f"({c.success_rate:.0%}, n={c.total_count})"
            )
        else:
            learner.set_instinct(instinct)
        promoted += 1

    if not dry_run and promoted:
        learner.save()  # 显式 save（plan v2 §C kimi must-fix）

    console.print(
        f"[green]✅ Promoted {promoted}[/green] candidate(s) "
        f"(eligible={len(candidates)}, before={before}, cap={allowed})"
    )
    if capped:
        console.print(f"[yellow]⚠️  growth cap {allowed} hit — 剩余候选延后到下次 promote[/yellow]")
    if not dry_run and promoted:
        console.print(f"[dim]saved to {_get_storage_path()}[/dim]")


@app.command("feedback-collect")
def feedback_collect(
    min_miss_count: int = typer.Option(
        3, "--min-miss-count", help="miss hash 被纳入衰减的次数下限"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印，不写盘"),
) -> None:
    """根据 miss counter 反馈下调 instinct 置信度（计划 §5e，仅 decay 方向）。

    - **Decay**：高频 miss 命中的 instinct → ``record_outcome(success=False)``，
      让 Wilson score 自动下调 confidence。负信号有真实外部来源（miss counter）。
    - **Early-stop**：confidence ≥ 0.95 或 ≤ 0.1 跳过（避免无意义震荡）。
    - **Watermark**：处理过的 miss hash 写盘，下次跳过；``miss.decay_frequent``
      把 frequent count 减半（不 clear，保留 first/last）。

    正向（boost）分支已拆除：正信号的唯一合法来源是显式人确认
    （CLI feedback、pending accept、replay 确认），自动
    ``record_outcome(success=True)`` 会毒化 Wilson confidence
    （与 unified.py 的既有设计哲学一致）。
    """
    from vibesop.core.instinct.learner import InstinctLearner
    from vibesop.core.skills.miss_counter import MissCounter

    miss = MissCounter(Path.cwd())
    processed_watermark = _load_watermark()
    frequent_clusters = miss.frequent(min_count=min_miss_count)
    frequent_hashes = {c.hash for c in frequent_clusters if c.hash not in processed_watermark}

    learner = InstinctLearner(_get_storage_path())
    decayed = 0
    skipped_early_stop = 0
    decayed_hashes: set[str] = set()
    # Iterate ALL instincts, not just reliable ones (``get_reliable_instincts``
    # requires ``total_applications >= 3``): an under-utilized instinct that
    # keeps accumulating frequent misses should decay too, not get a free
    # pass just because it hasn't been applied often. Early-stop guards both
    # ends of the confidence range.
    all_instincts = sorted(learner.instincts.values(), key=lambda i: i.confidence, reverse=True)
    for ins in all_instincts:
        # Early-stop: 置信度已饱和或已死亡，不再调整
        if ins.confidence >= 0.95 or ins.confidence <= 0.1:
            skipped_early_stop += 1
            continue

        h = miss.hash_for(ins.pattern)
        if h in frequent_hashes:
            if dry_run:
                console.print(
                    f"[dim]would decay:[/dim] {ins.pattern} (confidence={ins.confidence:.0%})"
                )
            else:
                learner.record_outcome(ins.id, success=False)
            decayed += 1
            decayed_hashes.add(h)
            _add_watermark(processed_watermark, h)

    if not dry_run and decayed:
        # Scope the miss-counter decay to hashes feedback-collect actually
        # touched — without this filter, ``decay_frequent`` halves every
        # cluster at ≥ min_miss_count, erasing signal for instincts that
        # were early-stopped or already in the watermark (pi Phase D P2-D).
        miss.decay_frequent(min_miss_count, hashes=decayed_hashes)
        learner.save()
        _save_watermark(processed_watermark)

    console.print(
        f"[bold]Feedback collected[/bold]: "
        f"[red]{decayed} decayed[/red], "
        f"[dim]{skipped_early_stop} early-stop skipped[/dim]"
    )
    if dry_run:
        console.print("[dim](dry-run: no writes)[/dim]")
