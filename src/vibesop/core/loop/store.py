"""Loop store — JSON-file persistence for loop definitions and runtime states.

存储路径:
    ~/.vibe/loops/{name}/spec.json    — 用户可编辑定义（HOME 级存储，不在项目树内，
                                        因此不会被 git 追踪；项目归属记录在
                                        LoopSpec.project_root 字段上）
    ~/.vibe/loops/{name}/state.json   — 运行时状态（系统维护）

设计要点:
    - 序列化通过 pydantic BaseModel 内建 ``model_dump_json`` /
      ``model_validate_json`` — 无需手写 dict 转换层。
    - 原子写入：先写 ``.tmp``，再 ``rename`` 覆盖目标。
    - name 字段防御性校验（拒绝 ``..`` / ``/`` / 空字符串），
      避免 ``delete_spec`` 被构造成路径遍历。
    - 区分"文件不存在"（debug 级日志，正常首次访问）和
      "schema drift / 损坏 JSON"（warning 级日志，需要排查）。

并发:
    v1 不做显式锁定。原子写入保证单个 spec/state 文件不会半写；
    跨 loop 的并发由调用方（CronDaemon v1 单线程）保证。
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import shutil
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from vibesop.core.loop.models import LoopSpec, LoopState

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# 与 LoopSpec.name 同款 pattern；store 层独立校验以避免路径遍历。
_SAFE_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class LoopStore:
    """Loop 配置的持久化存储。

    Args:
        base_dir: 存储根目录。默认 ``~/.vibe/loops/``。
    """

    SPEC_FILENAME = "spec.json"
    STATE_FILENAME = "state.json"

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or Path.home() / ".vibe" / "loops")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ── CRUD: Spec ────────────────────────────────────────────────────

    def save_spec(self, spec: LoopSpec) -> None:
        """保存或更新 loop 定义（原子写入）。"""
        self._require_safe_name(spec.name)
        path = self._spec_path(spec.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, spec.model_dump_json(indent=2))
        logger.info("Loop spec saved: %s", spec.name)

    def load_spec(self, name: str) -> LoopSpec | None:
        """加载 loop 定义。文件不存在或 schema 不匹配时返回 ``None``。"""
        if not self._is_safe_name(name):
            return None
        return self._load_model(self._spec_path(name), LoopSpec)

    def delete_spec(self, name: str) -> bool:
        """删除 loop 的全部数据（spec + state + 目录）。

        Returns:
            ``True`` 若实际删除了目录；``False`` 若目录不存在。
        """
        self._require_safe_name(name)
        loop_dir = self._loop_dir(name)
        if not loop_dir.exists():
            return False
        shutil.rmtree(loop_dir)
        logger.info("Loop deleted: %s", name)
        return True

    def list_specs(self) -> list[LoopSpec]:
        """列出所有已保存的 loop 定义（按目录名排序）。"""
        if not self.base_dir.exists():
            return []
        specs: list[LoopSpec] = []
        for item in sorted(self.base_dir.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue
            spec = self.load_spec(item.name)
            if spec is not None:
                specs.append(spec)
        return specs

    # ── CRUD: State ───────────────────────────────────────────────────

    def save_state(self, state: LoopState) -> None:
        """保存 loop 运行时状态（原子写入）。"""
        self._require_safe_name(state.spec.name)
        path = self._state_path(state.spec.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, state.model_dump_json(indent=2))

    def load_state(self, name: str) -> LoopState | None:
        """加载 loop 运行时状态。

        - 若 spec 不存在 → ``None``
        - 若 spec 存在但 state 不存在 → 返回默认 ``LoopState(spec=spec)``
        - 若 state 存在但 schema drift → ``None`` 并 warning
        """
        spec = self.load_spec(name)
        if spec is None:
            return None
        state = self._load_model(self._state_path(name), LoopState)
        if state is not None:
            return state
        return LoopState(spec=spec)

    # ── 路径辅助 ──────────────────────────────────────────────────────

    def _loop_dir(self, name: str) -> Path:
        return self.base_dir / name

    def _spec_path(self, name: str) -> Path:
        return self._loop_dir(name) / self.SPEC_FILENAME

    def _state_path(self, name: str) -> Path:
        return self._loop_dir(name) / self.STATE_FILENAME

    # ── 安全校验 ──────────────────────────────────────────────────────

    @staticmethod
    def _is_safe_name(name: str) -> bool:
        return bool(name) and bool(_SAFE_NAME_PATTERN.match(name))

    @classmethod
    def _require_safe_name(cls, name: str) -> None:
        """Raise ``LoopNameError`` if ``name`` could enable path traversal.

        ``LoopNameError`` multi-inherits ``ValueError`` so callers that still
        ``except ValueError`` keep working (deep-diagnosis-2026-07-24 P0-2).
        """
        if not cls._is_safe_name(name):
            from vibesop.core.exceptions import LoopNameError

            raise LoopNameError(name, f"must match {_SAFE_NAME_PATTERN.pattern}")

    # ── 文件 IO ───────────────────────────────────────────────────────

    @staticmethod
    def _load_model(path: Path, model_cls: type[T]) -> T | None:
        """安全加载 JSON 文件并反序列化为 pydantic 模型。

        三种结果：
            - 文件不存在 → ``None``（debug 日志，正常首次访问）
            - JSON 损坏或 schema drift → ``None``（warning 日志，需排查）
            - 成功 → 模型实例
        """
        if not path.exists():
            logger.debug("Loop file does not exist: %s", path)
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Cannot read %s: %s", path, e)
            return None
        try:
            return model_cls.model_validate_json(text)
        except (json.JSONDecodeError, ValidationError) as e:
            # Back up the corrupt file for forensic analysis rather than
            # silently masking the data loss. Callers fall back to a fresh
            # model (load_state -> LoopState(spec=spec); load_spec -> None),
            # so the loop remains usable rather than silently disappearing.
            backup = path.with_name(path.name + ".corrupt")
            with contextlib.suppress(OSError):
                # Best-effort backup; the warning below still surfaces the issue.
                path.rename(backup)
            logger.warning(
                "Loop file %s had invalid JSON or schema (backed up to %s): %s",
                path,
                backup,
                e,
            )
            return None

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """原子写入：先写 ``.tmp`` 再 ``rename`` 覆盖目标。

        在 POSIX 上 ``rename`` 是原子的；Windows 上同盘 rename 也是原子的。
        ``.tmp`` 与目标位于同一目录（同盘）。
        """
        tmp = path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)  # cross-platform atomic replace


__all__ = ["LoopStore"]
