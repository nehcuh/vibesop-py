"""Tests for vibesop.core.config.manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.core.config.manager import (
    ConfigManager,
    ConfigSource,
    ConfigSourcePriority,
    RoutingConfig,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager_no_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ConfigManager:
    """Return a ConfigManager with no global/project config files."""
    # Prevent global config from being picked up from the real home directory.
    monkeypatch.setattr(
        ConfigSource,
        "_resolve_config_path",
        staticmethod(lambda base_dir, name: None),  # type: ignore[arg-type]
    )
    return ConfigManager(project_root=str(tmp_path))


@pytest.fixture
def source_defaults() -> ConfigSource:
    """Return a ConfigSource populated with the built-in defaults."""
    return ConfigSource(
        priority=ConfigSourcePriority.DEFAULTS,
        data=ConfigManager.DEFAULT_CONFIG.copy(),
        path=None,
    )


# ---------------------------------------------------------------------------
# 1. Default configuration values
# ---------------------------------------------------------------------------


def test_default_config_values() -> None:
    """Built-in defaults contain expected keys and values."""
    defaults = ConfigManager.DEFAULT_CONFIG
    assert "llm" in defaults
    assert "routing" in defaults
    assert "security" in defaults
    assert "semantic" in defaults
    assert "optimization" in defaults

    assert defaults["llm"]["temperature"] == 0.7
    assert defaults["llm"]["max_tokens"] == 4096
    assert defaults["routing"]["min_confidence"] == 0.3
    assert defaults["routing"]["max_candidates"] == 3
    assert defaults["routing"]["use_cache"] is True
    assert defaults["security"]["scan_external"] is True
    assert defaults["semantic"]["enabled"] is False


# ---------------------------------------------------------------------------
# 2. get() method with dot notation
# ---------------------------------------------------------------------------


def test_get_dot_notation_top_level(source_defaults: ConfigSource) -> None:
    """ConfigSource.get resolves a single key."""
    assert source_defaults.get("llm") is not None
    assert isinstance(source_defaults.get("llm"), dict)


def test_get_dot_notation_nested(source_defaults: ConfigSource) -> None:
    """ConfigSource.get resolves nested keys via dot notation."""
    assert source_defaults.get("llm.temperature") == 0.7
    assert source_defaults.get("routing.min_confidence") == 0.3
    assert source_defaults.get("semantic.enabled") is False


def test_get_dot_notation_missing_returns_default(source_defaults: ConfigSource) -> None:
    """Missing keys return the supplied default."""
    assert source_defaults.get("does.not.exist") is None
    assert source_defaults.get("does.not.exist", "fallback") == "fallback"
    assert source_defaults.get("llm.missing") is None
    assert source_defaults.get("llm.missing", 42) == 42


def test_get_dot_notation_partial_path(source_defaults: ConfigSource) -> None:
    """Traversing into a non-dict returns the default."""
    # "llm.temperature" is a float, not a dict
    assert source_defaults.get("llm.temperature.invalid") is None
    assert source_defaults.get("llm.temperature.invalid", "default") == "default"


# ---------------------------------------------------------------------------
# 3. get_routing_config() returns RoutingConfig
# ---------------------------------------------------------------------------


def test_get_routing_config_type_and_defaults(manager_no_files: ConfigManager) -> None:
    """get_routing_config returns a RoutingConfig populated from defaults."""
    rc = manager_no_files.get_routing_config()
    assert isinstance(rc, RoutingConfig)
    assert rc.min_confidence == pytest.approx(0.3)
    assert rc.auto_select_threshold == pytest.approx(0.6)
    assert rc.max_candidates == 3
    assert rc.use_cache is True
    assert rc.enable_ai_triage is True
    assert rc.enable_embedding is False
    assert rc.confirmation_mode == "always"


# ---------------------------------------------------------------------------
# 4. ConfigSource.get() and has() with dot notation
# ---------------------------------------------------------------------------


def test_config_source_has_existing_keys(source_defaults: ConfigSource) -> None:
    """has() returns True for existing keys."""
    assert source_defaults.has("llm") is True
    assert source_defaults.has("llm.temperature") is True
    assert source_defaults.has("routing.min_confidence") is True
    assert source_defaults.has("optimization.prefilter.enabled") is True


def test_config_source_has_missing_keys(source_defaults: ConfigSource) -> None:
    """has() returns False for missing keys."""
    assert source_defaults.has("missing") is False
    assert source_defaults.has("llm.missing") is False
    assert source_defaults.has("llm.temperature.invalid") is False


def test_config_source_has_does_not_mutate(source_defaults: ConfigSource) -> None:
    """has() is a pure read operation."""
    before = source_defaults.data.copy()
    source_defaults.has("routing.min_confidence")
    assert source_defaults.data == before


# ---------------------------------------------------------------------------
# 5. ConfigSource._resolve_config_path prefers .toml over .yaml
# ---------------------------------------------------------------------------


def test_resolve_config_path_prefers_toml(tmp_path: Path) -> None:
    """When both .toml and .yaml exist, .toml is chosen."""
    (tmp_path / "config.toml").write_text("")
    (tmp_path / "config.yaml").write_text("")
    result = ConfigSource._resolve_config_path(tmp_path, "config")
    assert result == tmp_path / "config.toml"


def test_resolve_config_path_fallback_to_yaml(tmp_path: Path) -> None:
    """When only .yaml exists, it is returned."""
    (tmp_path / "config.yaml").write_text("")
    result = ConfigSource._resolve_config_path(tmp_path, "config")
    assert result == tmp_path / "config.yaml"


def test_resolve_config_path_returns_none_when_missing(tmp_path: Path) -> None:
    """When neither file exists, None is returned."""
    result = ConfigSource._resolve_config_path(tmp_path, "config")
    assert result is None


# ---------------------------------------------------------------------------
# 6. Deep merge behavior in _get_section
# ---------------------------------------------------------------------------


def test_get_section_deep_merge_overrides_nested_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_get_section deep-merges so that project overrides only change specified nested keys."""
    # Write a project config that overrides a single nested routing key.
    vibe_dir = tmp_path / ".vibe"
    vibe_dir.mkdir()
    config_file = vibe_dir / "config.toml"
    config_file.write_text('[routing]\nmin_confidence = 0.99\n')

    # Block global config so the only sources are defaults + project.
    monkeypatch.setattr(
        ConfigSource,
        "_resolve_config_path",
        staticmethod(lambda base_dir, name: None if "home" in str(base_dir).lower() else config_file),  # type: ignore[arg-type]
    )

    manager = ConfigManager(project_root=str(tmp_path))
    section = manager._get_section("routing")

    # Overridden value
    assert section["min_confidence"] == pytest.approx(0.99)
    # Unchanged nested values must still come from defaults
    assert section["max_candidates"] == 3
    assert section["use_cache"] is True
    assert section["enable_ai_triage"] is True


