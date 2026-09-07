"""Explicit parallel-worker intent — not role-persona counting.

W1 D2: MULTI_AGENT_SQUAD only when the user asked for independent
workers, never because the query named 实现/审查/架构/测试.
"""

from __future__ import annotations

import re

# Phrase tokens only. Must NOT include 实现/审查/测试/架构 or bare 「并行」.
PARALLEL_WORKER_TOKENS: tuple[str, ...] = (
    "并行工人",
    "并行施工队",
    "同时开工",
    "独立上下文",
    "多窗口工人",
    "多窗口指挥",
    "parallel workers",
    "independent contexts",
    "independent context workers",
    "tmux workers",
)

_NAMED_ITEM = re.compile(
    r"(?:子任务|模块|窗口|工人)\s*[A-Za-z0-9一二三四五六七八]",
)

_AND_PAIR = re.compile(
    r".{1,40}(?:和|与|以及| and )\s*.{1,40}",
    re.IGNORECASE,
)


def is_explicit_parallel_workers(query: str) -> bool:
    """True iff the query names parallel workers AND at least two work items."""
    text = query.strip()
    if not text:
        return False
    lowered = text.lower()
    if not any(token.lower() in lowered for token in PARALLEL_WORKER_TOKENS):
        return False
    if len(_NAMED_ITEM.findall(text)) >= 2:
        return True
    return _AND_PAIR.search(text) is not None
