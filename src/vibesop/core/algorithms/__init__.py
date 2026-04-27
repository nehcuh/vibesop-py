"""Reusable algorithm library for VibeSOP skills.

Algorithms declared in a skill's frontmatter can be resolved via AlgorithmRegistry.
"""

from vibesop.core.algorithms.interview.compute_ambiguity import compute_ambiguity
from vibesop.core.algorithms.ralph.scan_file import scan_file
from vibesop.core.algorithms.registry import AlgorithmRegistry

AlgorithmRegistry.register(
    "interview/compute_ambiguity",
    compute_ambiguity,
    "Mathematical ambiguity scoring from 5 clarity dimensions",
)
AlgorithmRegistry.register(
    "ralph/scan_file",
    scan_file,
    "Scan file for AI slop patterns (redundant comments, trivial wrappers, etc.)",
)

__all__ = ["AlgorithmRegistry", "compute_ambiguity", "scan_file"]
