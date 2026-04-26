"""技能配置管理器 - 管理技能级别的 LLM 和其他配置.

该模块提供了:
1. 技能级别的 LLM 配置加载
2. 全局配置与技能配置的合并
3. 配置优先级:技能配置 > 全局配置 > 环境变量 > 默认值

使用方式:
    # 获取技能的 LLM 配置
    config = SkillConfigManager.get_skill_llm_config("my-skill")

    # 设置技能的 LLM 配置
    SkillConfigManager.set_skill_llm_config("my-skill", {
        "provider": "openai",
        "model": "gpt-4",
        "temperature": 0.7
    })
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from vibesop.core.llm_config import (
    LLMConfig,
    LLMConfigResolver,
    LLMSource,
)
from vibesop.core.models import SkillLifecycle

logger = logging.getLogger(__name__)
console = Console()

# Backward-compatible alias
SkillLifecycleState = SkillLifecycle


@dataclass
class SkillConfig:
    """技能配置"""

    skill_id: str
    enabled: bool = True
    priority: int = 50
    category: str = "development"
    scope: str = "global"

    # 生命周期状态 (v5.0 预埋)
    lifecycle: SkillLifecycle = field(default_factory=lambda: SkillLifecycle.ACTIVE)

    # 使用统计预留字段 (v5.1 评估体系将填充)
    usage_stats: dict[str, Any] = field(default_factory=dict)

    # 版本历史预留字段 (v5.1 版本追踪将填充)
    version_history: list[dict[str, Any]] = field(default_factory=list)

    # 评估上下文扩展槽 (v5.1 评分维度将填充)
    evaluation_context: dict[str, Any] = field(default_factory=dict)

    # LLM 配置
    requires_llm: bool = False
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_temperature: float | None = None
    llm_api_key: str | None = None
    llm_api_base: str | None = None

    # 路由配置
    routing_patterns: list[str] | None = None

    # 元数据
    auto_configured: bool = False
    confidence: float = 0.5


class SkillConfigManager:
    """技能配置管理器"""

    # 配置文件路径
    SKILL_CONFIG_FILE = Path(".vibe/skills/auto-config.yaml")
    GLOBAL_CONFIG_FILE = Path(".vibe/config.yaml")
    GLOBAL_CONFIG_HOME = Path.home() / ".vibe" / "config.yaml"

    @classmethod
    def get_skill_config(cls, skill_id: str) -> SkillConfig | None:
        """获取技能配置

        Args:
            skill_id: 技能 ID

        Returns:
            技能配置对象,如果不存在则返回 None
        """

        # 1. 尝试从技能配置文件读取
        skill_config = cls._load_skill_config_from_file(skill_id)
        if skill_config:
            return skill_config

        # 2. 如果没有找到,返回默认配置
        logger.debug(f"No config found for skill {skill_id}, using defaults")
        return SkillConfig(skill_id=skill_id)

    @classmethod
    def get_skill_llm_config(cls, skill_id: str) -> LLMConfig | None:
        """获取技能的 LLM 配置

        优先级:
        1. 技能级别的 LLM 配置(.vibe/skills/auto-config.yaml)
        2. 全局 LLM 配置(.vibe/config.yaml)
        3. 环境变量
        4. Agent 环境
        5. 默认配置

        Args:
            skill_id: 技能 ID

        Returns:
            LLM 配置对象
        """

        # 1. 尝试从技能配置文件读取
        skill_config = cls._load_skill_config_from_file(skill_id)

        if skill_config and skill_config.requires_llm and skill_config.llm_provider:
            # 技能有自己的 LLM 配置
            console.print(
                f"[dim]  Using skill-level LLM config for {skill_id}[/dim]"
            )

            return LLMConfig(
                provider=skill_config.llm_provider,
                model=skill_config.llm_model or "claude-sonnet-4-6",
                api_key=skill_config.llm_api_key,
                api_base=skill_config.llm_api_base,
                temperature=skill_config.llm_temperature or 0.7,
                source=LLMSource.VIBESOP_CONFIG,
                confidence=0.95,  # 技能配置置信度高
            )

        # 2. 使用全局 LLM 配置解析器
        console.print(
            f"[dim]  Using global LLM config for {skill_id}[/dim]"
        )

        resolver = LLMConfigResolver()
        return resolver.resolve_llm_config(prefer_agent=True)

    @classmethod
    def set_skill_llm_config(
        cls,
        skill_id: str,
        llm_config: dict[str, Any]
    ) -> None:
        """设置技能的 LLM 配置

        Args:
            skill_id: 技能 ID
            llm_config: LLM 配置字典
                - provider: 提供商(anthropic, openai, etc.)
                - model: 模型名称
                - temperature: 温度参数
                - api_key: API 密钥(可选)
                - api_base: API 基础 URL(可选)
        """

        # 加载现有配置
        config_data = cls._load_skill_config_file()

        # 确保结构存在
        if "skills" not in config_data:
            config_data["skills"] = {}

        if skill_id not in config_data["skills"]:
            config_data["skills"][skill_id] = {}

        # 设置 LLM 配置
        config_data["skills"][skill_id]["llm"] = llm_config
        config_data["skills"][skill_id]["requires_llm"] = True

        # 保存配置
        cls._save_skill_config_file(config_data)

        console.print(f"[green]✓ LLM config saved for skill: {skill_id}[/green]")
        console.print(f"[dim]  Provider: {llm_config.get('provider')}[/dim]")
        console.print(f"[dim]  Model: {llm_config.get('model')}[/dim]")

    @classmethod
    def list_skill_configs(cls) -> dict[str, SkillConfig]:
        """列出所有技能配置

        Returns:
            技能 ID -> 技能配置的字典
        """

        config_data = cls._load_skill_config_file()
        skill_configs = {}

        for skill_id, skill_data in config_data.get("skills", {}).items():
            skill_configs[skill_id] = SkillConfig(
                skill_id=skill_id,
                enabled=skill_data.get("enabled", True),
                priority=skill_data.get("priority", 50),
                category=skill_data.get("category", "development"),
            scope=skill_data.get("scope", "global"),
            lifecycle=SkillLifecycle(skill_data.get("lifecycle", "active")),
            usage_stats=skill_data.get("usage_stats", {}),
            version_history=skill_data.get("version_history", []),
            evaluation_context=skill_data.get("evaluation_context", {}) or skill_data.get("metadata", {}),
                requires_llm=skill_data.get("requires_llm", False),
                llm_provider=skill_data.get("llm", {}).get("provider"),
                llm_model=skill_data.get("llm", {}).get("model"),
                llm_temperature=skill_data.get("llm", {}).get("temperature"),
                routing_patterns=skill_data.get("routing", {}).get("patterns"),
                auto_configured=skill_data.get("metadata", {}).get("auto_configured", False),
                confidence=skill_data.get("metadata", {}).get("confidence", 0.5),
            )

        return skill_configs

    @classmethod
    def update_skill_config(
        cls,
        skill_id: str,
        updates: dict[str, Any]
    ) -> None:
        """更新技能配置

        Args:
            skill_id: 技能 ID
            updates: 要更新的配置字段
        """

        # 加载现有配置
        config_data = cls._load_skill_config_file()

        # 确保结构存在
        if "skills" not in config_data:
            config_data["skills"] = {}

        if skill_id not in config_data["skills"]:
            config_data["skills"][skill_id] = {}

        # 更新配置
        for key, value in updates.items():
            if key == "llm":
                # LLM 配置特殊处理
                if "llm" not in config_data["skills"][skill_id]:
                    config_data["skills"][skill_id]["llm"] = {}
                config_data["skills"][skill_id]["llm"].update(value)
            else:
                config_data["skills"][skill_id][key] = value

        # 保存配置
        cls._save_skill_config_file(config_data)

        logger.debug("[dim]config updated for skill: %s[/dim]", skill_id)

    @classmethod
    def set_enabled(cls, skill_id: str, enabled: bool) -> None:
        """设置技能的启用状态

        Args:
            skill_id: 技能 ID
            enabled: 是否启用
        """
        cls.update_skill_config(skill_id, {"enabled": enabled})

    @classmethod
    def set_scope(cls, skill_id: str, scope: str) -> None:
        """设置技能的作用域

        Args:
            skill_id: 技能 ID
            scope: 作用域 ("global", "project", "session")
        """
        cls.update_skill_config(skill_id, {"scope": scope})

    @classmethod
    def set_lifecycle(cls, skill_id: str, state: SkillLifecycle | str) -> None:
        """设置技能的生命周期状态

        Args:
            skill_id: 技能 ID
            state: 生命周期状态 ("draft", "active", "deprecated", "archived")
        """
        if isinstance(state, str):
            state = SkillLifecycle(state)
        cls.update_skill_config(skill_id, {"lifecycle": state.value})

    @classmethod
    def delete_skill_config(cls, skill_id: str) -> None:
        """删除技能配置

        Args:
            skill_id: 技能 ID
        """

        # 加载现有配置
        config_data = cls._load_skill_config_file()

        # 删除技能配置
        if "skills" in config_data and skill_id in config_data["skills"]:
            del config_data["skills"][skill_id]

            # 保存配置
            cls._save_skill_config_file(config_data)

            console.print(f"[green]✓ Config deleted for skill: {skill_id}[/green]")
        else:
            console.print(f"[yellow]⚠ No config found for skill: {skill_id}[/yellow]")

    @classmethod
    def _load_skill_config_from_file(cls, skill_id: str) -> SkillConfig | None:
        """从文件加载技能配置"""

        config_data = cls._load_skill_config_file()

        if "skills" not in config_data or skill_id not in config_data["skills"]:
            return None

        skill_data = config_data["skills"][skill_id]
        llm_data = skill_data.get("llm", {})

        return SkillConfig(
            skill_id=skill_id,
            enabled=skill_data.get("enabled", True),
            priority=skill_data.get("priority", 50),
            category=skill_data.get("category", "development"),
            scope=skill_data.get("scope", "project"),
            lifecycle=SkillLifecycle(skill_data.get("lifecycle", "active")),
            usage_stats=skill_data.get("usage_stats", {}),
            version_history=skill_data.get("version_history", []),
            evaluation_context=skill_data.get("evaluation_context", {}) or skill_data.get("metadata", {}),
            requires_llm=skill_data.get("requires_llm", False),
            llm_provider=llm_data.get("provider"),
            llm_model=llm_data.get("model"),
            llm_temperature=llm_data.get("temperature"),
            llm_api_key=llm_data.get("api_key"),
            llm_api_base=llm_data.get("api_base"),
            routing_patterns=skill_data.get("routing", {}).get("patterns"),
            auto_configured=skill_data.get("metadata", {}).get("auto_configured", False),
            confidence=skill_data.get("metadata", {}).get("confidence", 0.5),
        )

    @classmethod
    def _load_skill_config_file(cls) -> dict[str, Any]:
        """加载技能配置文件"""

        # 尝试多个路径
        config_paths = [
            cls.SKILL_CONFIG_FILE,
            cls.GLOBAL_CONFIG_FILE,
            cls.GLOBAL_CONFIG_HOME,
        ]

        for config_path in config_paths:
            if config_path.exists():
                try:
                    with config_path.open() as f:
                        return yaml.safe_load(f) or {}
                except Exception as e:
                    console.print(f"[yellow]⚠ Failed to load {config_path}: {e}[/yellow]")

        return {}

    @classmethod
    def _save_skill_config_file(cls, config_data: dict[str, Any]) -> None:
        """保存技能配置文件"""

        config_file = cls.SKILL_CONFIG_FILE

        # 确保目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # 保存配置
        with config_file.open("w") as f:
            yaml.dump(config_data, f, default_flow_style=False)

        logger.info(f"Skill config saved to: {config_file}")


# 便捷函数
def get_skill_llm_config(skill_id: str) -> LLMConfig | None:
    """获取技能的 LLM 配置(便捷函数)

    Args:
        skill_id: 技能 ID

    Returns:
        LLM 配置对象
    """
    return SkillConfigManager.get_skill_llm_config(skill_id)


def set_skill_llm_config(skill_id: str, llm_config: dict[str, Any]) -> None:
    """设置技能的 LLM 配置(便捷函数)

    Args:
        skill_id: 技能 ID
        llm_config: LLM 配置字典
    """
    SkillConfigManager.set_skill_llm_config(skill_id, llm_config)


def list_skill_configs() -> dict[str, SkillConfig]:
    """列出所有技能配置(便捷函数)

    Returns:
        技能 ID -> 技能配置的字典
    """
    return SkillConfigManager.list_skill_configs()
