#!/usr/bin/env python3
"""Check version number consistency across all documentation files.

Scans markdown files for version declarations and reports inconsistencies.
This helps prevent the version-number chaos that occurs when docs drift.

Usage:
    python scripts/check_doc_versions.py
    python scripts/check_doc_versions.py --fix

Exit codes:
    0 - all versions consistent
    1 - inconsistencies found
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SOURCE_OF_TRUTH = PROJECT_ROOT / "pyproject.toml"

# Regex patterns to find version declarations in markdown files.
# The capture group is intentionally narrow: only MAJOR.MINOR.PATCH
# to avoid matching version ranges like 1.0.0..v1.1.1 or 5.5.0+).
VERSION_PATTERNS = [
    re.compile(r">\s*\*\*[Vv]ersion\*\*\s*[:：]\s*([0-9]+\.[0-9]+\.[0-9]+)"),
    re.compile(r">\s*[Vv]ersion\s*[:：]\s*([0-9]+\.[0-9]+\.[0-9]+)"),
    re.compile(r"\*\*[Vv]ersion\*\*\s*[:：]\s*([0-9]+\.[0-9]+\.[0-9]+)"),
    re.compile(r"[Vv]ersion\s*[:：]\s*([0-9]+\.[0-9]+\.[0-9]+)"),
    re.compile(r"\bv([0-9]+\.[0-9]+\.[0-9]+)\b"),
]

# Directories to skip entirely (not project docs)
SKIP_DIRS = {
    ".venv",
    ".vibe",
    ".omx",  # review/gate artifacts are point-in-time records, not versioned docs
    "core/skills",
    "examples",
    "scripts",
    "memory",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "node_modules",
}

# Files that are allowed to reference historical versions
HISTORICAL_FILES = {
    "CHANGELOG.md",
    "docs/ROADMAP.md",
    "docs/version_05.md",
    "docs/vibe-coding-article.md",
    "docs/DISCUSSION_SUMMARY.md",
    "docs/superpowers/plans/2026-04-24-architecture-optimization.md",
    "docs/superpowers/plans/2026-04-24-unify-v5-roadmap-orchestration.md",
    "docs/adr/001-skill-ecosystem-evolution.md",
    "docs/adr/002-optimization-roadmap-v55.md",
    "docs/archive/",
}


def get_expected_version() -> str:
    """Read canonical version from pyproject.toml."""
    text = SOURCE_OF_TRUTH.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        print("ERROR: Could not find version in pyproject.toml", file=sys.stderr)
        sys.exit(1)
    return match.group(1)


def is_historical_file(path: Path) -> bool:
    """Check if a file is allowed to reference historical versions."""
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    for prefix in HISTORICAL_FILES:
        if rel == prefix or rel.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


def should_skip(path: Path) -> bool:
    """Check if a file should be skipped (not a project doc)."""
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    return any(rel.startswith(skip + "/") for skip in SKIP_DIRS)


def find_versions_in_file(path: Path) -> list[tuple[int, str]]:
    """Find all version declarations in a markdown file."""
    versions: list[tuple[int, str]] = []
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in VERSION_PATTERNS:
            for match in pattern.finditer(line):
                versions.append((line_no, match.group(1)))
    return versions


def main() -> int:
    parser = argparse.ArgumentParser(description="Check doc version consistency")
    parser.add_argument("--fix", action="store_true", help="Auto-fix outdated versions")
    parser.parse_args()

    expected = get_expected_version()
    print(f"Canonical version (pyproject.toml): {expected}")
    print("-" * 60)

    md_files = list(PROJECT_ROOT.rglob("*.md"))
    inconsistencies: list[tuple[Path, int, str]] = []
    checked = 0

    for path in sorted(md_files):
        if should_skip(path) or is_historical_file(path):
            continue
        versions = find_versions_in_file(path)
        if not versions:
            continue
        checked += 1
        rel = path.relative_to(PROJECT_ROOT)
        for line_no, version in versions:
            if version != expected:
                inconsistencies.append((rel, line_no, version))
                print(f"  MISMATCH {rel}:{line_no} -> {version} (expected {expected})")

    print("-" * 60)
    if inconsistencies:
        print(f"FAIL: {len(inconsistencies)} version mismatch(es) in {checked} checked files.")
        return 1
    else:
        print(f"PASS: All versions consistent in {checked} checked files.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
