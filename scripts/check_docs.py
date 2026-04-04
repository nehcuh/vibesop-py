#!/usr/bin/env python3
"""Check documentation consistency with code."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def check_broken_file_references() -> list[str]:
    """Check for references to non-existent files in docs."""
    broken: list[str] = []

    docs_dir = ROOT / "docs"
    if not docs_dir.exists():
        return broken

    file_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for md_file in docs_dir.rglob("*.md"):
        content = md_file.read_text()
        for match in file_pattern.finditer(content):
            link_text, link_path = match.groups()

            if link_path.startswith("http") or link_path.startswith("#"):
                continue

            if not link_path.startswith("/"):
                ref_path = (md_file.parent / link_path).resolve()
            else:
                ref_path = (ROOT / link_path.lstrip("/")).resolve()

            if not ref_path.exists():
                broken.append(f"{md_file.relative_to(ROOT)}: {link_path}")

    return broken


def check_readme_references() -> list[str]:
    """Check README.md for broken references."""
    broken: list[str] = []
    readme = ROOT / "README.md"

    if not readme.exists():
        return broken

    content = readme.read_text()
    file_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for match in file_pattern.finditer(content):
        link_text, link_path = match.groups()

        if link_path.startswith("http") or link_path.startswith("#"):
            continue

        ref_path = (ROOT / link_path).resolve()
        if not ref_path.exists():
            broken.append(f"README.md: {link_path}")

    return broken


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
