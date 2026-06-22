"""``vibe loop`` CLI — autonomous scheduled task lifecycle + execution.

Usage:
    vibe loop create <name> --skill <id> --schedule "*/30 * * * *"
    vibe loop list [--status active|paused|failing|dead]
    vibe loop show <name>
    vibe loop delete <name> [--force]
    vibe loop pause <name>
    vibe loop resume <name>
    vibe loop tick [--name <name>]    # single polling cycle

Architecture:
    External cron / systemd timer / launchd invokes ``vibe loop tick``
    once per minute. ``tick`` loads all specs, filters out PAUSED/DEAD/
    RETIRED (scheduler stays stateless — filtering lives here), and
    calls ``execute_loop_tick`` for each spec whose CronExpr matches
    the current minute. Each tick is independent; no long-running
    process is required.

Design decisions (Phase 1-1 → 1-5 cumulative):
    - Pydantic ValidationError caught at CLI layer for create.
    - Status filtering in tick layer (CronDaemon stays stateless).
    - ``/slash-route use {skill_id}`` does NOT go through EXPLICIT
      layer (v1 limitation; documented in executor.py docstring).
    - Rich output style mirrors prompt_chain_cmd.py.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.loop.executor import execute_loop_tick
from vibesop.core.loop.models import LoopSpec, LoopState, LoopStatus
from vibesop.core.loop.scheduler import CronDaemon, CronExpr
from vibesop.core.loop.store import LoopStore

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(
    name="loop",
    help="管理自主循环任务 (Autonomous Loops)",
    no_args_is_help=True,
)


# Statuses that ``tick`` skips. RETIRED is user-archived; PAUSED is
# user-paused; DEAD has exhausted its failure budget. ACTIVE and
# FAILING are eligible for execution (FAILING means "consecutive
# failures under threshold — keep trying").
_SKIP_STATUSES: frozenset[LoopStatus] = frozenset(
    {LoopStatus.PAUSED, LoopStatus.DEAD, LoopStatus.RETIRED}
)

_STATUS_ICONS: dict[LoopStatus, str] = {
    LoopStatus.ACTIVE: "🟢",
    LoopStatus.PAUSED: "🟡",
    LoopStatus.FAILING: "🔴",
    LoopStatus.DEAD: "⚫",
    LoopStatus.RETIRED: "⚪",
}


def _target_str(spec: LoopSpec, truncate: int = 0) -> str:
    """Human-readable target string for table cells."""
    raw = spec.skill_id or spec.query or spec.workflow_id
    if truncate and len(raw) > truncate:
        return raw[: truncate - 3] + "..."
    return raw


# ──────────────────────────────────────────────────────────────────
# create
# ──────────────────────────────────────────────────────────────────


@app.command()
def create(
    name: str = typer.Argument(..., help="loop 名称（kebab-case，如 ci-watcher）"),
    skill_id: str = typer.Option("", "--skill", "-s", help="目标技能 ID"),
    query: str = typer.Option("", "--query", "-q", help="路由查询语句"),
    workflow: str = typer.Option("", "--workflow", "-w", help="工作流 ID"),
    schedule: str = typer.Option("0 0 * * *", "--schedule", help="cron 表达式（5 段）"),
    description: str = typer.Option("", "--desc", "-d", help="描述"),
    max_failures: int = typer.Option(3, "--max-failures", help="连续失败次数上限"),
) -> None:
    """创建新的定时循环任务。

    必须指定 ``--skill`` / ``--query`` / ``--workflow`` 之一作为执行目标。
    """
    if not any([skill_id, query, workflow]):
        console.print("[red]❌ 至少需要指定 --skill、--query 或 --workflow 之一[/red]")
        raise typer.Exit(1)

    try:
        spec = LoopSpec(
            name=name,
            description=description or f"Loop: {skill_id or query or workflow}",
            schedule=schedule,
            skill_id=skill_id,
            query=query,
            workflow_id=workflow,
            max_failures=max_failures,
        )
    except ValidationError as e:
        console.print("[red]❌ 参数校验失败:[/red]")
        for err in e.errors():
            loc = ".".join(str(p) for p in err.get("loc", []))
            console.print(f"  • {loc}: {err.get('msg', '')}")
        raise typer.Exit(1)

    # Pre-flight: cron must parse and produce a next-run.
    try:
        cron = CronExpr(schedule)
        next_run = cron.next_run_after()
    except (ValueError, RuntimeError) as e:
        console.print(f"[red]❌ cron 表达式无效: {e}[/red]")
        raise typer.Exit(1)

    store = LoopStore()
    if store.load_spec(name) is not None:
        console.print(
            f"[red]❌ Loop '{name}' 已存在。先删除 (vibe loop delete {name}) 或换名。[/red]"
        )
        raise typer.Exit(1)

    store.save_spec(spec)

    console.print(
        Panel(
            f"[bold green]✅ Loop Created[/bold green]\n"
            f"  [bold]Name:[/bold]        {spec.name}\n"
            f"  [bold]Schedule:[/bold]    {spec.schedule}\n"
            f"  [bold]Target:[/bold]      {_target_str(spec)}\n"
            f"  [bold]Status:[/bold]      🟢 Active\n"
            f"  [bold]Next Run:[/bold]    {next_run.strftime('%Y-%m-%d %H:%M UTC')}",
            title="VibeSOP Loop",
        )
    )
    console.print("\n[dim]外部 cron 调用 `vibe loop tick` 即可触发执行。[/dim]")


# ──────────────────────────────────────────────────────────────────
# list
# ──────────────────────────────────────────────────────────────────


@app.command("list")  # explicit name — function is `list_loops` to avoid shadowing builtin
def list_loops(
    status: str = typer.Option(
        "",
        "--status",
        "-s",
        help="按状态筛选 (active/paused/failing/dead/retired)",
    ),
) -> None:
    """列出所有 loop 任务。"""
    store = LoopStore()
    specs = store.list_specs()

    if not specs:
        console.print("[yellow]没有已创建的 loop。使用 `vibe loop create` 创建第一个。[/yellow]")
        return

    pairs: list[tuple[LoopSpec, LoopState]] = []
    for spec in specs:
        state = store.load_state(spec.name) or LoopState(spec=spec)
        if status and state.status.value != status.lower():
            continue
        pairs.append((spec, state))

    if not pairs:
        console.print(f"[yellow]没有匹配状态 '{status}' 的 loop。[/yellow]")
        return

    now = datetime.now(UTC)
    table = Table(title=f"VibeSOP Loops ({len(pairs)} shown / {len(specs)} total)")
    table.add_column("Name", style="cyan")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Target")
    table.add_column("Next Run")

    for spec, state in pairs:
        icon = _STATUS_ICONS.get(state.status, "⚪")
        next_run_str = ""
        if state.status not in _SKIP_STATUSES:
            try:
                next_run_str = (
                    CronExpr(spec.schedule).next_run_after(now).strftime("%m-%d %H:%M UTC")
                )
            except (ValueError, RuntimeError):
                next_run_str = "?"

        table.add_row(
            spec.name,
            spec.schedule,
            f"{icon} {state.status.value}",
            _target_str(spec, truncate=35),
            next_run_str,
        )

    console.print(table)


# ──────────────────────────────────────────────────────────────────
# show
# ──────────────────────────────────────────────────────────────────


@app.command()
def show(name: str = typer.Argument(..., help="loop 名称")) -> None:
    """查看 loop 详情和最近运行历史。"""
    store = LoopStore()
    spec = store.load_spec(name)
    if spec is None:
        console.print(f"[red]❌ Loop '{name}' 不存在[/red]")
        raise typer.Exit(1)

    state = store.load_state(name) or LoopState(spec=spec)
    icon = _STATUS_ICONS.get(state.status, "⚪")
    last_run = state.last_run_at.strftime("%Y-%m-%d %H:%M UTC") if state.last_run_at else "never"

    info = (
        f"[bold]Name:[/bold]           {spec.name}\n"
        f"[bold]Description:[/bold]    {spec.description}\n"
        f"[bold]Schedule:[/bold]       {spec.schedule}\n"
        f"[bold]Target:[/bold]         {_target_str(spec, truncate=60)}\n"
        f"[bold]Max Failures:[/bold]   {spec.max_failures}\n"
        f"[bold]Status:[/bold]         {icon} {state.status.value}\n"
        f"[bold]Total Runs:[/bold]     {state.total_runs}\n"
        f"[bold]Last Run:[/bold]       {last_run}\n"
    )
    if state.consecutive_failures > 0:
        info += f"[bold]Consecutive Fails:[/bold] {state.consecutive_failures}\n"

    if state.recent_runs:
        info += "\n[bold]Recent Runs:[/bold]\n"
        for r in state.recent_runs[-10:]:
            run_icon = "✅" if r.success else "❌"
            ts = r.started_at.strftime("%m-%d %H:%M")
            summary = r.output_summary[:55] or (r.error[:55] if r.error else "—")
            info += f"  {run_icon} {ts} | {summary}\n"

    console.print(Panel(info, title=f"Loop: {spec.name}"))


# ──────────────────────────────────────────────────────────────────
# delete
# ──────────────────────────────────────────────────────────────────


@app.command()
def delete(
    name: str = typer.Argument(..., help="loop 名称"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
) -> None:
    """删除 loop 任务（不可恢复，所有执行历史将被清除）。"""
    store = LoopStore()
    if store.load_spec(name) is None:
        console.print(f"[red]❌ Loop '{name}' 不存在[/red]")
        raise typer.Exit(1)

    if not force:
        confirmed = typer.confirm(
            f"确认删除 loop '{name}'？此操作不可恢复，所有执行历史将被清除。",
            default=False,
        )
        if not confirmed:
            console.print("[yellow]取消删除[/yellow]")
            raise typer.Exit(1)

    store.delete_spec(name)
    console.print(f"[green]✅ Loop '{name}' 已删除[/green]")


# ──────────────────────────────────────────────────────────────────
# pause / resume
# ──────────────────────────────────────────────────────────────────


@app.command()
def pause(name: str = typer.Argument(..., help="loop 名称")) -> None:
    """暂停 loop 执行（tick 将跳过此 loop，spec 不变）。"""
    store = LoopStore()
    spec = store.load_spec(name)
    if spec is None:
        console.print(f"[red]❌ Loop '{name}' 不存在[/red]")
        raise typer.Exit(1)

    state = store.load_state(name) or LoopState(spec=spec)
    if state.status == LoopStatus.PAUSED:
        console.print(f"[yellow]Loop '{name}' 已处于暂停状态[/yellow]")
        return

    state.status = LoopStatus.PAUSED
    store.save_state(state)
    console.print(f"[yellow]⏸️  Loop '{name}' 已暂停[/yellow]")


@app.command()
def resume(name: str = typer.Argument(..., help="loop 名称")) -> None:
    """恢复 loop 执行（重置连续失败计数）。"""
    store = LoopStore()
    spec = store.load_spec(name)
    if spec is None:
        console.print(f"[red]❌ Loop '{name}' 不存在[/red]")
        raise typer.Exit(1)

    state = store.load_state(name) or LoopState(spec=spec)
    if state.status == LoopStatus.ACTIVE:
        console.print(f"[yellow]Loop '{name}' 已处于活跃状态[/yellow]")
        return

    state.status = LoopStatus.ACTIVE
    state.consecutive_failures = 0
    store.save_state(state)
    console.print(f"[green]▶️ Loop '{name}' 已恢复[/green]")


# ──────────────────────────────────────────────────────────────────
# tick — single polling cycle (the missing execution bridge)
# ──────────────────────────────────────────────────────────────────


@app.command()
def tick(
    name: str = typer.Option(
        "",
        "--name",
        "-n",
        help="只检查指定 loop（默认检查全部）",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="只显示哪些会被触发，不实际执行",
    ),
) -> None:
    """执行一次轮询：检查所有 ACTIVE/FAILING loops 的 cron，匹配则执行。

    典型用法：外部 cron 每分钟调用 ``vibe loop tick`` 一次。
    """
    store = LoopStore()
    specs = store.list_specs()

    if not specs:
        console.print("[dim]没有 loop。使用 `vibe loop create` 创建。[/dim]")
        return

    # Filter by --name and by status (skip PAUSED/DEAD/RETIRED).
    eligible: list[LoopSpec] = []
    skipped: list[tuple[str, LoopStatus]] = []
    for spec in specs:
        if name and spec.name != name:
            continue
        state = store.load_state(spec.name) or LoopState(spec=spec)
        if state.status in _SKIP_STATUSES:
            skipped.append((spec.name, state.status))
        else:
            eligible.append(spec)

    if skipped and not eligible:
        console.print(
            f"[yellow]没有可执行的 loop — {len(skipped)} 个被跳过（PAUSED/DEAD/RETIRED）。[/yellow]"
        )
        return

    # Polling: which eligible specs match the current minute?
    daemon = CronDaemon()
    triggered = daemon.run_once(eligible)

    if not triggered:
        console.print(
            f"[dim]本轮无可触发 loop（{len(eligible)} eligible, {len(skipped)} skipped）。[/dim]"
        )
        return

    # Master kill-switch (C2): when loop.enabled is false, report what WOULD
    # trigger but do not execute (per LoopConfig docstring). Pre-fix this config
    # was dead — tick executed regardless of the switch.
    from vibesop.core.config.manager import ConfigManager

    if not ConfigManager().get_loop_config().enabled:
        console.print(
            f"[yellow]Loop execution disabled (loop.enabled=false) — "
            f"{len(triggered)} loop(s) would trigger:[/yellow]"
        )
        for spec in triggered:
            console.print(f"  • {spec.name} — {_target_str(spec, truncate=40)}")
        console.print("[dim]Set loop.enabled=true to execute.[/dim]")
        return

    # Dry-run: report and stop.
    if dry_run:
        console.print(f"[bold cyan]{len(triggered)}[/bold cyan] 个 loop 会被触发 (dry-run):")
        for spec in triggered:
            console.print(f"  • {spec.name} — {_target_str(spec, truncate=40)}")
        return

    # Execute each triggered loop. AgentRuntime is imported here (the CLI layer
    # may depend on agent) and injected into core/loop's executor, so core/loop
    # no longer imports the agent layer (Core->Agent inversion fix).
    from vibesop.agent.runtime.agent_runtime import AgentRuntime

    runtime = AgentRuntime()
    success_count = 0
    failure_count = 0
    for spec in triggered:
        console.print(f"[cyan]▶[/cyan] Ticking [bold]{spec.name}[/bold]...")
        record = execute_loop_tick(spec, runtime=runtime, store=store)
        if record.success:
            success_count += 1
            console.print(f"  [green]✅[/green] {record.matched_skill} ({record.duration_s}s)")
        else:
            failure_count += 1
            console.print(f"  [red]❌[/red] {record.error[:80]}")

    total = success_count + failure_count
    console.print(
        f"\n[bold]Tick 完成[/bold]: {total} 触发, "
        f"[green]{success_count} 成功[/green], "
        f"[red]{failure_count} 失败[/red]"
    )
    # Non-zero exit when any loop failed so external cron/launchd can detect it
    # (C3). Pre-fix tick always exited 0, masking total failure from the only
    # documented deployment (external cron every minute).
    if failure_count:
        raise typer.Exit(code=1)


__all__ = ["app"]
