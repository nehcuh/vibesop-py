"""Unified configuration manager for VibeSOP.

This module consolidates configuration from multiple sources:
- Built-in defaults
- Global config (~/.vibe/config.yaml)
- Project config (.vibe/config.yaml)
- Environment variables
- CLI arguments
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ConfigSourcePriority(str, Enum):
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
            self._load_from_file()

    def _load_from_file(self) -> None:
        """Load configuration from file."""
        try:
            import yaml

            with open(self.path, "r") as f:
                self.data = yaml.safe_load(f) or {}
        except Exception:
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
    enable_ai_triage: bool = False
    enable_embedding: bool = False
    max_candidates: int = Field(default=3, ge=1, le=10)
    use_cache: bool = True


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
    DEFAULT_CONFIG = {
        "routing": {
            "min_confidence": 0.3,
            "auto_select_threshold": 0.6,
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
    }

    # Environment variable prefix
    ENV_PREFIX = "VIBE_"

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
            source._load_from_file()
            self._sources[ConfigSourcePriority.GLOBAL] = source

        # 3. Project config (.vibe/config.yaml)
        project_config_path = self.project_root / ".vibe" / "config.yaml"
        if project_config_path.exists():
            source = ConfigSource(
                priority=ConfigSourcePriority.PROJECT,
                data={},
                path=project_config_path,
            )
            source._load_from_file()
            self._sources[ConfigSourcePriority.PROJECT] = source

        # 4. Legacy preferences (.vibe/preferences.json)
        preferences_path = self.project_root / ".vibe" / "preferences.json"
        if preferences_path.exists():
            import json

            with open(preferences_path, "r") as f:
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

    def _get_section(self, section: str) -> dict[str, Any]:
        """Get a complete configuration section merged from all sources.

        Args:
            section: Section name (e.g., "routing")

        Returns:
            Merged configuration dictionary
        """
        # Start with defaults
        result = self.DEFAULT_CONFIG.get(section, {}).copy()

        # Merge from each source in priority order
        for priority in ConfigSourcePriority:
            if priority in self._sources:
                source = self._sources[priority]
                if section in source.data:
                    result.update(source.data[section])

        # Check environment variables for this section
        prefix = f"{self.ENV_PREFIX}{section.upper()}_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower()
                result[config_key] = self._parse_env_value(value)

        return result

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

        # Clear cache
        self._cache.clear()
