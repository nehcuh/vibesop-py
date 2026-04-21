"""VibeSOP LLM 配置管理 - 统一的 LLM 配置和降级策略.

该模块提供了：
1. VibeSOP 配置文件中的 LLM 配置读取
2. Agent 环境（Claude Code, Cursor 等）的 LLM 检测
3. LLM 配置的优先级和降级策略

优先级：
1. Agent 环境的 LLM（最高优先级）
2. VibeSOP 配置的 LLM
3. 环境变量中的 LLM
4. 默认配置（最低优先级）
"""

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()


class LLMSource(Enum):
    """LLM 配置来源"""
    AGENT_ENV = "agent_environment"  # Claude Code, Cursor 等 Agent 环境
    VIBESOP_CONFIG = "vibesop_config"  # VibeSOP 配置文件
    ENV_VAR = "environment_variable"  # 环境变量
    DEFAULT = "default"  # 默认配置


@dataclass
class LLMConfig:
    """LLM 配置"""

    provider: str
    model: str
    api_key: str | None = None
    api_base: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    source: LLMSource = LLMSource.DEFAULT
    confidence: float = 1.0


class VibeSOPConfigManager:
    """VibeSOP 配置管理器"""

    CONFIG_PATHS = [
        Path(".vibe/config.yaml"),
        Path(".vibe/llm.yaml"),
        Path.home() / ".vibe" / "config.yaml",
        Path.home() / ".vibe" / "llm.yaml",
    ]

    @classmethod
    def get_llm_config(cls) -> LLMConfig | None:
        """从 VibeSOP 配置文件读取 LLM 配置"""

        for config_path in cls.CONFIG_PATHS:
            if not config_path.exists():
                continue

            try:
                with config_path.open() as f:
                    data = yaml.safe_load(f)

                # 检查 LLM 配置
                if "llm" in data:
                    llm_data = data["llm"]

                    return LLMConfig(
                        provider=llm_data.get("provider", "anthropic"),
                        model=llm_data.get("model", "claude-sonnet-4-6-20250514"),
                        api_key=llm_data.get("api_key"),
                        api_base=llm_data.get("api_base"),
                        temperature=llm_data.get("temperature", 0.7),
                        max_tokens=llm_data.get("max_tokens", 4096),
                        source=LLMSource.VIBESOP_CONFIG,
                    )

            except Exception as e:
                console.print(f"[dim]Warning: Failed to load {config_path}: {e}[/dim]")

        return None


class AgentEnvironmentDetector:
    """Agent 环境检测器"""

    AGENT_CONFIGS = {
        "claude-code": {
            "name": "Claude Code",
            "config_files": [
                Path(".claude/settings.json"),
                Path.home() / ".claude" / "settings.json",
            ],
            "provider": "anthropic",
            "model_detection": "model",
        },
        "cursor": {
            "name": "Cursor",
            "config_files": [
                Path(".cursor/settings.json"),
                Path.home() / ".cursor" / "settings.json",
            ],
            "provider": "anthropic",
            "model_detection": "model",
        },
        "continue-dev": {
            "name": "Continue.dev",
            "config_files": [
                Path(".continue/settings.json"),
                Path.home() / ".continue" / "settings.json",
            ],
            "provider": "mixed",  # 支持多个提供商
            "model_detection": "models",
        },
        "aider": {
            "name": "Aider",
            "config_files": [
                Path(".aider.conf.yaml"),
                Path.home() / ".aider.conf.yaml",
            ],
            "provider": "mixed",
            "model_detection": "model",
        },
        "kimi-cli": {
            "name": "Kimi Code CLI",
            "config_files": [
                Path(".kimi/settings.json"),
                Path.home() / ".kimi" / "settings.json",
            ],
            "provider": "mixed",
            "model_detection": "model",
        },
    }

    @classmethod
    def detect_agent(cls) -> str | None:
        """检测当前 Agent 环境"""

        for agent_id, agent_config in cls.AGENT_CONFIGS.items():
            for config_file in agent_config["config_files"]:
                if config_file.exists():
                    return agent_id

        return None

    @classmethod
    def get_agent_llm_config(cls) -> LLMConfig | None:
        """从 Agent 环境获取 LLM 配置"""

        agent_id = cls.detect_agent()
        if not agent_id:
            return None

        agent_config = cls.AGENT_CONFIGS[agent_id]
        config_file = agent_config["config_files"][0]

        try:
            with config_file.open() as f:
                data = json.load(f)

            # 根据不同的 Agent 读取配置
            model = data.get(agent_config["model_detection"])

            # Claude Code / Cursor
            if agent_id in ["claude-code", "cursor"]:
                if model:
                    # Claude 模型名称映射
                    model_mapping = {
                        "claude-sonnet-4-20250514": "claude-sonnet-4-6-20250514",
                        "claude-3-5-sonnet-20241022": "claude-3-5-sonnet-20241022",
                    }
                    claude_model = model_mapping.get(model, model)

                    return LLMConfig(
                        provider="anthropic",
                        model=claude_model,
                        api_key=None,  # Agent 会管理 API key
                        source=LLMSource.AGENT_ENV,
                        confidence=0.95,  # Agent 配置置信度高
                    )

            # Continue.dev
            elif agent_id == "continue-dev":
                if isinstance(model, dict):
                    provider = model.get("provider")
                    model_id = model.get("model")

                    if provider and model_id:
                        return LLMConfig(
                            provider=provider,
                            model=model_id,
                            api_key=None,  # Agent 会管理
                            source=LLMSource.AGENT_ENV,
                            confidence=0.90,
                        )

        except Exception as e:
            console.print(f"[dim]Warning: Failed to read Agent config: {e}[/dim]")

        return None


