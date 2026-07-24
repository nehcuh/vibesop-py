"""macOS launchd plist generation for LoopSpec schedules.

Converts a ``LoopSpec.schedule`` (5-field cron) into a launchd ``plist`` that
invokes ``vibe loop tick --name <NAME>`` on schedule. The plist is generic
across target types (skill/query/workflow/command_args) — the tick pipeline
already handles target dispatch plus PAUSED/DEAD/RETIRED filtering.

Schedule mapping:
    - ``*/N * * * *`` (every N minutes, clean divisor of 60) → ``StartInterval``
      with N*60 seconds. launchd runs the job every N seconds, but tick's own
      state machine deduplicates within the same minute via the tick lock.
    - Anything else → ``StartCalendarInterval`` with arrays for each field
      (launchd supports multi-value Minute/Hour/Day/Month/Weekday). ``*``
      fields are omitted (launchd treats absent keys as wildcard).
    - Cron ``*/N`` step syntax in non-minute positions expands via
      ``CronExpr`` (already does this for us as Python sets).

Why ``plistlib`` over hand-rolled XML: ProgramArguments is an array of
strings, each rendered as a ``<string>`` element. ``plistlib.dumps(FMT_XML)``
handles XML escaping correctly; rolling our own would risk corruption on
paths-with-spaces, special chars, unicode args. shlex.quote is *not* needed
here — ProgramArguments bypasses the shell entirely (no shell interpretation
on the argv array).

Modern launchctl (E.3 must-fix):
    - bootstrap: ``launchctl bootstrap gui/$(id -u) <plist>``
    - bootout:   ``launchctl bootout gui/$(id -u)/<label>``
The legacy ``load/unload`` are deprecated since macOS 10.10.
"""

from __future__ import annotations

import plistlib
import shlex
from dataclasses import dataclass
from pathlib import Path

from vibesop.core.loop.models import LoopSpec
from vibesop.core.loop.scheduler import CronExpr

LAUNCHD_LABEL_PREFIX = "com.vibesop.loop"
DEFAULT_VIBE_PREFIX = "uv run vibe"


def plist_label(loop_name: str) -> str:
    """Return the launchd label (e.g. ``com.vibesop.loop.instinct-assemble``)."""
    return f"{LAUNCHD_LABEL_PREFIX}.{loop_name}"


def plist_filename(loop_name: str) -> str:
    """Return the plist filename (e.g. ``com.vibesop.loop.instinct-assemble.plist``)."""
    return f"{plist_label(loop_name)}.plist"


def default_plist_path(loop_name: str) -> Path:
    """Return the standard user-Level LaunchAgents path for ``loop_name``."""
    return Path.home() / "Library" / "LaunchAgents" / plist_filename(loop_name)


def _is_wildcard(values: set[int], full_range: set[int]) -> bool:
    return values == full_range


def cron_to_start_calendar(cron: CronExpr) -> dict[str, list[int]] | None:
    """Convert a parsed cron expr to a launchd ``StartCalendarInterval`` dict.

    Returns ``None`` if the cron is ``* * * * *`` (every minute) — caller
    should fall back to ``StartInterval=60``.

    Wildcard fields are omitted from the dict so launchd treats them as
    "match any" (per launchd.plist(5) man page).
    """
    out: dict[str, list[int]] = {}
    if not _is_wildcard(cron.minutes, set(range(0, 60))):
        out["Minute"] = sorted(cron.minutes)
    if not _is_wildcard(cron.hours, set(range(0, 24))):
        out["Hour"] = sorted(cron.hours)
    if not _is_wildcard(cron.days, set(range(1, 32))):
        out["Day"] = sorted(cron.days)
    if not _is_wildcard(cron.months, set(range(1, 13))):
        out["Month"] = sorted(cron.months)
    if not _is_wildcard(cron.dow, set(range(0, 7))):
        # Cron uses 0=Sunday (POSIX); CronExpr normalises 7→0 in __init__.
        # launchd's StartCalendarInterval.Weekday also treats 0 and 7 as
        # Sunday, but 7 is the unambiguous form — some launchd consumers
        # reject 0 outright (deep-diagnosis-2026-07-24 P1-1).
        out["Weekday"] = sorted(7 if d == 0 else d for d in cron.dow)
    return out or None


def cron_to_start_interval_seconds(cron_str: str) -> int | None:
    """Detect simple ``*/N * * * *`` patterns and return N*60.

    Returns ``None`` if not a clean every-N-minutes pattern. Restricted to
    divisors of 60 because launchd's StartInterval is wall-clock seconds and
    we want tick cadence to stay aligned to minute boundaries.
    """
    parts = cron_str.split()
    if len(parts) != 5:
        return None
    minute, hour, dom, month, dow = parts
    if not minute.startswith("*/"):
        return None
    if not (hour == "*" and dom == "*" and month == "*" and dow == "*"):
        return None
    try:
        n = int(minute[2:])
    except ValueError:
        return None
    if not (1 <= n <= 30):
        return None
    if 60 % n != 0:
        return None
    return n * 60


