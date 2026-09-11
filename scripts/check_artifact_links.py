#!/usr/bin/env python3
"""Guard: tracked docs must not cite `.omx/artifacts/...` paths that git lost.

Why this exists
---------------
`.omx/` used to be ignored by `.git/info/exclude` (machine-local, invisible to
collaborators). Writes landed silently, and the 356 artifacts that survived did
so only because someone ran `git add -f` by hand. The R3/R4 prereg was rescued
that way too — an accounting ledger in a gitignored path is not a ledger.

So: tracked markdown must only point at `.omx/artifacts/...` files that are
actually in the index. A fresh clone must be able to follow every citation.

What it scans
-------------
By default: **tracked** markdown under the given roots (`docs/`, `README.md`,
`CHANGELOG.md`, `ROADMAP.md`). Tracked-only is deliberate — the verdict then
equals fresh-clone semantics, and an uncommitted draft cannot fail the guard.
Use `--include-untracked` to also scan working-tree markdown.

Verdicts (per reference)
------------------------
ok        target is in `git ls-files` (exact path, glob match, or dir prefix)
dangling  target exists on disk but is NOT tracked  -> exit 1
          This is the exact incident this guard is for: the doc cites an
          artifact that only lives on one machine.
stale     target is neither tracked nor on disk (e.g. a historical CHANGELOG
          entry for a gate synthesis that was never committed)
          -> warned, exit 0 by default; `--strict` makes it fatal.

`stale` is split out on purpose. A citation to a file that has vanished
everywhere cannot be repaired by `git add`, so treating it as fatal would make
the guard permanently red on a repo that already has such history, and a gate
that is always red is a gate nobody reads. `--strict` gives the full
fresh-clone invariant when you want it.

Usage:
    uv run python scripts/check_artifact_links.py
    uv run python scripts/check_artifact_links.py --strict
    uv run python scripts/check_artifact_links.py --root . --targets docs README.md
    uv run python scripts/check_artifact_links.py --tracked-list /tmp/ls-files.txt

Exit codes:
    0 - no dangling references (stale ones may still be reported)
    1 - at least one dangling reference (or a stale one under --strict)
    2 - could not determine the tracked set / nothing was scanned (fail-closed)
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Roots scanned by default: the curated docs plus the top-level narratives.
DEFAULT_TARGETS: tuple[str, ...] = ("docs", "README.md", "CHANGELOG.md", "ROADMAP.md")

ARTIFACT_PREFIX = ".omx/artifacts/"

# Captures `.omx/artifacts/<rest>` up to the first delimiter that cannot be
# part of a path in prose: whitespace, backtick, quote, pipe, or the
# CJK brackets/punctuation used in this repo's docs. Angle brackets are
# captured too so template placeholders can be recognised and dropped.
_REF_RE = re.compile(rf"{re.escape(ARTIFACT_PREFIX)}([^\s`'\"|（）【】「」，、；：。]+)")

# Trailing punctuation that is prose, not path. `.md` ends in a letter, so
# stripping a trailing dot is safe; `*` and `?` are kept for glob targets.
_TRAILING_JUNK = ".,;:!?)]}>。，；：！？）】、"


@dataclass(frozen=True)
class ArtifactRef:
    """A single `.omx/artifacts/...` citation found in a markdown file."""

    source: str  # repo-relative path of the citing document
    lineno: int
    target: str  # repo-relative posix path (or glob / dir prefix)
    kind: str  # "file" | "glob" | "dir"
    status: str  # "ok" | "dangling" | "stale"

    def render(self) -> str:
        return f"{self.source}:{self.lineno}: {self.status}: {self.target}"


def extract_targets(text: str) -> list[str]:
    """Return every `.omx/artifacts/...` target written in ``text``.

    Works for backticked paths, markdown link targets, and bare prose paths —
    all three appear in this repo. Template placeholders such as
    `.omx/artifacts/evo-lane-<id>-handback.md` are skipped: they name no file.
    """
    found: list[str] = []
    for match in _REF_RE.finditer(text):
        raw = match.group(1).rstrip(_TRAILING_JUNK).strip("<>")
        if not raw:
            continue
        if "<" in raw or ">" in raw:
            # A placeholder such as `evo-lane-<id>-handback.md` names no file.
            continue
        found.append(ARTIFACT_PREFIX + raw)
    return found


def _kind(target: str) -> str:
    if target.endswith("/"):
        return "dir"
    if any(ch in target for ch in "*?["):
        return "glob"
    return "file"


def classify(target: str, tracked: set[str], root: Path) -> str:
    """Return ``ok`` / ``dangling`` / ``stale`` for one normalized target."""
    kind = _kind(target)
    if kind == "dir":
        if any(path.startswith(target) for path in tracked):
            return "ok"
    elif kind == "glob":
        if any(fnmatch.fnmatch(path, target) for path in tracked):
            return "ok"
    elif target in tracked:
        return "ok"

    # Not in the index. Does it exist in this working tree at all?
    return "dangling" if (root / target).exists() else "stale"


def list_tracked(root: Path) -> set[str]:
    """Return repo-relative paths from ``git ls-files`` (NUL-separated)."""
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git ls-files failed in {root}: {proc.stderr.strip()}")
    return {entry for entry in proc.stdout.split("\0") if entry}


def read_tracked_list(path: Path) -> set[str]:
    """Read an injected tracked-path list (one path per line)."""
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def iter_markdown(
    root: Path,
    targets: Sequence[str],
    tracked: set[str],
    include_untracked: bool = False,
) -> Iterator[str]:
    """Yield repo-relative markdown paths under ``targets``.

    Tracked-only by default so the scan matches fresh-clone semantics; missing
    targets are simply skipped (a root that does not exist is not an error).
    """
    seen: set[str] = set()
    for target in targets:
        candidate = root / target
        if not candidate.exists():
            continue
        if candidate.is_file():
            paths = [candidate]
        else:
            paths = sorted(p for p in candidate.rglob("*.md") if p.is_file())
        for path in paths:
            rel = path.relative_to(root).as_posix()
            if rel in seen:
                continue
            if not include_untracked and rel not in tracked:
                continue
            seen.add(rel)
            yield rel


def scan(
    root: Path,
    targets: Sequence[str],
    tracked: set[str],
    include_untracked: bool = False,
) -> list[ArtifactRef]:
    """Collect every artifact reference under ``targets`` with its verdict."""
    refs: list[ArtifactRef] = []
    for rel in iter_markdown(root, targets, tracked, include_untracked):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for target in extract_targets(line):
                refs.append(
                    ArtifactRef(
                        source=rel,
                        lineno=lineno,
                        target=target,
                        kind=_kind(target),
                        status=classify(target, tracked, root),
                    )
                )
    return refs


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that tracked docs only cite git-tracked .omx/artifacts/ files.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root to scan (default: this script's project root).",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=list(DEFAULT_TARGETS),
        help="Files or directories, relative to --root, that are scanned for markdown.",
    )
    parser.add_argument(
        "--tracked-list",
        type=Path,
        default=None,
        help="Read the tracked-path set from this file instead of running git ls-files.",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Also scan markdown files that are not tracked (default: tracked only).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also fail (exit 1) on 'stale' references — the full fresh-clone invariant.",
    )
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    root: Path = args.root.resolve()

    try:
        tracked = (
            read_tracked_list(args.tracked_list)
            if args.tracked_list is not None
            else list_tracked(root)
        )
    except (RuntimeError, OSError) as exc:
        print(f"check_artifact_links: cannot determine tracked set: {exc}", file=sys.stderr)
        return 2

    refs = scan(root, args.targets, tracked, args.include_untracked)
    if not refs:
        # Nothing scanned is not the same as nothing wrong.
        scanned = list(iter_markdown(root, args.targets, tracked, args.include_untracked))
        if not scanned:
            print(
                "check_artifact_links: no markdown scanned — check --root/--targets.",
                file=sys.stderr,
            )
            return 2
        if not args.quiet:
            print(f"OK: {len(scanned)} markdown file(s) scanned, no artifact references.")
        return 0

    dangling = [ref for ref in refs if ref.status == "dangling"]
    stale = [ref for ref in refs if ref.status == "stale"]

    for ref in dangling:
        print(f"DANGLING {ref.render()}")
    for ref in stale:
        print(f"stale    {ref.render()}")

    if not args.quiet:
        ok = sum(1 for ref in refs if ref.status == "ok")
        print(
            f"check_artifact_links: {len(refs)} reference(s) — "
            f"{ok} ok, {len(dangling)} dangling, {len(stale)} stale."
        )
        if stale and not args.strict:
            print(
                "note: 'stale' targets are absent from both the index and the working tree; "
                "no `git add` can repair them. Re-run with --strict to fail on them."
            )

    return 1 if dangling or (args.strict and stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