class EnvVarLLMDetector:
    """环境变量 LLM 检测器"""

    @classmethod
    def get_llm_config(cls) -> LLMConfig | None:
        """从环境变量读取 LLM 配置"""

        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            return LLMConfig(
                provider="anthropic",
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6-20250514"),
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                api_base=os.getenv("ANTHROPIC_BASE_URL"),
                temperature=float(os.getenv("ANTHROPIC_TEMPERATURE", "0.7")),
                max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096")),
                source=LLMSource.ENV_VAR,
            )

        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            return LLMConfig(
                provider="openai",
                model=os.getenv("OPENAI_MODEL", "gpt-4"),
                api_key=os.getenv("OPENAI_API_KEY"),
                api_base=os.getenv("OPENAI_BASE_URL"),
                temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
                max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
                source=LLMSource.ENV_VAR,
            )

        return None


class LLMConfigResolver:
    """LLM 配置解析器 - 统一的配置获取和降级策略"""

    def __init__(self) -> None:
        self.logger = console

    def resolve_llm_config(
        self,
        skill_requirements: dict[str, Any] | None = None,
        prefer_agent: bool = True
    ) -> LLMConfig | None:
        """解析 LLM 配置（使用降级策略）

        Args:
            skill_requirements: 技能要求的 LLM 配置（可选）
            prefer_agent: 是否优先使用 Agent 的 LLM（默认 True）

        Returns:
            LLM 配置对象，如果没有任何配置则返回 None
        """

        self.logger.print("[dim]Resolving LLM configuration...[/dim]")

        # 优先级 1: Agent 环境的 LLM
        if prefer_agent:
            agent_config = AgentEnvironmentDetector.get_agent_llm_config()
            if agent_config:
                self.logger.print(f"  ✓ Using Agent's LLM: {agent_config.provider}/{agent_config.model}")

                # 验证是否满足技能需求
                if skill_requirements and self._meets_requirements(agent_config, skill_requirements):
                    return agent_config
                else:
                    self.logger.print("  ⚠ Agent's LLM doesn't meet skill requirements")

        # 优先级 2: VibeSOP 配置文件
        vibesop_config = VibeSOPConfigManager.get_llm_config()
        if vibesop_config:
            self.logger.print(f"  ✓ Using VibeSOP config: {vibesop_config.provider}/{vibesop_config.model}")

            if skill_requirements and self._meets_requirements(vibesop_config, skill_requirements):
                return vibesop_config
            else:
                self.logger.print("  ⚠ VibeSOP config doesn't meet skill requirements")

        # 优先级 3: 环境变量
        env_config = EnvVarLLMDetector.get_llm_config()
        if env_config:
            self.logger.print(f"  ✓ Using environment variables: {env_config.provider}/{env_config.model}")

            if skill_requirements and self._meets_requirements(env_config, skill_requirements):
                return env_config
            else:
                self.logger.print("  ⚠ Environment config doesn't meet skill requirements")

        # 优先级 4: 默认配置（不推荐用于生产）
        if skill_requirements:
            self.logger.print("  ⚠ No suitable LLM found, using defaults")
            return self._create_default_config(skill_requirements)

        self.logger.print("  ❌ No LLM configuration found")
        return None

    def _meets_requirements(
        self,
        config: LLMConfig,
        requirements: dict[str, Any]
    ) -> bool:
        """验证配置是否满足技能需求"""

        # 检查提供商
        if "provider" in requirements:
            required_provider = requirements["provider"]
            if config.provider != required_provider:
                return False

        # 检查模型
        if "recommended_models" in requirements:
            recommended_models = requirements["recommended_models"]
            if config.model not in recommended_models:
                # 检查是否是兼容模型
                return self._is_compatible_model(config.model, recommended_models)

        # 检查上下文窗口
        if "min_requirements" in requirements:
            min_req = requirements["min_requirements"]
            # TODO: 检查模型的实际能力
            # 这里简化处理，假设常用模型都满足
            pass

        return True

    def _is_compatible_model(
        self,
        model: str,
        recommended_models: list[str]
    ) -> bool:
        """检查模型是否兼容推荐模型"""

        # 简化版兼容性检查
        # 实际实现应该检查模型的能力
        model_family = model.split("-", maxsplit=1)[0] if "-" in model else model

        for recommended in recommended_models:
            rec_family = recommended.split("-")[0] if "-" in recommended else recommended
            if model_family == rec_family:
                return True

        return False

    def _create_default_config(
        self,
        requirements: dict[str, Any]
    ) -> LLMConfig:
        """创建默认配置"""

        # 使用推荐配置
        provider = requirements.get("provider", "anthropic")
        models = requirements.get("recommended_models", ["claude-sonnet-4-6-20250514"])

        return LLMConfig(
            provider=provider,
            model=models[0],
            api_key=None,
            source=LLMSource.DEFAULT,
            confidence=0.3,  # 低置信度
        )

    def get_llm_for_understanding(self) -> LLMConfig | None:
        """获取用于技能理解的 LLM 配置

        与 resolve_llm_config 不同，这个方法专注于理解阶段的 LLM 选择
        理解阶段不需要太高的准确性，快速响应更重要

        Returns:
            LLM 配置对象
        """

        # 理解阶段优先级：速度 > 准确性
        # 1. Agent 环境（最快）
        agent_config = AgentEnvironmentDetector.get_agent_llm_config()
        if agent_config:
            self.logger.print(f"[dim]  Using Agent's LLM for understanding: {agent_config.model}[/dim]")
            return agent_config

        # 2. 环境变量
        env_config = EnvVarLLMDetector.get_llm_config()
        if env_config:
            self.logger.print(f"[dim]  Using env LLM for understanding: {env_config.model}[/dim]")
            return env_config

        # 3. VibeSOP 配置
        vibesop_config = VibeSOPConfigManager.get_llm_config()
        if vibesop_config:
            self.logger.print(f"[dim]  Using VibeSOP config for understanding: {vibesop_config.model}[/dim]")
            return vibesop_config

        # 4. 默认（使用 Haiku - 快速且便宜）
        self.logger.print("[dim]  Using default LLM (claude-3-haiku-20240307) for understanding[/dim]")
        return LLMConfig(
            provider="anthropic",
            model="claude-3-haiku-20240307",
            source=LLMSource.DEFAULT,
        )


# 便捷函数
def get_llm_config(
    skill_requirements: dict[str, Any] | None = None,
    prefer_agent: bool = True
) -> LLMConfig | None:
    """获取 LLM 配置（便捷函数）

    Args:
        skill_requirements: 技能的 LLM 需求（可选）
        prefer_agent: 是否优先使用 Agent 的 LLM

    Returns:
        LLM 配置对象
    """
    resolver = LLMConfigResolver()
    return resolver.resolve_llm_config(skill_requirements, prefer_agent)


def get_agent_llm_config() -> LLMConfig | None:
    """获取 Agent 环境的 LLM 配置（便捷函数）"""
    return AgentEnvironmentDetector.get_agent_llm_config()


def is_in_agent_environment() -> bool:
    """检查是否在 Agent 环境中（便捷函数）"""
    return AgentEnvironmentDetector.detect_agent() is not None
