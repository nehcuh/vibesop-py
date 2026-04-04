"""Tests for utility helper functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.utils.helpers import (
    calculate_age,
    ensure_directory,
    format_timestamp,
    merge_dicts,
    normalize_path,
    truncate_text,
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
