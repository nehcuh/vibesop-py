#!/usr/bin/env python3
"""Guard: tracked docs must not cite `.omx/artifacts/...` paths that git lost.

Why this exists
---------------
`.omx/` used to be ignored by `.git/info/exclude` (machine-local, invisible to
collaborators). Writes landed silently, and artifacts that survived did so
only because someone ran `git add -f` by hand. An accounting ledger in a
gitignored path is not a ledger.

Settled policy: local-only historical/research artifacts may still be retained
under a developer-local `.git/info/exclude`. Any artifact cited by a tracked
Markdown document must itself be tracked. This guard enforces that
tracked-document contract even when a local exclude hides the file from
ordinary `git status`.

So: tracked markdown must only point at `.omx/artifacts/...` files that are
actually in the index. A fresh clone must be able to follow every citation.

What it scans
-------------
By default: **tracked** markdown under the given roots (`docs/`, `README.md`,
`CHANGELOG.md`, `ROADMAP.md`). Tracked-only is deliberate for the *citing
documents* — an uncommitted draft cannot fail the guard, so the scan set
matches fresh-clone semantics. Use `--include-untracked` to also scan
working-tree markdown.

Verdicts (per reference)
------------------------
ok        target is in `git ls-files` (exact path, glob match, or dir prefix).
          Tracked matching is index/fresh-clone based.
dangling  target is NOT tracked, but an on-disk hit exists  -> exit 1
          This is the exact incident this guard is for: the doc cites an
          artifact that only lives on one machine. A glob such as
          `.omx/artifacts/foo-*` with no tracked match is dangling when one
          or more matching paths exist on disk under `.omx/artifacts`.
          Dangling glob detection consults the working tree; a fresh clone
          with no untracked files would classify the same glob as stale.
stale     target is neither tracked nor on disk (e.g. a historical CHANGELOG
          entry for a gate synthesis that was never committed, or a glob
          with no on-disk match either)
          -> warned, exit 0 by default; `--strict` makes it fatal.

`stale` is split out on purpose. A citation to a file that has vanished
everywhere cannot be repaired by `git add`, so treating it as fatal would make
the guard permanently red on a repo that already has such history, and a gate
that is always red is a gate nobody reads. `--strict` gives the full
fresh-clone invariant when you want it.

Encoding
--------
`git ls-files -z` is read as bytes and decoded as UTF-8 with
``errors="surrogateescape"`` (lossless, independent of the process locale).
``text=True`` would decode via the locale encoding (cp1252 on many Windows
installs) and drop CJK paths. Injected ``--tracked-list`` files and scanned
markdown are UTF-8 strict: OSError / UnicodeDecodeError is exit 2.

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
import os
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

# Markdown *link destinations* only: a pre-`?` basename ending in `.` plus
# an alphanumeric extension (`report.md`) means the `?` starts a query
# (`report.md?raw`, `report.md?download`). `gate7-?.md` / `v1.2-?.md` do
# not match: the `?` sits before the suffix. Backticked and bare references
# do not use this heuristic — a lone `?` stays a glob wildcard.
_QUERY_AFTER_EXT_RE = re.compile(r"\.[A-Za-z0-9]+$")


class GuardError(Exception):
    """The inputs could not be read — the guard cannot reach a verdict."""


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


_DEST_PREFIX_BEFORE_DOT_SLASH = frozenset("(<: \t")
_LINK_DEF_INDENT = frozenset(" \t")


def _rskip_ws(text: str, i: int) -> int:
    """Walk left past ASCII spaces and tabs."""
    while i > 0 and text[i - 1] in " \t":
        i -= 1
    return i


def _skip_markdown_destination_prefix(text: str, start: int) -> int:
    """Walk left from an ``.omx/artifacts/`` match past wrapping destination syntax.

    Consumes, in this order: an optional ``./`` relative prefix, optional
    whitespace, an optional ``<`` angle opener, and optional whitespace after
    ``](`` or ``:``. ``./`` is skipped only when it is a path component (preceded
    by ``(``, ``<``, ``:``, or whitespace), not the trailing ``./`` of ``../``.
    """
    i = start
    if (
        i >= 2
        and text[i - 2 : i] == "./"
        and (i == 2 or text[i - 3] in _DEST_PREFIX_BEFORE_DOT_SLASH)
    ):
        i -= 2
    i = _rskip_ws(text, i)
    if i > 0 and text[i - 1] == "<":
        i -= 1
        i = _rskip_ws(text, i)
    return i


def _is_link_reference_definition(text: str, dest_start: int) -> bool:
    """True if ``dest_start`` follows a CommonMark link reference definition.

    Requires ``[label]:`` at the beginning of the current line, with up to
    three spaces or tabs of indentation. A 4-space indent is a code block, not
    a definition. The label must contain a non-whitespace character.
    """
    i = _rskip_ws(text, dest_start)
    if i < 2 or text[i - 1] != ":":
        return False
    i -= 1
    if text[i - 1] != "]":
        return False
    close = i - 1
    open_br = text.rfind("[", 0, close)
    if open_br == -1:
        return False
    label = text[open_br + 1 : close]
    if not label.strip() or "]" in label:
        return False
    line_prefix = text[:open_br]
    if "\n" in line_prefix:
        line_prefix = line_prefix.rsplit("\n", 1)[-1]
    return len(line_prefix) <= 3 and all(ch in _LINK_DEF_INDENT for ch in line_prefix)


def _is_markdown_link_destination(text: str, match: re.Match[str]) -> bool:
    """True if ``match`` sits in a Markdown link destination or definition.

    Inline: ``[x](.omx/artifacts/report.md?raw)``, with optional whitespace
    after ``(``, optional ``./`` before ``.omx``, and optional ``<...>``
    wrapping — including combinations such as ``[x]( <./.omx/...?raw> )``.

    Reference definition: ``[r]: .omx/artifacts/report.md?raw`` at line start
    with optional indent, optional ``./``, and optional angle wrapping.

    Backticks, bare prose, autolinks, and mid-line ``[label]:`` are not
    destinations. Query stripping stays context-aware; this is not
    unconditional extension stripping.
    """
    opener = _skip_markdown_destination_prefix(text, match.start())
    if opener >= 2 and text[opener - 2 : opener] == "](":
        return True
    return _is_link_reference_definition(text, opener)


def extract_targets(text: str) -> list[str]:
    """Return every `.omx/artifacts/...` target written in ``text``.

    Works for backticked paths, markdown link targets, and bare prose paths —
    all three appear in this repo. Template placeholders such as
    `.omx/artifacts/evo-lane-<id>-handback.md` are skipped: they name no file.

    Query stripping is context-aware: Markdown link destinations and
    reference definitions treat a ``?`` after a file extension as a URL
    query; backticked and bare references only strip an explicit
    ``key=value`` query and otherwise keep ``?`` as a glob wildcard. See
    ``_strip_markdown_suffixes``.
    """
    found: list[str] = []
    for match in _REF_RE.finditer(text):
        raw = match.group(1).rstrip(_TRAILING_JUNK).strip("<>")
        if not raw:
            continue
        if "<" in raw or ">" in raw:
            # A placeholder such as `evo-lane-<id>-handback.md` names no file.
            continue
        raw = _strip_markdown_suffixes(
            raw, markdown_link=_is_markdown_link_destination(text, match)
        )
        if not raw:
            continue
        found.append(ARTIFACT_PREFIX + raw)
    return found


def _strip_markdown_suffixes(raw: str, *, markdown_link: bool) -> str:
    """Drop a Markdown/URL fragment or query from a captured path.

    ``[x](.omx/artifacts/report.md#section)`` must validate ``report.md``.

    Context rule for ``?`` (conservative syntactic rule, no filesystem check):

    1. Fragment: drop everything from the first ``#``.
    2. Explicit ``key=value`` query (``report.md?raw=1``): strip from ``?``
       in every context.
    3. Markdown link destinations and reference definitions only: also
       strip a lone query flag when the pre-``?`` *basename* ends with
       ``.`` plus an alphanumeric extension
       (``[x](.omx/artifacts/report.md?raw)``,
       ``[x](./.omx/artifacts/report.md?raw)``,
       ``[r]: .omx/artifacts/report.md?download``), or when the query uses
       ``&``. A ``?`` that is not after an extension stays a glob
       (``gate7-?.md``).
    4. Backticked or bare references: a lone ``?`` is a glob wildcard
       (``gate7-?.md``, ``v1.2-?.md``, ``v1.2?.md``, ``report.v2?.md``,
       ``report.md?raw``). Dots in the stem are not evidence of a URL.
    """
    raw = raw.split("#", 1)[0]
    qpos = raw.find("?")
    if qpos == -1:
        return raw
    after = raw[qpos + 1 :]
    before = raw[:qpos]
    if "=" in after:
        return before
    if markdown_link:
        if "&" in after:
            return before
        basename = before.rsplit("/", 1)[-1]
        if _QUERY_AFTER_EXT_RE.search(basename):
            return before
    return raw


def _kind(target: str) -> str:
    if target.endswith("/"):
        return "dir"
    if any(ch in target for ch in "*?["):
        return "glob"
    return "file"


def _walk_onerror(err: OSError) -> None:
    """Fail closed when ``os.walk`` cannot list an artifacts subdirectory."""
    raise GuardError(f"cannot walk .omx/artifacts: {err}") from err


def _iter_on_disk_artifact_paths(artifact_root: Path) -> Iterator[str]:
    """Yield repo-relative posix paths under a resolved `.omx/artifacts` root.

    `os.walk(..., followlinks=False)` so a glob cannot traverse out of the
    artifact directory via `..` or directory symlinks. Listing errors raise
    ``GuardError`` instead of being skipped.
    """
    for dirpath, _dirnames, filenames in os.walk(
        artifact_root, followlinks=False, onerror=_walk_onerror
    ):
        dir_path = Path(dirpath)
        try:
            rel_dir = dir_path.relative_to(artifact_root).as_posix()
        except ValueError as extra:
            raise GuardError(f"walk escaped artifact root {artifact_root}: {dirpath}") from extra
        if rel_dir == ".":
            rel_dir = ""
        if rel_dir:
            yield ARTIFACT_PREFIX + rel_dir
            yield ARTIFACT_PREFIX + rel_dir + "/"
        for name in filenames:
            rel = f"{rel_dir}/{name}" if rel_dir else name
            yield ARTIFACT_PREFIX + rel


_ROOT_WHATS = frozenset({"repository root", "--root", "artifact root"})


def _resolve_path(path: Path, *, what: str) -> Path:
    """Resolve ``path``, converting loops / OS / ValueError into GuardError.

    ``RuntimeError`` / ``OSError`` (symlink loops, I/O) become
    ``cannot resolve ...``. ``ValueError`` is this boundary's mapping:
    ``invalid_root`` when ``what`` names a root, otherwise ``invalid_target``.
    """
    try:
        return path.resolve()
    except (RuntimeError, OSError) as exc:
        raise GuardError(f"cannot resolve {what} ({path}): {exc}") from exc
    except ValueError as extra:
        label = "invalid_root" if what in _ROOT_WHATS else "invalid_target"
        raise GuardError(f"{label}: cannot resolve {what} ({path}): {extra}") from extra


def _resolved_artifact_root(root: Path) -> Path | None:
    """Return the in-repo `.omx/artifacts` directory, or None if absent.

    A missing directory is not an error (no on-disk glob hits). If the path
    exists as a symlink loop, or resolves outside the repository, raise
    ``GuardError`` — the guard cannot safely decide whether a glob matches.
    """
    raw = root / ".omx" / "artifacts"
    try:
        present = raw.exists() or raw.is_symlink()
    except (OSError, ValueError) as exc:
        raise GuardError(f"cannot access artifact root {raw}: {exc}") from exc
    if not present:
        return None
    root_resolved = _resolve_path(root, what="repository root")
    artifact_root = _resolve_path(raw, what="artifact root")
    if not artifact_root.is_relative_to(root_resolved):
        raise GuardError(f"artifact root {raw} resolves outside repository root {root_resolved}")
    try:
        if not artifact_root.is_dir():
            return None
    except (OSError, ValueError) as extra:
        raise GuardError(f"cannot access artifact root {artifact_root}: {extra}") from extra
    return artifact_root


def _on_disk_glob_match(root: Path, pattern: str) -> bool:
    """True if any in-repo path under `.omx/artifacts` matches ``pattern``."""
    artifact_root = _resolved_artifact_root(root)
    if artifact_root is None:
        return False
    return any(fnmatch.fnmatch(rel, pattern) for rel in _iter_on_disk_artifact_paths(artifact_root))


def classify(target: str, tracked: set[str], root: Path) -> str:
    """Return ``ok`` / ``dangling`` / ``stale`` for one normalized target."""
    kind = _kind(target)
    if kind == "dir":
        if any(path.startswith(target) for path in tracked):
            return "ok"
    elif kind == "glob":
        if any(fnmatch.fnmatch(path, target) for path in tracked):
            return "ok"
        return "dangling" if _on_disk_glob_match(root, target) else "stale"
    elif target in tracked:
        return "ok"

    # Not in the index. Does it exist in this working tree at all?
    return "dangling" if (root / target).exists() else "stale"


def list_tracked(root: Path) -> set[str]:
    """Return repo-relative paths from ``git ls-files`` (NUL-separated).

    Git is invoked in binary mode (``text=False``). Decoding is UTF-8 with
    ``surrogateescape`` so a Windows cp1252 locale cannot drop CJK paths.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            text=False,
            check=False,
        )
    except OSError as exc:
        raise GuardError(f"git ls-files failed in {root}: {exc}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="surrogateescape").strip()
        raise GuardError(f"git ls-files failed in {root}: {err}")
    stdout = proc.stdout.decode("utf-8", errors="surrogateescape")
    return {entry for entry in stdout.split("\0") if entry}


def read_tracked_list(path: Path) -> set[str]:
    """Read an injected tracked-path list (one path per line, UTF-8 strict)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GuardError(f"cannot read tracked-list at {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise GuardError(f"cannot decode tracked-list at {path} as UTF-8: {exc}") from exc
    return {line.strip() for line in text.splitlines() if line.strip()}


def _resolve_in_root(root: Path, target: str) -> Path:
    """Resolve ``target`` under ``root``, or raise GuardError if it escapes.

    Absolute paths and ``../`` relative paths are rejected when they land
    outside ``root``, whether or not the path exists — a missing out-of-root
    target is still a bad argument, not a skipped scan root.
    """
    root_resolved = _resolve_path(root, what="repository root")
    joined = root / target
    candidate = _resolve_path(joined, what=f"target {target!r}")
    if not candidate.is_relative_to(root_resolved):
        raise GuardError(f"target {target!r} is outside repository root {root_resolved}")
    return candidate


def iter_markdown(
    root: Path,
    targets: Sequence[str],
    tracked: set[str],
    include_untracked: bool = False,
) -> Iterator[str]:
    """Yield repo-relative markdown paths under ``targets``.

    Tracked-only by default so the scan matches fresh-clone semantics; missing
    in-root targets are simply skipped (a root that does not exist is not an
    error). Out-of-root targets raise ``GuardError``.
    """
    seen: set[str] = set()
    root_resolved = _resolve_path(root, what="repository root")
    for target in targets:
        candidate = _resolve_in_root(root, target)
        try:
            if not candidate.exists():
                continue
            if candidate.is_file():
                paths = [candidate]
            else:
                paths = sorted(p for p in candidate.rglob("*.md") if p.is_file())
        except (OSError, ValueError) as extra:
            raise GuardError(f"cannot access target {target!r} ({candidate}): {extra}") from extra
        for path in paths:
            try:
                resolved = _resolve_path(path, what="scanned path")
                rel = resolved.relative_to(root_resolved).as_posix()
            except ValueError as extra:
                raise GuardError(
                    f"scanned path {path} is outside repository root {root_resolved}"
                ) from extra
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
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise GuardError(f"cannot read markdown at {path}: {exc}") from exc
        except UnicodeDecodeError as extra:
            raise GuardError(f"cannot decode markdown at {path} as UTF-8: {extra}") from extra
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

    try:
        root = _resolve_path(args.root, what="--root")
        tracked = (
            read_tracked_list(args.tracked_list)
            if args.tracked_list is not None
            else list_tracked(root)
        )
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
    except (GuardError, OSError) as extra:
        print(f"check_artifact_links: {extra}", file=sys.stderr)
        return 2

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
