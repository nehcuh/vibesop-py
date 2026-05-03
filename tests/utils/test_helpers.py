"""Tests for utility helper functions."""

from __future__ import annotations

from pathlib import Path

import pytest

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
    """Tests for normalize_path function."""

    def test_normalize_absolute_path(self) -> None:
        """Test normalizing an absolute path."""
        result = normalize_path(Path("/tmp/test"))
        assert result.is_absolute()

    def test_normalize_home_path(self) -> None:
        """Test normalizing a home directory path."""
        result = normalize_path(Path("~/test"))
        assert result.is_absolute()
        assert "~" not in str(result)


class TestEnsureDirectory:
    """Tests for ensure_directory function."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        """Test that ensure_directory creates the directory."""
        new_dir = tmp_path / "new" / "nested" / "dir"
        result = ensure_directory(new_dir)

        assert result.exists()
        assert result.is_dir()

    def test_existing_directory(self, tmp_path: Path) -> None:
        """Test that ensure_directory works with existing directory."""
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()

        result = ensure_directory(existing_dir)
        assert result.exists()


class TestMergeDicts:
    """Tests for merge_dicts function."""

    def test_simple_merge(self) -> None:
        """Test merging two simple dicts."""
        base = {"a": 1, "b": 2}
        overlay = {"c": 3}
        result = merge_dicts(base, overlay)

        assert result == {"a": 1, "b": 2, "c": 3}

    def test_overlay_overwrites(self) -> None:
        """Test that overlay values overwrite base values."""
        base = {"a": 1, "b": 2}
        overlay = {"b": 20}
        result = merge_dicts(base, overlay)

        assert result["b"] == 20

    def test_deep_merge(self) -> None:
        """Test deep merging nested dicts."""
        base = {"a": {"x": 1, "y": 2}}
        overlay = {"a": {"y": 20, "z": 3}}
        result = merge_dicts(base, overlay)

        assert result == {"a": {"x": 1, "y": 20, "z": 3}}

    def test_empty_overlay(self) -> None:
        """Test merging with empty overlay."""
        base = {"a": 1}
        result = merge_dicts(base, {})

        assert result == {"a": 1}

    def test_empty_base(self) -> None:
        """Test merging with empty base."""
        overlay = {"a": 1}
        result = merge_dicts({}, overlay)

        assert result == {"a": 1}


class TestTruncateText:
    """Tests for truncate_text function."""

    def test_no_truncation_needed(self) -> None:
        """Test text shorter than max_length."""
        result = truncate_text("hello", max_length=10)
        assert result == "hello"

    def test_truncation(self) -> None:
        """Test text longer than max_length."""
        result = truncate_text("hello world", max_length=8)
        assert len(result) <= 8
        assert result.endswith("...")

    def test_exact_length(self) -> None:
        """Test text exactly at max_length."""
        result = truncate_text("hello", max_length=5)
        assert result == "hello"

    def test_custom_suffix(self) -> None:
        """Test custom suffix."""
        result = truncate_text("hello world", max_length=8, suffix=">>")
        assert result.endswith(">>")


class TestFormatTimestamp:
    """Tests for format_timestamp function."""

    def test_format_timestamp(self) -> None:
        """Test formatting a timestamp."""
        result = format_timestamp(1700000000.0)
        assert "2023" in result
        assert ":" in result


class TestCalculateAge:
    """Tests for calculate_age function."""

    def test_seconds_ago(self) -> None:
        """Test age in seconds."""
        import time

        ts = time.time() - 30
        result = calculate_age(ts)
        assert "seconds" in result

    def test_minutes_ago(self) -> None:
        """Test age in minutes."""
        import time

        ts = time.time() - 120
        result = calculate_age(ts)
        assert "minute" in result

    def test_hours_ago(self) -> None:
        """Test age in hours."""
        import time

        ts = time.time() - 7200
        result = calculate_age(ts)
        assert "hour" in result

    def test_days_ago(self) -> None:
        """Test age in days."""
        import time

        ts = time.time() - 172800
        result = calculate_age(ts)
        assert "day" in result


class TestLoadYamlSafe:
    """Tests for load_yaml_safe function."""

    def test_normal_load(self, tmp_path: Path) -> None:
        """Test loading a valid YAML file."""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("name: test\nvalue: 42\n", encoding="utf-8")
        result = load_yaml_safe(yaml_file)
        assert result == {"name": "test", "value": 42}

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Test that FileNotFoundError is raised for missing file."""
        missing = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError):
            load_yaml_safe(missing)

    def test_parse_error(self, tmp_path: Path) -> None:
        """Test that ValueError is raised for invalid YAML."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("{ invalid", encoding="utf-8")
        with pytest.raises(ValueError):
            load_yaml_safe(bad_yaml)


class TestWriteYamlSafe:
    """Tests for write_yaml_safe function."""

    def test_normal_write(self, tmp_path: Path) -> None:
        """Test writing data to a YAML file."""
        yaml_file = tmp_path / "output.yaml"
        data = {"key": "value", "list": [1, 2, 3]}
        write_yaml_safe(yaml_file, data)
        assert yaml_file.exists()
        content = yaml_file.read_text(encoding="utf-8")
        assert "key: value" in content

    def test_round_trip(self, tmp_path: Path) -> None:
        """Test that written YAML can be read back correctly."""
        yaml_file = tmp_path / "roundtrip.yaml"
        data = {"name": "round", "nested": {"a": 1}}
        write_yaml_safe(yaml_file, data)
        loaded = load_yaml_safe(yaml_file)
        assert loaded == data


class TestGetCachePath:
    """Tests for get_cache_path function."""

    def test_returns_correct_path_structure(self, tmp_path: Path) -> None:
        """Test that cache path includes .vibe/.vibe/cache and path parts."""
        result = get_cache_path(tmp_path, "sub", "file.txt")
        assert result == tmp_path / ".vibe" / ".vibe/cache" / "sub" / "file.txt"

    def test_no_extra_parts(self, tmp_path: Path) -> None:
        """Test cache path with no additional parts."""
        result = get_cache_path(tmp_path)
        assert result == tmp_path / ".vibe" / ".vibe/cache"


class TestGetConfigPath:
    """Tests for get_config_path function."""

    def test_returns_correct_path_structure(self, tmp_path: Path) -> None:
        """Test that config path includes .vibe and path parts."""
        result = get_config_path(tmp_path, "settings.yaml")
        assert result == tmp_path / ".vibe" / "settings.yaml"

    def test_no_extra_parts(self, tmp_path: Path) -> None:
        """Test config path with no additional parts."""
        result = get_config_path(tmp_path)
        assert result == tmp_path / ".vibe"
