"""``vibe prompt-chain`` CLI — 生成多阶段 Claude Code 提示词链 + 容器验证。

子命令:
    vibe prompt-chain diagnose <feature> --files=...
    vibe prompt-chain generate <feature> --output=...
    vibe prompt-chain validate [--container=...] [--json]
    vibe prompt-chain run <feature>  # 一站式
"""

from __future__ import annotations

import logging

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.prompt_chain import (
    ContainerValidator,
    PromptChainGenerator,
)

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="prompt-chain",
    help="Generate phased Claude Code prompt chains and validate them in a Linux container.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def diagnose(
    feature: str = typer.Argument(..., help="功能名称，如 'Multi-Agent Squad'"),
    files: str = typer.Option(
        "",
        "--files",
        "-f",
        help="要诊断的文件路径，逗号分隔，如 'src/core/*.py,src/agent/*.py'",
    ),
) -> None:
    """Phase 0: 扇出诊断，输出文件清单。"""
    file_list = [f.strip() for f in files.split(",") if f.strip()]
    with console.status("[bold cyan]扫描文件..."):
        generator = PromptChainGenerator()
        report = generator.diagnose(files=file_list, feature_context=feature)

    console.print(
        Panel.fit(
            f"[bold green]诊断完成[/bold green]\n"
            f"  读取文件: {len(report.files_read)}\n"
            f"  问题域: {len(report.problem_domains)}\n"
            f"  需修改: {len(report.modified_files)} 文件\n"
            f"  需新建: {len(report.new_files)} 文件",
            title="🔍 诊断报告",
        )
    )

    if report.files_read:
        table = Table(title="文件清单", show_lines=False)
        table.add_column("#", style="dim")
        table.add_column("路径", style="cyan")
        for idx, path in enumerate(report.files_read, 1):
            table.add_row(str(idx), path)
        console.print(table)


@app.command()
def generate(
    feature: str = typer.Argument(..., help="功能名称"),
    output_dir: str = typer.Option(
        "./prompts",
        "--output",
        "-o",
        help="提示词输出目录",
    ),
) -> None:
    """Phase 1-N: 生成分阶段提示词文件。"""
    with console.status(f"[bold cyan]生成提示词链: {feature}"):
        generator = PromptChainGenerator()
        prompts = generator.generate(feature=feature, output_dir=output_dir)

    table = Table(title=f"📝 提示词链 — {feature}")
    table.add_column("阶段", style="cyan")
    table.add_column("标题", style="green")
    table.add_column("文件路径", style="yellow")

    for p in prompts:
        table.add_row(str(p.phase), p.title, str(p.output_path.name))

    console.print(table)
    console.print(
        f"\n✅ 共生成 [bold]{len(prompts)}[/bold] 个提示词文件到 [bold]{output_dir}[/bold]"
    )


@app.command()
def validate(
    container: str = typer.Option(
        "auto",
        "--container",
        "-c",
        help="容器运行时: orbstack, docker, lima, auto, local",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="以 JSON 格式输出验证报告",
    ),
) -> None:
    """Final: 在 Linux 容器（或本地）端到端验证。"""
    tool: str | None = None if container == "auto" else container
    skip = container == "local"

    with console.status("[bold cyan]执行验证流水线..."):
        validator = ContainerValidator(container_tool=tool)
        report = validator.validate(skip_container=skip)

    if json_output:
        console.print(report.to_json())
        return

    console.print(
        Panel.fit(
            f"[bold]容器运行时:[/bold] {report.environment.get('container_tool', 'N/A')}\n"
            f"[bold]Python:[/bold] {report.environment.get('python', 'N/A')}\n"
            f"[bold]耗时:[/bold] {report.duration_s:.1f}s",
            title="🐳 环境信息",
        )
    )

    result_table = Table(title="📊 验证结果")
    result_table.add_column("检查项", style="cyan")
    result_table.add_column("结果", style="green")
    for category, checks in report.results.items():
        if isinstance(checks, dict):
            for name, value in checks.items():
                if isinstance(value, bool):
                    icon = "✅" if value else "❌"
                    result_table.add_row(f"{category}.{name}", icon)
                else:
                    result_table.add_row(f"{category}.{name}", "—")
    console.print(result_table)

    if report.p0_issues:
        console.print("\n[bold red]❌ P0 问题:[/bold red]")
        for issue in report.p0_issues:
            console.print(f"  • {issue['check']}: {issue['detail']}")

    if report.p1_issues:
        console.print("\n[bold yellow]⚠️  P1 建议:[/bold yellow]")
        for issue in report.p1_issues:
            console.print(f"  • {issue['check']}: {issue['detail']}")

    console.print(f"\n[bold]{report.conclusion}[/bold]")


@app.command()
def run(
    feature: str = typer.Argument(..., help="功能名称"),
    files: str = typer.Option(
        "src/,tests/",
        "--files",
        "-f",
        help="诊断阶段的文件 glob，逗号分隔",
    ),
    output_dir: str = typer.Option(
        "./prompts",
        "--output",
        "-o",
        help="提示词输出目录",
    ),
    container: str = typer.Option(
        "auto",
        "--container",
        "-c",
        help="容器运行时",
    ),
) -> None:
    """一站式：诊断 → 生成提示词 → 容器验证。"""
    console.print(f"[bold]🚀 Prompt Chain Validator[/bold] — [green]{feature}[/green]\n")

    # Step 1: 诊断
    with console.status("[bold cyan]Step 1/3: 扇出诊断..."):
        file_list = [f.strip() for f in files.split(",") if f.strip()]
        generator = PromptChainGenerator()
        diagnosis = generator.diagnose(files=file_list, feature_context=feature)
    console.print(f"  ✅ 诊断完成（{len(diagnosis.files_read)} 个文件）\n")

    # Step 2: 生成
    with console.status("[bold cyan]Step 2/3: 生成提示词链..."):
        prompts = generator.generate(
            feature=feature,
            diagnosis=diagnosis,
            output_dir=output_dir,
        )
    console.print(f"  ✅ 生成 {len(prompts)} 个提示词文件\n")

    table = Table(show_header=True)
    table.add_column("#", style="dim")
    table.add_column("文件", style="cyan")
    for idx, p in enumerate(prompts, 1):
        table.add_row(str(idx), str(p.output_path.name))
    console.print(table)
    console.print()

    # Step 3: 验证
    with console.status("[bold cyan]Step 3/3: 容器验证..."):
        tool: str | None = None if container == "auto" else container
        validator = ContainerValidator(container_tool=tool)
        report = validator.validate(skip_container=(container == "local"))

    console.print(f"\n[bold]{report.conclusion}[/bold]")
    console.print(f"⏱  总耗时: {report.duration_s:.1f}s")


__all__ = ["app"]
