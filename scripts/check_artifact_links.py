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
Default (no ``--targets``): every **tracked** ``*.md`` path from
``git ls-files``. The scan set is derived from the index — exact paths,
no recursive worktree walk — so ignored and untracked trees are not
traversed. That includes tracked markdown under ``.omx/artifacts/``,
``memory/``, ``knowledge/``, ``PROJECT_CONTEXT.md``, and any future
documentation root. Tracked-only is deliberate for the *citing
documents*: an uncommitted draft cannot fail the guard, so the default
scan matches fresh-clone semantics.

``--targets`` is a deliberate narrowed override for local/focused use:
only those files or directories, relative to ``--root``, are scanned
(directories are walked). Out-of-root targets still fail closed.

``--include-untracked``:
    with ``--targets``
        also scan untracked markdown under those roots (existing walk).
    without ``--targets``
        also include untracked, non-ignored ``*.md`` from
        ``git ls-files --others --exclude-standard`` (git-derived; no
        Python walk of ignored environments). Refused with
        ``--tracked-list`` (exit 2): an injected tracked list cannot
        name untracked files, and walking the whole tree is not the
        default-mode contract.

Verdicts (per reference)
------------------------
Two axes. **ok vs not-ok** is index/fresh-clone based and never consults
the working tree. **dangling vs stale** is the only working-tree
distinction, and it is *this machine's* working tree.

ok        target is in `git ls-files` (exact path, glob match against
          tracked paths, or dir prefix of a tracked path). A tracked
          file missing from disk is still ok.
dangling  target is not in the index, but an on-disk hit exists here
          (regular file, broken symlink, or glob match under
          `.omx/artifacts`) -> exit 1. This is the local-only artifact
          incident: the doc cites a path that lives on one machine.
stale     target is in neither the index nor this working tree
          (historical citation, or a glob with no on-disk match either)
          -> warned, exit 0 by default; `--strict` makes it fatal.

A fresh clone has no untracked files, so the citation that is
``dangling`` on a developer machine (untracked local artifact) is
``stale`` after a clean checkout. That is why ``--check-baseline``
exists: CI cannot see the local file, and default stale handling would
stay green. Dangling stays fatal even when the key is in the baseline.

