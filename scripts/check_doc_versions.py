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
# to avoid matching version ranges like 1.0.0..v1.1.1.
#
# Pattern 5 policy (gate29 pi MEDIUM): the "since" exemption applies ONLY
# to the parenthesised annotation form `(vX.Y.Z+)` — see _is_since_annotation
# in find_versions_in_file. A BARE `vX.Y.Z+` (e.g. `> **Version**: v8.0.0+`)
# is still a current-version claim and IS checked. A bare `vX.Y.Z` without
# "+" is always checked.
VERSION_PATTERNS = [
    re.compile(r">\s*\*\*[Vv]ersion\*\*\s*[:：]\s*([0-9]+\.[0-9]+\.[0-9]+)"),
    re.compile(r">\s*[Vv]ersion\s*[:：]\s*([0-9]+\.[0-9]+\.[0-9]+)"),
    re.compile(r"\*\*[Vv]ersion\*\*\s*[:：]\s*([0-9]+\.[0-9]+\.[0-9]+)"),
    re.compile(r"[Vv]ersion\s*[:：]\s*([0-9]+\.[0-9]+\.[0-9]+)"),
    re.compile(r"\bv([0-9]+\.[0-9]+\.[0-9]+)\b"),
]

# Fix-side declaration patterns (gate29 claude MINOR): same contexts as
# VERSION_PATTERNS[:3] — bold/blockquote declaration headers — plus the
# Chinese doc-header labels (文档版本 / 版本, optionally followed by a Latin
# "Version"). Each allows an optional pre-release suffix (``.dev0`` / ``-dev``)
# which --fix STRIPS, so the written value is the exact expected version
# (previously ``8.2.0.dev0`` became ``8.1.0.dev0`` and still passed — the
# group-1-only replacement left the suffix behind).
#
# Safety boundary: pattern 4 of VERSION_PATTERNS (bare ``Version: X``) is
# check-only and deliberately NOT rewritten — in isolation it too often marks
# non-app versions (yaml frontmatter examples, spec-format versions).
_FIX_PATTERNS = [
    re.compile(r">\s*\*\*[Vv]ersion\*\*\s*[:：]\s*v?([0-9]+\.[0-9]+\.[0-9]+)(?:\.dev\d+|-dev)?"),
    re.compile(r">\s*[Vv]ersion\s*[:：]\s*v?([0-9]+\.[0-9]+\.[0-9]+)(?:\.dev\d+|-dev)?"),
    re.compile(r"\*\*[Vv]ersion\*\*\s*[:：]\s*v?([0-9]+\.[0-9]+\.[0-9]+)(?:\.dev\d+|-dev)?"),
    re.compile(
        r">\s*\*\*(?:文档版本|适用版本|版本)(?:\s*[Vv]ersion)?\*\*\s*[:：]\s*v?"
        r"([0-9]+\.[0-9]+\.[0-9]+)(?:\.dev\d+|-dev)?"
    ),
]

# Directories to skip entirely (not project docs)
SKIP_DIRS = {
    ".venv",
    ".vibe",
    ".omx",  # review/gate artifacts are point-in-time records, not versioned docs
    # Knowledge-base export snapshots for external tools (e.g. cmspark
    # import) — point-in-time records, version-stamped at generation.
    "knowledge",
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
    # Generated platform deploy output (produced by ``vibe build`` from
    # docs/ sources) — checking it double-counts the source docs.
    ".pi",
}

# Files that are allowed to reference historical versions
HISTORICAL_FILES = {
    "CHANGELOG.md",
    "docs/ROADMAP.md",
    "docs/vibe-coding-article.md",
    "docs/superpowers/plans/2026-04-24-architecture-optimization.md",
    "docs/superpowers/plans/2026-04-24-unify-v5-roadmap-orchestration.md",
    "docs/adr/001-skill-ecosystem-evolution.md",
    "docs/adr/002-optimization-roadmap-v55.md",
    # ADR-004 is a point-in-time decision record like 001/002 — the
    # exemption set was inconsistent without it.
    "docs/adr/004-deprecated-types-cleanup.md",
    # (Dead entries pruned in gate29: docs/version_05.md and
    # docs/DISCUSSION_SUMMARY.md moved into docs/archive/, which the
    # prefix entry below already covers.)
    "docs/archive/",
}

# Generator-owned files (emitted by ``vibe build``), exempt from app-version
# consistency checks. AGENTS.md's ``> **Version**: 1.0.0`` header is a stale
# CONFIG-FORMAT stamp from an old generator — orthogonal to pyproject's app
# version. CLAUDE.md currently carries NO version string at all; it stays in
# the set because it is equally generator-owned and a regeneration via the
# Jinja template (``templates/claude-code/CLAUDE.md.j2``) would stamp one.
# (The generator itself, adapters/_generation.py, already defaults to the
# real ``__version__``.)
GENERATED_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
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


def is_generated_file(path: Path) -> bool:
    """Check if a file is generator-owned (config-format version header)."""
    return path.relative_to(PROJECT_ROOT).as_posix() in GENERATED_FILES


_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _fence_state_transition(
    fence: tuple[str, int] | None, line: str
) -> tuple[tuple[str, int] | None, bool]:
    """CommonMark fence tracking. Returns (new_state, is_fence_line).

    A fence of N backticks/tildes closes only on the same char with
    length >= N — nested examples (````markdown wrapping ```yaml) must
    not desync the scanner.
    """
    m = _FENCE_RE.match(line)
    if not m:
        return fence, False
    seq = m.group(1)
    if fence is None:
        return (seq[0], len(seq)), True
    if seq[0] == fence[0] and len(seq) >= fence[1]:
        return None, True
    return fence, False


