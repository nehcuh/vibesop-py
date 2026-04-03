"""Common helper functions for VibeSOP.

This module provides utility functions that are used across
multiple modules, promoting code reuse and consistency.
"""

import os
from pathlib import Path
from typing import Any, Dict

from ruamel.yaml import YAML


def normalize_path(path: Path) -> Path:
    """Normalize a file path.

    Resolves user home directory (~) and converts to absolute path.

    Args:
        path: Path to normalize

    Returns:
        Normalized absolute path
    """
    expanded = path.expanduser()
    resolved = expanded.resolve()
    return resolved


def ensure_directory(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists

    Returns:
        The directory path
    """
    path = normalize_path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_yaml_safe(path: Path) -> Dict[str, Any]:
    """Load a YAML file safely with error handling.

    Args:
        path: Path to YAML file

    Returns:
        Parsed YAML data as dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If YAML parsing fails
        OSError: If file cannot be read
    """
    path = normalize_path(path)

    if not path.exists():
        from vibesop.constants import FileSystemSettings
        raise FileNotFoundError(
            f"YAML file not found: {path}"
        )

    try:
        yaml_parser = YAML()
        with open(path, "r", encoding=FileSystemSettings.DEFAULT_ENCODING) as f:
            data = yaml_parser.load(f)
            return data if isinstance(data, dict) else {}

    except Exception as e:
        raise ValueError(f"Failed to parse YAML file {path}: {e}") from e

    except (OSError, IOError) as e:
        raise OSError(f"Failed to read YAML file {path}: {e}") from e


def write_yaml_safe(path: Path, data: Dict[str, Any]) -> None:
    """Write data to YAML file safely.

    Args:
        path: Path to YAML file
        data: Data to write

    Raises:
        ValueError: If data serialization fails
        OSError: If file cannot be written
    """
    from vibesop.constants import FileSystemSettings
    from vibesop.utils.atomic_writer import write_text

    path = normalize_path(path)

    # Ensure parent directory exists
    ensure_directory(path.parent)

    try:
        from io import StringIO
        yaml_parser = YAML()
        yaml_parser.default_flow_style = False
        yaml_parser.sort_keys = False

        string_stream = StringIO()
        yaml_parser.dump(data, string_stream)
        yaml_content = string_stream.getvalue()

        write_text(path, yaml_content, encoding=FileSystemSettings.DEFAULT_ENCODING)

    except Exception as e:
        raise ValueError(f"Failed to serialize data to YAML: {e}") from e


def get_cache_path(base_dir: Path, *path_parts: str) -> Path:
    """Get a path within the cache directory.

    Args:
        base_dir: Base directory for cache
        *path_parts: Additional path components

    Returns:
        Path within cache directory
    """
    from vibesop.constants import CacheSettings, FileSystemSettings

    cache_dir = base_dir / FileSystemSettings.CONFIG_DIR / CacheSettings.DEFAULT_CACHE_DIR
    return cache_dir.joinpath(*path_parts)


def get_config_path(base_dir: Path, *path_parts: str) -> Path:
    """Get a path within the configuration directory.

    Args:
        base_dir: Base directory for config
        *path_parts: Additional path components

    Returns:
        Path within config directory
    """
    from vibesop.constants import FileSystemSettings

    config_dir = base_dir / FileSystemSettings.CONFIG_DIR
    return config_dir.joinpath(*path_parts)


def merge_dicts(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries.

    Args:
        base: Base dictionary
        overlay: Dictionary to overlay on base

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    return text[: max_length - len(suffix)] + suffix


def format_timestamp(timestamp: float) -> str:
    """Format a timestamp as human-readable string.

    Args:
        timestamp: Unix timestamp

    Returns:
        Formatted timestamp string
    """
    from datetime import datetime

    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def calculate_age(timestamp: float) -> str:
    """Calculate human-readable age from timestamp.

    Args:
        timestamp: Unix timestamp

    Returns:
        Human-readable age string (e.g., "2 days ago")
    """
    from datetime import datetime

    dt = datetime.fromtimestamp(timestamp)
    delta = datetime.now() - dt

    seconds = delta.total_seconds()

    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days > 1 else ''} ago"