Glob grammar: only ``*`` and ``?`` are wildcards. Square brackets are
literal path characters (``.omx/artifacts/v[1]/*.md`` names directory
``v[1]``, not a character class matching ``v1``).

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

Frozen-debt baseline
--------------------
Default stale handling is still warn-only (exit 0). That is ineffective in CI:
a citation that is dangling on a developer machine (untracked local file) is
stale on a fresh checkout, so the default gate stays green. ``--strict`` would
make every historical stale fatal forever.

``--check-baseline PATH`` is the CI gate. PATH is a versioned JSON snapshot of
the exact multiset of currently non-tracked (stale) citations, keyed by
repo-relative source + target + occurrence count — never by line number,
timestamp, absolute path, or commit SHA.

Schema (``schema_version`` 1)::

    {
      "schema_version": 1,
      "nontracked": [
        {"source": "docs/x.md", "target": ".omx/artifacts/y.md", "count": 1}
      ]
    }

Field names:
    schema_version  exact integer 1 (bool/float rejected)
    nontracked      list of unique (source, target) entries
    source          normalized repo-relative POSIX path of the citing markdown
    target          normalized ``.omx/artifacts/...`` path, glob, or dir prefix
                    (strict POSIX-relative; colon, backslash, and ``..``
                    rejected). Extraction stops at ASCII ``()`` / ``:`` / ``\\``
                    so line locators and parenthetical prose never become keys
                    (parentheses in a filename are POSIX-legal but not citable).
                    Remaining non-normalized citations (``../``, ``/./``, ``//``)
                    fail closed at scan time with source:line.
    count           exact positive integer occurrence count

Check-mode verdicts:
    dangling         always fatal, even when the key is in the baseline
    new_stale        current stale key absent from the baseline
    count_increase   current count > baselined count
    baseline_drift   baselined key missing or count decreased (resolved /
                     removed / tracked). Refresh the baseline explicitly.
    exact match      pass (exit 0)

``--write-baseline PATH`` writes the current stale multiset as sorted JSON
with a trailing newline and no timestamps or absolute paths. It refuses if
any dangling reference exists, so a local untracked artifact cannot be
legitimized. ``--check-baseline`` and ``--write-baseline`` are mutually
exclusive; ``--strict`` with ``--check-baseline`` is refused as ambiguous.

Usage:
    uv run python scripts/check_artifact_links.py
    uv run python scripts/check_artifact_links.py --strict
    uv run python scripts/check_artifact_links.py --root . --targets docs README.md
    uv run python scripts/check_artifact_links.py --include-untracked
    uv run python scripts/check_artifact_links.py --tracked-list /tmp/ls-files.txt
    uv run python scripts/check_artifact_links.py --check-baseline ci/artifact-links-baseline.json
    uv run python scripts/check_artifact_links.py --write-baseline ci/artifact-links-baseline.json

Exit codes:
    0 - no dangling references (stale ones may still be reported); or exact
        baseline match in check mode; or baseline written
    1 - at least one dangling reference (or a stale one under --strict); or
        baseline integrity drift; or write refused because of dangling refs
    2 - could not determine the tracked set / nothing was scanned / baseline
        missing, unreadable, or malformed / ambiguous flags (fail-closed)
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

# Bound so tests can inject OSError without patching the process-wide os module.
_os_write = os.write
_os_fsync = os.fsync
_os_replace = os.replace

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ARTIFACT_PREFIX = ".omx/artifacts/"
MARKDOWN_SUFFIX = ".md"
# Supported artifact glob wildcards. Square brackets are literal path
# characters — ``v[1]`` is a directory name, not a character class.
_GLOB_WILDCARDS = "*?"

BASELINE_SCHEMA_VERSION = 1
_BASELINE_TOP_KEYS: tuple[str, ...] = ("schema_version", "nontracked")
_BASELINE_ENTRY_KEYS: tuple[str, ...] = ("source", "target", "count")

# Captures `.omx/artifacts/<rest>` up to the first delimiter that cannot be
# part of a path in prose: whitespace, backtick, quote, pipe, ASCII
# parentheses / colon / backslash (line locators, parenthetical
# annotations, shell-escaped raw captures), or the CJK brackets and
# punctuation used in this repo's docs. Angle brackets are captured too
# so template placeholders can be recognised and dropped.
_REF_RE = re.compile(rf"{re.escape(ARTIFACT_PREFIX)}([^\s`'\"|\\():（）【】「」，、；：。]+)")

# Trailing punctuation that is prose, not path. `.md` ends in a letter, so
# stripping a trailing dot is safe. `*` and `?` are glob wildcards and are
# not stripped. Characters already excluded by `_REF_RE` (ASCII `():\\`
# and the CJK delimiter set) are omitted here.
_TRAILING_JUNK = ".,;!]}>！？"

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

    ASCII ``(``, ``)``, ``:``, and ``\\`` end a capture the same way CJK
    punctuation already does, so ``file:line``, parenthetical annotations,
    and shell-escaped trailing backslashes are not part of the target.

    Query stripping is context-aware: Markdown link destinations and
    reference definitions treat a ``?`` after a file extension as a URL
    query; backticked and bare references only strip an explicit
    ``key=value`` query and otherwise keep ``?`` as a glob wildcard. See
    ``_strip_markdown_suffixes``.

    Known prose delimiters are removed from the capture. Any remaining
    non-normalized citation (dot-segments, ``//``, a rest that starts
    with ``./``) is not rewritten: ``scan`` rejects it with a
    ``source:line`` ``GuardError`` before classification or baseline
    accumulation.
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
    if any(ch in target for ch in _GLOB_WILDCARDS):
        return "glob"
    return "file"


def _fnmatch_literal_brackets(name: str, pattern: str) -> bool:
    """fnmatch with ``[`` / ``]`` treated as literals; only ``*`` and ``?`` wildcards.

    ``fnmatch`` character classes would turn ``v[1]/*.md`` into a match for
    tracked ``v1/a.md``. Escape ``[`` as ``[[]`` so a bracket is a path
    character. ``]`` needs no extra escape once every ``[`` is closed.
    """
    return fnmatch.fnmatch(name, pattern.replace("[", "[[]"))


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


def _guard_resolve_error(path: Path, *, what: str, exc: BaseException) -> GuardError:
    if isinstance(exc, ValueError):
        label = "invalid_root" if what in _ROOT_WHATS else "invalid_target"
        return GuardError(f"{label}: cannot resolve {what} ({path}): {exc}")
    return GuardError(f"cannot resolve {what} ({path}): {exc}")


def _resolve_path(path: Path, *, what: str) -> Path:
    """Resolve ``path``, converting loops / OS / ValueError into GuardError.

    ``RuntimeError`` / ``OSError`` (symlink loops, I/O) become
    ``cannot resolve ...``. ``ValueError`` is this boundary's mapping:
    ``invalid_root`` when ``what`` names a root, otherwise ``invalid_target``.

    Python 3.13's default ``Path.resolve()`` no longer raises on symlink
    loops; it returns the path and ``exists()`` is False. ``strict=True``
    still raises ``OSError`` (ELOOP). Missing paths keep the non-strict
    result so callers can skip absent in-root targets.
    """
    try:
        resolved = path.resolve()
    except (RuntimeError, OSError, ValueError) as exc:
        raise _guard_resolve_error(path, what=what, exc=exc) from exc
    # 3.13 hides ELOOP unless strict=True. FileNotFoundError is a dangling
    # or missing path, not a loop — keep the non-strict result.
    try:
        path.resolve(strict=True)
    except FileNotFoundError:
        return resolved
    except (RuntimeError, OSError, ValueError) as extra:
        raise _guard_resolve_error(path, what=what, exc=extra) from extra
    return resolved


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
    return any(
        _fnmatch_literal_brackets(rel, pattern)
        for rel in _iter_on_disk_artifact_paths(artifact_root)
    )


def _literal_on_disk(root: Path, target: str) -> bool:
    """True if ``root/target`` exists as a directory entry (including a broken symlink).

    ``Path.exists()`` follows the symlink and is False for a dangling link;
    ``is_symlink()`` still sees the inode. Either is an on-disk hit for the
    dangling verdict. OSError propagates (fail closed, CLI exit 2).
    """
    path = root / target
    return path.exists() or path.is_symlink()


def classify(target: str, tracked: set[str], root: Path) -> str:
    """Return ``ok`` / ``dangling`` / ``stale`` for one normalized target."""
    # Exact index match wins before glob metacharacters in the filename
    # (``foo[1].md`` is a tracked file, not a character class).
    if target in tracked:
        return "ok"
    kind = _kind(target)
    if kind == "dir":
        if any(path.startswith(target) for path in tracked):
            return "ok"
    elif kind == "glob":
        # A literal on-disk path with * or ? is a filename, not a pattern.
        # Otherwise ``foo-*.md`` on disk would fnmatch tracked ``foo-1.md``.
        if _literal_on_disk(root, target):
            return "dangling"
        if any(_fnmatch_literal_brackets(path, target) for path in tracked):
            return "ok"
        return "dangling" if _on_disk_glob_match(root, target) else "stale"

    # Not in the index. Does it exist in this working tree at all?
    return "dangling" if _literal_on_disk(root, target) else "stale"


def _git_ls_files(root: Path, extra: Sequence[str] = ()) -> set[str]:
    """Return repo-relative paths from ``git ls-files -z`` plus ``extra``.

    Git is invoked in binary mode (``text=False``). Decoding is UTF-8 with
    ``surrogateescape`` so a Windows cp1252 locale cannot drop CJK paths.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", *extra],
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


def list_tracked(root: Path) -> set[str]:
    """Return repo-relative paths from ``git ls-files`` (NUL-separated)."""
    return _git_ls_files(root)


def list_untracked(root: Path) -> set[str]:
    """Untracked, non-ignored paths from ``git ls-files --others --exclude-standard``.

    Git itself skips ignored directories; this is not a Python walk of
    ``node_modules`` / ``.venv`` / other ignored trees.
    """
    return _git_ls_files(root, ("--others", "--exclude-standard"))


def _is_markdown_rel(rel: str) -> bool:
    return rel.endswith(MARKDOWN_SUFFIX)


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
    targets: Sequence[str] | None,
    tracked: set[str],
    include_untracked: bool = False,
) -> Iterator[str]:
    """Yield repo-relative markdown paths under ``targets``.

    ``targets is None`` (default scan): exact ``*.md`` paths from the
    tracked set, plus untracked non-ignored ``*.md`` from git when
    ``include_untracked`` is set. No recursive worktree walk.

    Explicit ``targets``: walk those files or directories. Tracked-only
    unless ``include_untracked``. Missing in-root targets are skipped (a
    root that does not exist is not an error). Out-of-root targets raise
    ``GuardError``.
    """
    if targets is None:
        rels = {path for path in tracked if _is_markdown_rel(path)}
        if include_untracked:
            rels |= {path for path in list_untracked(root) if _is_markdown_rel(path)}
        yield from sorted(rels)
        return

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
    targets: Sequence[str] | None,
    tracked: set[str],
    include_untracked: bool = False,
) -> list[ArtifactRef]:
    """Collect every artifact reference under ``targets`` with its verdict.

    ``targets is None`` scans every tracked (and, if requested, untracked)
    ``*.md`` path. Pass an explicit sequence to narrow.
    """
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
                if not _is_normalized_artifact_target(target):
                    raise GuardError(f"{rel}:{lineno}: invalid artifact target {target!r}")
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


@dataclass(frozen=True)
class BaselineEntry:
    """One unique (source, target) row in a schema_version 1 baseline."""

    source: str
    target: str
    count: int


@dataclass(frozen=True)
class Baseline:
    """Parsed frozen-debt baseline. ``as_counts`` is the comparison multiset."""

    schema_version: int
    nontracked: tuple[BaselineEntry, ...]

    def as_counts(self) -> dict[tuple[str, str], int]:
        return {(entry.source, entry.target): entry.count for entry in self.nontracked}


@dataclass(frozen=True)
class BaselineDiff:
    """Integrity drift between current stale citations and a baseline."""

    new_stale: tuple[tuple[str, str, int], ...]
    count_increase: tuple[tuple[str, str, int, int], ...]
    baseline_drift: tuple[tuple[str, str, int, int], ...]

    def has_integrity_drift(self) -> bool:
        return bool(self.new_stale or self.count_increase or self.baseline_drift)


def _is_normalized_posix_rel(path: str, *, allow_trailing_slash: bool = False) -> bool:
    """True if ``path`` is a normalized relative POSIX path (no filesystem escape)."""
    if type(path) is not str or not path:
        return False
    if "\\" in path or "\0" in path or ":" in path:
        return False
    if path.startswith("/") or path.startswith("./"):
        return False
    trailing = path.endswith("/")
    if trailing and not allow_trailing_slash:
        return False
    body = path[:-1] if trailing else path
    if not body or "//" in body or "/./" in body:
        return False
    return all(part not in ("", ".", "..") for part in body.split("/"))


def _is_normalized_artifact_target(target: str) -> bool:
    """True if ``target`` is a normalized in-repo ``.omx/artifacts/...`` path.

    Baseline keys are artifact path / glob / dir strings, not scanner
    identity fragments. Colon, backslash, NUL, ``..``, and other
    non-normalized POSIX forms are rejected here. Extraction still
    emits such strings when they appear in markdown; ``scan`` fails
    closed on them with source:line before classification.
    """
    if type(target) is not str or not target.startswith(ARTIFACT_PREFIX):
        return False
    rest = target[len(ARTIFACT_PREFIX) :]
    if rest == "":
        return True
    return _is_normalized_posix_rel(rest, allow_trailing_slash=True)


def _no_duplicate_object_pairs(pairs: list[tuple[object, object]]) -> dict[object, object]:
    """``object_pairs_hook`` that rejects duplicate JSON object keys."""
    out: dict[object, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _exact_int(value: object, *, what: str) -> int:
    if type(value) is not int:
        raise GuardError(f"{what} must be an exact integer, got {type(value).__name__}")
    return value


def _exact_str(value: object, *, what: str) -> str:
    if type(value) is not str:
        raise GuardError(f"{what} must be a string, got {type(value).__name__}")
    return value


def _expect_exact_keys(obj: dict[object, object], keys: tuple[str, ...], *, what: str) -> None:
    if set(obj) != set(keys) or len(obj) != len(keys):
        raise GuardError(f"{what} keys must be exactly {list(keys)}, got {list(obj)}")


def load_baseline(path: Path) -> Baseline:
    """Parse a schema_version 1 baseline. Fail closed on any malformation."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GuardError(f"cannot read baseline at {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as extra:
        raise GuardError(f"cannot decode baseline at {path} as UTF-8: {extra}") from extra
    try:
        payload = json.loads(text, object_pairs_hook=_no_duplicate_object_pairs)
    except json.JSONDecodeError as extra:
        raise GuardError(f"cannot parse baseline at {path} as JSON: {extra}") from extra
    except ValueError as extra:
        raise GuardError(f"malformed baseline at {path}: {extra}") from extra
    if type(payload) is not dict:
        raise GuardError(f"baseline at {path} must be a JSON object")
    _expect_exact_keys(payload, _BASELINE_TOP_KEYS, what="baseline")
    schema_version = _exact_int(payload["schema_version"], what="schema_version")
    if schema_version != BASELINE_SCHEMA_VERSION:
        raise GuardError(f"schema_version must be {BASELINE_SCHEMA_VERSION}, got {schema_version}")
    nontracked = payload["nontracked"]
    if type(nontracked) is not list:
        raise GuardError("nontracked must be a JSON list")
    entries: list[BaselineEntry] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(nontracked):
        if type(item) is not dict:
            raise GuardError(f"nontracked[{index}] must be a JSON object")
        _expect_exact_keys(item, _BASELINE_ENTRY_KEYS, what=f"nontracked[{index}]")
        source = _exact_str(item["source"], what=f"nontracked[{index}].source")
        target = _exact_str(item["target"], what=f"nontracked[{index}].target")
        count = _exact_int(item["count"], what=f"nontracked[{index}].count")
        if not _is_normalized_posix_rel(source):
            raise GuardError(
                f"nontracked[{index}].source is not a normalized repo-relative "
                f"POSIX path: {source!r}"
            )
        if not _is_normalized_artifact_target(target):
            raise GuardError(
                f"nontracked[{index}].target is not a normalized .omx/artifacts/ path: {target!r}"
            )
        if count < 1:
            raise GuardError(f"nontracked[{index}].count must be a positive integer, got {count}")
        key = (source, target)
        if key in seen:
            raise GuardError(f"duplicate logical baseline entry {source} -> {target}")
        seen.add(key)
        entries.append(BaselineEntry(source=source, target=target, count=count))
    return Baseline(schema_version=schema_version, nontracked=tuple(entries))


def stale_counts(refs: Sequence[ArtifactRef]) -> dict[tuple[str, str], int]:
    """Aggregate stale references into the baseline multiset (source, target)."""
    counts: dict[tuple[str, str], int] = {}
    for ref in refs:
        if ref.status != "stale":
            continue
        key = (ref.source, ref.target)
        counts[key] = counts.get(key, 0) + 1
    return counts


def render_baseline(counts: Mapping[tuple[str, str], int]) -> str:
    """Deterministic JSON: sorted entries, stable key order, trailing newline."""
    entries = [
        {"source": source, "target": target, "count": count}
        for (source, target), count in sorted(counts.items())
    ]
    payload = {"schema_version": BASELINE_SCHEMA_VERSION, "nontracked": entries}
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _write_all(fd: int, payload: bytes) -> None:
    """Write ``payload`` to ``fd``, looping until every byte is accepted."""
    offset = 0
    while offset < len(payload):
        written = _os_write(fd, payload[offset:])
        if written <= 0:
            raise OSError("short write to baseline temp")
        offset += written


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Replace ``path`` with ``payload`` via exclusive same-directory temp.

    ``tempfile.mkstemp`` is ``O_CREAT|O_EXCL`` and ``O_NOFOLLOW`` when the OS
    supports it, so a pre-existing ``.{name}.tmp`` symlink is not followed.
    ``os.replace`` then swaps the destination itself (symlink or file) rather
    than the symlink target. Cleanup unlinks only the temp this call created.
    """
    name = path.name
    fd = -1
    tmp_name: str | None = None
    try:
        if not name or name in {".", ".."}:
            raise ValueError(f"invalid baseline destination {path}")
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        _write_all(fd, payload)
        _os_fsync(fd)
        os.close(fd)
        fd = -1
        # Same-filesystem swap of the destination inode (symlink or file).
        _os_replace(tmp_name, path)
        tmp_name = None
    except (OSError, ValueError) as extra:
        raise GuardError(f"cannot write baseline at {path}: {extra}") from extra
    finally:
        if fd >= 0:
            with contextlib.suppress(OSError):
                os.close(fd)
        if tmp_name is not None:
            with contextlib.suppress(OSError):
                Path(tmp_name).unlink()


def write_baseline(path: Path, counts: Mapping[tuple[str, str], int]) -> None:
    """Atomically write a schema_version 1 baseline. No timestamps or abs paths.

    Malformed destinations (``Path('.')``, ``Path('/')``, ``Path('')``) and
    unencodable source/target strings become ``GuardError`` (CLI exit 2).
    """
    for (source, target), count in counts.items():
        if not _is_normalized_posix_rel(source):
            raise GuardError(f"cannot write baseline: invalid source {source!r}")
        if not _is_normalized_artifact_target(target):
            raise GuardError(f"cannot write baseline: invalid target {target!r}")
        if type(count) is not int or count < 1:
            raise GuardError(f"cannot write baseline: invalid count {count!r}")
    try:
        payload = render_baseline(counts).encode("utf-8")
    except UnicodeEncodeError as extra:
        raise GuardError(f"cannot write baseline at {path}: {extra}") from extra
    _atomic_write_bytes(path, payload)


def diff_baseline(
    current: Mapping[tuple[str, str], int],
    baseline: Mapping[tuple[str, str], int],
) -> BaselineDiff:
    """Compare current stale counts to a frozen baseline (exact multiset)."""
    new_stale: list[tuple[str, str, int]] = []
    count_increase: list[tuple[str, str, int, int]] = []
    baseline_drift: list[tuple[str, str, int, int]] = []
    for key, current_count in sorted(current.items()):
        expected = baseline.get(key)
        if expected is None:
            new_stale.append((key[0], key[1], current_count))
        elif current_count > expected:
            count_increase.append((key[0], key[1], expected, current_count))
        elif current_count < expected:
            baseline_drift.append((key[0], key[1], expected, current_count))
    for key, expected in sorted(baseline.items()):
        if key not in current:
            baseline_drift.append((key[0], key[1], expected, 0))
    return BaselineDiff(tuple(new_stale), tuple(count_increase), tuple(baseline_drift))


def _report_baseline_problems(dangling: Sequence[ArtifactRef], diff: BaselineDiff) -> None:
    for ref in dangling:
        print(f"DANGLING {ref.render()}")
    for source, target, count in diff.new_stale:
        print(f"NEW_STALE {source} {target} count={count} (not in baseline)")
    for source, target, expected, current in diff.count_increase:
        print(f"COUNT_INCREASE {source} {target} baseline={expected} current={current}")
    for source, target, expected, current in diff.baseline_drift:
        print(f"BASELINE_DRIFT {source} {target} baseline={expected} current={current}")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check that tracked markdown only cites git-tracked .omx/artifacts/ "
            "files. Default scan: every tracked *.md path."
        ),
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
        default=None,
        help=(
            "Narrow the scan to these files or directories, relative to --root. "
            "Default: every tracked *.md path from git ls-files (no worktree walk)."
        ),
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
        help=(
            "Also scan untracked markdown. With --targets, walk those roots. "
            "Without --targets, add untracked non-ignored *.md from git "
            "ls-files --others --exclude-standard. Refused with --tracked-list "
            "unless --targets is also set."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also fail (exit 1) on 'stale' references — the full fresh-clone invariant.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check-baseline",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Fail unless current non-tracked citations exactly match this frozen "
            "JSON baseline. Dangling references are always fatal."
        ),
    )
    mode.add_argument(
        "--write-baseline",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Write the current non-tracked citation multiset to PATH as sorted JSON. "
            "Refuses if any dangling reference exists."
        ),
    )
    parser.add_argument("--quiet", action="store_true", help="Only print problems.")
    return parser.parse_args(argv)


def _handle_write_baseline(
    path: Path,
    dangling: Sequence[ArtifactRef],
    counts: Mapping[tuple[str, str], int],
    *,
    quiet: bool,
) -> int:
    if dangling:
        for ref in dangling:
            print(f"DANGLING {ref.render()}")
        print(
            "check_artifact_links: refusing to write baseline: "
            f"{len(dangling)} dangling reference(s); track or remove them first.",
            file=sys.stderr,
        )
        return 1
    write_baseline(path, counts)
    if not quiet:
        occurrences = sum(counts.values())
        print(f"Wrote {len(counts)} nontracked entries ({occurrences} occurrence(s)) to {path}")
    return 0


def _handle_check_baseline(
    path: Path,
    refs: Sequence[ArtifactRef],
    dangling: Sequence[ArtifactRef],
    counts: Mapping[tuple[str, str], int],
    *,
    quiet: bool,
) -> int:
    baseline = load_baseline(path)
    diff = diff_baseline(counts, baseline.as_counts())
    _report_baseline_problems(dangling, diff)
    if dangling or diff.has_integrity_drift():
        if not quiet:
            print(
                "check_artifact_links: baseline mismatch — "
                f"{len(dangling)} dangling, {len(diff.new_stale)} new_stale, "
                f"{len(diff.count_increase)} count_increase, "
                f"{len(diff.baseline_drift)} baseline_drift."
            )
        return 1
    if not quiet:
        ok = sum(1 for ref in refs if ref.status == "ok")
        stale_n = sum(1 for ref in refs if ref.status == "stale")
        print(
            f"check_artifact_links: {len(refs)} reference(s) — "
            f"{ok} ok, {len(dangling)} dangling, {stale_n} stale "
            f"(exact baseline match, {sum(counts.values())} nontracked)."
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.check_baseline is not None and args.strict:
        print(
            "check_artifact_links: refusing --strict with --check-baseline; "
            "the baseline is the stale policy.",
            file=sys.stderr,
        )
        return 2
    if args.targets is None and args.include_untracked and args.tracked_list is not None:
        print(
            "check_artifact_links: refusing --include-untracked without --targets "
            "when --tracked-list is set; untracked files cannot be derived from "
            "an injected tracked list. Pass --targets to walk specific roots.",
            file=sys.stderr,
        )
        return 2

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
                    "check_artifact_links: no markdown scanned — "
                    "check --root/--targets (default is every tracked *.md).",
                    file=sys.stderr,
                )
                return 2
            dangling: list[ArtifactRef] = []
            counts: dict[tuple[str, str], int] = {}
            if args.write_baseline is not None:
                return _handle_write_baseline(
                    args.write_baseline, dangling, counts, quiet=args.quiet
                )
            if args.check_baseline is not None:
                return _handle_check_baseline(
                    args.check_baseline, refs, dangling, counts, quiet=args.quiet
                )
            if not args.quiet:
                print(f"OK: {len(scanned)} markdown file(s) scanned, no artifact references.")
            return 0

        dangling = [ref for ref in refs if ref.status == "dangling"]
        stale = [ref for ref in refs if ref.status == "stale"]
        counts = stale_counts(refs)

        if args.write_baseline is not None:
            return _handle_write_baseline(args.write_baseline, dangling, counts, quiet=args.quiet)
        if args.check_baseline is not None:
            return _handle_check_baseline(
                args.check_baseline, refs, dangling, counts, quiet=args.quiet
            )
    except (GuardError, OSError) as extra:
        print(f"check_artifact_links: {extra}", file=sys.stderr)
        return 2

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