def test_deep_merge_configs_recursively() -> None:
    """deep_merge_configs merges nested dicts rather than replacing them."""
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    overlay = {"a": {"y": 20, "z": 30}}
    merged = ConfigManager.deep_merge_configs(base, overlay)
    assert merged == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3}


def test_deep_merge_multiple_overlays() -> None:
    """Later overlays override earlier ones."""
    a = {"k": {"v": 1}}
    b = {"k": {"v": 2}}
    c = {"k": {"v": 3}}
    assert ConfigManager.deep_merge_configs(a, b, c) == {"k": {"v": 3}}


# ---------------------------------------------------------------------------
# 7. Environment variable override
# ---------------------------------------------------------------------------


def test_env_override_via_get(monkeypatch: pytest.MonkeyPatch, manager_no_files: ConfigManager) -> None:
    """Environment variables override config values for ConfigManager.get()."""
    monkeypatch.setenv("VIBE_ROUTING_MIN_CONFIDENCE", "0.95")
    # The manager caches results, but env was not set at construction time.
    # get() checks os.environ on every call, so it should see the env var.
    value = manager_no_files.get("routing.min_confidence")
    assert value == "0.95"  # env values come back as strings from os.environ


def test_env_override_in_get_section(monkeypatch: pytest.MonkeyPatch, manager_no_files: ConfigManager) -> None:
    """Environment variables override values inside _get_section with parsed types."""
    monkeypatch.setenv("VIBE_ROUTING_MIN_CONFIDENCE", "0.88")
    monkeypatch.setenv("VIBE_ROUTING_MAX_CANDIDATES", "7")
    section = manager_no_files._get_section("routing")
    assert section["min_confidence"] == pytest.approx(0.88)
    assert section["max_candidates"] == 7


