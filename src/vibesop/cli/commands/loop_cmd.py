"""``vibe loop`` CLI — autonomous scheduled task lifecycle + execution.

Usage:
    vibe loop create <name> --skill <id> --schedule "*/30 * * * *" [--global]
    vibe loop list [--status active|paused|failing|dead] [--all]
    vibe loop show <name>
    vibe loop delete <name> [--force]
    vibe loop pause <name>
    vibe loop resume <name>
    vibe loop adopt <name>              # pin ownership to cwd
    vibe loop migrate-ownership [--dry-run] [--yes]
    vibe loop tick [--name <name>] [--all]    # single polling cycle

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
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vibesop.core.loop.executor import execute_loop_tick
from vibesop.core.loop.models import LoopSpec, LoopState, LoopStatus, validate_transition
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


def _owns(spec: LoopSpec, cwd: Path) -> bool:
    """Return True iff ``spec`` is owned by (visible/runnable from) ``cwd``.

    Ownership rule (gate26): an unscoped spec (``project_root is None`` —
    legacy or deliberate ``--global``) is owned everywhere; a pinned spec is
    owned when ``cwd`` is inside its ``project_root``. Both sides are
    ``resolve()``-ed, which normalises symlinks (e.g. macOS ``/tmp`` →
    ``/private/tmp``). We deliberately do NOT casefold: on a case-insensitive
    APFS volume, ``/Repo`` and ``/repo`` spellings of the same directory are
    treated as different roots — an accepted edge (gate26 design §6).

    The check is deliberately ONE-DIRECTIONAL: cwd ⊆ project_root counts,
    project_root ⊂ cwd does NOT — running from a parent directory must not
    claim every project beneath it.
    """
    if spec.project_root is None:
        return True
    try:
        return cwd.resolve().is_relative_to(Path(spec.project_root).resolve())
    except OSError:
        # Unresolvable path (dangling symlink etc.) — treat as not owned
        # rather than executing against an unverifiable root.
        return False


def _target_str(spec: LoopSpec, truncate: int = 0) -> str:
    """Human-readable target string for table cells."""
    raw = (
        spec.skill_id
        or spec.query
        or spec.workflow_id
        or " ".join(spec.command_args)
        or "(no target)"
    )
    if truncate and len(raw) > truncate:
        return raw[: truncate - 3] + "..."
    return raw


def _acquire_tick_lock(store: LoopStore, name: str, *, blocking: bool = False) -> Any:
    """Acquire a per-loop advisory lock so overlapping ``vibe loop tick``
    processes (or a state-mutating command concurrent with a tick) don't race
    on ``state.json`` (load→mutate/save is a TOCTOU across processes; the
    atomic write only protects a single process).

    - ``blocking=False`` (default, used by ``tick``): skip (return ``None``)
      if another process holds the lock — overlapping ticks are redundant.
    - ``blocking=True`` (used by pause/resume/reset): wait for the lock so the
      state mutation completes after any in-progress tick.

    Returns the open lock-file handle (close it to release), or ``None`` if a
    non-blocking acquire found the lock held. Uses ``fcntl.flock`` on POSIX;
    on Windows falls back to atomic file creation (``O_CREAT | O_EXCL``) for
    cross-process mutual exclusion.
    """
    try:
        import fcntl
    except ImportError:
        # Windows: use atomic file creation as advisory lock
        lock_path = store.base_dir / name / ".tick.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if blocking:
            import time

            # Retry loop: spin-wait until the lock holder releases it.
            for _ in range(20):  # ~10 s timeout
                try:
                    lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    break
                except FileExistsError:
                    time.sleep(0.5)
            else:
                raise RuntimeError(f"Timed out waiting for tick lock: {lock_path}")
        else:
            try:
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except FileExistsError:
                return None
        lock_handle = os.fdopen(lock_fd, "w")
        # On Windows the lock file persists after close; unlink on release
        # so the next blocking acquire doesn't time out on a stale file.
        lock_handle._vibe_lock_path = lock_path  # type: ignore[attr-defined]
        return lock_handle
    lock_path = store.base_dir / name / ".tick.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = lock_path.open("w", encoding="utf-8")
    try:
        flag = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        fcntl.flock(lock_fd.fileno(), flag)
    except (BlockingIOError, OSError):
        lock_fd.close()
        return None
    return lock_fd


def _release_tick_lock(lock_handle: Any) -> None:
    """Release an advisory tick lock and clean up the lock file on Windows."""
    if lock_handle is None:
        return
    if hasattr(lock_handle, "close"):
        lock_handle.close()
    # On Windows (no fcntl), the lock file must be unlinked explicitly.
    lock_path = getattr(lock_handle, "_vibe_lock_path", None)
    if lock_path is not None:
        import contextlib

        with contextlib.suppress(OSError):
            lock_path.unlink()


# ──────────────────────────────────────────────────────────────────
# create
# ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _LoopPreset:
    """Resolved values for a ``--preset`` shortcut.

    Each preset fixes the ``command`` (the string the user would have passed
    to ``--command``) and the ``schedule`` (cron). The CLI's ``create``
    flow then runs through the normal validation path — preset is purely a
    "fill in the blanks" step, not a bypass.
    """

    command: str
    schedule: str
    description: str


# Three scheduled loops that close the instinct learning cycle.
# Times are staggered so the writer lock on instincts.jsonl doesn't
# contend: promote runs first (04:17), feedback 20 min later (04:37),
# assemble runs every 15 min but only reads sequences.jsonl (no lock
# contention with the other two).
_LOOP_PRESETS: dict[str, _LoopPreset] = {
    "instinct-assemble": _LoopPreset(
        command="sequence assemble",
        schedule="*/15 * * * *",
        description="Fold captured tool-call events into sequence-pattern candidates (every 15min).",
    ),
    "instinct-promote": _LoopPreset(
        command="instinct auto-promote --min-confidence 0.85",
        schedule="17 4 * * *",
        description="Promote high-confidence sequence candidates to persistent instincts (daily 04:17).",
    ),
    "instinct-feedback": _LoopPreset(
        command="instinct feedback-collect",
        schedule="37 4 * * *",
        description="Decay/boost instincts based on miss-counter signal (daily 04:37, 20min after promote).",
    ),
}


def _resolve_preset(preset: str) -> _LoopPreset:
    """Look up preset by name; friendly error if unknown.

    The error message distinguishes two cases:
    - The name IS a known preset but misspelled (e.g. ``instinct-asembled``)
      → list the valid options.
    - The name does NOT look like any preset (e.g. ``my-custom-loop``) →
      the user probably passed ``--preset`` by mistake; suggest removing
      it so they fall back to the normal ``--command`` / ``--skill`` path.
    """
    if preset not in _LOOP_PRESETS:
        available = ", ".join(sorted(_LOOP_PRESETS))
        if "instinct-" in preset or preset.endswith(("-assemble", "-promote", "-feedback")):
            # Looks like a typo of a known preset name.
            console.print(f"[red]❌ 未知 preset '{preset}'。可选：{available}[/red]")
        else:
            # Doesn't look like any preset — user probably meant --command.
            console.print(
                f"[red]❌ '{preset}' 不是预设名。请去掉 --preset 改用 --command，"
                f"或换成预设名之一：{available}[/red]"
            )
        raise typer.Exit(1)
    return _LOOP_PRESETS[preset]


@app.command()
def create(
    name: str = typer.Argument(..., help="loop 名称（kebab-case，如 ci-watcher）"),
    skill_id: str = typer.Option("", "--skill", "-s", help="目标技能 ID"),
    query: str = typer.Option("", "--query", "-q", help="路由查询语句"),
    workflow: str = typer.Option("", "--workflow", "-w", help="工作流 ID"),
    command: str = typer.Option(
        "",
        "--command",
        "-c",
        help="vibe 子命令（shlex 解析，如 'instinct auto-promote --min-confidence 0.85'）",
    ),
    preset: bool = typer.Option(
        False,
        "--preset",
        "-p",
        help=(
            "用 name 参数作为 preset key 加载预定义模板（instinct-assemble / instinct-promote / instinct-feedback），"
            "自动填入 --command 和 --schedule"
        ),
    ),
    schedule: str = typer.Option("0 0 * * *", "--schedule", help="cron 表达式（5 段）"),
    description: str = typer.Option("", "--desc", "-d", help="描述"),
    max_failures: int = typer.Option(3, "--max-failures", help="连续失败次数上限"),
    global_: bool = typer.Option(
        False,
        "--global",
        help="不钉项目归属（全局 loop：任意 cwd 下 list/tick 可见可执行）。默认钉到当前目录。",
    ),
) -> None:
    """创建新的定时循环任务。

    必须指定 ``--skill`` / ``--query`` / ``--workflow`` / ``--command`` 之一作为执行目标，
    或用 ``--preset`` 加载预定义模板（会同时设定 --command 和 --schedule）。

    项目归属（gate26）：默认把当前目录钉为 ``project_root``——裸 ``tick`` 只执行
    归属本项目的 loop，executor 也在归属根下执行。``--global`` 显式放弃归属
    （与旧版无字段 spec 同义：任意 cwd 可见可执行）。
    """
    # --preset 是一个 shortcut：根据 name 填充 --command + --schedule。
    # 设计为"先填充、再走主路径"——所有后续校验（4-way xor、cron parse）
    # 对 preset 与手填 command 一视同仁，避免出现"preset 绕过校验"的暗坑。
    if preset:
        resolved = _resolve_preset(name)
        if command:
            console.print(
                f"[yellow]⚠️  --preset 已为 '{name}' 提供默认 command，"
                f"忽略 --command '{command}'[/yellow]"
            )
        if schedule != "0 0 * * *":
            console.print(
                f"[yellow]⚠️  --preset 已为 '{name}' 提供默认 schedule，"
                f"忽略 --schedule '{schedule}'[/yellow]"
            )
        command = resolved.command
        schedule = resolved.schedule
        if not description:
            description = resolved.description

    # Parse --command via shlex so users can pass quoted args (e.g. paths
    # with spaces) without worrying about shell expansion. shlex.split raises
    # ValueError on mismatched quotes — surface as a friendly CLI error
    # rather than a traceback (mirrors Phase C FLAW #4 fix in install-launchd).
    try:
        command_args = shlex.split(command) if command else []
    except ValueError as e:
        console.print(f"[red]❌ --command 解析失败: {e}[/red]")
        raise typer.Exit(1) from e

    if not any([skill_id, query, workflow, command_args]):
        console.print("[red]❌ 至少需要指定 --skill、--query、--workflow 或 --command 之一[/red]")
        raise typer.Exit(1)

    # Ownership pinning (gate26): default pins Path.cwd(). Note Path.cwd()
    # returns the physical getcwd() path (symlinks already resolved by the
    # OS), so what gets pinned is the real directory the user is standing in.
    # Untrusted cwd (no .git/ or pyproject.toml) warns but does NOT refuse —
    # create only writes JSON, and --global is the documented escape hatch.
    project_root: str | None = None
    if not global_:
        cwd = Path.cwd()
        if not _is_project_root_trusted(cwd):
            console.print(
                f"[yellow]⚠️  cwd {cwd} 既非 git repo (无 .git/) 也无 pyproject.toml。"
                f" loop 仍将钉到这个目录；若想创建全局 loop 请加 --global。[/yellow]"
            )
        project_root = str(cwd)

    try:
        spec = LoopSpec(
            name=name,
            description=description or f"Loop: {skill_id or query or workflow or command}",
            schedule=schedule,
            skill_id=skill_id,
            query=query,
            workflow_id=workflow,
            command_args=command_args,
            max_failures=max_failures,
            project_root=project_root,
        )
    except ValidationError as e:
        console.print("[red]❌ 参数校验失败:[/red]")
        for err in e.errors():
            loc = ".".join(str(p) for p in err.get("loc", []))
            console.print(f"  • {loc}: {err.get('msg', '')}")
        raise typer.Exit(1) from e

    # Pre-flight: cron must parse and produce a next-run.
    try:
        cron = CronExpr(schedule)
        next_run = cron.next_run_after()
    except (ValueError, RuntimeError) as e:
        console.print(f"[red]❌ cron 表达式无效: {e}[/red]")
        raise typer.Exit(1) from e

    store = LoopStore()
    existing = store.load_spec(name)
    if existing is not None:
        # Name the conflicting loop's project so cross-project collisions
        # (HOME-level store, globally-unique names) are debuggable (gate26).
        console.print(
            f"[red]❌ Loop '{name}' 已存在（归属项目: "
            f"{existing.project_root or '(global)'}）。"
            f"先删除 (vibe loop delete {name}) 或换名。[/red]"
        )
        raise typer.Exit(1)

    store.save_spec(spec)

    console.print(
        Panel(
            f"[bold green]✅ Loop Created[/bold green]\n"
            f"  [bold]Name:[/bold]        {spec.name}\n"
            f"  [bold]Project:[/bold]     {spec.project_root or '(global)'}\n"
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
    all_: bool = typer.Option(
        False,
        "--all",
        help="列出全部 loop（含归属其他项目的），并显示 Project 列。默认只列归属当前项目的。",
    ),
) -> None:
    """列出 loop 任务（默认只列归属当前项目的；``--all`` 列全部）。"""
    store = LoopStore()
    specs = store.list_specs()

    if not specs:
        console.print("[yellow]没有已创建的 loop。使用 `vibe loop create` 创建第一个。[/yellow]")
        return

    cwd = Path.cwd()
    hidden = 0
    pairs: list[tuple[LoopSpec, LoopState]] = []
    for spec in specs:
        if not all_ and not _owns(spec, cwd):
            hidden += 1
            continue
        state = store.load_state(spec.name) or LoopState(spec=spec)
        if status and state.status.value != status.lower():
            continue
        pairs.append((spec, state))

    if not pairs:
        # gate27 claude#7: when ownership filtering hid every non-matching
        # loop, name that as the real cause — "没有匹配状态" alone would send
        # the user chasing a status filter that isn't why their loop is
        # invisible.
        if status:
            msg = f"没有匹配状态 '{status}' 的 loop"
            if hidden:
                msg += (
                    f"（另有 {hidden} 个归属其他项目的 loop 未参与本轮筛选"
                    f"——`vibe loop list --all` 查看全部）"
                )
            console.print(f"[yellow]{msg}。[/yellow]")
        else:
            console.print("[yellow]当前项目没有归属的 loop（--all 查看全部）。[/yellow]")
        return

    now = datetime.now(UTC)
    table = Table(title=f"VibeSOP Loops ({len(pairs)} shown / {len(specs)} total)")
    table.add_column("Name", style="cyan")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Target")
    if all_:
        table.add_column("Project")
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

        row = [
            spec.name,
            spec.schedule,
            f"{icon} {state.status.value}",
            _target_str(spec, truncate=35),
        ]
        if all_:
            row.append(spec.project_root or "(global)")
        row.append(next_run_str)
        table.add_row(*row)

    console.print(table)
    if hidden:
        console.print(
            f"[dim]{hidden} 个归属其他项目的 loop 已隐藏 —— `vibe loop list --all` 查看全部。[/dim]"
        )


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
        f"[bold]Project:[/bold]        {spec.project_root or '(global)'}\n"
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

    # Phase C (pi plan v2 新增 + 对抗 review FLAW #5): if a launchd plist
    # exists, best-effort bootout and delete it too — otherwise the orphaned
    # plist keeps firing tick on a spec that no longer exists, producing noise
    # in the log every minute. If bootout fails for a real reason (not "could
    # not find"), do NOT unlink the plist — keep it as a recovery artifact so
    # the user can re-run uninstall-launchd. Warn loudly that the launchd
    # label may still be active even though the spec is gone.
    plist_cleanup_failed = False
    if _is_macos():
        from vibesop.core.loop.launchd import default_plist_path

        plist_path = default_plist_path(name)
        if plist_path.exists():
            console.print("[dim]检测到 launchd plist，先注销…[/dim]")
            bootout_ok = _bootout_launchd(name, console=console, missing_ok=True)
            if bootout_ok:
                try:
                    plist_path.unlink()
                except OSError as e:
                    logger.warning("Failed to remove plist %s: %s", plist_path, e)
            else:
                plist_cleanup_failed = True
                console.print(
                    f"[yellow]⚠️  bootout 失败 — 保留 plist {plist_path}[/yellow]\n"
                    f"[yellow]   launchd label 可能仍活跃，请手工运行 "
                    f"'vibe loop uninstall-launchd {name}'[/yellow]"
                )

    store.delete_spec(name)
    if plist_cleanup_failed:
        console.print(
            f"[green]✅ Loop '{name}' 已删除[/green] [yellow](但 launchd 清理未完成，见上)[/yellow]"
        )
    else:
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

    # Hold the per-loop lock across load→mutate→save so a concurrent tick
    # can't overwrite this transition (kimi HIGH: was lock-free).
    tick_lock = _acquire_tick_lock(store, name, blocking=True)
    try:
        state = store.load_state(name) or LoopState(spec=spec)
        if state.status == LoopStatus.PAUSED:
            console.print(f"[yellow]Loop '{name}' 已处于暂停状态[/yellow]")
            return

        if not validate_transition(state.status, LoopStatus.PAUSED):
            console.print(
                f"[red]❌ 无法从 {state.status.value} 暂停 —— 仅 ACTIVE/FAILING 可暂停，"
                f"DEAD/RETIRED 需先 reset 或为终态。[/red]"
            )
            raise typer.Exit(1)

        state.status = LoopStatus.PAUSED
        store.save_state(state)
    finally:
        _release_tick_lock(tick_lock)
    console.print(f"[yellow]⏸️  Loop '{name}' 已暂停[/yellow]")


@app.command()
def resume(name: str = typer.Argument(..., help="loop 名称")) -> None:
    """恢复 loop 执行（重置连续失败计数）。"""
    store = LoopStore()
    spec = store.load_spec(name)
    if spec is None:
        console.print(f"[red]❌ Loop '{name}' 不存在[/red]")
        raise typer.Exit(1)

    # Hold the per-loop lock across load→mutate→save (kimi HIGH).
    tick_lock = _acquire_tick_lock(store, name, blocking=True)
    try:
        state = store.load_state(name) or LoopState(spec=spec)
        if state.status == LoopStatus.ACTIVE:
            console.print(f"[yellow]Loop '{name}' 已处于活跃状态[/yellow]")
            return

        if state.status == LoopStatus.DEAD:
            console.print(
                f"[yellow]Loop '{name}' 处于 DEAD 状态。使用 "
                f"[bold]vibe loop reset {name}[/bold] 清除失败计数并重新激活。[/yellow]"
            )
            raise typer.Exit(1)

        if not validate_transition(state.status, LoopStatus.ACTIVE):
            console.print(
                f"[red]❌ 无法从 {state.status.value} 恢复 —— "
                f"{state.status.value} 为终态，resume 仅用于 PAUSED/FAILING。[/red]"
            )
            raise typer.Exit(1)

        state.status = LoopStatus.ACTIVE
        state.consecutive_failures = 0
        store.save_state(state)
    finally:
        _release_tick_lock(tick_lock)
    console.print(f"[green]▶️ Loop '{name}' 已恢复[/green]")


@app.command()
def reset(name: str = typer.Argument(..., help="loop 名称")) -> None:
    """重置 DEAD loop 回 ACTIVE（清除连续失败计数）。

    DEAD 是终态，普通 ``resume`` 不会复活它；``reset`` 是唯一的恢复路径。
    """
    store = LoopStore()
    spec = store.load_spec(name)
    if spec is None:
        console.print(f"[red]❌ Loop '{name}' 不存在[/red]")
        raise typer.Exit(1)

    # Hold the per-loop lock across load→mutate→save (kimi HIGH).
    tick_lock = _acquire_tick_lock(store, name, blocking=True)
    try:
        state = store.load_state(name) or LoopState(spec=spec)
        if state.status != LoopStatus.DEAD:
            console.print(
                f"[yellow]Loop '{name}' 当前状态为 {state.status.value}，非 DEAD。"
                f"reset 仅用于 DEAD loop。[/yellow]"
            )
            raise typer.Exit(1)

        state.status = LoopStatus.ACTIVE
        state.consecutive_failures = 0
        store.save_state(state)
    finally:
        _release_tick_lock(tick_lock)
    console.print(f"[green]♻️ Loop '{name}' 已重置为 ACTIVE（连续失败计数已清零）[/green]")


# ──────────────────────────────────────────────────────────────────
# adopt / migrate-ownership (gate26: explicit ownership pinning)
# ──────────────────────────────────────────────────────────────────


@app.command()
def adopt(name: str = typer.Argument(..., help="loop 名称")) -> None:
    """把 loop 的项目归属钉到当前目录（cwd）。

    归属只由显式动作钉住（gate26）：``create`` 默认钉 cwd、``adopt`` 钉 cwd、
    ``migrate-ownership`` 从 launchd plist 回填。裸 ``tick`` 永不做首次写入
    式归属推断（谁先跑归谁是更坏的误归属）。
    """
    store = LoopStore()
    spec = store.load_spec(name)
    if spec is None:
        console.print(f"[red]❌ Loop '{name}' 不存在[/red]")
        raise typer.Exit(1)

    cwd = Path.cwd()
    # Reuse the install-launchd trust signal: warn on untrusted cwd but allow
    # (adopt only writes JSON; the user may legitimately pin a non-git dir).
    if not _is_project_root_trusted(cwd):
        console.print(
            f"[yellow]⚠️  cwd {cwd} 既非 git repo (无 .git/) 也无 pyproject.toml。"
            f" 仍将把 '{name}' 钉到这个目录——确认这是你想要的项目根。[/yellow]"
        )

    spec.project_root = str(cwd)
    # Hold the per-loop lock across spec+state writes so a concurrent tick
    # can't persist a stale state.json that embeds the OLD spec copy.
    tick_lock = _acquire_tick_lock(store, name, blocking=True)
    try:
        store.save_spec(spec)
        state = store.load_state(name)
        if state is not None:
            state.spec = spec
            store.save_state(state)
    finally:
        _release_tick_lock(tick_lock)
    console.print(f"[green]📌 Loop '{name}' 已钉到项目: {cwd}[/green]")


@app.command("migrate-ownership")
def migrate_ownership(
    dry_run: bool = typer.Option(False, "--dry-run", help="只报告将回填的归属，不写盘"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过逐条确认（默认每条回填前询问）"),
) -> None:
    """从 launchd plist 的 WorkingDirectory 回填存量 loop 的项目归属（仅 macOS）。

    读取 ``~/Library/LaunchAgents/com.vibesop.loop.*.plist`` 的
    ``WorkingDirectory`` 并写回对应 spec 的 ``project_root``（同时同步
    state.json 内嵌的 spec 副本）。注意：这也会把 ``--global`` 创建的 loop
    钉到 plist 记录的目录——全局 loop 请先卸载 plist 或用 ``--dry-run`` 检查。
    没有 plist 的 loop 会被列出并提示用 ``vibe loop adopt <name>`` 手工钉住。
    """
    store = LoopStore()
    specs = store.list_specs()

    if not specs:
        console.print("[yellow]没有 loop。[/yellow]")
        return

    from vibesop.core.loop.launchd import default_plist_path

    backfilled: list[str] = []
    no_plist: list[str] = []
    skipped_set: list[str] = []

    for spec in specs:
        if spec.project_root is not None:
            skipped_set.append(spec.name)
            continue
        plist_path = default_plist_path(spec.name)
        working_dir: str | None = None
        if _is_macos() and plist_path.exists():
            import plistlib

            try:
                with plist_path.open("rb") as f:
                    data = plistlib.load(f)
                wd = data.get("WorkingDirectory")
                if isinstance(wd, str) and wd:
                    working_dir = wd
            except (OSError, ValueError) as e:
                console.print(f"[yellow]⚠️  {spec.name}: plist 解析失败 ({e})，跳过[/yellow]")
                continue

        if working_dir is None:
            no_plist.append(spec.name)
            continue

        if dry_run:
            console.print(f"[cyan]DRY RUN[/cyan] {spec.name}: 将钉到 {working_dir}")
            backfilled.append(spec.name)
            continue

        if not yes and not typer.confirm(
            f"把 loop '{spec.name}' 钉到 {working_dir}（来自 plist）？", default=True
        ):
            console.print(f"[dim]跳过 {spec.name}[/dim]")
            continue

        spec.project_root = working_dir
        tick_lock = _acquire_tick_lock(store, spec.name, blocking=True)
        try:
            store.save_spec(spec)
            state = store.load_state(spec.name)
            if state is not None:
                state.spec = spec
                store.save_state(state)
        finally:
            _release_tick_lock(tick_lock)
        backfilled.append(spec.name)
        console.print(f"[green]📌 {spec.name} → {working_dir}[/green]")

    if no_plist:
        console.print(
            f"[yellow]{len(no_plist)} 个 loop 没有 launchd plist，无法自动回填"
            f"（{'非 macOS 或' if not _is_macos() else ''}从未 install-launchd）。[/yellow]"
        )
        for n in no_plist:
            console.print(f"  • {n} —— 到项目根目录运行 `vibe loop adopt {n}`")

    verb = "将回填" if dry_run else "已回填"
    console.print(
        f"[bold]migrate-ownership 完成[/bold]: {verb} {len(backfilled)}，"
        f"无 plist {len(no_plist)}，已有归属跳过 {len(skipped_set)}"
    )


# ──────────────────────────────────────────────────────────────────
# tick — single polling cycle (the missing execution bridge)
# ──────────────────────────────────────────────────────────────────


@app.command()
def tick(
    name: str = typer.Option(
        "",
        "--name",
        "-n",
        help="只检查指定 loop（默认检查归属当前项目的全部 loop）",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="只显示哪些会被触发，不实际执行",
    ),
    all_: bool = typer.Option(
        False,
        "--all",
        help=(
            "兼容口：跳过归属过滤，枚举全部 loop（含归属其他项目的）。"
            "供从 HOME 运行裸 tick 的系统 cron 用户保留旧行为。"
        ),
    ),
) -> None:
    """执行一次轮询：检查归属当前项目的 ACTIVE/FAILING loops 的 cron，匹配则执行。

    典型用法：外部 cron 每分钟调用 ``vibe loop tick`` 一次。

    归属语义（gate26）：裸 tick 只枚举归属当前项目的 loop（``--all`` 跳过过滤）；
    ``--name`` 是 launchd 调用形状，绕过归属过滤不变。
    """
    store = LoopStore()
    specs = store.list_specs()

    if not specs:
        console.print("[dim]没有 loop。使用 `vibe loop create` 创建。[/dim]")
        return

    # Ownership filter (gate26): a bare tick only enumerates loops owned by
    # the current project. --name bypasses it (that is the launchd call
    # shape); --all is the compat hatch. The skip line is printed BEFORE any
    # early return below so the zero-trigger / zero-eligible branches are
    # just as loud (review nit: silent skipping was the original bug's
    # twin — invisible mis-execution).
    cwd = Path.cwd()
    ownership_skipped: list[str] = []
    candidates: list[LoopSpec] = []
    for spec in specs:
        if name:
            if spec.name != name:
                continue
        elif not all_ and not _owns(spec, cwd):
            ownership_skipped.append(spec.name)
            continue
        candidates.append(spec)

    if ownership_skipped:
        shown = ", ".join(ownership_skipped[:5])
        suffix = f" 等共 {len(ownership_skipped)} 个" if len(ownership_skipped) > 5 else ""
        console.print(
            f"[yellow]⏭️  {len(ownership_skipped)} 个 loop 归属其他项目，已跳过"
            f"（{shown}{suffix}）—— 需执行请用 `vibe loop tick --all`。[/yellow]"
        )

    # Filter by status (skip PAUSED/DEAD/RETIRED).
    eligible: list[LoopSpec] = []
    skipped: list[tuple[str, LoopStatus]] = []
    for spec in candidates:
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
        # gate27 pi#5: distinguish "no owned loops at all" from "owned loops
        # exist but none are due this minute" — the old "(0 eligible,
        # 0 skipped)" read identically for both and masked the ownership
        # filter as the cause.
        if not eligible and ownership_skipped:
            console.print(
                f"[dim]本轮无归属当前项目的 loop 可执行"
                f"（{len(ownership_skipped)} 个归属其他项目，见上方跳过行）"
                f"—— `vibe loop tick --all` 可包含它们。[/dim]"
            )
        else:
            console.print(
                f"[dim]本轮无到期 loop（{len(eligible)} eligible, {len(skipped)} skipped）。[/dim]"
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

    success_count = 0
    failure_count = 0
    for enumerated in triggered:
        tick_lock = _acquire_tick_lock(store, enumerated.name)
        if tick_lock is None:
            console.print(
                f"[yellow]⏭️  {enumerated.name}: 另一个 tick 正在进行 —— 跳过以避免并发写冲突[/yellow]"
            )
            continue
        try:
            # gate27 (pi#1/claude#2): re-read the spec INSIDE the per-loop lock.
            # adopt/migrate-ownership take the same blocking lock, so once we
            # hold it the re-read is race-free; the enumerated snapshot could
            # otherwise be stale (adopt re-pinned between enumeration and lock
            # acquisition) and we'd execute with the OLD project_root. Residual
            # window by design: a loop NOT owned at enumeration time is not
            # re-considered even if adopt pins it to cwd meanwhile — the next
            # tick picks it up (reads always go through load_spec, so nothing
            # stale is persisted).
            spec = store.load_spec(enumerated.name)
            if spec is None:
                console.print(f"[yellow]⏭️  {enumerated.name}: spec 在枚举后被删除 —— 跳过[/yellow]")
                continue
            console.print(f"[cyan]▶[/cyan] Ticking [bold]{spec.name}[/bold]...")
            # Per-spec runtime pinned to the loop's ownership root (gate26
            # review: os.chdir was rejected — AgentRuntime freezes project_root
            # at construction, and components are lazy so per-spec cost is
            # negligible). Unscoped loops (project_root=None) keep the legacy
            # ambient-cwd runtime.
            runtime = (
                AgentRuntime(project_root=str(Path(spec.project_root).resolve()))
                if spec.project_root
                else AgentRuntime()
            )
            record = execute_loop_tick(spec, runtime=runtime, store=store)
            if record.success:
                success_count += 1
                console.print(f"  [green]✅[/green] {record.matched_skill} ({record.duration_s}s)")
            else:
                failure_count += 1
                category = (
                    record.failure_info.category.value if record.failure_info else "unclassified"
                )
                console.print(f"  [red]❌[/red] {record.error[:80]} [dim]({category})[/dim]")
        finally:
            _release_tick_lock(tick_lock)  # releases fcntl lock + unlinks on Windows

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


# ──────────────────────────────────────────────────────────────────
# install-launchd / uninstall-launchd (Phase C)
# ──────────────────────────────────────────────────────────────────


def _run_launchctl(cmd: list[str], *, console: Console) -> subprocess.CompletedProcess[str] | None:
    """Run a launchctl subprocess and translate FileNotFoundError to None.

    ``subprocess.run`` raises ``FileNotFoundError`` when ``launchctl`` isn't
    on PATH (rare on macOS but possible in containers / when PATH is broken).
    Callers check for ``None`` and treat it as a soft failure with a friendly
    message instead of letting the raw traceback surface (pi Phase C P-P1-1).
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        console.print(f"[red]❌ 找不到 launchctl——PATH 中缺失。命令: {' '.join(cmd)}[/red]")
        return None


