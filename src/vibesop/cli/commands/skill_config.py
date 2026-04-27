"""VibeSOP skill config command - Manage skill LLM configurations.

This command allows users to:
1. View skill LLM configurations
2. Set custom LLM configurations for specific skills
3. Update existing configurations
4. Delete skill configurations

Usage:
    vibe skill config list
    vibe skill config get <skill-id>
    vibe skill config set <skill-id> --provider openai --model gpt-4
    vibe skill config delete <skill-id>
"""

import json
from pathlib import Path

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.skills.config_manager import (
    SkillConfigManager,
    list_skill_configs,
)
from vibesop.core.skills.manager import SkillManager

console = Console()

_IMPORT_CONFIG_ARGUMENT = typer.Argument(..., help="Path to configuration file (JSON or YAML)")
_EXPORT_CONFIG_ARGUMENT = typer.Argument(..., help="Output file path (JSON or YAML)")


def list_configs() -> None:
    """List all skill configurations."""

    console.print("\n[bold cyan]📋 Skill Configurations[/bold cyan]\n")

    # 获取所有技能配置
    skill_configs = list_skill_configs()

    if not skill_configs:
        console.print("[yellow]⚠ No skill configurations found[/yellow]")
        console.print("[dim]Use 'vibe skill add' to auto-generate configurations[/dim]")
        raise typer.Exit(0)

    # 创建表格
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Skill ID", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Priority", style="yellow")
    table.add_column("Category", style="blue")
    table.add_column("LLM", style="red")
    table.add_column("Auto", style="dim")

    for skill_id, config in skill_configs.items():
        llm_info = "No"
        if config.requires_llm:
            provider = config.llm_provider or "N/A"
            model = config.llm_model or "N/A"
            llm_info = f"{provider}/{model}"

        auto = "✓" if config.auto_configured else "✗"

        table.add_row(
            skill_id,
            "✓" if config.enabled else "✗",
            str(config.priority),
            config.category,
            llm_info,
            auto,
        )

    console.print(table)

    # 显示统计信息
    total = len(skill_configs)
    enabled = sum(1 for c in skill_configs.values() if c.enabled)
    with_llm = sum(1 for c in skill_configs.values() if c.requires_llm)
    auto_configured = sum(1 for c in skill_configs.values() if c.auto_configured)

    console.print(
        f"\n[dim]Total: {total} | Enabled: {enabled} | With LLM: {with_llm} | Auto-configured: {auto_configured}[/dim]"
    )


def get_config(skill_id: str) -> None:
    """Get configuration for a specific skill.

    Args:
        skill_id: Skill identifier
    """

    console.print(f"\n[bold cyan]🔍 Configuration: {skill_id}[/bold cyan]\n")

    # 获取技能配置
    config = SkillConfigManager.get_skill_config(skill_id)

    if not config:
        console.print(f"[yellow]⚠ No configuration found for: {skill_id}[/yellow]")
        console.print("[dim]Use 'vibe skill config set' to create a configuration[/dim]")
        raise typer.Exit(1)

    # 显示基本信息
    console.print("[bold]Basic Information:[/bold]")
    console.print(f"  Skill ID: {config.skill_id}")
    console.print(f"  Enabled: {'✓' if config.enabled else '✗'}")
    console.print(f"  Priority: {config.priority}")
    console.print(f"  Category: {config.category}")
    console.print(f"  Scope: {config.scope}")

    # 显示 LLM 配置
    console.print("\n[bold]LLM Configuration:[/bold]")
    if config.requires_llm:
        console.print("  Requires LLM: Yes")
        if config.llm_provider:
            console.print(f"  Provider: {config.llm_provider}")
        if config.llm_model:
            console.print(f"  Model: {config.llm_model}")
        if config.llm_temperature:
            console.print(f"  Temperature: {config.llm_temperature}")
        if config.llm_api_base:
            console.print(f"  API Base: {config.llm_api_base}")

        # 获取实际的 LLM 配置
        from vibesop.core.skills.config_manager import get_skill_llm_config

        llm_config = get_skill_llm_config(skill_id)
        if llm_config:
            console.print(f"\n[dim]  Active LLM: {llm_config.provider}/{llm_config.model}[/dim]")
            console.print(f"[dim]  Source: {llm_config.source.value}[/dim]")
            console.print(f"[dim]  Confidence: {llm_config.confidence:.1%}[/dim]")
        else:
            console.print("\n[yellow]  ⚠ No LLM available - check global configuration[/yellow]")
    else:
        console.print("  Requires LLM: No")

    # 显示路由配置
    console.print("\n[bold]Routing Configuration:[/bold]")
    if config.routing_patterns:
        console.print(f"  Patterns ({len(config.routing_patterns)}):")
        for pattern in config.routing_patterns[:5]:
            console.print(f"    • {pattern}")
        if len(config.routing_patterns) > 5:
            console.print(f"    [dim]... and {len(config.routing_patterns) - 5} more[/dim]")
    else:
        console.print("  Patterns: None")

    # 显示元数据
    console.print("\n[bold]Metadata:[/bold]")
    console.print(f"  Auto-configured: {'Yes' if config.auto_configured else 'No'}")
    console.print(f"  Confidence: {config.confidence:.1%}")


