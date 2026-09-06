"""Sync featured skills registry from remote.

Usage:
    vibe sync-registry              Fetch latest featured skills
    vibe sync-registry --reset      Reset to built-in defaults
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
from rich.console import Console

from vibesop.core.skills.featured_registry import DEFAULT_REGISTRY_URL, FeaturedRegistry

app = typer.Typer(name="sync-registry", help="Sync featured skills registry")
console = Console()
logger = logging.getLogger(__name__)


@app.callback(invoke_without_command=True)
def sync(
    url: str = typer.Option(
        DEFAULT_REGISTRY_URL,
        "--url",
        "-u",
        help="Remote registry URL to sync from",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        "-r",
        help="Reset to built-in defaults (ignore remote)",
    ),
) -> None:
    """Sync the featured skills registry from a remote source.

    Fetches community-curated skill recommendations and merges
    them with the built-in registry. New skills are added without
    removing existing ones.

    Examples:
        vibe sync-registry                          # Sync from default URL
        vibe sync-registry --url <custom-url>       # Sync from custom source
        vibe sync-registry --reset                  # Reset to built-in defaults
    """
    project_root = Path.cwd()
    registry = FeaturedRegistry(project_root)

    before = registry.count()

    if reset:
        local_file = project_root / ".vibe" / "featured-skills.json"
        if local_file.exists():
            local_file.unlink()
        registry.reload()
        console.print(
            f"[green]Registry reset to built-in defaults.[/green] "
            f"[dim]({registry.count()} skills)[/dim]"
        )
        return

    # Try to fetch from remote
    added = 0
    try:
        import urllib.request

        # v7.0.11: safe_urlopen enforces https + private-host blocking.
        from vibesop.utils.url_safety import safe_urlopen

        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        body = safe_urlopen(req, max_bytes=50 * 1024 * 1024, timeout=10)
        data = json.loads(body)
        remote_skills = data.get("skills", [])
        added = registry.merge_remote(remote_skills)
    except Exception as e:
        logger.debug("Remote sync failed: %s", e)
        if url != DEFAULT_REGISTRY_URL:
            console.print(f"[yellow]Failed to fetch from {url}: {e}[/yellow]")
            raise typer.Exit(1) from e
        console.print("[dim]Remote registry not available. Using built-in defaults.[/dim]")
        registry.reload()
        console.print(f"[dim]{registry.count()} skills loaded.[/dim]")
        return

    if added > 0:
        registry.export_local()
        console.print(
            f"[green]Synced![/green] [bold]{added}[/bold] new skill(s) added "
            f"([dim]{before}[/dim] → [bold]{registry.count()}[/bold])"
        )
    else:
        # A successful sync with nothing new still refreshes the registry's
        # `updated_at` — but only when a local file already exists. Exporting
        # built-in defaults into a fresh local file would mask newer defaults
        # shipped by future wheel upgrades (the local file wins in _load()).
        if (project_root / ".vibe" / "featured-skills.json").exists():
            registry.export_local()
        console.print(f"[green]Already up to date.[/green] [dim]({registry.count()} skills)[/dim]")

    # Show stack coverage
    stacks = registry.stacks_available()
    console.print(f"[dim]Stacks covered:[/dim] {', '.join(sorted(stacks))}")
