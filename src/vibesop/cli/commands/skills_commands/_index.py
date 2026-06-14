# pyright: ignore[reportPossiblyUnboundVariable, reportUnnecessaryComparison]
"""Index command: build skill embedding index non-interactively.

v7.3.4 addition. Replaces the workaround of calling Python directly::

    uv run python -c "from vibesop.core.skills.indexer import SkillIndexer; ..."

Now users can simply::

    vibe skills index --scope global --force

The command uses :class:`LLMConfigResolver` to honor ``~/.vibe/config.toml``
(same priority chain as ``vibe route`` CLI). Without an LLM provider configured,
the indexer silently produces ``indexed_count: 0`` (same as before — kept as
explicit error here so users know to configure LLM first).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


def index(
    scope: str = typer.Option(
        "global",
        "--scope",
        "-s",
        help="Index scope: global, project, or all",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force rebuild (ignore content_hash cache)",
    ),
    max_workers: int = typer.Option(
        4,
        "--max-workers",
        "-w",
        help="Concurrent LLM calls (reduce for small / shared LLM servers)",
    ),
    project_root: Path = typer.Option(
        Path.cwd(),
        "--project-root",
        "-r",
        help="Project root (defaults to current directory)",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress progress bar",
    ),
) -> None:
    """Build skill embedding index for AI_TRIAGE.

    Examples::

        vibe skills index                         # global, use cache
        vibe skills index --force                 # global, rebuild all
        vibe skills index --scope project         # project-local only
        vibe skills index --max-workers 1         # sequential (small LLM)

    Without this index, AI_TRIAGE layer always reports
    "No embeddings in index" and short queries fall through to FALLBACK_LLM.
    """
    from vibesop.core.llm_config import LLMConfigResolver
    from vibesop.core.skills.indexer import SkillIndexer
    from vibesop.llm.factory import create_provider

    # Resolve LLM config (honors ~/.vibe/config.toml per S5 P1-A priority)
    resolver = LLMConfigResolver()
    cfg = resolver.get_llm_for_understanding()

    if not cfg or not cfg.provider:
        console.print(
            "[red]✗ No LLM provider configured.[/red]\n\n"
            "Set up ~/.vibe/config.toml first:\n\n"
            "  [llm]\n"
            '  provider = "deepseek"   # or "openai", "ollama", etc.\n'
            '  model = "deepseek-v4-flash"\n'
            "\n"
            "Then re-run: vibe skills index\n",
        )
        raise typer.Exit(1)

    console.print(
        f"[cyan]🔍 Building skill index[/cyan] "
        f"(provider={cfg.provider}/{cfg.model}, scope={scope}, "
        f"workers={max_workers}, force={force})"
    )

    def _factory() -> Any:
        return create_provider(
            provider=cfg.provider,
            api_key=cfg.api_key,
            base_url=cfg.api_base,
        )

    indexer = SkillIndexer(
        project_root=project_root,
        llm_factory=_factory,
    )

    result = indexer.build_index(
        scope=scope,  # type: ignore[arg-type]
        show_progress=not quiet,
        force=force,
        max_workers=max_workers,
    )

    if result.success:
        console.print(
            f"\n[green]✓ Index built:[/green] "
            f"{result.indexed_count} skills indexed, "
            f"{result.failed_count} failed"
        )
        if result.errors:
            console.print("[yellow]Errors (first 5):[/yellow]")
            for err in result.errors[:5]:
                console.print(f"  - {err}")
        if result.failed_count > 0:
            console.print(
                "\n[yellow]Failures may indicate:[/yellow]\n"
                "  - LLM model too small (<7B can't produce structured JSON)\n"
                "  - max_tokens too low for thinking models (v7.3.2 bumped to 4000)\n"
                "  - LLM provider unreachable"
            )
    else:
        console.print(f"[red]✗ Index build failed:[/red] {result.errors[:3]}")
        raise typer.Exit(1)
