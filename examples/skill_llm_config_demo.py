#!/usr/bin/env python3
"""VibeSOP 技能 LLM 配置管理演示.

这个脚本演示了如何：
1. 为技能设置独立的 LLM 配置
2. 获取技能的 LLM 配置
3. 查看配置优先级回退
4. 批量管理配置

使用方式:
    python examples/skill_llm_config_demo.py
"""

import json

# 添加项目路径
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibesop.core.skills.config_manager import (
    SkillConfigManager,
    get_skill_llm_config,
    list_skill_configs,
    set_skill_llm_config,
)

console = Console()


def demo_set_skill_config():
    """演示设置技能 LLM 配置"""

    console.print("\n[bold cyan]📝 演示 1: 设置技能 LLM 配置[/bold cyan]\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 修改配置文件路径
        original_path = SkillConfigManager.SKILL_CONFIG_FILE
        SkillConfigManager.SKILL_CONFIG_FILE = Path(tmpdir) / "auto-config.yaml"

        try:
            # 设置不同技能的 LLM 配置
            configs = {
                "code-reviewer": {
                    "name": "代码审查",
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-4",
                        "temperature": 0.2,
                    },
                    "reason": "需要高准确性，使用 GPT-4"
                },
                "brainstorm": {
                    "name": "头脑风暴",
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-3-opus-20240229",
                        "temperature": 0.9,
                    },
                    "reason": "需要创意，使用 Claude Opus + 高温度"
                },
                "debug-helper": {
                    "name": "调试助手",
                    "llm": {
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-6",
                        "temperature": 0.3,
                    },
                    "reason": "需要准确且快速，使用 Claude Sonnet"
                },
            }

            for skill_id, config in configs.items():
                console.print(f"[bold]✓ {config['name']} ({skill_id})[/bold]")
                console.print(f"  [dim]原因:[/dim] {config['reason']}")
                console.print(f"  [dim]LLM:[/dim] {config['llm']['provider']} / {config['llm']['model']}")
                console.print(f"  [dim]温度:[/dim] {config['llm']['temperature']}")

                set_skill_llm_config(skill_id, config['llm'])
                console.print()

        finally:
            # 恢复原始路径
            SkillConfigManager.SKILL_CONFIG_FILE = original_path


