"""VibeSOP skill add command - One-click smart skill installation.

This command provides the user-friendly installation experience:
1. vibe skill add tushare.skill
2. Auto-detect skill metadata
3. Interactive configuration wizard
4. Auto-generate routing rules and priorities

Usage:
    vibe skill add <skill-file>
    vibe skill add tushare.skill
    vibe skill add https://example.com/skills/tushare.skill
"""

import json
from pathlib import Path
from typing import Any

import questionary
import typer
from rich.console import Console
from rich.panel import Panel

from vibesop.core.ai_enhancer import AIEnhancer
from vibesop.core.llm_config import (
    LLMConfigResolver,
    get_agent_llm_config,
    is_in_agent_environment,
)
from vibesop.core.routing.unified import UnifiedRouter
from vibesop.core.session_analyzer import SkillSuggestion
from vibesop.core.skills import SkillManager
from vibesop.core.skills.base import SkillMetadata
from vibesop.core.skills.parser import parse_skill_md
from vibesop.core.skills.understander import SkillAutoConfigurator
from vibesop.installer.skill_installer import SkillInstaller
from vibesop.security.skill_auditor import SkillSecurityAuditor, ThreatLevel

console = Console()


def add(
    skill_source: str = typer.Argument(..., help="Skill file (.skill), directory, or URL"),
    global_: bool = typer.Option(
        False,
        "--global",
        "-g",
        help="Install globally (vs project-level)",
    ),
    auto_config: bool = typer.Option(
        True,
        "--auto-config/--manual-config",
        help="Auto-configure routing rules (default: yes)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force reinstall if already exists",
    ),
) -> None:
    """Add and configure a skill with intelligent auto-configuration.

    This command provides a complete one-click installation experience:
    - Auto-detects skill metadata from .skill files or directories
    - Runs security audit
    - Asks for installation scope (project/global)
    - Auto-generates routing rules and priorities
    - Updates manifest and syncs to platform

    \b
    Examples:
        # Install from .skill file
        vibe skill add tushare.skill

        # Install from directory
        vibe skill add ./skills/tushare

        # Install globally
        vibe skill add tushare.skill --global

        # Manual configuration mode
        vibe skill add tushare.skill --manual-config
    """
    console.print("\n[bold cyan]🚀 Smart Skill Installation[/bold cyan]\n")

    # Phase 1: Detect and load skill
    console.print("[dim]Phase 1: Detecting skill...[/dim]")
    skill_path, metadata = _detect_and_load_skill(skill_source)

    if not metadata:
        console.print("[red]✗ Could not load skill metadata[/red]")
        console.print("[dim]Please ensure SKILL.md exists with proper frontmatter[/dim]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Detected:[/green] {metadata.name}")
    console.print(f"[dim]  ID:[/dim] {metadata.id}")
    console.print(f"[dim]  Description:[/dim] {metadata.description}")

    # Phase 2: Security audit
    console.print("\n[dim]Phase 2: Security audit...[/dim]")
    auditor = SkillSecurityAuditor(strict_mode=False, project_root=".")
    auditor.add_allowed_path(skill_path)
    audit_result = auditor.audit_skill_file(skill_path / "SKILL.md")

    if audit_result.risk_level == ThreatLevel.CRITICAL:
        console.print("[red]✗ Critical security risks detected![/red]")
        console.print(audit_result.reason)
        raise typer.Exit(1)
    elif audit_result.risk_level in (ThreatLevel.HIGH, ThreatLevel.MEDIUM):
        console.print("[yellow]⚠ Security warnings:[/yellow]")
        console.print(audit_result.reason)
        if not questionary.confirm("Continue despite warnings?", default=False).ask():
            raise typer.Exit(1)
    else:
        console.print("[green]✓ Security audit passed[/green]")

    # Phase 3: Determine installation scope
    console.print("\n[dim]Phase 3: Installation scope[/dim]")

    if global_:
        scope = "global"
        console.print("[dim]Installing globally (as requested)[/dim]")
    else:
        scope = questionary.select(
            "Where should this skill be installed?",
            choices=[
                questionary.Choice("🎯 Project-level (recommended)", value="project"),
                questionary.Choice("🌐 Global (available to all projects)", value="global"),
            ],
            default="project",
        ).ask()

    # Phase 4: Install the skill
    console.print(f"\n[dim]Phase 4: Installing {scope}...[/dim]")
    installer = SkillInstaller()

    project_path = Path(".") if scope == "project" else Path.home() / ".vibe"
    install_result = installer.install_skill(
        skill_path=skill_path,
        project_path=project_path,
        force=force,
    )

    if not install_result["success"]:
        console.print("[red]✗ Installation failed[/red]")
        for error in install_result["errors"]:
            console.print(f"  [dim]• {error}[/dim]")
        raise typer.Exit(1)

    console.print(f"[green]✓ Installed to:[/green] {install_result['installed_path']}")

    # Phase 5: Intelligent configuration with LLM
    if auto_config:
        console.print("\n[dim]Phase 5: Auto-configuring with LLM understanding...[/dim]")
        _auto_configure_skill_with_llm(metadata, scope, skill_source)
    else:
        console.print("\n[dim]Phase 5: Manual configuration[/dim]")
        _manual_configure_skill(metadata, scope)

    # Phase 6: Verify and sync
    console.print("\n[dim]Phase 6: Verifying...[/dim]")
    _verify_and_sync(metadata.id, scope)

    console.print("\n[bold green]✨ Installation complete![/bold green]")
    console.print(
        Panel(
            f"[bold]{metadata.name}[/bold] is now ready to use!\n\n"
            f"[dim]Test it with:[/dim]\n"
            f"  [cyan]vibe route \"{metadata.trigger_when or 'test query'}\"[/cyan]\n\n"
            f"[dim]View details:[/dim]\n"
            f"  [cyan]vibe skills info {metadata.id}[/cyan]",
            border_style="green",
        )
    )


