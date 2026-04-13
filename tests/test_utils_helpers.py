"""Tests for common helper functions."""

from pathlib import Path

from vibesop.utils.helpers import (
    calculate_age,
    ensure_directory,
    format_timestamp,
    get_cache_path,
    get_config_path,
    load_yaml_safe,
    merge_dicts,
    normalize_path,
    truncate_text,
    write_yaml_safe,
)


class TestNormalizePath:
    """Test suite for normalize_path."""

    def test_expanduser(self, monkeypatch) -> None:
        """Should expand ~ to home directory."""
        import os
        home = os.path.expanduser("~")
        result = normalize_path(Path("~/docs"))
        assert str(result).startswith(home)
        assert "docs" in str(result)

    def test_resolve_relative(self) -> None:
        """Should resolve relative paths to absolute."""
        result = normalize_path(Path("."))
        assert result.is_absolute()


class TestEnsureDirectory:
    """Test suite for ensure_directory."""

    def test_creates_directory(self, tmp_path) -> None:
        """Should create directory if it doesn't exist."""
        target = tmp_path / "new" / "nested"
        result = ensure_directory(target)
        assert result.exists()
        assert result.is_dir()


class TestLoadYamlSafe:
    """Test suite for load_yaml_safe."""

    def test_load_valid_yaml(self, tmp_path) -> None:
        """Should parse valid YAML file."""
        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text("key: value\nlist:\n  - a\n  - b\n", encoding="utf-8")
        data = load_yaml_safe(yaml_path)
        assert data["key"] == "value"
        assert data["list"] == ["a", "b"]

    def test_file_not_found(self, tmp_path) -> None:
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_yaml_safe(tmp_path / "missing.yaml")

    def test_oserror_during_read(self, tmp_path, monkeypatch) -> None:
        """Should raise OSError when read fails."""
        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text("key: value\n", encoding="utf-8")

        def raise_oserror(*args, **kwargs):
            raise OSError("read error")

        monkeypatch.setattr(Path, "open", raise_oserror)
        with pytest.raises(OSError, match="Failed to read YAML file"):
            load_yaml_safe(yaml_path)

    def test_invalid_yaml_content(self, tmp_path) -> None:
        """Should raise ValueError for invalid YAML."""
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("not: valid: : yaml: [", encoding="utf-8")
        with pytest.raises(ValueError, match="Failed to parse YAML file"):
            load_yaml_safe(yaml_path)

    def test_non_dict_yaml_returns_empty_dict(self, tmp_path) -> None:
        """Should return empty dict when YAML is not a mapping."""
        yaml_path = tmp_path / "list.yaml"
        yaml_path.write_text("- a\n- b\n", encoding="utf-8")
        data = load_yaml_safe(yaml_path)
        assert data == {}


class TestWriteYamlSafe:
    """Test suite for write_yaml_safe."""

    def test_write_valid_data(self, tmp_path) -> None:
        """Should serialize dict to YAML file."""
        yaml_path = tmp_path / "out.yaml"
        write_yaml_safe(yaml_path, {"name": "test", "items": [1, 2]})
        content = yaml_path.read_text(encoding="utf-8")
        assert "name: test" in content
        assert "items:" in content

    def test_serialization_error(self, tmp_path, monkeypatch) -> None:
        """Should raise ValueError when serialization fails."""
        yaml_path = tmp_path / "out.yaml"

        def raise_error(*args, **kwargs):
            raise RuntimeError("dump failed")

        monkeypatch.setattr("ruamel.yaml.main.YAML.dump", raise_error)
        with pytest.raises(ValueError, match="Failed to serialize data to YAML"):
            write_yaml_safe(yaml_path, {"key": "value"})


class TestGetCachePath:
    """Test suite for get_cache_path."""

    def test_returns_cache_subdirectory(self, tmp_path) -> None:
        """Should return path under .vibe/cache."""
        result = get_cache_path(tmp_path, "session", "data.json")
        assert ".vibe" in str(result)
        assert "cache" in str(result)
        assert result.name == "data.json"


