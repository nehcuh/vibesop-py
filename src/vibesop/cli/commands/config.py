"""VibeSOP config command - Configuration management.

This command provides configuration management for various VibeSOP features,
including semantic matching configuration.

Usage:
    vibe config
    vibe config semantic
    vibe config semantic --enable
    vibe config semantic --model paraphrase-multilingual-mpnet-base-v2
    vibe config semantic --clear-cache
    vibe config semantic --warmup
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def config(
    semantic: bool = typer.Option(
        False,
        "--semantic",
        "-s",
        help="Show semantic configuration",
    ),
) -> None:
    """Manage VibeSOP configuration.

    Use --semantic flag to manage semantic matching settings.

    \\b
    Examples:
        # Show semantic configuration
        vibe config --semantic

        # Enable semantic matching globally
        vibe config semantic --enable

        # Disable semantic matching
        vibe config semantic --disable

        # Change semantic model
        vibe config semantic --model paraphrase-multilingual-mpnet-base-v2

        # Clear semantic cache
        vibe config semantic --clear-cache

        # Warmup semantic model (download + precompute)
        vibe config semantic --warmup
    """
    if semantic:
        _show_semantic_config()
    else:
        _show_general_config()


def config_semantic(
    action: str = typer.Argument(
        "show",
        help="Action to perform: show, enable, disable, model, clear-cache, warmup",
    ),
    enable: bool = typer.Option(
        False,
        "--enable",
        help="Enable semantic matching globally",
    ),
    disable: bool = typer.Option(
        False,
        "--disable",
        help="Disable semantic matching globally",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Change semantic model",
    ),
    clear_cache: bool = typer.Option(
        False,
        "--clear-cache",
        help="Clear semantic vector cache",
    ),
    warmup: bool = typer.Option(
        False,
        "--warmup",
        help="Download model and precompute pattern vectors",
    ),
) -> None:
    """Manage semantic matching configuration.

    This command allows you to configure semantic matching settings.

    \\b
    Actions:
        show: Show current configuration (default)
        enable: Enable semantic matching globally
        disable: Disable semantic matching globally
        model: Change the semantic model
        clear-cache: Clear the vector cache
        warmup: Pre-download model and precompute vectors

    \\b
    Examples:
        # Show configuration
        vibe config semantic

        # Enable semantic matching
        vibe config semantic --enable

        # Disable semantic matching
        vibe config semantic --disable

        # Change model
        vibe config semantic --model paraphrase-multilingual-mpnet-base-v2

        # Clear cache
        vibe config semantic --clear-cache

        # Warmup (download + precompute)
        vibe config semantic --warmup
    """
    from vibesop.semantic import check_semantic_available, SENTENCE_TRANSFORMERS_AVAILABLE

    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        console.print(
            Panel(
                "[bold red]❌ Semantic Matching Not Available[/bold red]\\n\\n"
                "sentence-transformers is not installed.\\n\\n"
                "[bold]Install with:[/bold]\\n"
                "  pip install vibesop[semantic]\\n\\n"
                "Or install the dependency directly:\\n"
                "  pip install sentence-transformers",
                title="[bold]Missing Dependency[/bold]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    if enable:
        _enable_semantic()
    elif disable:
        _disable_semantic()
    elif model:
        _set_semantic_model(model)
    elif clear_cache:
        _clear_semantic_cache()
    elif warmup:
        _warmup_semantic()
    else:
        _show_semantic_config()


def _show_general_config() -> None:
    """Show general VibeSOP configuration."""
    from vibesop import __version__

    console.print(
        Panel(
            f"[bold]VibeSOP[/bold] Configuration\\n\\n"
            f"Version: {__version__}\\n"
            f"Python: 3.12+\\n"
            f"\\n"
            f"[bold]Semantic Matching[/bold]\\n"
            f"  Status: [dim]Use --semantic flag to view[/dim]\\n"
            f"\\n"
            f"[bold]For more details, use:[/bold]\\n"
            f"  vibe config --semantic",
            title="[bold]Configuration[/bold]",
            border_style="blue",
        )
    )


def _show_semantic_config() -> None:
    """Show semantic matching configuration."""
    from vibesop.semantic import check_semantic_available, SENTENCE_TRANSFORMERS_AVAILABLE
    from vibesop.semantic.models import EncoderConfig

    available = check_semantic_available()
    config = EncoderConfig.from_env()

    # Check if enabled in env
    import os
    enabled = os.getenv("VIBE_SEMANTIC_ENABLED", "false").lower() == "true"

    console.print(
        Panel(
            f"[bold cyan]🧠 Semantic Matching Configuration[/bold cyan]\\n\\n"
            f"[bold]Status:[/bold] {'✅ Enabled' if enabled else '⚪ Disabled'}\\n"
            f"[bold]Available:[/bold] {'✅ Yes' if available else '❌ No'}\\n\\n"
            f"[bold]Model:[/bold]\\n"
            f"  Name: {config.model_name}\\n"
            f"  Device: {config.device}\\n"
            f"  Cache: {config.cache_dir or 'Default'}\\n"
            f"  Batch Size: {config.batch_size}\\n"
            f"\\n"
            f"[bold]Environment Variables:[/bold]\\n"
            f"  VIBE_SEMANTIC_ENABLED={os.getenv('VIBE_SEMANTIC_ENABLED', 'false')}\\n"
            f"  VIBE_SEMANTIC_MODEL={os.getenv('VIBE_SEMANTIC_MODEL', 'not set')}\\n"
            f"  VIBE_SEMANTIC_DEVICE={os.getenv('VIBE_SEMANTIC_DEVICE', 'not set')}\\n"
            f"\\n"
            f"[bold]Commands:[/bold]\\n"
            f"  [dim]vibe config semantic --enable[/dim]  # Enable globally\\n"
            f"  [dim]vibe config semantic --disable[/dim]  # Disable globally\\n"
            f"  [dim]vibe config semantic --warmup[/dim]   # Download & precompute\\n"
            f"  [dim]vibe config semantic --clear-cache[/dim]  # Clear cache",
            title="[bold]Semantic Configuration[/bold]",
            border_style="cyan" if available else "yellow",
        )
    )


def _enable_semantic() -> None:
    """Enable semantic matching globally."""
    import os

    console.print("[bold cyan]🧠 Enabling Semantic Matching...[/bold cyan]\\n")

    # Set environment variable
    os.environ["VIBE_SEMANTIC_ENABLED"] = "true"

    console.print("[green]✅ Semantic matching enabled[/green]\\n")
    console.print("[dim]Note: This only affects the current session.[/dim]")
    console.print("[dim]To make it permanent, set the environment variable in your shell profile:[/dim]")
    console.print()
    console.print("  [bold]export VIBE_SEMANTIC_ENABLED=true[/bold]")


def _disable_semantic() -> None:
    """Disable semantic matching globally."""
    import os

    console.print("[bold yellow]🧠 Disabling Semantic Matching...[/bold yellow]\\n")

    # Set environment variable
    os.environ["VIBE_SEMANTIC_ENABLED"] = "false"

    console.print("[yellow]⚪ Semantic matching disabled[/yellow]\\n")
    console.print("[dim]To make it permanent, remove the environment variable from your shell profile.[/dim]")


def _set_semantic_model(model_name: str) -> None:
    """Change semantic model.

    Args:
        model_name: Name of the model to use
    """
    import os

    console.print(f"[bold cyan]🧠 Setting Semantic Model...[/bold cyan]\\n")
    console.print(f"[dim]Model: {model_name}[/dim]\\n")

    # Set environment variable
    os.environ["VIBE_SEMANTIC_MODEL"] = model_name

    console.print("[green]✅ Model updated[/green]\\n")
    console.print("[dim]Note: This only affects the current session.[/dim]")
    console.print("[dim]To make it permanent, set the environment variable in your shell profile:[/dim]")
    console.print()
    console.print(f"  [bold]export VIBE_SEMANTIC_MODEL={model_name}[/bold]")


def _clear_semantic_cache() -> None:
    """Clear semantic vector cache."""
    from pathlib import Path
    from vibesop.semantic.models import EncoderConfig

    console.print("[bold cyan]🧠 Clearing Semantic Cache...[/bold cyan]\\n")

    config = EncoderConfig.from_env()
    cache_dir = config.cache_dir or Path.home() / ".cache" / "vibesop" / "semantic"

    if not cache_dir.exists():
        console.print("[yellow]⚠️  Cache directory does not exist[/yellow]")
        raise typer.Exit(0)

    # Remove cache directory
    import shutil
    shutil.rmtree(cache_dir)

    console.print(f"[green]✅ Cache cleared: {cache_dir}[/green]\\n")
    console.print("[dim]Vectors will be recomputed on next use.[/dim]")


def _warmup_semantic() -> None:
    """Warmup semantic model (download + precompute)."""
    from vibesop.semantic.encoder import SemanticEncoder
    from vibesop.semantic.cache import VectorCache
    from vibesop.triggers import DEFAULT_PATTERNS
    from vibesop.semantic.models import EncoderConfig
    import time

    console.print("[bold cyan]🧠 Warming Up Semantic Model...[/bold cyan]\\n")

    config = EncoderConfig.from_env()

    # Initialize encoder
    console.print(f"[dim]Loading model: {config.model_name}[/dim]")
    start = time.time()
    encoder = SemanticEncoder(
        model_name=config.model_name,
        device=config.device,
        cache_dir=config.cache_dir,
    )
    load_time = time.time() - start
    console.print(f"[green]✅ Model loaded in {load_time:.1f}s[/green]\\n")

    # Initialize cache
    cache_dir = config.cache_dir or Path.home() / ".cache" / "vibesop" / "semantic"
    cache = VectorCache(cache_dir=cache_dir, encoder=encoder)

    # Precompute pattern vectors
    console.print("[dim]Precomputing pattern vectors...[/dim]")
    start = time.time()

    patterns_with_examples = [
        p for p in DEFAULT_PATTERNS
        if p.examples or p.semantic_examples
    ]

    for pattern in patterns_with_examples:
        examples = pattern.examples + pattern.semantic_examples
        if examples:
            cache.get_or_compute(pattern.pattern_id, examples)

    compute_time = time.time() - start
    console.print(f"[green]✅ Computed {len(patterns_with_examples)} vectors in {compute_time:.1f}s[/green]\\n")

    # Save to disk
    console.print("[dim]Saving cache to disk...[/dim]")
    cache.save_to_disk()
    console.print("[green]✅ Cache saved[/green]\\n")

    # Show cache stats
    stats = cache.get_cache_stats()
    console.print(
        Panel(
            f"[bold]✅ Warmup Complete[/bold]\\n\\n"
            f"Model: {config.model_name}\\n"
            f"Device: {encoder.get_device()}\\n"
            f"Vectors: {stats['size']} patterns\\n"
            f"Cache Size: {stats['size_mb']:.2f} MB\\n"
            f"\\n"
            f"[bold]Time:[/bold]\\n"
            f"  Load: {load_time:.1f}s\\n"
            f"  Compute: {compute_time:.1f}s\\n"
            f"  Total: {load_time + compute_time:.1f}s",
            title="[bold green]Ready[/bold green]",
            border_style="green",
        )
    )