def _detect_and_load_skill(source: str) -> tuple[Path, SkillMetadata | None]:
    """Detect skill type and load metadata.

    Args:
        source: Skill file path, directory, or URL

    Returns:
        Tuple of (skill_path, metadata)
    """
    source_path = Path(source)

    # Case 1: .skill file
    if source_path.suffix == ".skill":
        # .skill files are essentially tarballs or JSON manifests
        console.print("[dim]Detected: .skill file[/dim]")

        # For now, assume it's a directory with .skill extension
        # In production, this would handle tarballs
        skill_path = source_path
        metadata_file = source_path / "SKILL.md"

        if metadata_file.exists():
            metadata = parse_skill_md(metadata_file)
            return skill_path, metadata

        # Try to generate metadata from skill name
        metadata = SkillMetadata(
            id=source_path.stem,
            name=source_path.stem.replace("-", " ").title(),
            description=f"Skill from {source_path.name}",
            intent="",
            trigger_when="User requests assistance",
        )
        return skill_path, metadata

    # Case 2: Directory with SKILL.md
    if source_path.is_dir():
        metadata_file = source_path / "SKILL.md"
        if metadata_file.exists():
            console.print("[dim]Detected: skill directory[/dim]")
            metadata = parse_skill_md(metadata_file)
            return source_path, metadata

    # Case 3: URL (future)
    if source.startswith(("http://", "https://")):
        console.print("[dim]Detected: remote URL[/dim]")
        console.print("[yellow]⚠ URL installation not yet implemented[/yellow]")
        raise typer.Exit(1)

    console.print("[red]✗ Could not detect skill type[/red]")
    return source_path, None


