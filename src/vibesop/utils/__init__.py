"""Utility modules for VibeSOP.

This package contains various utility modules for
external tools detection, marker file management, and
atomic file operations.
"""

# External tools detection
from vibesop.utils.external_tools import (
    ExternalToolsDetector,
    ToolInfo,
    ToolStatus,
)

# Marker file management
from vibesop.utils.marker_files import (
    MarkerFileManager,
    MarkerData,
    MarkerType,
)

# Atomic file operations
from vibesop.utils.atomic_writer import (
    AtomicWriter,
    AtomicWriteError,
    write_text,
    write_bytes,
    atomic_open,
)

# Common helper functions
from vibesop.utils.helpers import (
    normalize_path,
    ensure_directory,
    load_yaml_safe,
    write_yaml_safe,
    get_cache_path,
    get_config_path,
    merge_dicts,
    truncate_text,
    format_timestamp,
    calculate_age,
)

__all__ = [
    # External tools
    "ExternalToolsDetector",
    "ToolInfo",
    "ToolStatus",
    # Marker files
    "MarkerFileManager",
    "MarkerData",
    "MarkerType",
    # Atomic operations
    "AtomicWriter",
    "AtomicWriteError",
    "write_text",
    "write_bytes",
    "atomic_open",
    # Helpers
    "normalize_path",
    "ensure_directory",
    "load_yaml_safe",
    "write_yaml_safe",
    "get_cache_path",
    "get_config_path",
    "merge_dicts",
    "truncate_text",
    "format_timestamp",
    "calculate_age",
]
