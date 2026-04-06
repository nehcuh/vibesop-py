"""Reusable algorithm library for skill support.

This package provides pure algorithm implementations that can be used
by any skill, not limited to omx skills.

**@experimental**: This is a new feature (v4.0). The API may change.

**Documentation**: See docs/algorithms-guide.md for complete usage guide
and integration examples.

Quick Start:
    from vibesop.core.algorithms import compute_ambiguity

    result = compute_ambiguity(
        DimensionScore(score=0.8),
        DimensionScore(score=0.5),
        DimensionScore(score=0.6),
        DimensionScore(score=0.4),
        DimensionScore(score=0.7),
    )
    print(f"Ambiguity: {result.ambiguity:.2f}")

Available Algorithms:
    • compute_ambiguity() - Multi-dimensional ambiguity scoring
    • scan_file() / scan_files() - AI slop detection in code

Status: Infrastructure awaiting skill integration. Contributions welcome!
"""

from vibesop.core.algorithms.interview.ambiguity import (
    AmbiguityResult,
    DimensionScore,
    compute_ambiguity,
)
from vibesop.core.algorithms.ralph.deslop import (
    SlopPattern,
    SlopReport,
    scan_file,
    scan_files,
)

__all__ = [
    "AmbiguityResult",
    "DimensionScore",
    "SlopPattern",
    "SlopReport",
    "compute_ambiguity",
    "scan_file",
    "scan_files",
]