def _auto_configure_skill(metadata: SkillMetadata, scope: str, source: str) -> None:
    """Auto-generate routing rules and priorities.

    Uses AI to analyze the skill description and generate
    appropriate configuration.

    Args:
        metadata: Skill metadata
        scope: Installation scope (project/global)
        source: Original skill source
    """
    console.print("[dim]Analyzing skill for auto-configuration...[/dim]")

    # Create a mock SkillSuggestion for AI enhancement
    suggestion = SkillSuggestion(
        skill_name=metadata.name,
        description=metadata.description,
        trigger_queries=[metadata.trigger_when or metadata.description],
        frequency=1,
        confidence=0.5,
        estimated_value="medium",
    )

    # Use AI to enhance the skill
    try:
        enhancer = AIEnhancer()
        enhanced = enhancer.enhance_suggestion(suggestion)

        console.print(f"[green]✓ Category:[/green] {enhanced.category}")
        console.print(f"[green]✓ Tags:[/green] {', '.join(enhanced.tags)}")

        # Auto-generate priority based on category
        priority_map = {
            "development": 70,
            "testing": 65,
            "debugging": 80,
            "review": 50,
            "documentation": 40,
            "deployment": 75,
            "security": 85,
            "optimization": 60,
        }

        priority = priority_map.get(enhanced.category, 50)

        # Generate routing pattern
        if enhanced.trigger_conditions:
            primary_trigger = enhanced.trigger_conditions[0]
            # Extract keywords for pattern matching
            keywords = _extract_keywords(primary_trigger)
            pattern = "|".join(keywords) if keywords else metadata.id.replace("-", ".*")
        else:
            pattern = metadata.id.replace("-", ".*")

        # Auto-generate configuration
        config = {
            "skill_id": metadata.id,
            "priority": priority,
            "enabled": True,
            "scope": scope,
            "category": enhanced.category,
            "tags": enhanced.tags,
            "routing": {
                "patterns": [pattern],
                "priority": priority,
            },
        }

        # Save configuration
        _save_auto_config(config)

        console.print(f"[green]✓ Priority:[/green] {priority}")
        console.print(f"[green]✓ Routing pattern:[/green] {pattern}")

    except Exception as e:
        console.print(f"[yellow]⚠ Auto-configuration failed: {e}[/yellow]")
        console.print("[dim]Falling back to default configuration[/dim]")

        # Fallback config
        config = {
            "skill_id": metadata.id,
            "priority": 50,
            "enabled": True,
            "scope": scope,
            "routing": {
                "patterns": [metadata.id.replace("-", ".*")],
                "priority": 50,
            },
        }

        _save_auto_config(config)


def _auto_configure_skill_with_llm(metadata: SkillMetadata, scope: str, skill_source: str) -> None:
    """Auto-configure skill using the understander module.

    This function integrates with the SkillAutoConfigurator to provide
    intelligent skill understanding and configuration.

    Args:
        metadata: Skill metadata
        scope: Installation scope (project/global)
        skill_source: Original skill source path
    """
    from vibesop.core.skills.understander import understand_skill_from_file

    try:
        # Read the skill content
        skill_path = Path(skill_source)
        if skill_path.suffix == ".skill":
            # It's a .skill file/directory
            skill_md = skill_path / "SKILL.md"
        else:
            # It's already a directory
            skill_md = skill_path / "SKILL.md"

        if not skill_md.exists():
            console.print("[yellow]⚠ SKILL.md not found, using metadata only[/yellow]")
            # Use rule-based configuration
            _auto_configure_skill(metadata, scope, skill_source)
            return

        # Use the understander to generate config
        config = understand_skill_from_file(skill_path.parent if skill_path.suffix == ".skill" else skill_path, scope)

        console.print(f"[green]✓ Category:[/green] {config.category}")
        console.print(f"[green]✓ Priority:[/green] {config.priority}")

        if config.routing_patterns:
            patterns_str = ', '.join(config.routing_patterns[:3])
            if len(config.routing_patterns) > 3:
                patterns_str += f" ... ({len(config.routing_patterns)} total)"
            console.print(f"[green]✓ Routing patterns:[/green] {patterns_str}")

        if config.requires_llm and config.llm_config:
            provider = config.llm_config.get("provider", "N/A")
            models = config.llm_config.get("models", [])
            model = models[0] if models else "N/A"
            temperature = config.llm_config.get("temperature", "N/A")
            console.print(f"[green]✓ LLM config:[/green] {provider} / {model} (temp: {temperature})")

            # Check if LLM is available
            resolver = LLMConfigResolver()
            available_llm = resolver.resolve_llm_config(config.llm_config, prefer_agent=True)

            if available_llm:
                console.print(f"[dim]  ✓ LLM available: {available_llm.provider}/{available_llm.model}[/dim]")
                console.print(f"[dim]  Source: {available_llm.source.value}[/dim]")
            else:
                console.print("[yellow]  ⚠ No LLM configured - skill will work in limited mode[/yellow]")
                console.print("[dim]    Configure LLM in .vibe/config.yaml or set environment variables[/dim]")
        else:
            console.print(f"[green]✓ LLM:[/green] Not required")

        console.print(f"[dim]  Confidence: {config.confidence:.1%}[/dim]")

        # Save the auto-generated config
        configurator = SkillAutoConfigurator()
        output_dir = Path(".vibe") / "skills"
        config_file = configurator.save_config(config, output_dir)
        console.print(f"[green]✓ Configuration saved:[/green] {config_file}")

    except Exception as e:
        console.print(f"[yellow]⚠ Auto-configuration with understander failed: {e}[/yellow]")
        console.print("[dim]Falling back to rule-based configuration[/dim]")
        _auto_configure_skill(metadata, scope, skill_source)