def _bootstrap_launchd(plist_path: Path, *, console: Console, loop_name: str) -> bool:
    """Run ``launchctl bootstrap`` and report. Returns True on success.

    Refresh handling: if the label is already bootstrapped (returncode 125 or
    stderr contains "already bootstrapped"), launchd has cached the OLD plist
    and will NOT re-read the file. We detect this and do an automatic
    bootout-then-bootstrap so the new schedule/env_overrides actually take
    effect (adversarial review Phase C FLAW #2).

    Args:
        plist_path: Path to the plist file to bootstrap.
        console: Rich console for status output.
        loop_name: Bare loop name (without label prefix) — used to construct
            the bootout command on the refresh path, and to print accurate
            recovery hints (FLAW #3: don't print the prefixed stem).
    """
    from vibesop.core.loop.launchd import bootstrap_command

    cmd = bootstrap_command(plist_path)
    result = _run_launchctl(cmd, console=console)
    if result is None:
        return False
    if result.returncode == 0:
        return True

    already = result.returncode == 125 or "already bootstrapped" in (result.stderr or "").lower()
    if already:
        # Refresh path: bootout the stale entry, then re-bootstrap. The plist
        # on disk is already the new one (caller wrote it before invoking us).
        console.print("[dim]已注册，重新加载（bootout → bootstrap）…[/dim]")
        if not _bootout_launchd(loop_name, console=console, missing_ok=True):
            return False
        result2 = _run_launchctl(cmd, console=console)
        if result2 is None:
            return False
        if result2.returncode == 0:
            return True
        console.print(f"[red]❌ refresh 后 bootstrap 仍失败 (exit {result2.returncode})[/red]")
        if result2.stderr:
            console.print(f"[dim]{result2.stderr.strip()}[/dim]")
        return False

    console.print(f"[red]❌ launchctl bootstrap 失败 (exit {result.returncode})[/red]")
    if result.stderr:
        console.print(f"[dim]{result.stderr.strip()}[/dim]")
    return False


