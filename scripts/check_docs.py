#!/usr/bin/env python3
"""Check documentation consistency with code.

Validates that markdown links in docs/ and README.md resolve to real files,
and that ``path#fragment`` links point at anchors that actually exist in the
target document (GitHub heading-slug rules).

Calibration notes (gate-debt cleanup):
    - Fenced code blocks are stripped before scanning: Rich console markup
      inside embedded Python snippets (e.g. ``[yellow](见上)[/yellow]``)
      otherwise parses as a markdown link and false-positives.
    - ``docs/archive/`` is exempt (point-in-time snapshots), aligned with
      check_doc_versions.py's HISTORICAL_FILES.
"""

from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Point-in-time snapshots — aligned with check_doc_versions.HISTORICAL_FILES.
EXEMPT_DIRS = ("docs/archive/",)

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)

# CommonMark fence rule: a fence of N backticks (or tildes) closes only on a
# fence of the same char with length >= N. Matters for nested examples (a
# ````markdown block containing a ```yaml block).
_FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _looks_like_path(file_part: str) -> bool:
    """Heuristic gate against markup false positives: a real file reference
    contains a slash or a dot (``docs/x.md``, ``./y``, ``ROADMAP.md``).
    Rich-style markup pasted as plain text — ``[yellow](见上)``,
    ``[dim]({category})`` in unfenced diff dumps — has neither and is not a
    link worth resolving.

    Accepted blind spot (gate29 pi#5): a genuine link whose target has
    neither slash nor dot (e.g. a bare ``[x](habit)``) is silently SKIPPED,
    not flagged. In practice real doc links always carry a path separator or
    an extension; the one observed instance of the bare form lived in
    docs/archive/ (exempt)."""
    return "/" in file_part or "." in file_part


def _strip_code_fences(content: str) -> str:
    """Blank out fenced code blocks so embedded markup isn't parsed as links."""
    out: list[str] = []
    fence: tuple[str, int] | None = None  # (char, length) of the open fence
    for line in content.splitlines():
        m = _FENCE_OPEN_RE.match(line)
        if m:
            seq = m.group(1)
            if fence is None:
                fence = (seq[0], len(seq))
                out.append("")
                continue
            if seq[0] == fence[0] and len(seq) >= fence[1]:
                fence = None
                out.append("")
                continue
        out.append("" if fence else line)
    return "\n".join(out)


def _github_slug(heading: str) -> str:
    """GitHub heading-anchor slug: lowercase, drop punctuation (keep word
    chars, spaces, hyphens), spaces -> hyphens."""
    s = heading.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def _anchors_of(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return {_github_slug(m.group(1)) for m in _HEADING_RE.finditer(_strip_code_fences(text))}


def _check_links_in(md_file: Path, base: Path) -> list[str]:
    """Validate markdown links in ``md_file``; relative links resolve from
    ``base``, root-absolute links from the repo root."""
    broken: list[str] = []
    content = _strip_code_fences(md_file.read_text(encoding="utf-8"))

    for match in _LINK_RE.finditer(content):
        _link_text, link_path = match.groups()

        if link_path.startswith("http") or link_path.startswith("#"):
            continue

        # Split off a #fragment: the file must exist AND the anchor must
        # exist in the target document.
        file_part, _, fragment = link_path.partition("#")
        fragment = urllib.parse.unquote(fragment)

        if file_part and not _looks_like_path(file_part):
            continue

        if not file_part:
            ref_path = md_file
        elif not file_part.startswith("/"):
            ref_path = (base / file_part).resolve()
        else:
            ref_path = (ROOT / file_part.lstrip("/")).resolve()

        if not ref_path.exists():
            broken.append(f"{md_file.relative_to(ROOT)}: {link_path}")
        elif fragment and ref_path.is_file() and fragment not in _anchors_of(ref_path):
            broken.append(f"{md_file.relative_to(ROOT)}: {link_path} (missing anchor)")

    return broken


def check_broken_file_references() -> list[str]:
    """Check for references to non-existent files in docs."""
    broken: list[str] = []

    docs_dir = ROOT / "docs"
    if not docs_dir.exists():
        return broken

    for md_file in docs_dir.rglob("*.md"):
        rel = md_file.relative_to(ROOT).as_posix()
        if any(rel.startswith(d) for d in EXEMPT_DIRS):
            continue
        broken.extend(_check_links_in(md_file, md_file.parent))

    return broken


def check_readme_references() -> list[str]:
    """Check README.md for broken references."""
    readme = ROOT / "README.md"
    if not readme.exists():
        return []
    return _check_links_in(readme, ROOT)


def main() -> None:
    """Run all consistency checks."""
    print("Checking documentation consistency...\n")

    broken: list[str] = []
    broken.extend(check_broken_file_references())
    broken.extend(check_readme_references())

    if broken:
        print(f"Found {len(broken)} broken references:\n")
        for ref in broken:
            print(f"  ❌ {ref}")
        sys.exit(1)
    else:
        print("✅ No broken references found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
