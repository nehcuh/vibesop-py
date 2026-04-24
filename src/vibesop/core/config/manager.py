"""Unified configuration manager for VibeSOP.

This module consolidates configuration from multiple sources:
- Built-in defaults
- Global config (~/.vibe/config.yaml)
- Project config (.vibe/config.yaml)
- Environment variables
- CLI arguments
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from vibesop.core.config.optimization_config import OptimizationConfig


class ConfigSourcePriority(StrEnum):
    """Configuration source priority levels (low to high)."""

    DEFAULTS = "defaults"  # 1. Built-in defaults
    GLOBAL = "global"  # 2. Global config (~/.vibe/config.yaml)
    PROJECT = "project"  # 3. Project config (.vibe/config.yaml)
    PREFERENCES = "preferences"  # 4. Legacy preferences (.vibe/preferences.json)
    ENV = "env"  # 5. Environment variables
    CLI = "cli"  # 6. Command-line arguments


@dataclass
class ConfigSource:
    """A configuration source.

    Attributes:
        priority: Source priority level
        data: Configuration data from this source
        path: Path to config file (if applicable)
    """

    priority: ConfigSourcePriority
    data: dict[str, Any]
    path: Path | None = None

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from this source.

        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        # Support dot notation
        keys = key.split(".")
        value = self.data

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value if value is not None else default

    def has(self, key: str) -> bool:
        """Check if this source has a key.

        Args:
            key: Configuration key

        Returns:
            True if key exists in this source
        """
        keys = key.split(".")
        value = self.data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return False

        return True

    def reload(self) -> None:
        """Reload configuration from file."""
        if self.path and self.path.exists():
            self.load_from_file()

    def load_from_file(self) -> None:
        """Load configuration from file."""
        if self.path is None:
            self.data = {}
            return
        try:
            import yaml

            with self.path.open() as f:
                self.data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.debug(f"Failed to load config from {self.path}: {e}")
            self.data = {}


class RoutingConfig(BaseModel):
    """Configuration for routing behavior.

    Attributes:
        min_confidence: Minimum confidence threshold for auto-selection
        auto_select_threshold: Confidence threshold for automatic skill selection
        enable_ai_triage: Enable AI semantic triage (Layer 0)
        enable_embedding: Enable embedding-based matching (Layer 5)
        max_candidates: Maximum number of candidates to return
        use_cache: Enable caching for improved performance
    """

    min_confidence: float = Field(default=0.3, ge=0.0, le=1.0)
    auto_select_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    confirmation_mode: str = Field(
        default="always",
        description="User confirmation mode: always (default), never, or ambiguous_only",
    )
    enable_orchestration: bool = Field(
        default=True,
        description="Enable multi-skill orchestration for multi-intent queries",
    )
    enable_ai_triage: bool = True
    enable_embedding: bool = False
    max_candidates: int = Field(default=3, ge=1, le=10)
    use_cache: bool = True
    ai_triage_max_skills: int = Field(default=20, ge=5, le=50)
    ai_triage_max_tokens: int = Field(default=100, ge=50, le=500)
    ai_triage_prompt_version: str = Field(default="v1")
    ai_triage_budget_monthly: float = Field(default=5.0, ge=0.0)
    ai_triage_log_calls: bool = True
    ai_triage_circuit_breaker_enabled: bool = True
    ai_triage_circuit_breaker_failure_threshold: int = Field(default=3, ge=1, le=10)
    ai_triage_circuit_breaker_latency_threshold_ms: float = Field(default=500.0, ge=100.0)
    ai_triage_circuit_breaker_cooldown_seconds: int = Field(default=60, ge=10)
    session_aware: bool = Field(
        default=True,
        description="Enable session-state-aware routing for multi-turn conversations",
    )
    session_stickiness_boost: float = Field(
        default=0.08,
        ge=0.0,
        le=0.2,
        description="Confidence boost for current skill in multi-turn continuity",
    )
    fallback_mode: Literal["transparent", "silent", "disabled"] = Field(
        default="transparent",
        description="Behavior when no skill matches: transparent (explain + suggest), silent (quiet fallback), disabled (show 'no match')",
    )
    default_strategy: Literal["auto", "sequential", "parallel", "hybrid"] = Field(
        default="auto",
        description="Default execution strategy for multi-skill orchestration: auto, sequential, parallel, hybrid",
    )


class SecurityConfig(BaseModel):
    """Configuration for security settings.

    Attributes:
        scan_external: Scan external skill files for threats
        require_audit: Require security audit for external skills
        allowed_paths: Whitelist of allowed skill directories
        block_patterns: List of blocked threat patterns
    """

    scan_external: bool = True
    require_audit: bool = True
    allowed_paths: list[str] = Field(
        default_factory=lambda: [
            "~/.claude/skills",
            "~/.config/skills",
            ".vibe/skills",
        ]
    )
    block_patterns: list[str] = Field(default_factory=list)


class SemanticConfig(BaseModel):
    """Configuration for semantic matching.

    Attributes:
        enabled: Enable semantic matching
        model: Sentence transformer model name
        cache_embeddings: Cache computed embeddings
        batch_size: Batch size for embedding computation
    """

    enabled: bool = False
    model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    cache_embeddings: bool = True
    batch_size: int = 32


class ConfigManager:
    """Unified configuration manager.

    This class consolidates configuration from multiple sources
    and provides a simple interface for accessing configuration values.

    Example:
        >>> manager = ConfigManager(project_root=".")
        >>> value = manager.get("routing.min_confidence", default=0.3)
        >>> routing_config = manager.get_routing_config()
    """

    # Default configuration
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "routing": {
            "min_confidence": 0.3,
            "auto_select_threshold": 0.6,
            "confirmation_mode": "always",
            "enable_orchestration": True,
            "enable_ai_triage": False,
            "enable_embedding": False,
            "max_candidates": 3,
            "use_cache": True,
        },
        "security": {
            "scan_external": True,
            "require_audit": True,
            "allowed_paths": [
                "~/.claude/skills",
                "~/.config/skills",
                ".vibe/skills",
            ],
            "block_patterns": [],
        },
        "semantic": {
            "enabled": False,
            "model": "paraphrase-multilingual-MiniLM-L12-v2",
            "cache_embeddings": True,
            "batch_size": 32,
        },
        "optimization": {
            "enabled": True,
            "prefilter": {
                "enabled": True,
                "min_candidates": 5,
                "max_candidates": 15,
                "always_include_p0": True,
                "namespace_relevance_threshold": 0.3,
            },
            "preference_boost": {
                "enabled": True,
                "weight": 0.3,
                "min_samples": 2,
                "decay_days": 30,
            },
            "clustering": {
                "enabled": True,
                "auto_resolve": True,
                "confidence_gap_threshold": 0.1,
                "min_skills_for_clustering": 10,
                "max_clusters": 12,
            },
        },
    }

    # Environment variable prefix
    ENV_PREFIX = "VIBE_"

    @staticmethod
    def deep_merge_configs(*configs: dict[str, Any]) -> dict[str, Any]:
        """Deep merge multiple configuration dictionaries.

        Later configs override earlier configs. Nested dictionaries are
        merged recursively rather than replaced.

        Priority order (lowest to highest):
            1. Built-in defaults
            2. Global config (~/.vibe/config.yaml)
            3. Project config (.vibe/config.yaml)
            4. Environment variables (VIBE_*)
            5. CLI arguments

        Args:
            *configs: Configuration dictionaries to merge

        Returns:
            Merged configuration dictionary

        Example:
            >>> defaults = {"routing": {"min_confidence": 0.3, "cache": True}}
            >>> project = {"routing": {"min_confidence": 0.5}}
            >>> cli = {"routing": {"cache": False}}
            >>> merged = ConfigManager.deep_merge_configs(defaults, project, cli)
            >>> assert merged["routing"]["min_confidence"] == 0.5
            >>> assert merged["routing"]["cache"] is False
        """
        if not configs:
            return {}

        # Start with first config
        result = configs[0].copy()

        # Merge each subsequent config
        for config in configs[1:]:
            result = ConfigManager._deep_merge_dicts(result, config)

        return result

    @staticmethod
    def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries.

        Args:
            base: Base dictionary
            override: Override dictionary (takes precedence)

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = ConfigManager._deep_merge_dicts(result[key], value)
            else:
                # Override with new value
                result[key] = value

        return result

    def __init__(self, project_root: str | Path = "."):
        """Initialize the configuration manager.

        Args:
            project_root: Path to project root directory
        """
        self.project_root = Path(project_root).resolve()
        self._sources: dict[ConfigSourcePriority, ConfigSource] = {}
        self._cache: dict[str, Any] = {}

        # Initialize configuration sources
        self._init_sources()

    def _init_sources(self) -> None:
        """Initialize all configuration sources."""
        # 1. Built-in defaults (always available)
        self._sources[ConfigSourcePriority.DEFAULTS] = ConfigSource(
            priority=ConfigSourcePriority.DEFAULTS,
            data=self.DEFAULT_CONFIG.copy(),
            path=None,
        )

        # 2. Global config (~/.vibe/config.yaml)
        global_config_path = Path.home() / ".vibe" / "config.yaml"
        if global_config_path.exists():
            source = ConfigSource(
                priority=ConfigSourcePriority.GLOBAL,
                data={},
                path=global_config_path,
            )
            source.load_from_file()
            self._sources[ConfigSourcePriority.GLOBAL] = source

        # 3. Project config (.vibe/config.yaml)
        project_config_path = self.project_root / ".vibe" / "config.yaml"
        if project_config_path.exists():
            source = ConfigSource(
                priority=ConfigSourcePriority.PROJECT,
                data={},
                path=project_config_path,
            )
            source.load_from_file()
            self._sources[ConfigSourcePriority.PROJECT] = source

        # 4. Legacy preferences (.vibe/preferences.json)
        preferences_path = self.project_root / ".vibe" / "preferences.json"
        if preferences_path.exists():
            import json

            with preferences_path.open() as f:
                data = json.load(f)

            # Map legacy preferences to new structure
            mapped_data = self._map_legacy_preferences(data)
            self._sources[ConfigSourcePriority.PREFERENCES] = ConfigSource(
                priority=ConfigSourcePriority.PREFERENCES,
                data=mapped_data,
                path=preferences_path,
            )

    def _map_legacy_preferences(self, prefs: dict[str, Any]) -> dict[str, Any]:
        """Map legacy preferences to new config structure.

        Args:
            prefs: Legacy preferences dictionary

        Returns:
            Mapped configuration dictionary
        """
        mapped = {}

        # Map routing preferences
        if "routing" in prefs:
            mapped["routing"] = {
                "min_confidence": prefs["routing"].get("min_confidence", 0.3),
                "enable_ai": prefs["routing"].get("enable_ai", False),
            }

        # Map semantic preferences
        if "semantic" in prefs:
            mapped["semantic"] = {
                "enabled": prefs["semantic"].get("enabled", False),
                "model": prefs["semantic"].get("model", "paraphrase-multilingual-MiniLM-L12-v2"),
            }

        return mapped

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Values are resolved by checking sources in priority order
        (highest priority first).

        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        # Check cache first
        cache_key = f"get:{key}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check environment variables first (highest priority)
        env_key = self._key_to_env(key)
        if env_key in os.environ:
            value = os.environ[env_key]
            self._cache[cache_key] = value
            return value

        # Check sources in reverse priority order (highest first)
        for priority in reversed(ConfigSourcePriority):
            if priority in self._sources:
                source = self._sources[priority]
                if source.has(key):
                    value = source.get(key, default)
                    self._cache[cache_key] = value
                    return value

        self._cache[cache_key] = default
        return default

    def get_routing_config(self) -> RoutingConfig:
        """Get routing configuration.

        Returns:
            RoutingConfig instance with merged values from all sources
        """
        return RoutingConfig(**self._get_section("routing"))

    def get_security_config(self) -> SecurityConfig:
        """Get security configuration.

        Returns:
            SecurityConfig instance with merged values from all sources
        """
        return SecurityConfig(**self._get_section("security"))

    def get_semantic_config(self) -> SemanticConfig:
        """Get semantic configuration.

        Returns:
            SemanticConfig instance with merged values from all sources
        """
        return SemanticConfig(**self._get_section("semantic"))

    def get_optimization_config(self) -> OptimizationConfig:
        """Get optimization configuration.

        Returns:
            OptimizationConfig instance with merged values from all sources
        """
        from vibesop.core.config.optimization_config import OptimizationConfig

        return OptimizationConfig(**self._get_section("optimization"))

    def load_policy(self) -> dict[str, Any]:
        """Load full policy configuration.

        Returns:
            Dictionary with security, routing, behavior, and custom sections
        """
        return {
            "security": self._get_section("security"),
            "routing": self._get_section("routing"),
            "behavior": self._get_section("behavior"),
            "custom": self._get_section("custom"),
        }

    def _get_section(self, section: str) -> dict[str, Any]:
        """Get a complete configuration section merged from all sources.

        Args:
            section: Section name (e.g., "routing")

        Returns:
            Merged configuration dictionary
        """
        # Collect all sources that have this section
        configs_to_merge = []

        # 1. Built-in defaults
        if section in self.DEFAULT_CONFIG:
            configs_to_merge.append({section: self.DEFAULT_CONFIG[section]})

        # 2-6. Other sources in priority order
        for priority in ConfigSourcePriority:
            if priority in self._sources:
                source = self._sources[priority]
                if section in source.data:
                    configs_to_merge.append({section: source.data[section]})

        # Deep merge all configs
        merged = self.deep_merge_configs(*configs_to_merge)

        # 7. Environment variables (highest priority per-key)
        prefix = f"{self.ENV_PREFIX}{section.upper()}_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix) :].lower()
                # Apply env var overrides
                if section not in merged:
                    merged[section] = {}
                merged[section][config_key] = self._parse_env_value(value)

        return merged.get(section, {})

    def _key_to_env(self, key: str) -> str:
        """Convert configuration key to environment variable name.

        Args:
            key: Configuration key (e.g., "routing.min_confidence")

        Returns:
            Environment variable name (e.g., "VIBE_ROUTING_MIN_CONFIDENCE")
        """
        return f"{self.ENV_PREFIX}{key.upper().replace('.', '_')}"

    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value to appropriate type.

        Args:
            value: String value from environment

        Returns:
            Parsed value (bool, int, float, or str)
        """
        # Try boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # Try int
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        # Return as string
        return value

    def reload(self) -> None:
        """Reload all configuration sources."""
        self._cache.clear()

        for source in self._sources.values():
            source.reload()

    def set_cli_override(self, key: str, value: Any) -> None:
        """Set a CLI override (highest priority).

        Args:
            key: Configuration key
            value: Configuration value
        """
        # Create CLI source if it doesn't exist
        if ConfigSourcePriority.CLI not in self._sources:
            self._sources[ConfigSourcePriority.CLI] = ConfigSource(
                priority=ConfigSourcePriority.CLI,
                data={},
                path=None,
            )

        # Set the value (support dot notation)
        keys = key.split(".")
        data = self._sources[ConfigSourcePriority.CLI].data

        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]

        data[keys[-1]] = value

        self._cache.clear()

    # --- Registry loading (migrated from ConfigLoader) ---

    def load_registry(self, force_reload: bool = False) -> dict[str, Any]:
        """Load skill registry from core/registry.yaml.

        Args:
            force_reload: Force reload even if cached

        Returns:
            Dictionary with registry data
        """
        cache_key = "_registry"
        if not force_reload and cache_key in self._cache:
            return self._cache[cache_key]

        registry_path = self.project_root / "core" / "registry.yaml"

        if not registry_path.exists():
            return {"skills": [], "version": "1.0.0"}

        try:
            from ruamel.yaml import YAML

            yaml = YAML()
            with registry_path.open("r", encoding="utf-8") as f:
                data = yaml.load(f) or {}

            self._cache[cache_key] = data
            return data
        except Exception as e:
            logger.debug(f"Failed to load registry from {registry_path}: {e}")
            return {"skills": [], "version": "1.0.0"}

    def get_all_skills(self, force_reload: bool = False) -> list[dict[str, Any]]:
        """Get all skills from registry.

        Args:
            force_reload: Force reload even if cached

        Returns:
            List of skill definitions
        """
        registry = self.load_registry(force_reload=force_reload)
        return registry.get("skills", [])

    def get_skill_by_id(
        self,
        skill_id: str,
        force_reload: bool = False,
    ) -> dict[str, Any] | None:
        """Get skill definition by ID.

        Args:
            skill_id: Skill identifier
            force_reload: Force reload even if cached

        Returns:
            Skill definition or None if not found
        """
        skills = self.get_all_skills(force_reload=force_reload)

        for skill in skills:
            if skill.get("id") == skill_id:
                return skill

        if skill_id.startswith("/"):
            shorthand = skill_id[1:]
            for skill in skills:
                sid = skill.get("id", "")
                if sid.endswith(f"/{shorthand}") or sid.endswith(f"-{shorthand}"):
                    return skill
        else:
            for skill in skills:
                sid = skill.get("id", "")
                if sid.endswith(f"/{skill_id}") or sid.endswith(f"-{skill_id}"):
                    return skill

        return None

    def get_skills_by_namespace(
        self,
        namespace: str,
        force_reload: bool = False,
    ) -> list[dict[str, Any]]:
        """Get all skills in a namespace.

        Args:
            namespace: Namespace to filter by
            force_reload: Force reload even if cached

        Returns:
            List of skill definitions in namespace
        """
        skills = self.get_all_skills(force_reload=force_reload)
        return [skill for skill in skills if skill.get("namespace") == namespace]

    def search_skills(
        self,
        query: str,
        force_reload: bool = False,
    ) -> list[dict[str, Any]]:
        """Search skills by keyword in intent or description.

        Args:
            query: Search query
            force_reload: Force reload even if cached

        Returns:
            List of matching skills
        """
        skills = self.get_all_skills(force_reload=force_reload)
        query_lower = query.lower()
        return [skill for skill in skills if query_lower in skill.get("intent", "").lower()]

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
