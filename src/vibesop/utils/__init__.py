"""Utility modules for VibeSOP.

This package contains various utility modules for
external tools detection, marker file management, and
atomic file operations.
"""

# External tools detection
# Atomic file operations
from vibesop.utils.atomic_writer import (
    AtomicWriteError,
    AtomicWriter,
    atomic_open,
    write_bytes,
    write_text,
)
from vibesop.utils.external_tools import (
    ExternalToolsDetector,
    ToolInfo,
    ToolStatus,
)

# Common helper functions
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

# Marker file management
from vibesop.utils.marker_files import (
    MarkerData,
    MarkerFileManager,
    MarkerType,
)

__all__ = [
    "AtomicWriteError",
    # Atomic operations
    "AtomicWriter",
    # External tools
    "ExternalToolsDetector",
    "MarkerData",
    # Marker files
    "MarkerFileManager",
    "MarkerType",
    "ToolInfo",
    "ToolStatus",
    "atomic_open",
    "calculate_age",
    "ensure_directory",
    "format_timestamp",
    "get_cache_path",
    "get_config_path",
    "load_yaml_safe",
    "merge_dicts",
    # Helpers
    "normalize_path",
    "truncate_text",
    "write_bytes",
    "write_text",
    "write_yaml_safe",
]
