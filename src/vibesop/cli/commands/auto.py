"""VibeSOP auto command - Automatic intent detection and execution.

This command provides automatic keyword detection and skill/workflow
activation based on natural language input.

Usage:
    vibe auto <query>
    vibe auto "scan for security issues"
    vibe auto "帮我扫描安全漏洞"
    vibe auto --dry-run "deploy configuration"
    vibe auto --verbose "generate documentation"
"""

from __future__ import annotations

import json
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from vibesop.triggers import DEFAULT_PATTERNS, KeywordDetector, SkillActivator
from vibesop.triggers.models import PatternCategory, PatternMatch
from vibesop.semantic.models import EncoderConfig

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
        0.6,
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
    """Automatically detect intent and execute appropriate skill/workflow.

    This command uses intelligent keyword detection to understand what you
    want to do and automatically activates the appropriate skill or workflow.

    \\b
    Examples:
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

    \\b
    How it works:
        1. Analyzes your query using 30+ predefined patterns
        2. Matches against keywords, regex patterns, and semantic similarity
        3. Activates the appropriate skill or workflow
        4. Falls back to semantic routing if needed

    \\b
    Semantic matching (v2.1.0):
        Enable with --semantic flag for improved synonym detection and
        multilingual support. Uses sentence transformer embeddings for
        true semantic understanding (not just TF-IDF).

    \\b
    Pattern categories:
        - Security: scan, analyze, audit, fix, report
        - Config: deploy, validate, render, diff, backup
        - Dev: build, test, debug, refactor, lint, format
        - Docs: generate, update, format, readme, api, changelog
        - Project: init, migrate, audit, upgrade, clean, status
    """
    import asyncio

    console.print(f"\\n[bold cyan]🎯 Intelligent Auto-Execution[/bold cyan]\\n{'=' * 40}\\n")

    # Parse input data
    input_dict: dict[str, Any] = {}
    if input_data:
        try:
            input_dict = json.loads(input_data)
        except json.JSONDecodeError as e:
            console.print(f"[red]✗ Invalid JSON input: {e}[/red]")
            raise typer.Exit(1)

    # Show query
    console.print(f"[bold]Query:[/bold] {query}\\n")

    # Detect intent
    if verbose:
        semantic_status = "enabled" if enable_semantic else "disabled"
        console.print(
            f"[dim]Detecting intent (min confidence: {min_confidence}, "
            f"semantic: {semantic_status})...[/dim]\\n"
        )

    # Initialize semantic config if enabled
    semantic_config = None
    if enable_semantic:
        semantic_config = EncoderConfig(
            model_name=semantic_model,
        )

    detector = KeywordDetector(
        patterns=DEFAULT_PATTERNS,
        confidence_threshold=min_confidence,
        enable_semantic=enable_semantic,
        semantic_config=semantic_config,
    )
    match = detector.detect_best(query, min_confidence=min_confidence)

    if not match:
        _show_no_match_detected(query, min_confidence, verbose)
        raise typer.Exit(1)

    # Show match
    _show_match_details(match, verbose)

    # Dry run
    if dry_run:
        _show_dry_run(match, input_dict)
        return

    # Execute
    console.print(f"\\n[bold]Executing...[/bold]\\n")

    try:
        # Execute activation
        activator = SkillActivator()
        result = asyncio.run(activator.activate(match, input_data=input_dict))

        # Show result
        _show_execution_result(result, verbose)

    except Exception as e:
        console.print(f"[red]✗ Execution failed: {e}[/red]")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1)


def _show_match_details(match: PatternMatch, verbose: bool) -> None:
    """Show detected pattern match details.

    Args:
        match: Pattern match result
        verbose: Show detailed output
    """
    # Find pattern
    from vibesop.triggers import DEFAULT_PATTERNS

    pattern = next((p for p in DEFAULT_PATTERNS if p.pattern_id == match.pattern_id), None)

    if pattern:
        # Category emoji
        category_emoji = _get_category_emoji(pattern.category)

        console.print(
            Panel(
                f"[{category_emoji}] [bold cyan]{pattern.name}[/bold cyan]\\n\\n"
                f"[dim]ID:[/dim] {match.pattern_id}\\n"
                f"[dim]Category:[/dim] {pattern.category.value}\\n"
                f"[dim]Confidence:[/dim] {match.confidence:.2%}\\n"
                f"[dim]Description:[/dim] {pattern.description}\\n"
                + (
                    f"[dim]Keywords:[/dim] {', '.join(match.matched_keywords[:5])}\\n"
                    if match.matched_keywords
                    else ""
                )
                + (
                    f"[dim]Regex:[/dim] {len(match.matched_regex)} patterns matched\\n"
                    if match.matched_regex
                    else ""
                )
                + (
                    f"[dim]Semantic:[/dim] {match.semantic_score:.2%} "
                    f"({match.semantic_method or 'N/A'})\\n"
                    if match.semantic_score
                    else ""
                )
                + (f"[dim]Model:[/dim] {match.model_used or 'N/A'}\\n" if match.model_used else "")
                + (
                    f"[dim]Encoding Time:[/dim] {match.encoding_time * 1000:.1f}ms\\n"
                    if match.encoding_time
                    else ""
                ),
                title="[bold green]✓ Intent Detected[/bold green]",
                border_style="green",
            )
        )

        if verbose:
            console.print(f"[dim]Skill ID: {pattern.skill_id}[/dim]")
            if pattern.workflow_id:
                console.print(f"[dim]Workflow ID: {pattern.workflow_id}[/dim]")