@dataclass(frozen=True)
class LaunchdSchedule:
    """The launchd schedule key+value to inject into the plist dict."""

    key: str  # "StartInterval" or "StartCalendarInterval"
    value: int | dict[str, list[int]]


def schedule_for_cron(cron_str: str) -> LaunchdSchedule:
    """Pick the right launchd schedule representation for ``cron_str``.

    Preference order:
        1. ``*/N * * * *`` (clean divisor of 60) → ``StartInterval`` (simpler,
           handles drift correctly without minute-array expansion).
        2. Anything else → ``StartCalendarInterval`` via ``CronExpr``.
    """
    interval = cron_to_start_interval_seconds(cron_str)
    if interval is not None:
        return LaunchdSchedule(key="StartInterval", value=interval)
    cron = CronExpr(cron_str)
    cal = cron_to_start_calendar(cron)
    if cal is None:
        # ``* * * * *`` → run every minute. Use StartInterval=60.
        return LaunchdSchedule(key="StartInterval", value=60)
    return LaunchdSchedule(key="StartCalendarInterval", value=cal)


def _parse_vibe_prefix(prefix: str) -> list[str]:
    """shlex-split the vibe invocation prefix.

    Handles quoted paths with spaces (e.g.
    ``VIBESOP_RUN_PREFIX='"/path/with space/uv" run vibe'``). Raises
    ``ValueError`` on mismatched quotes — better to fail loud at install time
    than to silently produce a broken plist that launchd will reject every
    tick (adversarial review Phase C FLAW #4).
    """
    return shlex.split(prefix, posix=True)


def render_plist(
    spec: LoopSpec,
    *,
    project_root: Path,
    vibe_prefix: str = DEFAULT_VIBE_PREFIX,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> bytes:
    """Render a launchd plist (XML bytes) for ``spec``.

    Args:
        spec: Loop definition. Only ``name``, ``schedule``, and
            ``env_overrides`` are consumed — the tick pipeline handles target
            dispatch (skill/query/workflow/command_args) plus state machine.
        project_root: ``WorkingDirectory`` for the launched process. Pass
            ``Path.cwd()`` at install time.
        vibe_prefix: How to invoke the vibe CLI. Defaults to ``"uv run vibe"``
            (assumes uv on PATH and a pyproject.toml in ``project_root`` or
            its parents). Override via ``VIBESOP_RUN_PREFIX`` env var.
        stdout_path: ``StandardOutPath``. Defaults to ``<loop_dir>/out.log``.
        stderr_path: ``StandardErrorPath``. Defaults to ``<loop_dir>/err.log``.

    Returns:
        XML plist bytes suitable for writing to ``~/Library/LaunchAgents/``.
    """
    label = plist_label(spec.name)
    prefix_argv = _parse_vibe_prefix(vibe_prefix)
    argv = [*prefix_argv, "loop", "tick", "--name", spec.name]

    # Co-locate logs with the per-loop state directory so they're easy to
    # find and rotate together. ``LoopStore`` defaults to ``~/.vibe/loops``
    # (global, not project-local), and ``save_spec`` mkdirs the per-name
    # subdir — so defaulting log paths here guarantees the directory exists
    # at bootstrap time. Using ``project_root`` would point into a dir that
    # nothing creates, and launchd refuses to spawn jobs whose
    # ``StandardOutPath`` parent doesn't exist (kimi Phase C K-P1-1).
    loop_dir = Path.home() / ".vibe" / "loops" / spec.name
    stdout = stdout_path or (loop_dir / "out.log")
    stderr = stderr_path or (loop_dir / "err.log")

    schedule = schedule_for_cron(spec.schedule)

    plist: dict[str, object] = {
        "Label": label,
        "ProgramArguments": argv,
        "WorkingDirectory": str(project_root),
        "StandardOutPath": str(stdout),
        "StandardErrorPath": str(stderr),
        "RunAtLoad": False,
        # launchd's process picker is more reliable than our in-process
        # watchdog; let launchd keep the agent alive on unexpected exit.
        "KeepAlive": False,
        schedule.key: schedule.value,
    }
    if spec.env_overrides:
        plist["EnvironmentVariables"] = dict(spec.env_overrides)

    return plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=False)


def bootstrap_command(plist_path: Path) -> list[str]:
    """Return the modern launchctl bootstrap argv (E.3 must-fix).

    Caller runs this via subprocess; output goes to the user's terminal.
    """
    import os

    return ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)]


def bootout_command(loop_name: str) -> list[str]:
    """Return the modern launchctl bootout argv for ``loop_name``."""
    import os

    return ["launchctl", "bootout", f"gui/{os.getuid()}/{plist_label(loop_name)}"]


__all__ = [
    "DEFAULT_VIBE_PREFIX",
    "LAUNCHD_LABEL_PREFIX",
    "LaunchdSchedule",
    "bootout_command",
    "bootstrap_command",
    "cron_to_start_calendar",
    "cron_to_start_interval_seconds",
    "default_plist_path",
    "plist_filename",
    "plist_label",
    "render_plist",
    "schedule_for_cron",
]
