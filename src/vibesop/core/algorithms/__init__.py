"""Reusable algorithm library for VibeSOP skills.

Algorithms declared in a skill's frontmatter can be resolved via AlgorithmRegistry.
"""

from vibesop.core.algorithms.interview.ambiguity import compute_ambiguity
from vibesop.core.algorithms.ralph.deslop import scan_file, scan_files
from vibesop.core.algorithms.registry import AlgorithmRegistry

AlgorithmRegistry.register(
    "interview/compute_ambiguity",
    compute_ambiguity,
    description="Mathematical ambiguity scoring for requirements clarification",
)
AlgorithmRegistry.register(
    "ralph/scan_file",
    scan_file,
    description="AI slop detection for a single file",
)
AlgorithmRegistry.register(
    "ralph/scan_files",
    scan_files,
    description="Batch AI slop detection across multiple files",
)

__all__ = ["AlgorithmRegistry"]