def set_config(
    skill_id: str = typer.Argument(..., help="Skill identifier"),
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="LLM provider (anthropic, openai, etc.)"
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Model name"),
    temperature: float | None = typer.Option(
        None, "--temperature", "-t", help="Temperature parameter"
    ),
    api_key: str | None = typer.Option(
        None, "--api-key", help="API key (optional, uses global if not specified)"
    ),
    api_base: str | None = typer.Option(None, "--api-base", help="API base URL (optional)"),
) -> None:
    """Set LLM configuration for a specific skill.

    This allows you to override the global LLM configuration for a specific skill.

    Examples:
        # Set OpenAI GPT-4 for a skill
        vibe skill config set code-reviewer --provider openai --model gpt-4 --temperature 0.2

        # Set Anthropic Claude for a skill
        vibe skill config set brainstorm --provider anthropic --model claude-3-opus-20240229

        # Interactive mode
        vibe skill config set my-skill
    """

    console.print(f"\n[bold cyan]⚙️  Configure LLM: {skill_id}[/bold cyan]\n")

    # 检查技能是否存在
    try:
        skill_manager = SkillManager()
        skill_def = skill_manager.get_skill(skill_id)
        if skill_def:
            console.print(f"[dim]Skill found: {skill_def.metadata.name}[/dim]\n")
    except (OSError, ValueError):
        console.print(f"[yellow]⚠ Warning: Skill '{skill_id}' not found in registry[/yellow]")
        console.print(
            "[dim]Configuration will be saved, but skill may not be installed yet\n[/dim]"
        )

    # 如果没有提供参数,使用交互式模式
    if not any([provider, model]):
        console.print("[dim]Interactive mode - answer the questions below[/dim]\n")

        # 选择提供商
        provider = questionary.select(
            "Which LLM provider?",
            choices=[
                questionary.Choice("🤖 Anthropic (Claude)", value="anthropic"),
                questionary.Choice("🧠 OpenAI (GPT)", value="openai"),
                questionary.Choice("🔮 Google (Gemini)", value="google"),
                questionary.Choice("🌐 Other", value="other"),
            ],
        ).ask()

        if not provider:
            raise typer.Exit(0)

        # 根据提供商推荐模型
        if provider == "anthropic":
            model_choices = [
                questionary.Choice(
                    "Claude 3.5 Sonnet (Recommended)", value="claude-3-5-sonnet-20241022"
                ),
                questionary.Choice("Claude Sonnet 4.6", value="claude-sonnet-4-6-20250514"),
                questionary.Choice("Claude 3 Opus", value="claude-3-opus-20240229"),
                questionary.Choice("Claude 3 Haiku (Fast)", value="claude-3-haiku-20240307"),
            ]
        elif provider == "openai":
            model_choices = [
                questionary.Choice("GPT-4 (Recommended)", value="gpt-4"),
                questionary.Choice("GPT-4 Turbo", value="gpt-4-turbo"),
                questionary.Choice("GPT-3.5 Turbo (Fast)", value="gpt-3.5-turbo"),
            ]
        elif provider == "google":
            model_choices = [
                questionary.Choice("Gemini Pro", value="gemini-pro"),
                questionary.Choice("Gemini Ultra", value="gemini-ultra"),
            ]
        else:
            model = questionary.text("Enter model name:").ask()
            model_choices = []

        if model_choices:
            model = questionary.select(
                "Which model?",
                choices=model_choices,
            ).ask()

        # 选择温度
        temperature = questionary.select(
            "Select temperature (creativity):",
            choices=[
                questionary.Choice("🎯 Precise (0.1-0.3)", value=0.2),
                questionary.Choice("⚖️  Balanced (0.4-0.7)", value=0.5),
                questionary.Choice("🎨 Creative (0.8-1.0)", value=0.9),
            ],
        ).ask()

    # 构建配置
    llm_config = {}

    if provider:
        llm_config["provider"] = provider

    if model:
        llm_config["model"] = model

    if temperature is not None:
        llm_config["temperature"] = temperature

    if api_key:
        llm_config["api_key"] = api_key

    if api_base:
        llm_config["api_base"] = api_base

    # 保存配置
    SkillConfigManager.set_skill_llm_config(skill_id, llm_config)

    console.print("\n[bold green]✓ Configuration saved[/bold green]")

    # 显示如何使用
    console.print(
        Panel(
            f"[bold]{skill_id}[/bold] will now use:\n\n"
            f"  [cyan]Provider:[/cyan] {provider}\n"
            f"  [cyan]Model:[/cyan] {model}\n"
            f"  [cyan]Temperature:[/cyan] {temperature}\n\n"
            f"[dim]Test it with:[/dim]\n"
            f'  [cyan]vibe route "{skill_id}"[/cyan]',
            border_style="green",
        )
    )


