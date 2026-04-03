"""VibeSOP memory command - Manage conversation memory.

This command allows viewing and managing stored conversation
memory for context persistence.

Usage:
    vibe memory list
    vibe memory show ID
    vibe memory search QUERY
    vibe memory prune
    vibe memory --help

Examples:
    # List all memory entries
    vibe memory list

    # Show a specific memory
    vibe memory show abc123

    # Search memories
    vibe memory search "routing"

    # Prune old memories
    vibe memory prune --days 30
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from vibesop.core.memory.manager import MemoryManager

console = Console()


def memory(
    action: str = typer.Argument(..., help="Action: list, show, search, prune, stats"),
    id_or_query: Optional[str] = typer.Argument(None, help="Memory ID or search query"),
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Maximum results to show",
    ),
    days: int = typer.Option(
        30,
        "--days",
        "-d",
        help="Days to keep when pruning",
    ),
) -> None:
    """Manage conversation memory.

    This command allows you to view and search stored conversation
    memory, which helps maintain context across sessions.

    \b
    Examples:
        # List all memory entries
        vibe memory list

        # Show detailed view of a memory
        vibe memory show abc123

        # Search for specific content
        vibe memory search "routing"

        # Show memory statistics
        vibe memory stats

        # Remove old memories
        vibe memory prune --days 30
    """
    manager = MemoryManager()

    if action == "list":
        _do_list(manager, limit)
    elif action == "show":
        _do_show(manager, id_or_query)
    elif action == "search":
        _do_search(manager, id_or_query, limit)
    elif action == "prune":
        _do_prune(manager, days)
    elif action == "stats":
        _do_stats(manager)
    elif action == "clear":
        _do_clear(manager)
    else:
        console.print(
            f"[red]✗ Unknown action: {action}[/red]\n"
            f"[dim]Valid actions: list, show, search, prune, stats, clear[/dim]"
        )
        raise typer.Exit(1)


def _do_list(manager: MemoryManager, limit: int) -> None:
    """List memory entries.

    Args:
        manager: MemoryManager instance
        limit: Maximum entries to show
    """
    console.print(
        f"\n[bold cyan]🧠 Conversation Memory[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    conversations = manager.list_conversations(limit=limit)

    if not conversations:
        console.print("[dim]No conversations found[/dim]")
        return

    # Create table
    table = Table()
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Messages", style="dim")
    table.add_column("Created", style="dim")

    for conv in conversations:
        msg_count = len(conv.messages) if hasattr(conv, "messages") else 0

        table.add_row(
            conv.id[:8],
            conv.title[:40],
            str(msg_count),
            conv.created_at.strftime("%Y-%m-%d") if hasattr(conv, "created_at") else "N/A",
        )

    console.print(table)

    if len(conversations) >= limit:
        console.print(f"\n[dim]Showing {limit} most recent conversations[/dim]")


def _do_show(manager: MemoryManager, memory_id: str | None) -> None:
    """Show a specific memory entry.

    Args:
        manager: MemoryManager instance
        memory_id: Memory ID to show
    """
    if not memory_id:
        console.print("[red]✗ ID required for show action[/red]")
        console.print("[dim]Usage: vibe memory show ID[/dim]")
        raise typer.Exit(1)

    conv = manager.get_conversation(memory_id)

    if not conv:
        # Try to find by partial ID
        all_convs = manager.list_conversations(limit=1000)
        for c in all_convs:
            if c.id.startswith(memory_id):
                conv = c
                break

    if not conv:
        console.print(f"[red]✗ Conversation not found: {memory_id}[/red]")
        raise typer.Exit(1)

    # Display conversation
    messages_preview = "\n".join(
        f"  [{msg.role.value}] {msg.content[:50]}..."
        for msg in (conv.messages or [])[:3]
    )

    console.print(
        Panel(
            f"[bold]ID:[/bold] {conv.id}\n"
            f"[bold]Title:[/bold] {conv.title}\n"
            f"[bold]Created:[/bold] {conv.created_at if hasattr(conv, 'created_at') else 'N/A'}\n"
            f"[bold]Messages:[/bold] {len(conv.messages or [])}\n\n"
            f"[bold]Recent Messages:[/bold]\n"
            f"{messages_preview}\n",
            title=f"[bold]Conversation: {conv.title[:30]}[/bold]",
            border_style="blue",
        )
    )


def _do_search(manager: MemoryManager, query: str | None, limit: int) -> None:
    """Search memory entries.

    Args:
        manager: MemoryManager instance
        query: Search query
        limit: Maximum results
    """
    if not query:
        console.print("[red]✗ Query required for search action[/red]")
        console.print("[dim]Usage: vibe memory search QUERY[/dim]")
        raise typer.Exit(1)

    console.print(
        f"\n[bold cyan]🔍 Searching Memory[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    console.print(f"[dim]Query: {query}[/dim]\n")

    # Simple search through conversations
    all_convs = manager.list_conversations(limit=1000)
    results = []

    query_lower = query.lower()
    for conv in all_convs:
        # Search in title
        if query_lower in conv.title.lower():
            results.append((conv, 1.0))
            continue

        # Search in messages
        for msg in (conv.messages or []):
            if query_lower in msg.content.lower():
                results.append((conv, 0.8))
                break

    if not results:
        console.print("[dim]No results found[/dim]")
        return

    console.print(f"[green]Found {len(results)} results[/green]\n")

    # Create table
    table = Table()
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Match", style="dim")

    for conv, score in results[:10]:
        table.add_row(
            conv.id[:8],
            conv.title[:40],
            f"{score:.0%}",
        )

    console.print(table)


def _do_prune(manager: MemoryManager, days: int) -> None:
    """Prune old memory entries.

    Args:
        manager: MemoryManager instance
        days: Days to keep
    """
    from datetime import datetime, timedelta

    console.print(f"[dim]Pruning conversations older than {days} days...[/dim]")

    cutoff = datetime.now() - timedelta(days=days)
    all_convs = manager.list_conversations(limit=1000)

    count = 0
    for conv in all_convs:
        if conv.created_at < cutoff:
            if manager.delete_conversation(conv.id):
                count += 1

    console.print(f"[green]✓ Pruned {count} old conversations[/green]")


def _do_stats(manager: MemoryManager) -> None:
    """Show memory statistics.

    Args:
        manager: MemoryManager instance
    """
    console.print(
        f"\n[bold cyan]📊 Memory Statistics[/bold cyan]"
        f"\n{'=' * 40}\n"
    )

    all_convs = manager.list_conversations(limit=1000)

    total_messages = sum(len(conv.messages or []) for conv in all_convs)

    console.print(f"  [dim]Total conversations:[/dim] {len(all_convs)}")
    console.print(f"  [dim]Total messages:[/dim] {total_messages}")

    if all_convs:
        newest = max(all_convs, key=lambda c: c.created_at)
        oldest = min(all_convs, key=lambda c: c.created_at)
        console.print(f"  [dim]Oldest conversation:[/dim] {oldest.created_at.strftime('%Y-%m-%d')}")
        console.print(f"  [dim]Newest conversation:[/dim] {newest.created_at.strftime('%Y-%m-%d')}")


def _do_clear(manager: MemoryManager) -> None:
    """Clear all memory entries.

    Args:
        manager: MemoryManager instance
    """
    console.print("[red]⚠️  This will delete all memory entries![/red]")

    # Note: In real implementation, would ask for confirmation
    console.print("\n[dim]Use manager.clear_all() directly if you're sure.[/dim]")
