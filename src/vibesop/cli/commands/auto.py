"""VibeSOP auto command - Automatic intent detection and execution.

This command provides automatic keyword detection and skill/workflow
activation based on natural language input.

DEPRECATED (v3.0.0): This command is deprecated. Use 'vibe route' instead.
The 'vibe auto' command will be removed in v4.0.0.

Usage:
    vibe auto <query>
    vibe auto "scan for security issues"
    vibe auto "帮我扫描安全漏洞"
    vibe auto --dry-run "deploy configuration"
    vibe auto --verbose "generate documentation"
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from vibesop.core.routing import UnifiedRouter, RoutingConfig

console = Console()


def auto(
    query: str = typer.Argument(..., help="Natural language query describing what you want to do"),
    input_data: Optional[str] = typer.Option(
        None,
        "--input",
        "-i",
        help="Input data as JSON string",
    ),
    min_confidence: float = typer.Option(
        0.3,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold (0.0 - 1.0)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done without executing",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output",
    ),
    # Semantic options (v2.1.0)
    enable_semantic: bool = typer.Option(
        False,
        "--semantic",
        "-s",
        help="Enable semantic matching using sentence embeddings",
    ),
    semantic_model: str = typer.Option(
        "paraphrase-multilingual-MiniLM-L12-v2",
        "--semantic-model",
        help="Semantic model name (default: paraphrase-multilingual-MiniLM-L12-v2)",
    ),
    semantic_threshold: float = typer.Option(
        0.7,
        "--semantic-threshold",
        help="Semantic similarity threshold (0.0 - 1.0, default: 0.7)",
    ),
) -> None:
    """[DEPRECATED] Automatically detect intent and execute appropriate skill.

    **DEPRECATED (v3.0.0)**: This command is deprecated. Use 'vibe route' instead.
    The 'vibe auto' command will be removed in v4.0.0.

    Migration:
        OLD: vibe auto "scan for security issues"
        NEW: vibe route "scan for security issues"

    For automatic skill execution, use the skill directly:
        OLD: vibe auto "debug error"  # (would auto-execute)
        NEW: vibe skills execute systematic-debugging "debug error"

    This command currently delegates to the new UnifiedRouter for backward
    compatibility, but please migrate to 'vibe route' for future support.

    \\b
    Examples (deprecated):
        # Detect and execute security scan
        vibe auto "scan for security issues"

        # Deploy configuration
        vibe auto "deploy configuration to production"

        # Generate documentation
        vibe auto "generate API documentation"

        # Chinese queries work too
        vibe auto "帮我扫描安全漏洞"

        # Enable semantic matching for better accuracy
        vibe auto "帮我检查代码安全问题" --semantic

        # Preview what would happen
        vibe auto --dry-run "run tests"

        # Provide input data
        vibe auto "scan" --input '{"target": "./src"}'

        # Adjust confidence threshold
        vibe auto "test" --min-confidence 0.5
    """
    # Show deprecation warning
    warnings.warn(
        "vibe auto is deprecated. Use 'vibe route' instead. "
        "vibe auto will be removed in v4.0.0.",
        DeprecationWarning,
        stacklevel=2,
    )

    console.print(
        f"\n[yellow]⚠️  'vibe auto' is deprecated. Use 'vibe route' instead.[/yellow]\n"
    )

    _auto_impl(
        query=query,
        input_data=input_data,
        min_confidence=min_confidence,
        dry_run=dry_run,
        verbose=verbose,
        enable_semantic=enable_semantic,
        semantic_model=semantic_model,
        semantic_threshold=semantic_threshold,
    )


def _auto_impl(
    query: str,
    input_data: Optional[str] = None,
    min_confidence: float = 0.3,
    dry_run: bool = False,
    verbose: bool = False,
    enable_semantic: bool = False,
    semantic_model: str = "paraphrase-multilingual-MiniLM-L12-v2",
    semantic_threshold: float = 0.7,
) -> None:
    """Internal implementation using UnifiedRouter."""
    import asyncio

    console.print(f"\n[bold cyan]🎯 Intelligent Auto-Execution[/bold cyan]\n{'=' * 40}\n")

    # Parse input data
    input_dict: dict[str, Any] = {}
    if input_data:
        try:
            input_dict = json.loads(input_data)
        except json.JSONDecodeError as e:
            console.print(f"[red]✗ Invalid JSON input: {e}[/red]")
            raise typer.Exit(1)

    # Show query
    console.print(f"[bold]Query:[/bold] {query}\n")

    if verbose:
        console.print(
            f"[dim]Routing query (min confidence: {min_confidence})...[/dim]\n"
        )

    # Initialize routing config
    config = RoutingConfig(
        min_confidence=min_confidence,
        enable_embedding=enable_semantic,
    )

    # Route using UnifiedRouter
    router = UnifiedRouter(
        project_root=Path.cwd(),
        config=config,
    )

    result = router.route(query)

    if not result.has_match:
        _show_no_match_detected(query, min_confidence, verbose)
        raise typer.Exit(1)

    # Show match
    _show_match_details(result, verbose)

    # Dry run
    if dry_run:
        _show_dry_run(result, input_dict)
        return

    # Execute
    console.print(f"\n[bold]Executing...[/bold]\n")

    try:
        # Execute the matched skill
        from vibesop.core.skills import SkillManager

        manager = SkillManager(project_root=Path.cwd())
        skill_result = asyncio.run(
            manager.execute_skill(
                result.primary.skill_id,
                query,
                context=input_dict,
            )
        )

        # Show result
        _show_execution_result(skill_result, verbose)

    except Exception as e:
        console.print(f"[red]✗ Execution failed: {e}[/red]")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1)


def _show_match_details(result: Any, verbose: bool) -> None:
    """Show detected pattern match details.

    Args:
        result: Routing result from UnifiedRouter
        verbose: Show detailed output
    """
    primary = result.primary

    # Category emoji based on layer
    layer_emoji = _get_layer_emoji(primary.layer)

    console.print(
        Panel(
            f"[{layer_emoji}] [bold cyan]{primary.skill_id}[/bold cyan]\n\n"
            f"[dim]Layer:[/dim] {primary.layer.value}\n"
            f"[dim]Confidence:[/dim] {primary.confidence:.2%}\n"
            f"[dim]Source:[/dim] {primary.source}\n"
            f"[dim]Duration:[/dim] {result.duration_ms:.1f}ms\n"
            + (f"[dim]Metadata:[/dim] {primary.metadata}\n" if verbose and primary.metadata else ""),
            title="[bold green]✓ Intent Detected[/bold green]",
            border_style="green",
        )
    )

    if verbose and result.alternatives:
        console.print(f"\n[bold]Alternatives:[/bold]")
        for i, alt in enumerate(result.alternatives[:3], 1):
            console.print(f"  {i}. {alt.skill_id} - {alt.confidence:.1%}")


def _show_dry_run(result: Any, input_data: dict[str, Any]) -> None:
    """Show dry-run preview.

    Args:
        result: Routing result
        input_data: Input data for execution
    """
    primary = result.primary

    console.print(
        Panel(
            f"[bold yellow]🔍 DRY RUN[/bold yellow]\n\n"
            f"[bold]Action:[/bold] SKILL\n"
            f"[bold]Skill ID:[/bold] {primary.skill_id}\n"
            f"[bold]Layer:[/bold] {primary.layer.value}\n"
            f"[bold]Confidence:[/bold] {primary.confidence:.1%}\n\n"
            f"[bold]Will execute:[/bold]\n"
            f"  • Skill: {primary.skill_id}\n"
            f"  • Source: {primary.source}\n"
            + (f"  • Input: {json.dumps(input_data, indent=2)}\n" if input_data else "")
            + f"\n[dim]Remove --dry-run to execute.[/dim]",
            title="[bold]Preview[/bold]",
            border_style="yellow",
        )
    )


def _show_execution_result(skill_result: Any, verbose: bool) -> None:
    """Show execution result.

    Args:
        skill_result: Skill execution result
        verbose: Show detailed output
    """
    # Handle different result formats
    if isinstance(skill_result, dict):
        success = skill_result.get("success", True)
        result_data = skill_result.get("result")
    elif hasattr(skill_result, "success"):
        success = skill_result.success
        result_data = getattr(skill_result, "result", None)
    else:
        success = True
        result_data = skill_result

    if success:
        console.print(
            Panel(
                f"[bold green]✓ Skill completed successfully[/bold green]\n\n"
                + (
                    f"[bold]Result:[/bold]\n{result_data}\n"
                    if result_data and verbose
                    else ""
                ),
                title="[bold green]Success[/bold green]",
                border_style="green",
            )
        )
    else:
        error = getattr(skill_result, "error", "Unknown error")
        if isinstance(skill_result, dict):
            error = skill_result.get("error", "Unknown error")

        console.print(
            Panel(
                f"[bold red]✗ Execution failed[/bold red]\n\n"
                f"[bold]Error:[/bold] {error}\n",
                title="[bold red]Failure[/bold red]",
                border_style="red",
            )
        )


def _show_no_match_detected(query: str, min_confidence: float, verbose: bool) -> None:
    """Show message when no pattern matches.

    Args:
        query: User query
        min_confidence: Confidence threshold used
        verbose: Show detailed output
    """
    console.print(
        Panel(
            f"[bold yellow]⚠ No intent detected[/bold yellow]\n\n"
            f"[bold]Query:[/bold] {query}\n"
            f"[bold]Confidence threshold:[/bold] {min_confidence:.2%}\n\n"
            f"[dim]The system couldn't detect a clear intent from your query.[/dim]\n"
            f"[dim]Try:[/dim]\n"
            f"  • [dim]Rephrasing your query[/dim]\n"
            f"  • [dim]Using different keywords[/dim]\n"
            f"  • [dim]Lowering the confidence threshold with --min-confidence[/dim]\n"
            f"  • [dim]Using --verbose to see detection details[/dim]\n"
            f"  • [dim]Listing available skills with [cyan]vibe skills list[/cyan][/dim]",
            title="[bold]No Match[/bold]",
            border_style="yellow",
        )
    )


def _get_layer_emoji(layer: Any) -> str:
    """Get emoji for routing layer.

    Args:
        layer: RoutingLayer enum

    Returns:
        Emoji string
    """
    from vibesop.core.routing import RoutingLayer

    emojis = {
        RoutingLayer.AI: "🤖",
        RoutingLayer.EXPLICIT: "🎯",
        RoutingLayer.SCENARIO: "📋",
        RoutingLayer.SEMANTIC: "🧠",
        RoutingLayer.FUZZY: "🔍",
    }
    return emojis.get(layer, "📌")