def _strip_code_fences(text: str) -> str:
    """Blank out fenced code blocks.

    Code blocks carry EXAMPLES (install commands with ``pkg@v1.0.0`` git
    tags, config snippets with version comments), not version declarations
    about this project — scanning them false-positives.
    """
    out: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        fence, is_fence = _fence_state_transition(fence, line)
        out.append("" if (fence or is_fence) else line)
    return "\n".join(out)


def _is_since_annotation(line: str, match: re.Match[str]) -> bool:
    """True iff a pattern-5 ``vX.Y.Z`` match is the exempt since-annotation
    form: followed by ``+`` AND wrapped in parentheses — ``(v5.3.0+)``.

    A bare ``v8.0.0+`` (no parens) is NOT exempt: it reads as a
    current-version claim (gate29 pi MEDIUM — the previous blanket ``(?!+)``
    hid real stale declarations like ``> **Version**: v8.0.0+``).
    """
    if line[match.end(1) : match.end(1) + 1] != "+":
        return False
    return match.start() > 0 and line[match.start() - 1] == "("


def find_versions_in_file(path: Path) -> list[tuple[int, str]]:
    """Find all version declarations in a markdown file."""
    versions: list[tuple[int, str]] = []
    text = _strip_code_fences(path.read_text(encoding="utf-8"))
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in VERSION_PATTERNS:
            for match in pattern.finditer(line):
                if pattern is VERSION_PATTERNS[4] and _is_since_annotation(line, match):
                    continue
                versions.append((line_no, match.group(1)))
    return versions


def _sub_declaration(pattern: re.Pattern[str], line: str, expected: str) -> str:
    """Replace the version token of every ``pattern`` match with ``expected``.

    ``_FIX_PATTERNS`` put the optional pre-release suffix OUTSIDE group 1, so
    the replacement spans group-1-start → match-end: ``8.2.0.dev0`` becomes
    exactly ``8.1.0``, no suffix left behind.
    """
    out: list[str] = []
    last = 0
    for m in pattern.finditer(line):
        out.append(line[last : m.start(1)])
        out.append(expected)
        last = m.end()
    out.append(line[last:])
    return "".join(out)


def _sub_group1(pattern: re.Pattern[str], line: str, expected: str) -> str:
    """Replace only the captured version group of every ``pattern`` match."""
    out: list[str] = []
    last = 0
    for m in pattern.finditer(line):
        out.append(line[last : m.start(1)])
        out.append(expected)
        last = m.end(1)
    out.append(line[last:])
    return "".join(out)


def fix_file(path: Path, expected: str) -> int:
    """Auto-fix stale CURRENT-version references in ``path``.

    Deliberately narrow (a wrong bulk rewrite is worse than a manual one).
    What --fix WILL rewrite:
        - explicit declaration headers (``> **Version**: X`` / ``**Version**: X``
          / ``> Version: X`` and the Chinese ``> **文档版本**：`` / ``> **版本**：``
          forms), including an optional ``v`` prefix and a ``.devN`` / ``-dev``
          suffix which is stripped so the written value is exactly ``expected``;
        - pattern-5 ``vX.Y.Z`` matches on lines containing BOTH "current" and
          "version" (dual-word guard — a bare "current" matched unrelated prose
          like "Phase 1: Current Platforms (v4.3.0)", a real misfire).
    What --fix will NOT touch:
        - bare ``Version: X`` without bold/blockquote context (VERSION_PATTERNS[4]
          is check-only — in isolation it too often marks non-app versions such
          as yaml frontmatter or spec-format versions);
        - "since" annotations ``(vX.Y.Z)`` / ``(vX.Y.Z+)`` — their semantics
          must be judged by a human;
        - anything inside fenced code blocks (examples, not declarations).

    Returns the number of rewritten lines.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    fixed = 0
    fence: tuple[str, int] | None = None
    for i, line in enumerate(lines):
        fence, is_fence = _fence_state_transition(fence, line)
        if fence or is_fence:
            continue
        new_line = line
        for pattern in _FIX_PATTERNS:
            new_line = _sub_declaration(pattern, new_line, expected)
        lowered = line.lower()
        if "current" in lowered and "version" in lowered:
            new_line = _sub_group1(VERSION_PATTERNS[4], new_line, expected)
        if new_line != line:
            lines[i] = new_line
            fixed += 1
    if fixed:
        path.write_text("".join(lines), encoding="utf-8")
    return fixed


def main() -> int:
    parser = argparse.ArgumentParser(description="Check doc version consistency")
    parser.add_argument(
        "--fix",
        action="store_true",
        help=(
            "Auto-fix stale current-version references (explicit 'Version:' "
            "declarations and 'current: vX.Y.Z' mentions) before checking. "
            "Never rewrites 'since' annotations like (vX.Y.Z[+])."
        ),
    )
    args = parser.parse_args()

    expected = get_expected_version()
    print(f"Canonical version (pyproject.toml): {expected}")
    print("-" * 60)

    md_files = list(PROJECT_ROOT.rglob("*.md"))

    if args.fix:
        fixed_total = 0
        for path in sorted(md_files):
            if should_skip(path) or is_historical_file(path) or is_generated_file(path):
                continue
            fixed_total += fix_file(path, expected)
        print(f"--fix: rewrote {fixed_total} line(s).")
        print("-" * 60)

    inconsistencies: list[tuple[Path, int, str]] = []
    checked = 0

    for path in sorted(md_files):
        if should_skip(path) or is_historical_file(path) or is_generated_file(path):
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
