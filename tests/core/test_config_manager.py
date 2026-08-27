"""Tests for vibesop.core.config.manager."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

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
    assert rc.confirmation_mode == "ambiguous_only"
    assert rc.index_match_threshold == pytest.approx(0.20)


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
    (tmp_path / "config.toml").write_text("", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("", encoding="utf-8")
    result = ConfigSource._resolve_config_path(tmp_path, "config")
    assert result == tmp_path / "config.toml"


def test_resolve_config_path_fallback_to_yaml(tmp_path: Path) -> None:
    """When only .yaml exists, it is returned."""
    (tmp_path / "config.yaml").write_text("", encoding="utf-8")
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
    config_file.write_text("[routing]\nmin_confidence = 0.99\n", encoding="utf-8")

    # Block global config so the only sources are defaults + project.
    monkeypatch.setattr(
        ConfigSource,
        "_resolve_config_path",
        staticmethod(
            lambda base_dir, name: None if "home" in str(base_dir).lower() else config_file
        ),  # type: ignore[arg-type]
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


def test_env_override_via_get(
    monkeypatch: pytest.MonkeyPatch, manager_no_files: ConfigManager
) -> None:
    """Environment variables override config values for ConfigManager.get()."""
    monkeypatch.setenv("VIBE_ROUTING_MIN_CONFIDENCE", "0.95")
    # The manager caches results, but env was not set at construction time.
    # get() checks os.environ on every call, so it should see the env var.
    value = manager_no_files.get("routing.min_confidence")
    assert value == "0.95"  # env values come back as strings from os.environ


def test_env_override_in_get_section(
    monkeypatch: pytest.MonkeyPatch, manager_no_files: ConfigManager
) -> None:
    """Environment variables override values inside _get_section with parsed types."""
    monkeypatch.setenv("VIBE_ROUTING_MIN_CONFIDENCE", "0.88")
    monkeypatch.setenv("VIBE_ROUTING_MAX_CANDIDATES", "7")
    section = manager_no_files._get_section("routing")
    assert section["min_confidence"] == pytest.approx(0.88)
    assert section["max_candidates"] == 7


def test_env_override_boolean_parsing(
    monkeypatch: pytest.MonkeyPatch, manager_no_files: ConfigManager
) -> None:
    """Boolean env values are parsed correctly in _get_section."""
    monkeypatch.setenv("VIBE_ROUTING_ENABLE_AI_TRIAGE", "false")
    section = manager_no_files._get_section("routing")
    assert section["enable_ai_triage"] is False


def test_env_override_integer_parsing(
    monkeypatch: pytest.MonkeyPatch, manager_no_files: ConfigManager
) -> None:
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
    config_file.write_text('[section]\nkey = "value"\nnum = 42\n', encoding="utf-8")
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
    config_file.write_text("section:\n  key: value\n  num: 42\n", encoding="utf-8")
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


# ---------------------------------------------------------------------------
# 8. load_registry — must never silently degrade to zero skills
# ---------------------------------------------------------------------------


def test_load_registry_returns_skills_when_valid(tmp_path: Path) -> None:
    """A well-formed registry.yaml yields a non-empty skill list."""
    core_dir = tmp_path / "core"
    core_dir.mkdir()
    (core_dir / "registry.yaml").write_text(
        "skills:\n  - id: superpowers/brainstorm\n    name: Brainstorm\n",
        encoding="utf-8",
    )
    manager = ConfigManager(project_root=str(tmp_path))
    registry = manager.load_registry(force_reload=True)
    assert len(registry.get("skills", [])) == 1
    assert registry["skills"][0]["id"] == "superpowers/brainstorm"


def test_load_registry_logs_error_on_parse_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A malformed registry must be LOUD (ERROR), not silently empty.

    Regression for the silent-lobotomy bug: load_registry used to swallow parse
    errors at DEBUG level and return an empty dict, so every consumer (routing,
    manifest builder, inspect) silently saw ZERO skills with no signal.
    """
    core_dir = tmp_path / "core"
    core_dir.mkdir()
    # guaranteed parse error: unclosed flow sequence
    (core_dir / "registry.yaml").write_text("skills: [unclosed bracket\n", encoding="utf-8")
    manager = ConfigManager(project_root=str(tmp_path))
    with caplog.at_level("ERROR", logger="vibesop.core.config.manager"):
        registry = manager.load_registry(force_reload=True)
    # documented empty contract is preserved (does not raise) ...
    assert registry == {"skills": [], "version": "1.0.0"}
    # ... but it MUST log at ERROR so the operator sees the misconfiguration.
    assert any(
        "Failed to parse skill registry" in rec.message and rec.levelname == "ERROR"
        for rec in caplog.records
    ), f"expected ERROR log for malformed registry; got: {[r.message for r in caplog.records]}"