def demo_get_skill_config():
    """演示获取技能 LLM 配置"""

    console.print("\n[bold cyan]🔍 演示 2: 获取技能 LLM 配置[/bold cyan]\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 修改配置文件路径
        original_path = SkillConfigManager.SKILL_CONFIG_FILE
        SkillConfigManager.SKILL_CONFIG_FILE = Path(tmpdir) / "auto-config.yaml"

        try:
            # 设置配置
            set_skill_llm_config("code-reviewer", {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.2,
            })

            # 获取配置
            llm_config = get_skill_llm_config("code-reviewer")

            if llm_config:
                console.print("[bold]✓ LLM 配置:[/bold]")
                console.print(f"  [dim]提供商:[/dim] {llm_config.provider}")
                console.print(f"  [dim]模型:[/dim] {llm_config.model}")
                console.print(f"  [dim]温度:[/dim] {llm_config.temperature}")
                console.print(f"  [dim]配置来源:[/dim] {llm_config.source.value}")
                console.print(f"  [dim]置信度:[/dim] {llm_config.confidence:.1%}")
            else:
                console.print("[yellow]⚠ 未找到 LLM 配置[/yellow]")

        finally:
            # 恢复原始路径
            SkillConfigManager.SKILL_CONFIG_FILE = original_path


def demo_list_configs():
    """演示列出所有技能配置"""

    console.print("\n[bold cyan]📋 演示 3: 列出所有技能配置[/bold cyan]\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 修改配置文件路径
        original_path = SkillConfigManager.SKILL_CONFIG_FILE
        SkillConfigManager.SKILL_CONFIG_FILE = Path(tmpdir) / "auto-config.yaml"

        try:
            # 设置多个技能的配置
            configs = {
                "code-reviewer": {"provider": "openai", "model": "gpt-4", "temperature": 0.2},
                "brainstorm": {"provider": "anthropic", "model": "claude-3-opus-20240229", "temperature": 0.9},
                "debug-helper": {"provider": "anthropic", "model": "claude-sonnet-4-6", "temperature": 0.3},
            }

            for skill_id, llm_config in configs.items():
                set_skill_llm_config(skill_id, llm_config)

            # 列出所有配置
            all_configs = list_skill_configs()

            # 创建表格
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("技能 ID", style="cyan")
            table.add_column("已启用", style="green")
            table.add_column("优先级", style="yellow")
            table.add_column("类别", style="blue")
            table.add_column("LLM", style="red")

            for skill_id, config in sorted(all_configs.items()):
                llm_info = "No"
                if config.requires_llm:
                    provider = config.llm_provider or "N/A"
                    model = config.llm_model or "N/A"
                    llm_info = f"{provider}/{model}"

                table.add_row(
                    skill_id,
                    "✓" if config.enabled else "✗",
                    str(config.priority),
                    config.category,
                    llm_info,
                )

            console.print(table)

        finally:
            # 恢复原始路径
            SkillConfigManager.SKILL_CONFIG_FILE = original_path


def demo_priority_fallback():
    """演示配置优先级回退"""

    console.print("\n[bold cyan]🔄 演示 4: 配置优先级回退[/bold cyan]\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 修改配置文件路径
        original_path = SkillConfigManager.SKILL_CONFIG_FILE
        SkillConfigManager.SKILL_CONFIG_FILE = Path(tmpdir) / "auto-config.yaml"

        try:
            skill_id = "my-skill"

            # 1. 技能级别配置
            console.print("[bold]步骤 1: 设置技能级别配置[/bold]")
            set_skill_llm_config(skill_id, {
                "provider": "openai",
                "model": "gpt-4",
            })

            llm_config = get_skill_llm_config(skill_id)
            if llm_config:
                console.print(f"  ✓ 使用技能配置: {llm_config.provider}/{llm_config.model}")
                console.print(f"    来源: {llm_config.source.value}")

            # 2. 删除技能配置
            console.print("\n[bold]步骤 2: 删除技能配置[/bold]")
            SkillConfigManager.delete_skill_config(skill_id)

            llm_config = get_skill_llm_config(skill_id)
            if llm_config:
                console.print(f"  ✓ 回退到: {llm_config.provider}/{llm_config.model}")
                console.print(f"    来源: {llm_config.source.value}")
            else:
                console.print("  ⚠ 未找到配置（使用默认值）")

            console.print("\n[dim]优先级顺序:[/dim]")
            console.print("  [dim]1. 技能配置 → 2. 全局配置 → 3. 环境变量 → 4. Agent → 5. 默认值[/dim]")

        finally:
            # 恢复原始路径
            SkillConfigManager.SKILL_CONFIG_FILE = original_path


def demo_batch_import_export():
    """演示批量导入/导出配置"""

    console.print("\n[bold cyan]📦 演示 5: 批量导入/导出配置[/bold cyan]\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 修改配置文件路径
        original_path = SkillConfigManager.SKILL_CONFIG_FILE
        SkillConfigManager.SKILL_CONFIG_FILE = Path(tmpdir) / "auto-config.yaml"

        try:
            # 1. 创建批量配置文件
            console.print("[bold]步骤 1: 创建批量配置文件[/bold]")

            batch_config = {
                "code-reviewer": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.2,
                },
                "brainstorm": {
                    "provider": "anthropic",
                    "model": "claude-3-opus-20240229",
                    "temperature": 0.9,
                },
            }

            config_file = Path(tmpdir) / "batch-config.json"
            with config_file.open("w") as f:
                json.dump(batch_config, f, indent=2)

            console.print(f"  ✓ 创建配置文件: {config_file.name}")
            console.print(f"  [dim]包含 {len(batch_config)} 个技能配置[/dim]")

            # 2. 导入配置
            console.print("\n[bold]步骤 2: 导入配置[/bold]")

            for skill_id, llm_config in batch_config.items():
                set_skill_llm_config(skill_id, llm_config)
                console.print(f"  ✓ {skill_id}: {llm_config['provider']}/{llm_config['model']}")

            # 3. 导出配置
            console.print("\n[bold]步骤 3: 导出配置[/bold]")

            all_configs = list_skill_configs()
            export_data = {}

            for skill_id, config in all_configs.items():
                if config.requires_llm and config.llm_provider:
                    export_data[skill_id] = {
                        "provider": config.llm_provider,
                        "model": config.llm_model,
                        "temperature": config.llm_temperature,
                    }

            export_file = Path(tmpdir) / "exported-config.json"
            with export_file.open("w") as f:
                json.dump(export_data, f, indent=2)

            console.print(f"  ✓ 导出 {len(export_data)} 个配置到: {export_file.name}")

        finally:
            # 恢复原始路径
            SkillConfigManager.SKILL_CONFIG_FILE = original_path


def main():
    """主函数"""

    console.print("\n[bold cyan]🎯 VibeSOP 技能 LLM 配置管理演示[/bold cyan]")
    console.print("[dim]展示如何为技能配置独立的 LLM 设置[/dim]\n")

    # 演示 1: 设置配置
    demo_set_skill_config()

    # 演示 2: 获取配置
    demo_get_skill_config()

    # 演示 3: 列出配置
    demo_list_configs()

    # 演示 4: 优先级回退
    demo_priority_fallback()

    # 演示 5: 批量导入/导出
    demo_batch_import_export()

    # 总结
    console.print("\n" + "=" * 70)
    console.print("[bold green]✨ 演示完成！[/bold green]")
    console.print("=" * 70)

    console.print(
        Panel(
            "[bold]核心功能:[/bold]\n\n"
            "• [cyan]为每个技能配置独立的 LLM[/cyan]\n"
            "• [cyan]智能配置优先级回退[/cyan]\n"
            "• [cyan]批量导入/导出配置[/cyan]\n"
            "• [cyan]完整的 Python API[/cyan]\n\n"
            "[dim]使用 'vibe skill config --help' 查看所有命令[/dim]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
