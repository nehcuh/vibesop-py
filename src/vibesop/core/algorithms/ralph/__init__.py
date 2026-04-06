"""Ralph algorithm library — AI slop detection."""

from vibesop.core.algorithms.ralph.deslop import (
    SLOP_PATTERNS,
    SlopPattern,
    SlopReport,
    scan_file,
    scan_files,
)

__all__ = [
    "SLOP_PATTERNS",
    "SlopPattern",
    "SlopReport",
    "scan_file",
    "scan_files",
]