class TestGetConfigPath:
    """Test suite for get_config_path."""

    def test_returns_config_subdirectory(self, tmp_path) -> None:
        """Should return path under .vibe."""
        result = get_config_path(tmp_path, "config.yaml")
        assert ".vibe" in str(result)
        assert result.name == "config.yaml"


class TestMergeDicts:
    """Test suite for merge_dicts."""

    def test_shallow_merge(self) -> None:
        """Should overlay simple keys."""
        base = {"a": 1, "b": 2}
        overlay = {"b": 3, "c": 4}
        result = merge_dicts(base, overlay)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge(self) -> None:
        """Should recursively merge nested dicts."""
        base = {"a": {"x": 1, "y": 2}}
        overlay = {"a": {"y": 3, "z": 4}}
        result = merge_dicts(base, overlay)
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_overlay_replaces_non_dict(self) -> None:
        """Overlay should replace base value when types differ."""
        base = {"a": [1, 2]}
        overlay = {"a": {"nested": "value"}}
        result = merge_dicts(base, overlay)
        assert result == {"a": {"nested": "value"}}


class TestTruncateText:
    """Test suite for truncate_text."""

    def test_no_truncation_when_short(self) -> None:
        """Should return original text if within limit."""
        assert truncate_text("hello", max_length=10) == "hello"

    def test_truncation_with_default_suffix(self) -> None:
        """Should truncate and append default suffix."""
        text = "a" * 20
        result = truncate_text(text, max_length=10)
        assert result.endswith("...")
        assert len(result) == 10

    def test_truncation_with_custom_suffix(self) -> None:
        """Should truncate and append custom suffix."""
        text = "a" * 20
        result = truncate_text(text, max_length=10, suffix="..")
        assert result.endswith("..")
        assert len(result) == 10


class TestFormatTimestamp:
    """Test suite for format_timestamp."""

    def test_formats_correctly(self) -> None:
        """Should format Unix timestamp as expected."""
        result = format_timestamp(0)
        assert "1970-01-01" in result
        # Local timezone may shift the exact time; just verify HH:MM:SS pattern
        import re
        assert re.search(r"\d{2}:\d{2}:\d{2}", result)


class TestCalculateAge:
    """Test suite for calculate_age."""

    def test_seconds_ago(self, monkeypatch) -> None:
        """Should report seconds for very recent timestamps."""
        import datetime

        now = datetime.datetime(2024, 1, 1, 12, 0, 0)
        monkeypatch.setattr(datetime, "datetime", type("MockDT", (), {"now": staticmethod(lambda: now), "fromtimestamp": datetime.datetime.fromtimestamp}))
        result = calculate_age(now.timestamp() - 30)
        assert "seconds ago" in result

    def test_minutes_ago(self, monkeypatch) -> None:
        """Should report minutes for timestamps within an hour."""
        import datetime

        now = datetime.datetime(2024, 1, 1, 12, 0, 0)
        monkeypatch.setattr(datetime, "datetime", type("MockDT", (), {"now": staticmethod(lambda: now), "fromtimestamp": datetime.datetime.fromtimestamp}))
        result = calculate_age(now.timestamp() - 120)
        assert "2 minutes ago" in result

    def test_hours_ago(self, monkeypatch) -> None:
        """Should report hours for timestamps within a day."""
        import datetime

        now = datetime.datetime(2024, 1, 1, 12, 0, 0)
        monkeypatch.setattr(datetime, "datetime", type("MockDT", (), {"now": staticmethod(lambda: now), "fromtimestamp": datetime.datetime.fromtimestamp}))
        result = calculate_age(now.timestamp() - 7200)
        assert "2 hours ago" in result

    def test_days_ago(self, monkeypatch) -> None:
        """Should report days for older timestamps."""
        import datetime

        now = datetime.datetime(2024, 1, 1, 12, 0, 0)
        monkeypatch.setattr(datetime, "datetime", type("MockDT", (), {"now": staticmethod(lambda: now), "fromtimestamp": datetime.datetime.fromtimestamp}))
        result = calculate_age(now.timestamp() - 172800)
        assert "2 days ago" in result


import pytest
