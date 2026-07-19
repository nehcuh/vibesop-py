# pyright: ignore[reportArgumentType]
"""VibeSOP LLM 配置管理 - 统一的 LLM 配置和降级策略."""

import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

import yaml
from rich.console import Console

from vibesop.llm.models import (
    ANTHROPIC_DEFAULT_MODEL,
    OPENAI_SMART_MODEL,
)
from vibesop.llm.models import (
    PROVIDER_DEFAULT_MODELS as _PROVIDER_DEFAULT_MODELS,
)

console = Console()
logger = logging.getLogger(__name__)


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

    CONFIG_PATHS: ClassVar[list[Path]] = [
        Path(".vibe/config.toml"),
        Path(".vibe/config.yaml"),
        Path(".vibe/llm.toml"),
        Path(".vibe/llm.yaml"),
        Path.home() / ".vibe" / "config.toml",
        Path.home() / ".vibe" / "config.yaml",
        Path.home() / ".vibe" / "llm.toml",
        Path.home() / ".vibe" / "llm.yaml",
    ]

    @classmethod
    def get_llm_config(cls) -> LLMConfig | None:
        for config_path in cls.CONFIG_PATHS:
            if not config_path.exists():
                continue

            try:
                suffix = config_path.suffix.lower()
                if suffix == ".toml":
                    from vibesop.utils.encoding import load_toml_with_fallback

                    data = load_toml_with_fallback(config_path)
                else:
                    from vibesop.utils.encoding import read_text_with_fallback

                    data = yaml.safe_load(read_text_with_fallback(config_path)) or {}

                # 检查 LLM 配置
                if "llm" in data:
                    llm_data = data["llm"]

                    return LLMConfig(
                        provider=llm_data.get("provider", "deepseek"),
                        model=llm_data.get("model", "deepseek-v4-flash"),
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

    AGENT_CONFIGS: ClassVar[dict[str, dict[str, Any]]] = {
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
                Path(".kimi-code/settings.json"),
                Path.home() / ".kimi-code" / "settings.json",
            ],
            "provider": "mixed",
            "model_detection": "model",
        },
    }

    @classmethod
    def detect_agent(cls) -> tuple[str, Path] | None:
        for agent_id, agent_config in cls.AGENT_CONFIGS.items():
            for config_file in agent_config["config_files"]:
                if config_file.exists():
                    return agent_id, config_file
        return None

    @classmethod
    def get_agent_llm_config(cls) -> LLMConfig | None:
        detected = cls.detect_agent()
        if not detected:
            return None

        agent_id, config_file = detected
        agent_config = cls.AGENT_CONFIGS[agent_id]

        try:
            with config_file.open(encoding="utf-8") as f:
                data = json.load(f)

            # 根据不同的 Agent 读取配置
            model = data.get(agent_config["model_detection"])

            # Claude Code / Cursor
            if agent_id in ["claude-code", "cursor"]:
                if model:
                    # Claude 模型名称映射
                    model_mapping = {
                        "claude-sonnet-4-20250514": "claude-sonnet-4-6",
                        "claude-sonnet-4-6-20250514": "claude-sonnet-4-6",
                        "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
                    }
                    claude_model = model_mapping.get(model, model)

                    return LLMConfig(
                        provider="anthropic",
                        model=str(claude_model),
                        api_key=None,  # Agent 会管理 API key
                        source=LLMSource.AGENT_ENV,
                        confidence=0.95,  # Agent 配置置信度高
                    )

            # Continue.dev
            elif agent_id == "continue-dev" and isinstance(model, dict):
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
    """环境变量 LLM 检测器."""

    PROVIDER_ENV_MAP: ClassVar[dict[str, dict[str, str | None]]] = {
        "deepseek": {
            "api_key": "DEEPSEEK_API_KEY",
            "api_base": "DEEPSEEK_BASE_URL",
            "model": "DEEPSEEK_MODEL",
        },
        "kimi": {
            "api_key": "KIMI_API_KEY",
            "api_base": "KIMI_BASE_URL",
            "model": "KIMI_MODEL",
        },
        "zhipu": {
            "api_key": "ZHIPU_API_KEY",
            "api_base": "ZHIPU_BASE_URL",
            "model": "ZHIPU_MODEL",
        },
        "ollama": {
            "api_key": None,
            "api_base": "OLLAMA_BASE_URL",
            "model": "OLLAMA_MODEL",
        },
    }

    PROVIDER_DEFAULT_MODELS: ClassVar[dict[str, str]] = {
        **_PROVIDER_DEFAULT_MODELS,
        "ollama": "qwen3:35b-a3b-mlx",
    }

    PROVIDER_DEFAULT_BASES: ClassVar[dict[str, str]] = {
        "deepseek": "https://api.deepseek.com",
        "kimi": "https://api.moonshot.cn/v1",
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",
        "ollama": "http://localhost:11434/v1",
    }

    @classmethod
    def get_llm_config(cls) -> LLMConfig | None:
        generic_provider = os.getenv("VIBE_LLM_PROVIDER")
        if generic_provider:
            return cls._build_config(generic_provider)

        # Priority 2: Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            return cls._build_config(
                "anthropic",
                api_key_env="ANTHROPIC_API_KEY",
                base_url_env="ANTHROPIC_BASE_URL",
                model_env="ANTHROPIC_MODEL",
                default_model=ANTHROPIC_DEFAULT_MODEL,
            )

        # Priority 3: OpenAI
        if os.getenv("OPENAI_API_KEY"):
            return cls._build_config(
                "openai",
                api_key_env="OPENAI_API_KEY",
                base_url_env="OPENAI_BASE_URL",
                model_env="OPENAI_MODEL",
                default_model=OPENAI_SMART_MODEL,
            )

        # Priority 4: Provider-specific env vars (deepseek, kimi, zhipu, etc.)
        for provider_name, env_keys in cls.PROVIDER_ENV_MAP.items():
            api_key_env = env_keys.get("api_key")
            if api_key_env and os.getenv(api_key_env):
                return cls._build_config(provider_name)

        # Priority 5: Ollama (no API key; detect via base URL env or default localhost)
        ollama_base = os.getenv("OLLAMA_BASE_URL")
        if ollama_base or cls._is_ollama_reachable():
            return cls._build_config("ollama")

        return None

    @classmethod
    def _is_ollama_reachable(cls) -> bool:
        try:
            import urllib.request

            # v7.0.11: use safe_urlopen with block_private_hosts=False
            # because Ollama legitimately runs on localhost. Scheme is
            # hardcoded to http://localhost:11434 so no SSRF surface.
            from vibesop.utils.url_safety import safe_urlopen

            req = urllib.request.Request(
                "http://localhost:11434/api/tags",
                method="GET",
            )
            body = safe_urlopen(
                req,
                max_bytes=1024 * 1024,
                timeout=2,
                allowed_schemes=("http", "https"),
                block_private_hosts=False,
            )
            return bool(body)
        except Exception:
            return False

    @classmethod
    def _build_config(
        cls,
        provider: str,
        api_key_env: str | None = None,
        base_url_env: str | None = None,
        model_env: str | None = None,
        default_model: str | None = None,
    ) -> LLMConfig:
        provider_map = cls.PROVIDER_ENV_MAP.get(provider, {})

        _api_key_env = api_key_env or provider_map.get("api_key")
        _base_url_env = base_url_env or provider_map.get("api_base")
        _model_env = model_env or provider_map.get("model")

        api_key = os.getenv(_api_key_env) if _api_key_env else None
        api_base = os.getenv(_base_url_env) if _base_url_env else None
        if not api_base:
            api_base = cls.PROVIDER_DEFAULT_BASES.get(provider)
        model = (
            (os.getenv(_model_env) if _model_env else None)
            or default_model
            or cls.PROVIDER_DEFAULT_MODELS.get(provider, "default")
        )

        return LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=float(os.getenv("VIBE_LLM_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("VIBE_LLM_MAX_TOKENS", "4096")),
            source=LLMSource.ENV_VAR,
        )


class LLMConfigResolver:
    """LLM 配置解析器 - 统一的配置获取和降级策略"""

    def __init__(self) -> None:
        # Status/info output goes to stderr so it never pollutes stdout in
        # --json (machine-readable) mode. Pre-fix, `vibe route --json` emitted
        # "Using default LLM ..." on stdout before the JSON, breaking
        # json.loads for any consumer.
        self.logger = Console(stderr=True)

    def resolve_llm_config(
        self, skill_requirements: dict[str, Any] | None = None, prefer_agent: bool = True
    ) -> LLMConfig | None:
        self.logger.print("[dim]Resolving LLM configuration...[/dim]")

        # 优先级 1: Agent 环境的 LLM
        if prefer_agent:
            agent_config = AgentEnvironmentDetector.get_agent_llm_config()
            if agent_config:
                self.logger.print(
                    f"  ✓ Using Agent's LLM: {agent_config.provider}/{agent_config.model}"
                )

                # 验证是否满足技能需求
                if skill_requirements and self._meets_requirements(
                    agent_config, skill_requirements
                ):
                    return agent_config
                else:
                    self.logger.print("  ⚠ Agent's LLM doesn't meet skill requirements")

        # 优先级 2: VibeSOP 配置文件
        vibesop_config = VibeSOPConfigManager.get_llm_config()
        if vibesop_config:
            self.logger.print(
                f"  ✓ Using VibeSOP config: {vibesop_config.provider}/{vibesop_config.model}"
            )

            if skill_requirements and self._meets_requirements(vibesop_config, skill_requirements):
                return vibesop_config
            else:
                self.logger.print("  ⚠ VibeSOP config doesn't meet skill requirements")

        # 优先级 3: 环境变量
        env_config = EnvVarLLMDetector.get_llm_config()
        if env_config:
            self.logger.print(
                f"  ✓ Using environment variables: {env_config.provider}/{env_config.model}"
            )

            if skill_requirements and self._meets_requirements(env_config, skill_requirements):
                return env_config
            else:
                self.logger.print("  ⚠ Environment config doesn't meet skill requirements")

        # 优先级 4: 默认配置(不推荐用于生产)
        if skill_requirements:
            self.logger.print("  ⚠ No suitable LLM found, using defaults")
            return self._create_default_config(skill_requirements)

        self.logger.print("  ❌ No LLM configuration found")
        return None

    def _meets_requirements(self, config: LLMConfig, requirements: dict[str, Any]) -> bool:
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
            requirements["min_requirements"]
            # TODO: 检查模型的实际能力
            # 这里简化处理,假设常用模型都满足
            pass

        return True

    def _is_compatible_model(self, model: str, recommended_models: list[str]) -> bool:
        model_family = model.split("-", maxsplit=1)[0] if "-" in model else model

        for recommended in recommended_models:
            rec_family = recommended.split("-")[0] if "-" in recommended else recommended
            if model_family == rec_family:
                return True

        return False

    def _create_default_config(self, requirements: dict[str, Any]) -> LLMConfig:
        provider = requirements.get("provider", "deepseek")
        models = requirements.get("recommended_models", ["deepseek-v4-flash"])

        return LLMConfig(
            provider=provider,
            model=models[0],
            api_key=None,
            source=LLMSource.DEFAULT,
            confidence=0.3,  # 低置信度
        )

    def get_llm_for_understanding(self) -> LLMConfig | None:
        agent_config = AgentEnvironmentDetector.get_agent_llm_config()
        if agent_config:
            self.logger.print(
                f"[dim]  Using Agent's LLM for understanding: {agent_config.model}[/dim]"
            )
            return agent_config

        # 2. VibeSOP 配置 (用户显式声明优先于环境变量)
        vibesop_config = VibeSOPConfigManager.get_llm_config()
        if vibesop_config:
            # v7.3.4: changed from logger.print() to logger.debug() — the print
            # polluted JSON output of `vibe route --json` and other commands
            # that auto-resolve LLM provider via AgentRuntime (which now calls
            # this resolver on every hook invocation, post-Round 3 P0 fix).
            logger.debug(
                "Using VibeSOP config for understanding: %s/%s",
                vibesop_config.provider,
                vibesop_config.model,
            )
            return vibesop_config

        # 3. 环境变量
        env_config = EnvVarLLMDetector.get_llm_config()
        if env_config:
            self.logger.print(f"[dim]  Using env LLM for understanding: {env_config.model}[/dim]")
            return env_config

        # 4. 默认(使用 Haiku - 快速且便宜)
        self.logger.print("[dim]  Using default LLM (deepseek-v4-flash) for understanding[/dim]")
        return LLMConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            source=LLMSource.DEFAULT,
        )


# 便捷函数
def get_llm_config(
    skill_requirements: dict[str, Any] | None = None, prefer_agent: bool = True
) -> LLMConfig | None:
    resolver = LLMConfigResolver()
    return resolver.resolve_llm_config(skill_requirements, prefer_agent)


def get_agent_llm_config() -> LLMConfig | None:
    """获取 Agent 环境的 LLM 配置(便捷函数)"""
    return AgentEnvironmentDetector.get_agent_llm_config()


def is_in_agent_environment() -> bool:
    """检查是否在 Agent 环境中(便捷函数)"""
    return AgentEnvironmentDetector.detect_agent() is not None