def _show_dry_run(match: PatternMatch, input_data: dict[str, Any]) -> None:
    """Show dry-run preview.

    Args:
        match: Pattern match result
        input_data: Input data for execution
    """
    from vibesop.triggers import DEFAULT_PATTERNS

    pattern = next((p for p in DEFAULT_PATTERNS if p.pattern_id == match.pattern_id), None)

    if not pattern:
        return

    action = "workflow" if pattern.workflow_id else "skill"

    console.print(
        Panel(
            f"[bold yellow]🔍 DRY RUN[/bold yellow]\\n\\n"
            f"[bold]Action:[/bold] {action.upper()}\\n"
            f"[bold]Pattern:[/bold] {pattern.name}\\n"
            f"[bold]Description:[/bold] {pattern.description}\\n\\n"
            f"[bold]Will execute:[/bold]\\n"
            f"  • {action.title()}: {pattern.workflow_id or pattern.skill_id}\\n"
            f"  • Query: {pattern.description}\\n"
            + (f"  • Input: {json.dumps(input_data, indent=2)}\\n" if input_data else "")
            + f"\\n[dim]Remove --dry-run to execute.[/dim]",
            title="[bold]Preview[/bold]",
            border_style="yellow",
        )
    )


def _show_execution_result(result: dict[str, Any], verbose: bool) -> None:
    """Show execution result.

    Args:
        result: Execution result dict
        verbose: Show detailed output
    """
    if result.get("success"):
        action = result.get("action", "unknown").upper()
        console.print(
            Panel(
                f"[bold green]✓ {action} completed successfully[/bold green]\\n\\n"
                f"[bold]Pattern ID:[/bold] {result.get('pattern_id', 'N/A')}\\n"
                + (
                    f"[bold]Skill ID:[/bold] {result.get('skill_id', 'N/A')}\\n"
                    if result.get("skill_id")
                    else ""
                )
                + (
                    f"[bold]Workflow ID:[/bold] {result.get('workflow_id', 'N/A')}\\n"
                    if result.get("workflow_id")
                    else ""
                )
                + (
                    f"[bold]Routed:[/bold] Yes (via semantic routing)\\n"
                    if result.get("routed")
                    else ""
                ),
                title="[bold green]Success[/bold green]",
                border_style="green",
            )
        )

        if verbose and result.get("result"):
            console.print(f"\\n[bold]Result:[/bold]")
            console.print(result["result"])

    else:
        error = result.get("error", "Unknown error")
        console.print(
            Panel(
                f"[bold red]✗ Execution failed[/bold red]\\n\\n"
                f"[bold]Error:[/bold] {error}\\n\\n"
                f"[bold]Pattern ID:[/bold] {result.get('pattern_id', 'N/A')}",
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
            f"[bold yellow]⚠ No intent detected[/bold yellow]\\n\\n"
            f"[bold]Query:[/bold] {query}\\n"
            f"[bold]Confidence threshold:[/bold] {min_confidence:.2%}\\n\\n"
            f"[dim]The system couldn't detect a clear intent from your query.[/dim]\\n"
            f"[dim]Try:[/dim]\\n"
            f"  • [dim]Rephrasing your query[/dim]\\n"
            f"  • [dim]Using different keywords[/dim]\\n"
            f"  • [dim]Lowering the confidence threshold with --min-confidence[/dim]\\n"
            f"  • [dim]Using --verbose to see detection details[/dim]\\n\\n"
            f"[dim]Supported categories:[/dim] Security, Config, Dev, Docs, Project",
            title="[bold]No Match[/bold]",
            border_style="yellow",
        )
    )

    if verbose:
        # Show available patterns
        _show_available_patterns()


def _show_available_patterns() -> None:
    """Show available trigger patterns."""
    from vibesop.triggers import DEFAULT_PATTERNS

    console.print(f"\\n[bold]Available Patterns:[/bold]\\n")

    # Group by category
    by_category: dict[str, list[Any]] = {}
    for pattern in DEFAULT_PATTERNS:
        cat = pattern.category.value
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(pattern)

    # Show each category
    for category, patterns in sorted(by_category.items()):
        emoji = _get_category_emoji(patterns[0].category)
        console.print(f"  {emoji} [bold]{category.title()}:[/bold]")

        for pattern in sorted(patterns, key=lambda p: p.name):
            console.print(f"    • {pattern.name}")
            if pattern.examples:
                example = pattern.examples[0]
                console.print(f'      [dim]e.g., "{example}"[/dim]')


def _get_category_emoji(category: PatternCategory) -> str:
    """Get emoji for pattern category.

    Args:
        category: Pattern category

    Returns:
        Emoji string
    """
    emojis = {
        PatternCategory.SECURITY: "🔒",
        PatternCategory.CONFIG: "⚙️",
        PatternCategory.DEV: "🛠️",
        PatternCategory.DOCS: "📚",
        PatternCategory.PROJECT: "📁",
    }
    return emojis.get(category, "📌")