def test_env_override_boolean_parsing(monkeypatch: pytest.MonkeyPatch, manager_no_files: ConfigManager) -> None:
    """Boolean env values are parsed correctly in _get_section."""
    monkeypatch.setenv("VIBE_ROUTING_ENABLE_AI_TRIAGE", "false")
    section = manager_no_files._get_section("routing")
    assert section["enable_ai_triage"] is False


def test_env_override_integer_parsing(monkeypatch: pytest.MonkeyPatch, manager_no_files: ConfigManager) -> None:
    """Integer env values are parsed correctly in _get_section."""
    monkeypatch.setenv("VIBE_ROUTING_AI_TRIAGE_MAX_SKILLS", "42")
    section = manager_no_files._get_section("routing")
    assert section["ai_triage_max_skills"] == 42


def test_key_to_env_conversion(manager_no_files: ConfigManager) -> None:
    """_key_to_env translates dot-notation keys to prefixed env names."""
    assert manager_no_files._key_to_env("routing.min_confidence") == "VIBE_ROUTING_MIN_CONFIDENCE"
    assert manager_no_files._key_to_env("llm.api_key") == "VIBE_LLM_API_KEY"


def test_parse_env_value_booleans(manager_no_files: ConfigManager) -> None:
    """_parse_env_value handles boolean-like strings."""
    assert manager_no_files._parse_env_value("true") is True
    assert manager_no_files._parse_env_value("yes") is True
    assert manager_no_files._parse_env_value("1") is True
    assert manager_no_files._parse_env_value("false") is False
    assert manager_no_files._parse_env_value("no") is False
    assert manager_no_files._parse_env_value("0") is False


def test_parse_env_value_numbers(manager_no_files: ConfigManager) -> None:
    """_parse_env_value handles int and float strings."""
    assert manager_no_files._parse_env_value("42") == 42
    assert manager_no_files._parse_env_value("3.14") == pytest.approx(3.14)


def test_parse_env_value_string_fallback(manager_no_files: ConfigManager) -> None:
    """_parse_env_value returns the raw string when no type matches."""
    assert manager_no_files._parse_env_value("hello") == "hello"


# ---------------------------------------------------------------------------
# ConfigSource file loading
# ---------------------------------------------------------------------------


def test_config_source_load_from_toml(tmp_path: Path) -> None:
    """ConfigSource.load_from_file reads TOML correctly."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[section]\nkey = "value"\nnum = 42\n')
    source = ConfigSource(
        priority=ConfigSourcePriority.PROJECT,
        data={},
        path=config_file,
    )
    source.load_from_file()
    assert source.data == {"section": {"key": "value", "num": 42}}


def test_config_source_load_from_yaml(tmp_path: Path) -> None:
    """ConfigSource.load_from_file reads YAML correctly."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("section:\n  key: value\n  num: 42\n")
    source = ConfigSource(
        priority=ConfigSourcePriority.PROJECT,
        data={},
        path=config_file,
    )
    source.load_from_file()
    assert source.data == {"section": {"key": "value", "num": 42}}


def test_config_source_reload_noop_without_path() -> None:
    """reload() is a no-op when path is None."""
    source = ConfigSource(
        priority=ConfigSourcePriority.DEFAULTS,
        data={"a": 1},
        path=None,
    )
    source.reload()
    assert source.data == {"a": 1}