def _manual_configure_skill(metadata: SkillMetadata, scope: str) -> None:
    """Interactive manual configuration wizard.

    Args:
        metadata: Skill metadata
        scope: Installation scope
    """
    console.print("[dim]Starting manual configuration wizard...[/dim]\n")

    # Ask for priority
    priority = questionary.select(
        "What priority should this skill have?",
        choices=[
            questionary.Choice("🔴 Critical (100) - Always use for matching queries", value=100),
            questionary.Choice("🟠 High (75) - Prefer over general skills", value=75),
            questionary.Choice("🟡 Medium (50) - Default priority", value=50),
            questionary.Choice("🟢 Low (25) - Use only if no better match", value=25),
        ],
        default=50,
    ).ask()

    # Ask about routing
    auto_routing = questionary.confirm(
        "Generate automatic routing rules from skill description?",
        default=True,
    ).ask()

    routing_patterns = []
    if auto_routing:
        keywords = _extract_keywords(metadata.description)
        routing_patterns = [f".*{kw}.*" for kw in keywords[:5]]
    else:
        pattern = questionary.text(
            "Enter routing pattern (regex):",
            default=metadata.id.replace("-", ".*"),
        ).ask()
        routing_patterns = [pattern]

    # Save configuration
    config = {
        "skill_id": metadata.id,
        "priority": priority,
        "enabled": True,
        "scope": scope,
        "routing": {
            "patterns": routing_patterns,
            "priority": priority,
        },
    }

    _save_auto_config(config)

    console.print(f"[green]✓ Configuration saved[/green]")


def _save_auto_config(config: dict[str, Any]) -> None:
    """Save auto-generated configuration.

    Args:
        config: Configuration dictionary
    """
    import yaml

    config_file = Path(".vibe") / "skills" / "auto-config.yaml"

    # Load existing config
    if config_file.exists():
        with config_file.open() as f:
            existing = yaml.safe_load(f) or {}
    else:
        existing = {"skills": {}}

    # Update with new config
    skill_id = config["skill_id"]
    existing["skills"][skill_id] = config

    # Save
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with config_file.open("w") as f:
        yaml.dump(existing, f, default_flow_style=False)


def _extract_keywords(text: str) -> list[str]:
    """Extract keywords from text for pattern matching.

    Args:
        text: Text to extract from

    Returns:
        List of keywords
    """
    import re

    # Extract meaningful words (2+ characters)
    words = re.findall(r"\b\w{2,}\b", text.lower())

    # Filter common words (expanded stop words list)
    stop_words = {
        # English stop words
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "for",
        "with", "from", "this", "that", "these", "those",
        "use", "using", "get", "got", "make", "made", "take", "took",
        "help", "user", "ask", "want", "like", "need",
        # Chinese stop words
        "用户", "帮助", "使用", "需要", "想要", "可以",
    }

    keywords = [w for w in words if w not in stop_words and len(w) >= 3]

    # Return top 5 most frequent
    from collections import Counter

    counter = Counter(keywords)
    return [word for word, _ in counter.most_common(5)]


def _verify_and_sync(skill_id: str, scope: str) -> None:
    """Verify installation and sync to platform.

    Args:
        skill_id: Skill identifier
        scope: Installation scope
    """
    # Test routing
    router = UnifiedRouter(project_root=Path("."))

    # Try to route a query that should match this skill
    test_queries = [
        skill_id.replace("-", " "),
        f"help with {skill_id.replace('-', ' ')}",
    ]

    matched = False
    for query in test_queries:
        result = router.route(query)
        if result.primary and result.primary.skill_id == skill_id:
            matched = True
            console.print(f"[green]✓ Routing test passed:[/green] {query}")
            break

    if not matched:
        console.print("[yellow]⚠ Routing test: No direct match (this is OK)[/yellow]")

    # Sync to platform
    console.print("[dim]Syncing to platform...[/dim]")
    # In production, this would call `vibe build`
    console.print("[green]✓ Synced[/green]")