def _bootout_launchd(loop_name: str, *, console: Console, missing_ok: bool = False) -> bool:
    """Run ``launchctl bootout`` for ``loop_name``. Returns True on success.

    ``missing_ok=True`` treats "not bootstrapped" as success (used by ``delete``
    so a loop whose plist was already removed doesn't fail teardown).
    """
    from vibesop.core.loop.launchd import bootout_command, plist_label

    cmd = bootout_command(loop_name)
    result = _run_launchctl(cmd, console=console)
    if result is None:
        return False
    if result.returncode == 0:
        return True
    stderr_lower = (result.stderr or "").lower()
    # launchctl prints "Could not find ..." when the label was never bootstrapped
    # (or was already booted out). Non-fatal for delete / uninstall idempotency.
    if missing_ok and ("could not find" in stderr_lower or "no such" in stderr_lower):
        return True
    console.print(f"[red]❌ launchctl bootout 失败 (exit {result.returncode})[/red]")
    if result.stderr:
        console.print(f"[dim]{result.stderr.strip()}[/dim]")
    console.print(f"[dim]label: {plist_label(loop_name)}[/dim]")
    return False


def _is_macos() -> bool:
    return sys.platform == "darwin"


# Whitelisted directories where ``uv`` may live without raising suspicion
# (deep-diagnosis-2026-07-24 P1-5). A ``uv`` resolved from ``.``, ``$HOME``,
# or a world-writable tmp dir could be a malicious binary planted to be picked
# up by ``shutil.which``; persisting that path into a launchd plist bakes the
# attacker's binary into every scheduled tick.
UV_PATH_WHITELIST: tuple[str, ...] = (
    "/opt/homebrew/bin",  # Homebrew on Apple Silicon
    "/usr/local/bin",  # Homebrew on Intel / manual install
    "/usr/bin",  # system package manager
    str(Path.home() / ".local/bin"),  # pipx / uv self-install
)