def test_load_registry_returns_empty_when_missing(tmp_path: Path) -> None:
    """Neither a repo checkout nor a wheel bundle -> empty (quiet is fine)."""
    manager = ConfigManager(project_root=str(tmp_path))
    registry = manager.load_registry(force_reload=True)
    assert registry == {"skills": [], "version": "1.0.0"}


def test_load_registry_falls_back_to_wheel_bundle(tmp_path: Path, monkeypatch) -> None:
    """pipx/uv-tool installs have no repo checkout: the wheel-bundled
    registry.yaml (vibesop/builtin_data/core/) must actually be parsed
    and served, not just path-resolved."""
    import vibesop

    fake_pkg = tmp_path / "site-packages" / "vibesop"
    bundled = fake_pkg / "builtin_data" / "core" / "registry.yaml"
    bundled.parent.mkdir(parents=True)
    bundled.write_text(
        "skills:\n  - id: bundled-demo\n    name: Bundled demo\n",
        encoding="utf-8",
    )
    fake_init = fake_pkg / "__init__.py"
    fake_init.write_text("", encoding="utf-8")
    monkeypatch.setattr(vibesop, "__file__", str(fake_init))

    manager = ConfigManager(project_root=str(tmp_path))
    registry = manager.load_registry(force_reload=True)

    assert [s["id"] for s in registry["skills"]] == ["bundled-demo"]


# ---------------------------------------------------------------------------
# 9. F-19: malformed project/global config must be LOUD (not silently ignored)
# ---------------------------------------------------------------------------


def test_config_source_load_logs_error_on_parse_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression for F-19: load_from_file must log ERROR (not DEBUG) on parse failure.

    Previously a typo'd config silently fell back to defaults with zero signal
    at the default log level, so operators couldn't tell their config was rejected.
    """
    config_file = tmp_path / "config.toml"
    # guaranteed parse error: unquoted string where a number is expected
    config_file.write_text("[routing]\nmin_confidence = not-a-number\n", encoding="utf-8")
    source = ConfigSource(
        priority=ConfigSourcePriority.PROJECT,
        data={},
        path=config_file,
    )
    with caplog.at_level("ERROR", logger="vibesop.core.config.manager"):
        source.load_from_file()
    # graceful-degrade contract preserved (does not raise, data reset)
    assert source.data == {}
    # ... but MUST log at ERROR so the operator sees the rejected config.
    assert any(
        "Failed to parse config" in rec.message and rec.levelname == "ERROR"
        for rec in caplog.records
    ), f"expected ERROR log for malformed config; got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# 10. F-20: typed config models tolerate unknown (legacy/env/typo) keys
# ---------------------------------------------------------------------------


def test_routing_config_tolerates_unknown_keys() -> None:
    """Regression for F-20: extra keys must not raise ValidationError.

    _map_legacy_preferences emits ``routing.enable_ai`` (renamed to
    ``enable_ai_triage``); pydantic's default extra rejection turned this
    stale field into a crash on UnifiedRouter init.
    """
    rc = RoutingConfig(enable_ai=False, min_confidence=0.3, bogus_field="x")
    assert rc.min_confidence == pytest.approx(0.3)
    # real field unaffected; the unknown extras were silently dropped
    assert rc.enable_ai_triage is True


def test_get_routing_config_tolerates_legacy_preferences(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end F-20: a stale v7 preferences.json must not crash routing init."""
    vibe_dir = tmp_path / ".vibe"
    vibe_dir.mkdir()
    (vibe_dir / "preferences.json").write_text(
        '{"routing": {"enable_ai": false, "min_confidence": 0.3}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ConfigSource,
        "_resolve_config_path",
        staticmethod(lambda base_dir, name: None),  # type: ignore[arg-type]
    )
    manager = ConfigManager(project_root=str(tmp_path))
    rc = manager.get_routing_config()  # must not raise ValidationError
    assert isinstance(rc, RoutingConfig)
    assert rc.min_confidence == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# 11. routing.index_match_threshold (SEMANTIC_INDEX bigram hit threshold)
# ---------------------------------------------------------------------------


def test_index_match_threshold_default() -> None:
    """Default stays 0.20 — calibration data is insufficient to justify a change."""
    assert RoutingConfig().index_match_threshold == pytest.approx(0.20)


