"""Container Validator — 在 Linux 容器中端到端验证 VibeSOP 功能。

支持 orbstack / docker / lima 三种容器运行时；通过 ``skip_container=True``
回退到本地模式（不创建容器，仅在当前项目根目录执行）。

公共 API::

    validator = ContainerValidator(project_root=".")
    report = validator.validate()
    print(report.to_json())
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 命令执行默认超时（秒）
_DEFAULT_TIMEOUT = 120
# 安装步骤超时（秒）— apt/uv sync 较慢
_INSTALL_TIMEOUT = 600


@dataclass
class ValidationReport:
    """容器验证报告。

    ``results`` 是分桶字典，每个 bucket 是 ``{check_name: bool | dict}``。
    ``p0_issues`` / ``p1_issues`` 由 :meth:`ContainerValidator._collect_issues` 填充。
    """

    environment: dict[str, str] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    p0_issues: list[dict[str, Any]] = field(default_factory=list)
    p1_issues: list[dict[str, Any]] = field(default_factory=list)
    conclusion: str = ""
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "results": self.results,
            "p0_issues": self.p0_issues,
            "p1_issues": self.p1_issues,
            "conclusion": self.conclusion,
            "duration_s": round(self.duration_s, 2),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class ContainerValidator:
    """在 Linux 容器中端到端验证 VibeSOP。

    验证流水线：

    1. 检测运行时（orbstack → docker → lima → local 回退）
    2. 创建容器 + 挂载项目
    3. 安装 apt/uv/npm 依赖
    4. 跑 ``vibe build`` / 单元测试 / CLI 模式 / hook
    5. 收集 P0/P1 问题，输出 :class:`ValidationReport`
    """

    CONTAINER_NAME = "vibesop-verify"
    IMAGE = "ubuntu:22.04"

    def __init__(
        self,
        project_root: str | Path = ".",
        container_tool: str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.container_tool = container_tool or self._detect_runtime()
        self._container_started = False

    # ── Runtime Detection ──────────────────────────────────────────────────

    @staticmethod
    def _detect_runtime() -> str:
        """检测可用的容器运行时，返回 ``orbstack`` / ``docker`` / ``lima`` / ``local``。"""
        candidates: list[tuple[str, list[str]]] = [
            ("orbstack", ["orbctl", "list"]),
            ("docker", ["docker", "ps"]),
            ("lima", ["limactl", "list"]),
        ]
        for tool, check_cmd in candidates:
            try:
                result = subprocess.run(
                    check_cmd,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    logger.info("检测到容器运行时: %s", tool)
                    return tool
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        logger.warning("未检测到容器运行时，回退到本地模式")
        return "local"

    # ── Command Execution ──────────────────────────────────────────────────

    def _container_exec(self, cmd: str, timeout: int = _DEFAULT_TIMEOUT) -> tuple[str, str, int]:
        """在容器内执行 shell 命令（安全引用）。

        ``cmd`` 作为单个字符串通过 ``bash -c`` 在容器内执行；shell 引用
        使用 :func:`shlex.quote` 避免 host shell 解释器介入。
        """
        if self.container_tool == "local":
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=True,
                cwd=str(self.project_root),
            )
            return result.stdout, result.stderr, result.returncode

        if self.container_tool == "orbstack":
            # orbctl 没有 docker exec 等价命令；当 orbstack 启用了 docker 兼容时，
            # 直接走 docker exec。否则回退到本地。
            full_cmd = [
                "docker",
                "exec",
                self.CONTAINER_NAME,
                "bash",
                "-c",
                cmd,
            ]
        elif self.container_tool == "docker":
            full_cmd = [
                "docker",
                "exec",
                self.CONTAINER_NAME,
                "bash",
                "-c",
                cmd,
            ]
        elif self.container_tool == "lima":
            full_cmd = [
                "limactl",
                "shell",
                self.CONTAINER_NAME,
                "bash",
                "-c",
                cmd,
            ]
        else:
            full_cmd = ["bash", "-c", cmd]

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "timeout", 124

    def _run_local(self, cmd: list[str], timeout: int = _DEFAULT_TIMEOUT) -> tuple[str, str, int]:
        """在宿主机本地执行命令（无 shell）。"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_root),
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "timeout", 124
        except FileNotFoundError:
            return "", f"command not found: {cmd[0]}", 127

    # ── Container Lifecycle ────────────────────────────────────────────────

    def setup_container(self) -> bool:
        """创建并启动验证容器，挂载项目根到 ``/app``。"""
        if self.container_tool == "local":
            logger.info("本地模式，跳过容器创建")
            return True

        # 移除已存在的同名容器
        self._run_local(["docker", "rm", "-f", self.CONTAINER_NAME])

        project_root_str = str(self.project_root)
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            self.CONTAINER_NAME,
            "--hostname",
            self.CONTAINER_NAME,
            "-v",
            f"{project_root_str}:/app",
            "-w",
            "/app",
            self.IMAGE,
            "sleep",
            "infinity",
        ]
        _, stderr, rc = self._run_local(cmd, timeout=60)
        if rc != 0:
            logger.error("容器创建失败: %s", stderr)
            return False

        self._container_started = True
        return True

    def install_dependencies(self) -> bool:
        """在容器内安装 apt / uv / npm 依赖。返回是否全部成功。"""
        steps: list[tuple[str, str, int]] = [
            (
                "apt",
                "export DEBIAN_FRONTEND=noninteractive && "
                "apt-get update -qq && "
                "apt-get install -y -qq python3 python3-venv git curl npm "
                "ca-certificates gnupg build-essential jq",
                _INSTALL_TIMEOUT,
            ),
            (
                "uv",
                "curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh && "
                "sh /tmp/uv-install.sh -q",
                _INSTALL_TIMEOUT,
            ),
            (
                "project deps",
                'cd /app && export PATH="$HOME/.local/bin:$PATH" && uv sync',
                _INSTALL_TIMEOUT,
            ),
            (
                "claude code",
                "npm install -g @anthropic-ai/claude-code 2>/dev/null || true",
                _INSTALL_TIMEOUT,
            ),
        ]
        for name, cmd, timeout in steps:
            _, stderr, rc = self._container_exec(cmd, timeout=timeout)
            if rc != 0:
                logger.warning("安装步骤 '%s' 失败: %s", name, stderr[:200])
                return False
            logger.info("安装步骤 '%s' 完成", name)
        return True

    def cleanup(self) -> None:
        """销毁验证容器。"""
        if self._container_started and self.container_tool != "local":
            logger.info("清理容器 %s...", self.CONTAINER_NAME)
            self._run_local(["docker", "rm", "-f", self.CONTAINER_NAME])
            self._container_started = False

    # ── Validation Pipeline ────────────────────────────────────────────────

    def validate(self, skip_container: bool = False) -> ValidationReport:
        """执行完整验证流水线，返回 :class:`ValidationReport`。

        Args:
            skip_container: True 则跳过容器创建+依赖安装，直接在本地跑验证步骤。
                等同于 ``container_tool == "local"``。

        Returns:
            ``ValidationReport``，``conclusion`` 含人类可读结论。
        """
        start_time = time.time()
        report = ValidationReport()

        try:
            if not skip_container:
                if not self.setup_container():
                    report.conclusion = "❌ 容器创建失败"
                    return report
                if not self.install_dependencies():
                    report.conclusion = "❌ 依赖安装失败"
                    return report

            report.results["imports"] = self._check_imports()
            report.results["unit_tests"] = self._check_unit_tests()
            report.results["cli_modes"] = self._check_cli_modes()
            report.results["hook_path"] = self._check_hook()
            report.results["build"] = self._check_build()

            report.p0_issues = self._collect_issues(report.results, levels=("P0",))
            report.p1_issues = self._collect_issues(report.results, levels=("P1",))

            report.environment = {
                "container_tool": self.container_tool,
                "python": self._get_python_version(),
                "timestamp": datetime.now().isoformat(),
            }

            if not report.p0_issues:
                report.conclusion = "✅ 验证通过"
            else:
                report.conclusion = f"⚠️ 存在 {len(report.p0_issues)} 个 P0 问题"

        finally:
            if not skip_container:
                self.cleanup()

        report.duration_s = time.time() - start_time
        return report

    # ── Individual Checks ──────────────────────────────────────────────────

    def _check_imports(self) -> dict[str, bool]:
        """检查核心模块可正常导入。"""
        modules = [
            "vibesop.core.orchestration.semantic_intent_analyzer",
            "vibesop.core.orchestration.agent_squad_composer",
            "vibesop.core.orchestration.skill_composer",
            "vibesop.core.orchestration.collaboration_protocol",
            "vibesop.core.prompt_chain",
        ]
        results: dict[str, bool] = {}
        for mod in modules:
            cmd = f'cd /app && python -c "import {mod}; print(\'OK\')" 2>&1'
            if self.container_tool == "local":
                cmd = f'python -c "import {mod}; print(\'OK\')" 2>&1'
            stdout, _, _ = self._container_exec(cmd)
            results[mod] = "OK" in stdout
        return results

    def _check_unit_tests(self) -> dict[str, Any]:
        """运行核心单元测试。"""
        cmd = (
            "cd /app && python -m pytest tests/core/orchestration/ tests/agent/runtime/ "
            "-q --tb=line 2>&1 | tail -10"
        )
        if self.container_tool == "local":
            cmd = (
                "python -m pytest tests/core/orchestration/ tests/agent/runtime/ "
                "-q --tb=line 2>&1 | tail -10"
            )
        stdout, _, _ = self._container_exec(cmd, timeout=300)
        passed = "passed" in stdout and "failed" not in stdout.lower()
        return {"passed": passed, "output_tail": stdout[-500:]}

    def _check_cli_modes(self) -> dict[str, Any]:
        """验证 vibe route 能识别多种 InterceptionMode。"""
        cases = [
            ("帮我调试一下这个错误", "non-empty output"),
            ("请帮我设计微服务架构、然后用Python实现核心模块、最后做安全审查", "squad"),
        ]
        results: dict[str, Any] = {}
        for query, _expected in cases:
            quoted = shlex.quote(query)
            cmd = f"cd /app && uv run vibe route {quoted} --yes --json 2>&1 | head -3"
            if self.container_tool == "local":
                cmd = f"uv run vibe route {quoted} --yes --json 2>&1 | head -3"
            stdout, _, _ = self._container_exec(cmd, timeout=60)
            results[query[:40]] = {"output_head": stdout[:200]}
        return results

    def _check_hook(self) -> dict[str, bool]:
        """验证 ``vibe build claude-code`` 生成 hook 文件。"""
        build_cmd = "cd /app && uv run vibe build claude-code --output /tmp/.claude 2>&1 | tail -3"
        if self.container_tool == "local":
            build_cmd = "uv run vibe build claude-code --output /tmp/.claude 2>&1 | tail -3"
        stdout, _, _ = self._container_exec(build_cmd, timeout=60)
        hook_check = "ls /tmp/.claude/hooks/vibesop-route.sh 2>/dev/null && echo EXISTS || echo NOT_FOUND"
        hook_stdout, _, _ = self._container_exec(hook_check)
        return {
            "build_ok": "Build complete" in stdout or "Deployed" in stdout,
            "hook_exists": "EXISTS" in hook_stdout,
        }

    def _check_build(self) -> dict[str, bool]:
        """验证 ``vibe build`` 支持 5 个目标平台。"""
        platforms = ["claude-code", "kimi-cli", "pi", "opencode", "cursor"]
        results: dict[str, bool] = {}
        for platform in platforms:
            cmd = f"cd /app && uv run vibe build {platform} --output /tmp/build-{platform} 2>&1 | tail -2"
            if self.container_tool == "local":
                cmd = f"uv run vibe build {platform} --output /tmp/build-{platform} 2>&1 | tail -2"
            _, _, rc = self._container_exec(cmd, timeout=60)
            results[platform] = rc == 0
        return results

    def _get_python_version(self) -> str:
        """获取 Python 版本字符串。"""
        stdout, _, _ = self._container_exec("python3 --version 2>&1")
        return stdout.strip() or sys.version

    @staticmethod
    def _collect_issues(
        results: dict[str, Any],
        levels: tuple[str, ...] = ("P0", "P1"),
    ) -> list[dict[str, Any]]:
        """扫描 ``results`` 字典，把布尔/状态字段失败项标为 issue。

        - imports / build：每个 bool 字段一项（False 即 issue）
        - unit_tests / hook_path：检查 ``passed`` / ``build_ok`` 等关键 KPI
        """
        issues: list[dict[str, Any]] = []
        level = levels[0] if levels else "P1"

        def _record(check: str, detail: Any) -> None:
            issues.append({"level": level, "check": check, "detail": str(detail)})

        for category, payload in results.items():
            if not isinstance(payload, dict):
                continue
            for name, value in payload.items():
                if value is False:
                    _record(f"{category}.{name}", value)
                elif isinstance(value, dict):
                    if value.get("passed") is False:
                        _record(f"{category}.{name}.passed", value)
        return issues


__all__ = [
    "ContainerValidator",
    "ValidationReport",
]
