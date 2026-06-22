"""技能配置管理器 - 管理技能级别的 LLM 和其他配置."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

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

# Module-level cache for loaded skill config files.
# _load_skill_config_file() is a hot path called once per skill (395+ times
# on cold start). Without caching, the same YAML file is parsed 395 times.
_CONFIG_FILE_CACHE: dict[Path, tuple[float, dict[str, Any]]] = {}

# Backward-compatible alias
SkillLifecycleState = SkillLifecycle


@dataclass
class SkillConfig:
    """Runtime persistence model for skill configuration.

    Distinct from ``vibesop.spec.SkillSpec`` (the immutable SKILL.md spec):
    - ``SkillSpec`` is loaded from SKILL.md frontmatter at startup; it describes
      *what a skill is* (id, name, type, triggers, capabilities).
    - ``SkillConfig`` is written by ``SkillConfigManager`` to
      ``.vibe/skills/auto-config.yaml``; it tracks *how a skill is configured at
      runtime* (usage_stats, project scope, LLM choice, evaluation_context).

    The two models have intentionally disjoint field sets: spec fields belong
    on SkillSpec, runtime/persistence fields belong on SkillConfig. Mixing them
    pollutes the spec layer with mutable state.

    See ADR-004 Phase 2 (withdrawn 2026-06-14) for the original (incorrect)
    unification plan and its rationale for rejection.
    """

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

    # 弃用原因
    deprecation_reason: str | None = None


class SkillConfigManager:
    """技能配置管理器."""

    # 配置文件路径
    SKILL_CONFIG_FILE = Path(".vibe/skills/auto-config.yaml")
    GLOBAL_CONFIG_FILE = Path(".vibe/config.toml")
    GLOBAL_CONFIG_HOME = Path.home() / ".vibe" / "config.toml"

    def __init__(self, project_root: str | Path | None = None):
        self._project_root = Path(project_root).resolve() if project_root else None

    def _resolve_path(self, path: Path) -> Path:
        if path.is_absolute() or self._project_root is None:
            return path
        return self._project_root / path

    @classmethod
    def get_skill_config(cls, skill_id: str) -> SkillConfig | None:
        skill_config = cls._load_skill_config_from_file(skill_id)
        if skill_config:
            return skill_config

        logger.debug(f"No config found for skill {skill_id}, using defaults")
        return SkillConfig(skill_id=skill_id)

    @classmethod
    def get_skill_llm_config(cls, skill_id: str) -> LLMConfig | None:
        skill_config = cls._load_skill_config_from_file(skill_id)

        if skill_config and skill_config.requires_llm and skill_config.llm_provider:
            console.print(f"[dim]  Using skill-level LLM config for {skill_id}[/dim]")

            return LLMConfig(
                provider=skill_config.llm_provider,
                model=skill_config.llm_model or "claude-sonnet-4-6",
                api_key=skill_config.llm_api_key,
                api_base=skill_config.llm_api_base,
                temperature=skill_config.llm_temperature or 0.7,
                source=LLMSource.VIBESOP_CONFIG,
                confidence=0.95,  # 技能配置置信度高
            )

        console.print(f"[dim]  Using global LLM config for {skill_id}[/dim]")

        resolver = LLMConfigResolver()
        return resolver.resolve_llm_config(prefer_agent=True)

    @classmethod
    def set_skill_llm_config(cls, skill_id: str, llm_config: dict[str, Any]) -> None:
        config_data = cls._load_skill_config_file()

        if "skills" not in config_data:
            config_data["skills"] = {}

        if skill_id not in config_data["skills"]:
            config_data["skills"][skill_id] = {}

        config_data["skills"][skill_id]["llm"] = llm_config
        config_data["skills"][skill_id]["requires_llm"] = True

        cls._save_skill_config_file(config_data)

        console.print(f"[green]✓ LLM config saved for skill: {skill_id}[/green]")
        console.print(f"[dim]  Provider: {llm_config.get('provider')}[/dim]")
        console.print(f"[dim]  Model: {llm_config.get('model')}[/dim]")

    @classmethod
    def list_skill_configs(cls) -> dict[str, SkillConfig]:

        config_data = cls._load_skill_config_file()
        skill_configs = {}

        for skill_id, skill_data in config_data.get("skills", {}).items():
            if not isinstance(skill_data, dict):
                continue
            skill_configs[skill_id] = SkillConfig(
                skill_id=skill_id,
                enabled=skill_data.get("enabled", True),
                priority=skill_data.get("priority", 50),
                category=skill_data.get("category", "development"),
                scope=skill_data.get("scope", "global"),
                lifecycle=SkillLifecycle(skill_data.get("lifecycle", "active")),
                usage_stats=skill_data.get("usage_stats", {}),
                version_history=skill_data.get("version_history", []),
                evaluation_context=skill_data.get("evaluation_context", {})
                or skill_data.get("metadata", {}),
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
    def update_skill_config(cls, skill_id: str, updates: dict[str, Any]) -> None:
        config_data = cls._load_skill_config_file()

        if "skills" not in config_data:
            config_data["skills"] = {}

        if skill_id not in config_data["skills"]:
            config_data["skills"][skill_id] = {}

        for key, value in updates.items():
            if key == "llm":
                if "llm" not in config_data["skills"][skill_id]:
                    config_data["skills"][skill_id]["llm"] = {}
                config_data["skills"][skill_id]["llm"].update(value)
            else:
                config_data["skills"][skill_id][key] = value

        cls._save_skill_config_file(config_data)

        logger.debug("[dim]config updated for skill: %s[/dim]", skill_id)

    @classmethod
    def set_enabled(cls, skill_id: str, enabled: bool) -> None:
        cls.update_skill_config(skill_id, {"enabled": enabled})

    @classmethod
    def set_scope(cls, skill_id: str, scope: str) -> None:
        cls.update_skill_config(skill_id, {"scope": scope})

    @classmethod
    def set_lifecycle(cls, skill_id: str, state: SkillLifecycle | str) -> None:
        if isinstance(state, SkillLifecycle):
            cls.update_skill_config(skill_id, {"lifecycle": state.value})
        else:
            cls.update_skill_config(skill_id, {"lifecycle": SkillLifecycle(state).value})

    @classmethod
    def delete_skill_config(cls, skill_id: str) -> None:
        config_data = cls._load_skill_config_file()

        if "skills" in config_data and skill_id in config_data["skills"]:
            del config_data["skills"][skill_id]

            cls._save_skill_config_file(config_data)

            console.print(f"[green]✓ Config deleted for skill: {skill_id}[/green]")
        else:
            console.print(f"[yellow]⚠ No config found for skill: {skill_id}[/yellow]")

    @classmethod
    def _load_skill_config_from_file(cls, skill_id: str) -> SkillConfig | None:
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
            scope=skill_data.get("scope", "global"),
            lifecycle=SkillLifecycle(skill_data.get("lifecycle", "active")),
            usage_stats=skill_data.get("usage_stats", {}),
            version_history=skill_data.get("version_history", []),
            evaluation_context=skill_data.get("evaluation_context", {})
            or skill_data.get("metadata", {}),
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
        config_path = cls.SKILL_CONFIG_FILE
        if not config_path.exists():
            return {}

        try:
            mtime = config_path.stat().st_mtime
            cached = _CONFIG_FILE_CACHE.get(config_path)
            if cached is not None and cached[0] == mtime:
                return cached[1]

            if config_path.suffix.lower() == ".toml":
                import tomllib

                with config_path.open("rb") as f:
                    data = tomllib.load(f) or {}
            else:
                with config_path.open() as f:
                    data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                _CONFIG_FILE_CACHE[config_path] = (mtime, data)
            return cast("dict[str, Any]", data)
        except Exception as e:
            console.print(f"[yellow]⚠ Failed to load {config_path}: {e}[/yellow]")

        return {}

    @classmethod
    def _save_skill_config_file(cls, config_data: dict[str, Any]) -> None:

        config_file = cls.SKILL_CONFIG_FILE

        config_file.parent.mkdir(parents=True, exist_ok=True)

        with config_file.open("w") as f:
            yaml.dump(config_data, f, default_flow_style=False)

        _CONFIG_FILE_CACHE.pop(config_file, None)
        logger.info(f"Skill config saved to: {config_file}")


# 便捷函数
def get_skill_llm_config(skill_id: str) -> LLMConfig | None:
    return SkillConfigManager.get_skill_llm_config(skill_id)


def set_skill_llm_config(skill_id: str, llm_config: dict[str, Any]) -> None:
    SkillConfigManager.set_skill_llm_config(skill_id, llm_config)


def list_skill_configs() -> dict[str, SkillConfig]:
    return SkillConfigManager.list_skill_configs()