def test_index_match_threshold_from_project_toml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A [routing] index_match_threshold in .vibe/config.toml takes effect."""
    vibe_dir = tmp_path / ".vibe"
    vibe_dir.mkdir()
    (vibe_dir / "config.toml").write_text(
        "[routing]\nindex_match_threshold = 0.42\n",
        encoding="utf-8",
    )
    real_resolve = ConfigSource._resolve_config_path  # pyright: ignore[reportPrivateUsage]

    def _no_global(base_dir: Path, name: str) -> Path | None:
        # Keep the real home ~/.vibe config out of this test.
        if base_dir == Path.home() / ".vibe":
            return None
        return real_resolve(base_dir, name)

    monkeypatch.setattr(
        ConfigSource,
        "_resolve_config_path",
        staticmethod(_no_global),  # type: ignore[arg-type]
    )
    manager = ConfigManager(project_root=str(tmp_path))
    rc = manager.get_routing_config()
    assert rc.index_match_threshold == pytest.approx(0.42)


def test_index_match_threshold_out_of_range_rejected() -> None:
    """Values outside [0.0, 1.0) are rejected by pydantic — TolerantConfig
    only ignores unknown keys, it does not relax field constraints. 1.0 is
    excluded because the confidence scaling divides by (1.0 - threshold)."""
    with pytest.raises(ValidationError):
        RoutingConfig(index_match_threshold=1.5)
    with pytest.raises(ValidationError):
        RoutingConfig(index_match_threshold=-0.1)
    with pytest.raises(ValidationError):
        RoutingConfig(index_match_threshold=1.0)


def test_ai_triage_recall_min_similarity_bounds() -> None:
    """ai_triage_recall_min_similarity is bounded to [0.0, 1.0] inclusive —
    unlike index_match_threshold, 1.0 is valid here (drop everything)."""
    assert RoutingConfig().ai_triage_recall_min_similarity == pytest.approx(0.25)
    RoutingConfig(ai_triage_recall_min_similarity=0.0)
    RoutingConfig(ai_triage_recall_min_similarity=1.0)
    with pytest.raises(ValidationError):
        RoutingConfig(ai_triage_recall_min_similarity=-0.1)
    with pytest.raises(ValidationError):
        RoutingConfig(ai_triage_recall_min_similarity=1.1)


def test_index_external_match_threshold_default_and_bounds() -> None:
    """External pack profiles clear a higher SEMANTIC_INDEX token bar (0.30);
    bounded to [0.0, 1.0) like index_match_threshold."""
    assert RoutingConfig().index_external_match_threshold == pytest.approx(0.30)
    RoutingConfig(index_external_match_threshold=0.0)
    RoutingConfig(index_external_match_threshold=0.9)
    with pytest.raises(ValidationError):
        RoutingConfig(index_external_match_threshold=1.0)
    with pytest.raises(ValidationError):
        RoutingConfig(index_external_match_threshold=-0.1)


def test_index_embedding_min_margin_default_and_bounds() -> None:
    """Embedding fallback requires a top1-top2 gap (default 0.05); 0 disables
    the check, values above 0.5 are rejected as nonsense."""
    assert RoutingConfig().index_embedding_min_margin == pytest.approx(0.05)
    RoutingConfig(index_embedding_min_margin=0.0)
    RoutingConfig(index_embedding_min_margin=0.5)
    with pytest.raises(ValidationError):
        RoutingConfig(index_embedding_min_margin=-0.1)
    with pytest.raises(ValidationError):
        RoutingConfig(index_embedding_min_margin=0.6)


def test_index_embedding_threshold_default_and_bounds() -> None:
    """index_embedding_threshold (embedding-fallback cosine floor) defaults to
    0.45 and is bounded to [0.0, 1.0) like index_match_threshold."""
    assert RoutingConfig().index_embedding_threshold == pytest.approx(0.45)
    RoutingConfig(index_embedding_threshold=0.0)
    RoutingConfig(index_embedding_threshold=0.9)
    with pytest.raises(ValidationError):
        RoutingConfig(index_embedding_threshold=1.0)
    with pytest.raises(ValidationError):
        RoutingConfig(index_embedding_threshold=-0.1)


def test_index_external_trusted_floor_default_and_bounds() -> None:
    """index_external_trusted_floor (pack-vs-trusted arbitration) defaults to
    0.35; bounded to [0.0, 1.0). 0 disables the arbitration."""
    assert RoutingConfig().index_external_trusted_floor == pytest.approx(0.35)
    RoutingConfig(index_external_trusted_floor=0.0)
    RoutingConfig(index_external_trusted_floor=0.9)
    with pytest.raises(ValidationError):
        RoutingConfig(index_external_trusted_floor=1.0)
    with pytest.raises(ValidationError):
        RoutingConfig(index_external_trusted_floor=-0.1)