def delete_config(skill_id: str) -> None:
    """Delete configuration for a specific skill.

    Args:
        skill_id: Skill identifier
    """

    console.print(f"\n[bold cyan]🗑️  Delete Configuration: {skill_id}[/bold cyan]\n")

    # 确认删除
    confirm = questionary.confirm(
        f"Are you sure you want to delete the configuration for '{skill_id}'?",
        default=False,
    ).ask()

    if not confirm:
        console.print("[yellow]Cancelled[/yellow]")
        raise typer.Exit(0)

    # 删除配置
    SkillConfigManager.delete_skill_config(skill_id)

    console.print("\n[bold green]✓ Configuration deleted[/bold green]")
    console.print("[dim]The skill will use global configuration from now on[/dim]")


def import_config(
    config_file: Path = _IMPORT_CONFIG_ARGUMENT,
) -> None:
    """Import skill configurations from a file.

    The file should contain a dictionary of skill_id -> llm_config mappings.

    Example JSON:
    {
        "code-reviewer": {
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.2
        },
        "brainstorm": {
            "provider": "anthropic",
            "model": "claude-3-opus-20240229",
            "temperature": 0.9
        }
    }

    Args:
        config_file: Path to configuration file
    """

    console.print("\n[bold cyan]📥 Import Configurations[/bold cyan]\n")

    # 读取配置文件
    if not config_file.exists():
        console.print(f"[red]✗ File not found: {config_file}[/red]")
        raise typer.Exit(1)

    try:
        with config_file.open() as f:
            if config_file.suffix in [".yaml", ".yml"]:
                import yaml

                configs = yaml.safe_load(f)
            else:
                configs = json.load(f)
    except Exception as e:
        console.print(f"[red]✗ Failed to load file: {e}[/red]")
        raise typer.Exit(1) from e

    # 导入配置
    imported = 0
    failed = 0

    for skill_id, llm_config in configs.items():
        try:
            SkillConfigManager.set_skill_llm_config(skill_id, llm_config)
            imported += 1
        except Exception as e:
            console.print(f"[yellow]⚠ Failed to import {skill_id}: {e}[/yellow]")
            failed += 1

    console.print("\n[bold green]✓ Import complete[/bold green]")
    console.print(f"  [green]Imported:[/green] {imported}")
    if failed > 0:
        console.print(f"  [yellow]Failed:[/yellow] {failed}")


def export_config(
    output_file: Path = _EXPORT_CONFIG_ARGUMENT,
) -> None:
    """Export all skill configurations to a file.

    Args:
        output_file: Path to output file
    """

    console.print("\n[bold cyan]📤 Export Configurations[/bold cyan]\n")

    # 获取所有配置
    skill_configs = list_skill_configs()

    if not skill_configs:
        console.print("[yellow]⚠ No configurations to export[/yellow]")
        raise typer.Exit(0)

    # 转换为导出格式
    export_data = {}

    for skill_id, config in skill_configs.items():
        if config.requires_llm and config.llm_provider:
            export_data[skill_id] = {
                "provider": config.llm_provider,
                "model": config.llm_model,
                "temperature": config.llm_temperature,
            }

    # 保存到文件
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with output_file.open("w") as f:
            if output_file.suffix in [".yaml", ".yml"]:
                import yaml

                yaml.dump(export_data, f, default_flow_style=False)
            else:
                json.dump(export_data, f, indent=2)

        console.print(f"[bold green]✓ Exported {len(export_data)} configurations[/bold green]")
        console.print(f"  [dim]Output:[/dim] {output_file}")
    except Exception as e:
        console.print(f"[red]✗ Failed to save file: {e}[/red]")
        raise typer.Exit(1) from e
