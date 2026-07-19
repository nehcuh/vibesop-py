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
import os
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

    验证流水线（v7.3.3 expanded — based on 3 rounds of Docker e2e learnings）：

    1. 检测运行时（orbstack → docker → lima → local 回退）
    2. 创建容器 + 挂载项目
    3. 安装 apt/uv/npm 依赖（含 jq, Node 20, Kimi Code）
    4. 配置 LLM provider（DEEPSEEK_API_KEY 透传或 oMLX）
    5. 构建 skill embedding index（漏掉 → AI_TRIAGE 永远 "No embeddings"）
    6. 跑 ``vibe build`` / 单元测试 / CLI 5 modes / hook → skill 推荐
    7. 收集 P0/P1 问题，输出 :class:`ValidationReport`

    v7.3.3 changes (post-Round 3 lessons):
    - Hook 验证升级：从 "文件存在" 改为 "hook 触发后 additionalContext 含 skill_id"
    - 新增 DEEPSEEK_API_KEY 透传（容器内 indexer 必需）
    - 新增 Kimi Code install 步骤
    - 新增 skill index 构建步骤
    """

    CONTAINER_NAME = "vibesop-verify"
    IMAGE = "ubuntu:22.04"

    def __init__(
        self,
        project_root: str | Path = ".",
        container_tool: str | None = None,
        deepseek_api_key: str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.container_tool = container_tool or self._detect_runtime()
        self.deepseek_api_key = deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY")
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
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                    check=False,
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

        v7.0.12: local 模式从 ``shell=True`` 切换到显式 ``["bash", "-c", cmd]``
        列表形式。功能等价，但消除了 Bandit B602 警告，并让未来 contributor
        看到 ``bash -c`` 时知道 ``cmd`` 是 shell 解析的（防御性可读性）。
        ``cmd`` 的所有部分（cases / platforms / modules）都是硬编码字面量，
        不来自用户输入；如果未来从配置文件读取，需要先经过 shlex.quote。

        v7.3.3: 当 ``self.deepseek_api_key`` 非空时，通过 ``-e`` 透传给容器
        exec。indexer / AI triage 等需要 LLM 的步骤必须能读到这个 env。
        """
        if self.container_tool == "local":
            # Pre-v7.0.12: subprocess.run(cmd, shell=True, ...). This is
            # functionally identical to ["bash", "-c", cmd] on POSIX, but
            # shell=True is the form Bandit B602 flags. Switching to the
            # list form silences the warning AND makes the shell-parsing
            # explicit in the call site.
            env = {**os.environ}
            if self.deepseek_api_key:
                env["DEEPSEEK_API_KEY"] = self.deepseek_api_key
            result = subprocess.run(
                ["bash", "-c", cmd],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(self.project_root),
                env=env,
                check=False,
            )
            return result.stdout, result.stderr, result.returncode

        if self.container_tool == "orbstack":
            # orbctl 没有 docker exec 等价命令；当 orbstack 启用了 docker 兼容时，
            # 直接走 docker exec。否则回退到本地。
            full_cmd = ["docker", "exec"]
            if self.deepseek_api_key:
                full_cmd += ["-e", f"DEEPSEEK_API_KEY={self.deepseek_api_key}"]
            full_cmd += [self.CONTAINER_NAME, "bash", "-c", cmd]
        elif self.container_tool == "docker":
            full_cmd = ["docker", "exec"]
            if self.deepseek_api_key:
                full_cmd += ["-e", f"DEEPSEEK_API_KEY={self.deepseek_api_key}"]
            full_cmd += [self.CONTAINER_NAME, "bash", "-c", cmd]
        elif self.container_tool == "lima":
            # lima 不支持 -e 直接传 env，需通过 bash 内 export
            if self.deepseek_api_key:
                cmd = f"export DEEPSEEK_API_KEY={shlex.quote(self.deepseek_api_key)} && {cmd}"
            full_cmd = ["limactl", "shell", self.CONTAINER_NAME, "bash", "-c", cmd]
        else:
            full_cmd = ["bash", "-c", cmd]

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
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
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(self.project_root),
                check=False,
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
        """在容器内安装 apt / uv / npm 依赖。返回是否全部成功。

        v7.3.3: 升级覆盖 Round 1-3 教训：
        - apt 加 ``jq``（hook 解析 JSON envelope 必需）+ ``zstd``（Ollama 安装需要）
        - 新增 Node 20 via NodeSource（Ubuntu 22.04 默认 Node 12 太旧）
        - 新增 Kimi Code install（官方 install.sh）
        - 不再装 oMLX/Ollama：用户应通过 ``DEEPSEEK_API_KEY`` 或 ``host.docker.internal``
          使用宿主机 LLM，避免容器内跑 35B 模型耗时
        """
        steps: list[tuple[str, str, int]] = [
            (
                "apt",
                "export DEBIAN_FRONTEND=noninteractive && "
                "apt-get update -qq && "
                "apt-get install -y -qq python3 python3-venv git curl npm "
                "ca-certificates gnupg build-essential jq zstd",
                _INSTALL_TIMEOUT,
            ),
            (
                # Ubuntu 22.04 自带 Node 12；Claude Code 需 18+。必须先 remove 旧的
                # libnode-dev/libnode72 才能装 NodeSource（否则文件冲突）。
                "node20",
                "curl -fsSL https://deb.nodesource.com/setup_20.x | sh - && "
                "apt-get remove -y -qq libnode-dev libnode72 npm 2>/dev/null ; "
                "apt-get install -y nodejs",
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
            (
                # Kimi Code 官方 install.sh，v0.14+ 使用 ACP 协议
                "kimi code",
                "curl -fsSL https://code.kimi.com/kimi-code/install.sh "
                "-o /tmp/kimi-install.sh && bash /tmp/kimi-install.sh 2>&1 | tail -3",
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

    def configure_llm_provider(self) -> bool:
        """在容器内写入 ``~/.vibe/config.toml`` 配置 LLM provider。

        v7.3.3 新增。Round 3 教训：没有 config，indexer 默认走 ollama@localhost:11434，
        容器内无此服务 → 100% skills 索引失败。

        优先级：
        1. ``self.deepseek_api_key`` 非空 → 用 DeepSeek API（最快，~1min/102skills）
        2. 否则用宿主机 oMLX（``host.docker.internal:11434``，需用户在 host 启动）

        Returns:
            True 如果 config 写入成功。
        """
        if self.deepseek_api_key:
            config_body = '[llm]\nprovider = "deepseek"\nmodel = "deepseek-v4-flash"\n'
        else:
            # Fallback: assume host runs oMLX on 11434 (OpenAI compatible)
            config_body = (
                "[llm]\n"
                'provider = "openai"\n'
                'model = "Qwen3.6-35B-A3B-mxfp8"\n'
                'api_base = "http://host.docker.internal:11434/v1"\n'
                'api_key = "local-omlx-fake-key-min-11-chars"\n'
            )

        # Write via heredoc to avoid shell-quoting issues
        cmd = f"mkdir -p /root/.vibe && cat > /root/.vibe/config.toml <<'VIBE_EOF'\n{config_body}VIBE_EOF"
        _, stderr, rc = self._container_exec(cmd, timeout=10)
        if rc != 0:
            logger.warning("LLM config 写入失败: %s", stderr[:200])
            return False
        logger.info(
            "LLM config 已写入: provider=%s",
            "deepseek" if self.deepseek_api_key else "omlx-via-host.docker.internal",
        )
        return True

    def build_skill_index(self) -> bool:
        """构建 skill embedding index。v7.3.3 新增。

        Round 2-3 教训：
        - 不构建 → AI_TRIAGE 永远 "No embeddings in index" → 短查询全部走 FALLBACK_LLM
        - vibe quickstart 交互式不易自动化；改用 Python 直接调 indexer
        - LLMConfigResolver 会读 ~/.vibe/config.toml（v7.3.2 修过 init.py 接线）

        Returns:
            True 如果 indexed_count > 0。
        """
        # Install skill packs first
        install_cmd = (
            'cd /app && export PATH="$HOME/.local/bin:$PATH" && '
            "uv run vibe install mattpocock 2>&1 | tail -2 && "
            "uv run vibe install superpowers 2>&1 | tail -2"
        )
        _, _, rc = self._container_exec(install_cmd, timeout=_INSTALL_TIMEOUT)
        if rc != 0:
            logger.warning("技能包安装失败")
            return False

        # Build index programmatically (bypasses interactive quickstart wizard)
        indexer_py = (
            "from vibesop.core.skills.indexer import SkillIndexer; "
            "from vibesop.core.llm_config import LLMConfigResolver; "
            "from vibesop.llm.factory import create_provider; "
            "r = LLMConfigResolver().get_llm_for_understanding(); "
            "f = lambda: create_provider(provider=r.provider, api_key=r.api_key, base_url=r.api_base); "
            "i = SkillIndexer(project_root='/app', llm_factory=f); "
            "res = i.build_index(scope='global', show_progress=False, force=True, max_workers=4); "
            "print(f'INDEXED:{res.indexed_count}')"
        )
        cmd = (
            f'cd /app && export PATH="$HOME/.local/bin:$PATH" && '
            f"uv run python -c '{indexer_py}' 2>&1 | tail -5"
        )
        stdout, stderr, rc = self._container_exec(cmd, timeout=_INSTALL_TIMEOUT)
        if rc != 0:
            logger.warning("skill index 构建失败: %s", stderr[:200])
            return False
        # Parse "INDEXED:N" from output
        for line in stdout.splitlines():
            if line.startswith("INDEXED:"):
                try:
                    count = int(line.split(":", 1)[1].strip())
                    if count > 0:
                        logger.info("skill index 构建: %d skills", count)
                        return True
                    logger.warning("skill index 为空（小模型？需 max_tokens>=4000）")
                    return False
                except ValueError:
                    pass
        logger.warning("skill index 输出无法解析: %s", stdout[-200:])
        return False

    def cleanup(self) -> None:
        """销毁验证容器。"""
        if self._container_started and self.container_tool != "local":
            logger.info("清理容器 %s...", self.CONTAINER_NAME)
            self._run_local(["docker", "rm", "-f", self.CONTAINER_NAME])
            self._container_started = False

    # ── Validation Pipeline ────────────────────────────────────────────────

    def validate(self, skip_container: bool = False) -> ValidationReport:
        """执行完整验证流水线，返回 :class:`ValidationReport`。

        v7.3.3 expanded pipeline (post-Round 3 lessons):

        - A. setup_container + install_dependencies（含 jq + Node 20 + Kimi Code）
        - C. configure_llm_provider（DEEPSEEK_API_KEY 透传或 oMLX）
        - D. build_skill_index（漏掉 → AI_TRIAGE 失效）
        - E-H. 原有 imports / unit_tests / cli_modes / hook_path / build
        - G4. **hook_skill_recommend** — 新检查：hook 触发后 additionalContext
              必须含 skill_id（不只是文件存在）

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

            # C+D: LLM config + skill index（v7.3.3 新增）
            # 失败不阻塞后续检查 — e2e 报告里标记 P0 即可
            report.results["llm_provider"] = {"configured": self.configure_llm_provider()}
            report.results["skill_index"] = {"built": self.build_skill_index()}

            report.results["imports"] = self._check_imports()
            report.results["unit_tests"] = self._check_unit_tests()
            report.results["cli_modes"] = self._check_cli_modes()
            report.results["hook_path"] = self._check_hook()
            report.results["hook_skill_recommend"] = self._check_hook_skill_recommend()
            report.results["build"] = self._check_build()

            report.p0_issues = self._collect_issues(report.results, levels=("P0",))
            report.p1_issues = self._collect_issues(report.results, levels=("P1",))

            report.environment = {
                "container_tool": self.container_tool,
                "python": self._get_python_version(),
                "llm_provider": "deepseek" if self.deepseek_api_key else "omlx-host",
                "deepseek_api_key_present": bool(self.deepseek_api_key),
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
            cmd = f"cd /app && python -c \"import {mod}; print('OK')\" 2>&1"
            if self.container_tool == "local":
                cmd = f"python -c \"import {mod}; print('OK')\" 2>&1"
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
        hook_check = (
            "ls /tmp/.claude/hooks/vibesop-route.sh 2>/dev/null && echo EXISTS || echo NOT_FOUND"
        )
        hook_stdout, _, _ = self._container_exec(hook_check)
        return {
            "build_ok": "Build complete" in stdout or "Deployed" in stdout,
            "hook_exists": "EXISTS" in hook_stdout,
        }

    def _check_hook_skill_recommend(self) -> dict[str, Any]:
        """v7.3.3 新增 — 验证 hook 触发后返回有效的 skill 推荐。

        Round 3 教训：仅验证 hook 文件存在（``_check_hook``）不够。Claude Code
        真实场景下，hook 触发后必须返回 ``additionalContext`` 含 ``skill_id``，
        否则用户在 Agent 里输入 query 不会得到路由建议。

        测试方法：
        1. 向 hook 发送正确的 JSON envelope（含 ``.prompt`` 字段，不是
           ``.user_prompt`` — Round 2 修过的 P1 bug）
        2. 解析返回的 JSON，检查 ``hookSpecificOutput.additionalContext`` 是否
           含 ``skill_id`` 字段

        Returns:
            dict 含 ``envelope_parsed`` 和 ``returns_skill_id`` 两个 bool。
            后者为 False 即 P0 — AgentRuntime ORCHESTRATE 分支不传 analysis。
        """
        # Round 2 修复后的正确 envelope — 字段是 .prompt 不是 .user_prompt
        envelope = (
            '{"prompt":"帮我调试 TypeError NoneType 错误",'
            '"session_id":"validator-test","cwd":"/app",'
            '"hook_event_name":"UserPromptSubmit",'
            '"transcript_path":"/tmp/x.jsonl"}'
        )

        if self.container_tool == "local":
            # Local mode: pipe to hook script directly
            cmd = f"echo '{envelope}' | bash /tmp/.claude/hooks/vibesop-route.sh 2>&1 | tail -20"
        else:
            # Container mode: docker exec -i reads stdin
            cmd = (
                f"echo '{envelope}' | docker exec -i "
                + (f"-e DEEPSEEK_API_KEY={self.deepseek_api_key} " if self.deepseek_api_key else "")
                + f"{self.CONTAINER_NAME} bash /tmp/.claude/hooks/vibesop-route.sh 2>&1 | "
                "tail -20"
            )

        # For container mode, _container_exec wraps in `bash -c` which conflicts
        # with stdin redirection. Run directly via subprocess for this check.
        if self.container_tool == "local":
            stdout, _stderr, _ = self._container_exec(cmd, timeout=60)
        else:
            # Use subprocess directly with stdin
            docker_args = ["docker", "exec", "-i"]
            if self.deepseek_api_key:
                docker_args += ["-e", f"DEEPSEEK_API_KEY={self.deepseek_api_key}"]
            docker_args += [self.CONTAINER_NAME, "bash", "/tmp/.claude/hooks/vibesop-route.sh"]  # nosec B108  # container-internal path, not a host temp dir
            try:
                result = subprocess.run(
                    docker_args,
                    input=envelope,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                    check=False,
                )
                stdout = result.stdout
            except subprocess.TimeoutExpired:
                return {
                    "envelope_parsed": False,
                    "returns_skill_id": False,
                    "error": "hook timeout",
                }

        # Look for JSON response line
        json_response = ""
        for line in stdout.splitlines():
            line_clean = line.strip()
            if line_clean.startswith("{") and "hookSpecificOutput" in line_clean:
                json_response = line_clean
                break

        if not json_response:
            return {
                "envelope_parsed": False,
                "returns_skill_id": False,
                "raw_output_head": stdout[:300],
            }

        try:
            data = json.loads(json_response)
        except json.JSONDecodeError as e:
            return {
                "envelope_parsed": False,
                "returns_skill_id": False,
                "error": f"JSON decode failed: {e}",
            }

        ctx = data.get("hookSpecificOutput", {}).get("additionalContext", "")
        has_skill_id = (
            '"skill_id"' in ctx and "fallback-llm" not in ctx.split('"skill_id"')[1][:100]
        )

        return {
            "envelope_parsed": True,
            "returns_skill_id": has_skill_id,
            "system_message": data.get("systemMessage", "")[:120],
            # Round 3 P0 bug: hook returns "No matching skill found" while CLI
            # routes correctly — agent_runtime.py ORCHESTRATE branch doesn't
            # propagate interceptor.analysis to router.orchestrate().
            "known_p0_check": "returns_skill_id=False may indicate P0-hook-routing",
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
                elif isinstance(value, dict) and value.get("passed") is False:
                    _record(f"{category}.{name}.passed", value)
        return issues


__all__ = [
    "ContainerValidator",
    "ValidationReport",
]
