#!/usr/bin/env python3
"""VibeSOP 技能自动理解演示脚本.

这个脚本演示了如何在 bash 环境（非 Agent 环境）中：
1. 读取技能的 SKILL.md
2. 自动理解技能的用途和特征
3. 生成配置（优先级、路由规则、LLM 配置）
4. 保存配置

使用方式:
    python examples/skill_understanding_demo.py
"""

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# 添加项目路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vibesop.core.skills.understander import (
    SkillAutoConfigurator,
    SkillType,
    understand_skill_from_file,
    KeywordAnalyzer,
    CategoryRules,
)
from vibesop.core.skills.base import SkillMetadata

console = Console()


def demo_understanding_skill(skill_id: str, skill_path: Path) -> None:
    """演示理解和配置单个技能"""

    console.print(f"\n{'='*60}")
    console.print(f"[bold cyan]🔍 Understanding Skill: {skill_id}[/bold cyan]")
    console.print(f"{'='*60}\n")

    # 显示原始信息
    console.print("[dim]原始信息 (Raw Info):[/dim]")
    console.print(f"  路径: {skill_path}")

    # Step 1: 关键词分析
    console.print("\n[bold]Step 1: 关键词分析[/bold]")

    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        content = skill_md.read_text()

        analysis = KeywordAnalyzer.analyze(content[:500])  # 分析前 500 字符

        console.print(f"  关键词: {', '.join(analysis.keywords)}")
        console.print(f"  需要 LLM: {'是' if analysis.requires_llm else '否'}")
        console.print(f"  复杂度: {analysis.complexity.value}")
        console.print(f"  紧急性: {analysis.urgency.value}")

    # Step 2: 自动理解和配置
    console.print("\n[bold]Step 2: 自动理解和配置[/bold]")

    try:
        config = understand_skill_from_file(skill_path)

        # 显示生成的配置
        console.print(f"\n  ✅ 理解为: {config.category}")
        console.print(f"  ✅ 优先级: {config.priority}")
        console.print(f"  ✅ 路由规则: {len(config.routing_patterns)} 条")

        if config.requires_llm:
            llm = config.llm_config
            models = llm.get("models", [])
            console.print(f"  ✅ LLM: {llm.get('provider')} / {models[0] if models else 'N/A'}")

        console.print(f"  ✅ 置信度: {config.confidence:.1%}")
        console.print(f"  ✅ 配置来源: {config.config_source}")

    except Exception as e:
        console.print(f"  ❌ 错误: {e}")
        return

    # Step 3: 显示详细配置
    console.print("\n[bold]Step 3: 生成的配置详情[/bold]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("配置项", style="cyan")
    table.add_column("值", style="green")

    table.add_row("技能 ID", config.skill_id)
    table.add_row("类别", config.category)
    table.add_row("优先级", str(config.priority))
    table.add_row("启用状态", "是" if config.enabled else "否")
    table.add_row("路由规则", "\n".join(config.routing_patterns[:3]))

    if config.requires_llm:
        llm = config.llm_config
        table.add_row("LLM 提供商", llm.get("provider", "N/A"))
        models = llm.get("models", [])
        table.add_row("LLM 模型", models[0] if models else "N/A")
        table.add_row("温度", str(llm.get("temperature", "N/A")))

    table.add_row("置信度", f"{config.confidence:.1%}")
    table.add_row("配置来源", config.config_source)

    console.print(table)

    # Step 4: 保存配置
    console.print("\n[bold]Step 4: 保存配置[/bold]")

    output_dir = Path(".vibe/skills")
    configurator = SkillAutoConfigurator()

    try:
        config_file = configurator.save_config(config, output_dir)
        console.print(f"  ✅ 配置已保存: {config_file}")

        # 显示配置文件内容
        console.print("\n[dim]配置文件内容:[/dim]")
        import yaml
        with open(config_file) as f:
            config_data = yaml.safe_load(f)

        console.print(yaml.dump(config_data, default_flow_style=False, indent=2))

    except Exception as e:
        console.print(f"  ❌ 保存失败: {e}")


def demo_rule_engine() -> None:
    """演示规则引擎"""

    console.print("\n" + "="*60)
    console.print("[bold cyan]📐 规则引擎演示[/bold cyan]")
    console.print("="*60 + "\n")

    # 演示类别规则
    console.print("[bold]类别规则示例:[/bold]\n")

    for category, rules in CategoryRules.RULES.items():
        priority_range = rules.get("priority_range", (50, 50))
        console.print(f"  {category:15} 优先级: {priority_range[0]}-{priority_range[1]}")

        llm_config = rules.get("llm", {})
        if llm_config:
            provider = llm_config.get("provider", "N/A")
            models = llm_config.get("models", [])
            model_str = models[0] if models else "N/A"
            console.print(f"    LLM: {provider} / {model_str}")
            console.print(f"    温度: {llm_config.get('temperature', 'N/A')}")

        console.print("")


def demo_keyword_analysis() -> None:
    """演示关键词分析"""

    console.print("\n" + "="*60)
    console.print("[bold cyan]🔑 关键词分析演示[/bold cyan]")
    console.print("="*60 + "\n")

    # 测试文本
    test_cases = [
        {
            "name": "调试技能",
            "text": "Systematic debugging workflow for finding and fixing bugs",
        },
        {
            "name": "代码审查",
            "text": "AI-powered code review and quality assurance",
        },
        {
            "name": "创意头脑风暴",
            "text": "Creative brainstorming and idea generation",
        },
        {
            "name": "量化交易",
            "text": "使用 Tushare API 开发量化交易策略",
        },
    ]

    for test_case in test_cases:
        console.print(f"[bold]{test_case['name']}:[/bold]")
        console.print(f"  [dim]文本:[/dim] {test_case['text']}")

        analysis = KeywordAnalyzer.analyze(test_case['text'])

        console.print(f"  关键词: {', '.join(analysis.keywords)}")
        console.print(f"  需要 LLM: {'是' if analysis.requires_llm else '否'}")
        console.print(f"  复杂度: {analysis.complexity.value}")
        console.print(f"  紧急性: {analysis.urgency.value}")
        console.print()


def main() -> None:
    """主函数"""

    console.print("\n[bold cyan]🎯 VibeSOP 技能自动理解演示[/bold cyan]")
    console.print("[dim]展示如何在 bash 环境中自动理解技能并生成配置[/dim]\n")

    # 1. 演示规则引擎
    demo_rule_engine()

    # 2. 演示关键词分析
    demo_keyword_analysis()

    # 3. 演示完整流程（如果技能存在）
    console.print("\n" + "="*60)
    console.print("[bold cyan]🔄 完整流程演示[/bold cyan]")
    console.print("="*60 + "\n")

    # 检查是否有可测试的技能
    test_skills = [
        ("systematic-debugging", Path("core/skills/systematic-debugging")),
        ("gstack/review", Path(".claude/skills/gstack/review")),
    ]

    for skill_id, skill_path in test_skills:
        if skill_path.exists():
            demo_understanding_skill(skill_id, skill_path)
            break
    else:
        console.print("[yellow]⚠️  没有找到可测试的技能文件[/yellow]")
        console.print("[dim]跳过完整流程演示[/dim]")

    console.print("\n[bold green]✨ 演示完成！[/bold green]\n")


if __name__ == "__main__":
    main()
