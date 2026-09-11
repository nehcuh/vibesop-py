#!/usr/bin/env python3
"""Claude Code PreToolUse hook：保护 R3+R4 任务中的判据与既有实现。

为什么需要它
------------
提示词里写"请勿修改 X"是**请求**，模型可能忽略；hook 是**强制**。
本项目两份预注册里的判据（证伪线、阈值、门槛）必须在开工前写死，
一旦被"顺手调整"，整个实验的效力就没了。这个 hook 把该纪律变成机制。

行为
----
- 收到 Claude Code 的 PreToolUse JSON（stdin）
- 若 ``tool_name`` 属于写类工具，且目标路径命中受保护模式 → **exit 2**（阻断），
  stderr 内容会回灌给模型作为纠正提示
- 其他情况 → exit 0（放行）
- **解析失败时 exit 0**（fail-open）：hook 自身故障不应把整个仓库锁死。
  若要 fail-closed，把 ``FAIL_MODE`` 改成 "closed"。

接法（.claude/settings.local.json）
-----------------------------------
    {
      "hooks": {
        "PreToolUse": [
          {
            "matcher": "Edit|Write|MultiEdit|NotebookEdit",
            "hooks": [
              {
                "type": "command",
                "command": "python3 /Users/huchen/Projects/vibesop-py/.claude/hooks/guard_protected_paths.py"
              }
            ]
          }
        ]
      }
    }
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path
from typing import Any

FAIL_MODE = "open"  # "open" | "closed"

#: 写类工具名（非写类工具直接放行）
WRITE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

#: 受保护路径（fnmatch 模式，匹配绝对路径）。命中即阻断。
#: 分三组：判据文件 / 被明确禁止修改的既有实现 / 既有标定脚本。
PROTECTED_PATTERNS: tuple[tuple[str, str], ...] = (
    # —— 判据：不得改（改了就等于事后挪动证伪线）——
    (
        "*/vibesop-py/.omx/artifacts/optimization-convergence-r3-prereg.md",
        "R3 预注册是判据文件。判据必须在开跑前写死；若你认为判据有误，"
        "停下来向用户提出，不要自行修改。",
    ),
    (
        "*/vibesop-py/.omx/artifacts/optimization-convergence-r4-prereg.md",
        "R4 预注册是判据文件。同上：有异议就提出，不要改。",
    ),
    (
        "*/vibesop-py/docs/specs/2026-09-11-optimization-convergence-requirements.md",
        "需求文档是验收来源。R3/R4 的范围与验收标准以它为准；"
        "若发现它写错了，向用户提出，不要就地改写。",
    ),
    # —— 被明确禁止修改的既有实现（本任务只做就绪度检查，不标定、不改行为）——
    (
        "*/vibesop-py/src/vibesop/core/observability/behavior_consistency.py",
        "该模块的既有行为不在本任务范围内（R4 只做就绪度检查）。"
        "需要复用的函数请 import；需要适配请在 R4 脚本内做适配层。",
    ),
    (
        "*/vibesop-py/src/vibesop/core/routing/benchmark.py",
        "路由基线门禁不在本任务范围内（指纹扩展属 R6，未授权）。",
    ),
    # —— 既有标定脚本：不要重写 ——
    (
        "*/vibesop-py/scripts/calibrate_behavior_threshold.py",
        "该脚本已存在。R4 本轮不重新标定，只做就绪度检查；"
        "就绪后才轮到它上场（且是后续独立任务）。",
    ),
)


def _extract_path(tool_input: dict[str, Any]) -> str | None:
    """尽力从 tool_input 里取目标路径。取不到返回 None（放行）。"""
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    # MultiEdit 等可能给 edits 数组，取首个带路径的
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for item in edits:
            if isinstance(item, dict):
                found = _extract_path(item)
                if found:
                    return found
    return None


def _check(payload: dict[str, Any]) -> str | None:
    """返回阻断原因，放行则返回 None。"""
    tool_name = payload.get("tool_name")
    if tool_name not in WRITE_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    target = _extract_path(tool_input)
    if not target:
        return None
    # 归一化：解析符号链接与相对路径，避免用 ../ 或软链绕过
    try:
        normalised = str(Path(target).expanduser().resolve())
    except (OSError, RuntimeError):
        normalised = target
    for pattern, reason in PROTECTED_PATTERNS:
        if fnmatch.fnmatch(normalised, pattern):
            return (
                f"BLOCKED by guard_protected_paths hook.\n"
                f"  tool      : {tool_name}\n"
                f"  target    : {normalised}\n"
                f"  reason    : {reason}\n"
                f"这条约束是任务范围内的硬性要求，不是建议。"
                f"若你确信必须修改该文件才能完成任务，停下来向用户说明原因并请求授权。"
            )
    return None


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0 if FAIL_MODE == "open" else 2
    if not isinstance(payload, dict):
        return 0 if FAIL_MODE == "open" else 2

    reason = _check(payload)
    if reason is None:
        return 0
    sys.stderr.write(reason + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
