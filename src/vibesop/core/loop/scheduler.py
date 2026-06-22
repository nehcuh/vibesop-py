"""Lightweight cron expression parser + dispatcher — no external deps.

支持标准 5 段 cron 格式：
    minute (0-59)
    hour   (0-23)
    day    (1-31)
    month  (1-12)
    dow    (0-6, 0=Sunday; 7 also accepted as Sunday for compat)

支持每段语法：
    ``*``        通配符
    ``15``       固定值
    ``*/5``      步进（从范围下限开始）
    ``1-10/3``   范围 + 步进（从范围下限起）
    ``1,15,30``  列表
    ``9-17``     范围

非标准但接受：
    ``30/10``    固定值 + 步进（Quartz 风格；Vixie cron 不支持）

设计决策：
    - 与 WorkflowEngine.LOOP_UNTIL_DRY 解耦（那是语义 loop）
    - 只回答"什么时间触发"，不回答"触发了执行什么"
    - 分钟级精度，纯 Python 实现，零外部依赖
    - CronDaemon 是无状态单次轮询函数 —— v1 不需要 long-running 进程，
      外部 cron（systemd timer / launchd / crontab）每分钟调用一次即可。
      参见 ROADMAP v8.0 架构图。

修复记录（相对草稿）:
    P0  _parse_field 的 ``*/N`` 范围 base bug —— ``1-10/3`` 现正确得 {1,4,7,10}
    P1  dow 同时接受 0 和 7 为 Sunday（POSIX 兼容）
    P1  移除 ``CronDaemon._running`` 死字段 + 删除"承诺未交付"的 docstring
    P1  收紧 run_once 签名为 ``Sequence[LoopSpec]``
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

logger = logging.getLogger(__name__)


def _parse_field(field: str, min_val: int, max_val: int) -> set[int]:
    """解析单个 cron 字段，返回匹配值的集合。

    Args:
        field: 原始段字符串（不预期被 trim，内部按需处理）。
        min_val: 合法下限（含）。
        max_val: 合法上限（含）。

    Returns:
        匹配值集合。空集合表示字段无任何合法值（调用方应抛错）。
    """
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue

        if part == "*":
            values.update(range(min_val, max_val + 1))
            continue

        if "/" in part:
            base_str, step_str = part.split("/", 1)
            try:
                step = int(step_str)
            except ValueError:
                continue
            if step <= 0:
                continue

            if base_str == "*":
                start, end = min_val, max_val
            elif "-" in base_str:
                lo_str, _, hi_str = base_str.partition("-")
                try:
                    start = int(lo_str)
                    end = int(hi_str) if hi_str else max_val
                except ValueError:
                    continue
            else:
                try:
                    start = int(base_str)
                except ValueError:
                    continue
                end = max_val

            start = max(start, min_val)
            end = min(end, max_val)
            if start > end:
                continue
            values.update(range(start, end + 1, step))

        elif "-" in part:
            lo_str, _, hi_str = part.partition("-")
            try:
                low = int(lo_str)
                high = int(hi_str) if hi_str else max_val
            except ValueError:
                continue
            if low > high:
                continue
            values.update(range(max(low, min_val), min(high, max_val) + 1))

        else:
            try:
                v = int(part)
            except ValueError:
                continue
            if min_val <= v <= max_val:
                values.add(v)

    return values


# Python weekday → cron weekday 映射
# Python: Monday=0, ..., Sunday=6
# cron:   Sunday=0, Monday=1, ..., Saturday=6
_PY_TO_CRON_DOW: dict[int, int] = {
    0: 1,  # Mon
    1: 2,  # Tue
    2: 3,  # Wed
    3: 4,  # Thu
    4: 5,  # Fri
    5: 6,  # Sat
    6: 0,  # Sun
}


class CronExpr:
    """标准 5 段 cron 表达式解析器。

    Args:
        expr: cron 表达式，如 ``"*/15 * * * *"``。

    Raises:
        ValueError: 表达式不是合法的 5 段格式，或某段无合法值。
    """

    _MAX_SEARCH_MINUTES = 366 * 24 * 60  # ~one year; safety net for sparse exprs

    def __init__(self, expr: str) -> None:
        fields = expr.strip().split()
        if len(fields) != 5:
            raise ValueError(
                f"cron 表达式必须为 5 段（分 时 日 月 周），收到 {len(fields)} 段: {expr!r}"
            )

        self.minutes = _parse_field(fields[0], 0, 59)
        self.hours = _parse_field(fields[1], 0, 23)
        self.days = _parse_field(fields[2], 1, 31)
        self.months = _parse_field(fields[3], 1, 12)
        # POSIX: dow 0 and 7 both = Sunday. Normalise 7 → 0.
        dow_raw = _parse_field(fields[4], 0, 7)
        self.dow = {0 if v == 7 else v for v in dow_raw}
        # POSIX crontab(5): when BOTH day-of-month and day-of-week are restricted
        # (neither is '*'), the command runs on EITHER match (OR); otherwise AND.
        # Pre-fix this used AND always, so '0 0 1 * 1' fired only on the 1st AND
        # Monday, not '1st OR Monday'.
        # POSIX/Vixie: "restricted" = the field is NOT the bare wildcard '*'.
        # `*/2`, `1-31`, `1,15` are all restricted (only a bare '*' is not). A
        # substring '*' check would wrongly treat `*/2` as unrestricted (AND).
        self._dom_dow_both_restricted = fields[2].strip() != "*" and fields[4].strip() != "*"

        empty_fields = [
            name
            for name, vals in (
                ("minute", self.minutes),
                ("hour", self.hours),
                ("day", self.days),
                ("month", self.months),
                ("dow", self.dow),
            )
            if not vals
        ]
        if empty_fields:
            raise ValueError(f"cron 表达式 {expr!r} 字段无合法值: {', '.join(empty_fields)}")

        self._raw = expr

    def next_run_after(self, after: datetime | None = None) -> datetime:
        """返回 ``after`` 之后的下一次触发时间（分钟精度，UTC）。

        Args:
            after: 基准时间。默认当前 UTC 时间。秒和微秒归零。

        Returns:
            下次触发时间。

        Raises:
            RuntimeError: 一年内无匹配时间（极稀疏表达式，理论上不应发生）。
        """
        after = (after or datetime.now(UTC)).replace(second=0, microsecond=0)
        dt = after + timedelta(minutes=1)

        for _ in range(self._MAX_SEARCH_MINUTES):
            if self._matches(dt):
                return dt
            dt += timedelta(minutes=1)

        raise RuntimeError(
            f"无法在 {self._MAX_SEARCH_MINUTES} 次迭代内找到 cron {self._raw!r} 的下一次触发"
        )

    def should_run(self, dt: datetime | None = None) -> bool:
        """判断给定时间是否匹配 cron 表达式。

        对秒/微秒不敏感 —— 只要 minute/hour/day/month/weekday 匹配即为 True。
        即整分钟内的任意时刻（包括 30.000s 和 30.999s）都视为匹配。
        """
        dt = dt or datetime.now(UTC)
        return self._matches(dt)

    def _matches(self, dt: datetime) -> bool:
        dom_match = dt.day in self.days
        dow_match = _PY_TO_CRON_DOW.get(dt.weekday(), -1) in self.dow
        # POSIX OR-semantics when both dom and dow are restricted (see __init__).
        day_match = (
            (dom_match or dow_match)
            if self._dom_dow_both_restricted
            else (dom_match and dow_match)
        )
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and day_match
            and dt.month in self.months
        )

    def __repr__(self) -> str:
        return f"CronExpr({self._raw!r})"


class _Schedulable(Protocol):
    """Structural type for anything CronDaemon can poll."""

    name: str
    schedule: str
    trigger: object  # StrEnum-likes expose .value


class CronDaemon:
    """无状态 cron 轮询函数包。

    v1 不持有长期运行线程：外部调度器（systemd timer / launchd /
    crontab / GitHub Actions cron）按需调用 ``run_once`` 即可。
    这样可以避免进程状态管理、PID 文件、信号处理等长期进程的复杂度，
    同时和 ROADMAP v8.0 架构图（"外部 cron → VibeSOP Loop Daemon"）一致。

    若未来需要内嵌常驻进程，新增 ``run_forever(stop_event: threading.Event)``
    方法即可，不破坏现有 API。
    """

    def run_once(self, specs: Sequence[_Schedulable]) -> list[_Schedulable]:
        """单次轮询：返回所有当前时间匹配的 specs 子集。

        Args:
            specs: 待检查的可调度对象列表（LoopSpec 或鸭子类型）。

        Returns:
            当前 UTC 时间应触发的 specs 子集（保持原顺序）。
            无效 cron 会被静默跳过并 warning（不影响其他 spec）。
        """
        now = datetime.now(UTC)
        triggered: list[_Schedulable] = []

        for spec in specs:
            trigger_attr = getattr(spec, "trigger", None)
            trigger_val = (
                trigger_attr.value if hasattr(trigger_attr, "value") else str(trigger_attr or "")
            )
            schedule = getattr(spec, "schedule", "")

            if trigger_val != "cron" or not schedule:
                continue

            try:
                cron = CronExpr(schedule)
            except (ValueError, RuntimeError) as e:
                logger.warning(
                    "Loop %s has invalid cron %r: %s — skipped",
                    getattr(spec, "name", "?"),
                    schedule,
                    e,
                )
                continue

            if cron.should_run(now):
                triggered.append(spec)

        return triggered


__all__ = ["CronDaemon", "CronExpr"]