def _is_uv_path_trusted(uv_path: str) -> bool:
    """Return True iff ``uv_path`` lives under a whitelisted directory."""
    path = Path(uv_path)
    for whitelist_dir in UV_PATH_WHITELIST:
        wl = Path(whitelist_dir)
        try:
            path.relative_to(wl)
            return True
        except ValueError:
            continue
    return False


def _is_project_root_trusted(project_root: Path) -> bool:
    """Return True iff ``project_root`` looks like a real project root.

    A git working tree (``.git/``) is the cheapest signal that the user is
    intentionally working here, not a directory an attacker lured them into
    cd-ing to before running ``install-launchd`` (deep-diagnosis-2026-07-24
    P1-4 — without this check the attacker-controlled cwd would be persisted
    into launchd's WorkingDirectory and re-run on every tick).
    """
    return (project_root / ".git").exists() or (project_root / "pyproject.toml").exists()


@app.command("install-launchd")
def install_launchd(
    name: str = typer.Argument(..., help="loop 名称"),
    vibe_prefix: str | None = typer.Option(
        None,
        "--vibe-prefix",
        envvar="VIBESOP_RUN_PREFIX",
        help="vibe CLI 调用前缀（默认自动解析 uv 绝对路径 + ' run vibe'）。带空格的路径需加引号。",
    ),
    trust_cwd: bool = typer.Option(
        False,
        "--trust-cwd",
        help="跳过 cwd 校验：当前目录不是 git repo / pyproject.toml 时也允许安装 (P1-4)。",
    ),
    trust_uv_path: bool = typer.Option(
        False,
        "--trust-uv-path",
        help="跳过 uv 路径白名单校验：uv 来自非白名单目录时也允许安装 (P1-5)。",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印 plist，不写盘、不 bootstrap"),
) -> None:
    """生成 launchd plist 并注册到 ~/Library/LaunchAgents/（仅 macOS）。

    流程：
        1. 加载 LoopSpec
        2. 渲染 plist XML（ProgramArguments = prefix + ['loop','tick','--name',NAME]）
        3. 写到 ~/Library/LaunchAgents/com.vibesop.loop.<name>.plist
        4. 调 ``launchctl bootstrap gui/$(id -u) <plist>`` 注册

    ProgramArguments 调用通用的 ``vibe loop tick``，所以同一 plist 模板适用
    于 skill / query / workflow / command_args 四种 target。Target dispatch
    和 PAUSED/DEAD/RETIRED 过滤由 tick 内部处理。

    安全 (deep-diagnosis-2026-07-24 P1-4 / P1-5)：
        - 默认拒绝把不可信 cwd 持久化为 launchd WorkingDirectory；cwd 必须含
          ``.git/`` 或 ``pyproject.toml``，否则用 ``--trust-cwd`` 显式放行。
        - 默认拒绝把非白名单 ``uv`` 路径写入 plist；白名单覆盖 Homebrew /
          ``~/.local/bin`` / ``/usr/bin``，否则用 ``--trust-uv-path`` 放行。

    注：``vibe loop create`` 暂未暴露 ``--command`` flag（Phase D 补），所以
    command_args loop 需手工编辑 spec.json 或通过 ``--dry-run`` 检查后再用。
    """
    if not _is_macos():
        console.print("[red]❌ install-launchd 仅支持 macOS（其他平台请用 cron 或 systemd）[/red]")
        raise typer.Exit(1)

    from vibesop.core.loop.launchd import (
        DEFAULT_VIBE_PREFIX,
        default_plist_path,
        render_plist,
    )

    store = LoopStore()
    spec = store.load_spec(name)
    if spec is None:
        console.print(f"[red]❌ Loop '{name}' 不存在[/red]")
        raise typer.Exit(1)

    # launchd's default PATH is `/usr/bin:/bin:/usr/sbin:/sbin` — it does NOT
    # inherit the user's shell PATH, so `/opt/homebrew/bin` (where Homebrew
    # installs uv on Apple Silicon) is missing. A bare ``uv run vibe`` would
    # fail every tick with "uv: command not found". When the user hasn't
    # pinned a prefix, resolve ``uv`` to its absolute path at install time
    # so the plist is self-contained (kimi Phase C K-P1-2).
    if vibe_prefix is None:
        import shutil

        uv_path = shutil.which("uv")
        if uv_path:
            # P1-5: refuse non-whitelisted uv paths unless the user explicitly
            # trusts them. An attacker who controls PATH (or plants a ``uv``
            # in ``.`` or a tmp dir) could otherwise persist their binary
            # into the launchd plist.
            if not _is_uv_path_trusted(uv_path) and not trust_uv_path:
                console.print(
                    f"[red]❌ uv 路径 {uv_path} 不在白名单 {list(UV_PATH_WHITELIST)}。"
                    f" 若确实可信，加 --trust-uv-path 显式放行 (P1-5)。[/red]"
                )
                raise typer.Exit(1)
            prefix = f"{uv_path} run vibe"
        else:
            console.print(
                "[yellow]⚠️  未在 PATH 找到 'uv'——回退到 'uv run vibe'。"
                " launchd 默认 PATH 不含 Homebrew，tick 大概率失败。"
                " 请用 --vibe-prefix 指定绝对路径，如 "
                "'/opt/homebrew/bin/uv run vibe'。[/yellow]"
            )
            prefix = DEFAULT_VIBE_PREFIX
    else:
        prefix = vibe_prefix
    project_root = Path.cwd()
    # gate26: install-launchd does NOT backfill spec.project_root (ownership is
    # pinned only by create/adopt/migrate-ownership). But if the spec IS pinned
    # to a different directory, the plist's WorkingDirectory (cwd) and the
    # executor's exec_root (spec.project_root) would disagree — warn loudly.
    if spec.project_root is not None:
        try:
            mismatch = Path(spec.project_root).resolve() != project_root.resolve()
        except OSError:
            mismatch = True
        if mismatch:
            console.print(
                f"[yellow]⚠️  Loop '{name}' 已钉到 {spec.project_root}，与当前 cwd "
                f"{project_root} 不一致。plist 的 WorkingDirectory 仍写 cwd，但 tick 执行"
                f"会在钉住的项目根下进行；如需改钉，请运行 `vibe loop adopt {name}`。[/yellow]"
            )
    # P1-4: refuse unvetted cwds so an attacker can't lure the user into a
    # hostile directory and persist it via launchd's WorkingDirectory.
    if not _is_project_root_trusted(project_root) and not trust_cwd:
        console.print(
            f"[red]❌ cwd {project_root} 既非 git repo (无 .git/) 也无 pyproject.toml。"
            f" launchd 会把此目录持久化为 WorkingDirectory——若确实可信，"
            f" 加 --trust-cwd 显式放行 (P1-4)。[/red]"
        )
        raise typer.Exit(1)
    try:
        plist_bytes = render_plist(
            spec,
            project_root=project_root,
            vibe_prefix=prefix,
            # Keep plist log paths aligned with where the tick process actually
            # reads/writes state — pass the store's real base_dir instead of
            # assuming ~/.vibe/loops (deep-diagnosis-2026-07-24 P1-6).
            loop_base_dir=store.base_dir,
        )
    except ValueError as e:
        # shlex.split raises ValueError on mismatched quotes — fail loud at
        # install time rather than silently producing a broken plist that
        # launchd would reject every tick (adversarial review Phase C FLAW #4).
        console.print(f"[red]❌ VIBESOP_RUN_PREFIX / --vibe-prefix 解析失败: {e}[/red]")
        raise typer.Exit(1) from e

    if dry_run:
        console.print(Panel(plist_bytes.decode(), title=f"[bold]DRY RUN: {name}[/bold]"))
        return

    plist_path = default_plist_path(spec.name)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(plist_bytes)

    console.print(f"[green]✅ plist 已写入: {plist_path}[/green]")
    console.print(f"[dim]ProgramArguments: {prefix} loop tick --name {name}[/dim]")
    console.print(f"[dim]WorkingDirectory: {project_root}[/dim]")

    if not _bootstrap_launchd(plist_path, console=console, loop_name=spec.name):
        # Clean up the orphaned plist so we don't leave a half-installed state
        # (adversarial review Phase C FLAW #1). The user can re-run after fixing
        # whatever blocked bootstrap.
        try:
            plist_path.unlink()
        except OSError as e2:
            logger.warning("Failed to clean up plist after bootstrap failure: %s", e2)
        raise typer.Exit(1)

    console.print(
        f"\n[bold]下一步[/bold]: launchd 已注册。查看状态:\n"
        f"  [dim]launchctl print gui/$(id -u)/com.vibesop.loop.{name}[/dim]\n"
        f"  [dim]tail -f ~/.vibe/loops/{name}/out.log[/dim]"
    )


@app.command("uninstall-launchd")
def uninstall_launchd(
    name: str = typer.Argument(..., help="loop 名称"),
    keep_plist: bool = typer.Option(False, "--keep-plist", help="保留 plist 文件（仅 bootout）"),
) -> None:
    """从 launchd 注销 loop（``launchctl bootout``）并删除 plist。

    幂等：loop 未注册时也返回成功。
    """
    if not _is_macos():
        console.print("[red]❌ uninstall-launchd 仅支持 macOS[/red]")
        raise typer.Exit(1)

    from vibesop.core.loop.launchd import default_plist_path

    plist_path = default_plist_path(name)
    bootout_ok = _bootout_launchd(name, console=console, missing_ok=True)
    if not bootout_ok:
        raise typer.Exit(1)

    if keep_plist:
        console.print(f"[green]✅ 已 bootout（保留 plist: {plist_path}）[/green]")
        return

    if plist_path.exists():
        plist_path.unlink()
        console.print(f"[green]✅ 已删除 plist: {plist_path}[/green]")
    else:
        console.print("[green]✅ 已 bootout（plist 本来就不存在）[/green]")


__all__ = ["app"]
