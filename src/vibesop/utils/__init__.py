"""Utility modules for VibeSOP.

This package contains various utility modules for
external tools detection, marker file management, and
atomic file operations.
"""

from vibesop.utils.external_tools import (
    ExternalToolsDetector,
    ToolInfo,
    ToolStatus,
)
from vibesop.utils.marker_files import (
    MarkerFileManager,
    MarkerData,
    MarkerType,
)
from vibesop.utils.atomic_writer import (
    AtomicWriter,
    AtomicWriteError,
    write_text,
    write_bytes,
    atomic_open,
)

__all__ = [
    "ExternalToolsDetector",
    "ToolInfo",
    "ToolStatus",
    "MarkerFileManager",
    "MarkerData",
    "MarkerType",
    "AtomicWriter",
    "AtomicWriteError",
    "write_text",
    "write_bytes",
    "atomic_open",
]
