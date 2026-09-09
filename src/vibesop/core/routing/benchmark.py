"""Hermetic routing baseline: fingerprint + entry-level compare (gate45 P1).

Pure data functions shared by ``scripts/eval_routing.py`` (CLI) and
``tests/test_routing_baseline.py`` (unit tests). Nothing here constructs a
router — importing this module must not pull the routing stack.

Gate semantics (see docs/dev/routing-benchmark.md):
- fingerprint = sha256 over CONTENT hashes only (registry, skill-definition
  files, dataset, canonical posture). No mtimes, no absolute paths —
  a checkout at a different location (CI vs local) fingerprints identically.
- ``--check`` exit codes: 0 pass / 1 new top-1 fail / 3 stale baseline
  (missing, unreadable, schema-version mismatch, or fingerprint mismatch —
  the routed universe changed, refresh instead of comparing apples to
  oranges). Entries that newly PASS while the fingerprint still matches
  (only possible via router/threshold changes) exit 0 with a
  refresh-recommended note.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "BASELINE_VERSION",
    "HERMETIC_POSTURE",
    "CheckOutcome",
    "check_update_absorption",
    "compare_entries",
    "compute_fingerprint",
    "evaluate_against_baseline",
    "load_baseline",
    "write_baseline",
]

BASELINE_VERSION = 1

# Canonical hermetic posture, hashed into every fingerprint: changing the
# posture (re-enabling a layer, unpinning the universe) must invalidate all
# baselines, not silently compare across postures. scenario_layer is pinned
# empty deliberately: in an editable install it reads empty by accident
# (bundled registry only exists in wheels), and a wheel-installed env must
# not silently regenerate the baseline into a different universe.
HERMETIC_POSTURE: dict[str, Any] = {
    "enable_embedding": False,
    "enable_ai_triage": False,
    "enable_external": False,
    "strict_search_paths": True,
    "load_sentence_transformer": "patched-to-null",
    "scenario_layer": "disabled",
    "cwd": "tmp",
    "project_root": "tmp",
    "home_env": "tmp",
}

# Generated/dependency trees under a skills dir whose contents differ between
# a fresh checkout and a used one — never fingerprinted.
_HASHED_SUFFIXES = frozenset({".md", ".yaml", ".yml"})
_SKIPPED_DIR_PARTS = frozenset({".git", "__pycache__", "node_modules", ".venv"})


def _hash_file(path: Path) -> str:
    # Normalize CRLF -> LF so a Windows autocrlf checkout fingerprints
    # identically to an LF checkout of the same content.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _hash_tree(root: Path) -> dict[str, str]:
    """{relative_posix_path: sha256} for every skill-definition file under root.

    Content-only by construction: file mtimes and the root's absolute
    location are not hashed, so ``touch``-ed files and checkouts at
    different paths fingerprint identically. Symlinked files are skipped —
    the pinned roots must be plain checkouts (loader-visible symlinked
    skills would evade the fingerprint).
    """
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if not p.is_file() or p.is_symlink():
            continue
        if p.suffix.lower() not in _HASHED_SUFFIXES:
            continue
        if any(part in _SKIPPED_DIR_PARTS for part in p.relative_to(root).parts):
            continue
        out[p.relative_to(root).as_posix()] = _hash_file(p)
    return out


def compute_fingerprint(
    *,
    registry_file: Path,
    skill_roots: dict[str, Path],
    dataset_file: Path,
    posture: dict[str, Any],
) -> dict[str, Any]:
    """Content fingerprint of everything the hermetic eval depends on."""
    inputs: dict[str, Any] = {
        "registry.yaml": _hash_file(registry_file),
        "dataset": _hash_file(dataset_file),
        "posture": posture,
    }
    for label, root in skill_roots.items():
        inputs[f"skills:{label}"] = _hash_tree(root)
    top = hashlib.sha256(
        json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {"version": BASELINE_VERSION, "sha": top, "inputs": inputs}


@dataclass
class CheckOutcome:
    """Result of comparing current entries against a baseline."""

    exit_code: int
    reason: str
    new_fails: list[dict[str, Any]] = field(default_factory=list)
    new_passes: list[dict[str, Any]] = field(default_factory=list)
    drift_warnings: list[str] = field(default_factory=list)
    matched_entries: int = 0
    known_fails: int = 0

    @property
    def stale(self) -> bool:
        return self.exit_code == 3


def _entries_wellformed(entries: Any) -> bool:
    """Entries must be a list of dicts each carrying a string ``query``."""
    return isinstance(entries, list) and all(
        isinstance(e, dict) and isinstance(e.get("query"), str) for e in entries
    )


def _known_fail_class(entry: dict[str, Any]) -> str:
    """Injection class of a failing (ok1 false) entry for the gate.

    - ``"no_match"`` — nothing was injected: ``primary`` is None or the
      ``fallback-llm`` sentinel (or the layer is ``fallback_llm``).
    - ``"wrong"``    — a REAL skill was routed that is not the gold: an
      active misroute whose content would be injected.
    - ``"unknown"``  — entry carries no usable primary/layer (pre-schema
      baseline rows); treated conservatively (never triggers the
      no_match→wrong new-fail path, since the old class is unknown).
    """
    if "primary" not in entry:
        return "unknown"
    primary = entry.get("primary")
    if primary is None or primary == "fallback-llm":
        return "no_match"
    if entry.get("layer") == "fallback_llm":
        return "no_match"
    if not isinstance(primary, str) or not primary:
        return "unknown"
    return "wrong"


def compare_entries(
    baseline_entries: list[dict[str, Any]],
    current_entries: list[dict[str, Any]],
) -> CheckOutcome:
    """Pure entry-level compare (fingerprints already matched).

    Queries are the comparison key: duplicate queries inside one dataset
    collapse (last one wins). The current dataset has none and its content
    is fingerprinted, so a collision cannot silently change semantics.

    Classification per query:
    - ok1 true→false  — new fail (exit 1)
    - ok1 false→true  — new pass (exit 0, refresh recommended)
    - pass→pass with primary/layer change — drift warning only
    - known fail → known fail — usually silent (documented contract), with
      two observability exceptions keyed on the failure CLASS (gate-health
      finding 2026-09: the ok1 boolean cannot tell a benign no-match from an
      active wrong-skill injection, so a router that starts *injecting a real
      wrong skill* on a query that used to fall back would pass the gate
      silently while degrading the must-not-guess invariant):
        * no-match/fallback class → active-misroute class is a NEW fail
          (exit 1) — content starts being injected where nothing was;
        * active misroute → different active misroute is a drift warning;
        * active misroute → no-match/fallback is a drift warning
          (improved; refresh recommended).
    - current query absent from baseline — only reachable when the dataset
      changed (fingerprint already exited 3); a failing one is still
      reported as a new fail rather than swallowed.

    Malformed input (non-list, or an entry whose ``query`` is missing or
    not a string — unhashable queries would crash the dict comprehension)
    is treated as unreadable: exit 3 instead of a traceback. The reason
    names the malformed side — a malformed *baseline* is healed by
    ``--update-baseline``, but malformed *current* entries come from the
    benchmark's own run, which a baseline refresh cannot fix.
    """
    if not _entries_wellformed(baseline_entries):
        return CheckOutcome(
            exit_code=3,
            reason="malformed baseline entries — regenerate with --update-baseline",
        )
    if not _entries_wellformed(current_entries):
        return CheckOutcome(
            exit_code=3,
            reason=(
                "malformed current entries (benchmark self-run output) — "
                "fix the eval harness; refreshing the baseline cannot heal this"
            ),
        )
    base = {e["query"]: e for e in baseline_entries}
    cur = {e["query"]: e for e in current_entries}

    new_fails: list[dict[str, Any]] = []
    new_passes: list[dict[str, Any]] = []
    drift_warnings: list[str] = []
    matched = 0
    known_fails = 0

    for query, c in cur.items():
        b = base.get(query)
        if b is None:
            if not c.get("ok1"):
                new_fails.append(
                    {
                        "query": query,
                        "expect": c.get("expect", []),
                        "baseline": None,
                        "current": f"{c.get('primary')} ({c.get('layer')})",
                    }
                )
            continue
        matched += 1
        if b.get("ok1") and not c.get("ok1"):
            new_fails.append(
                {
                    "query": query,
                    "expect": c.get("expect") or b.get("expect", []),
                    "baseline": f"{b.get('primary')} ({b.get('layer')})",
                    "current": f"{c.get('primary')} ({c.get('layer')})",
                }
            )
        elif not b.get("ok1") and c.get("ok1"):
            new_passes.append({"query": query, "primary": c.get("primary")})
        elif b.get("ok1") and c.get("ok1"):
            if (b.get("primary"), b.get("layer")) != (c.get("primary"), c.get("layer")):
                drift_warnings.append(
                    f"{query}: {b.get('primary')}/{b.get('layer')} -> "
                    f"{c.get('primary')}/{c.get('layer')}"
                )
        else:
            # Both failing (a known fail). The ok1 boolean alone cannot
            # distinguish "router honestly found nothing" from "router
            # actively routed a real wrong skill" — see the class-keyed
            # observability notes in the docstring above.
            known_fails += 1
            b_cls = _known_fail_class(b)
            c_cls = _known_fail_class(c)
            if c_cls == "wrong" and b_cls == "no_match":
                # Degrade into the injection class: content starts being
                # routed on a query that used to fall back honestly.
                known_fails -= 1
                new_fails.append(
                    {
                        "query": query,
                        "expect": c.get("expect") or b.get("expect", []),
                        "baseline": f"{b.get('primary')} ({b.get('layer')}) [no-match/fallback]",
                        "current": f"{c.get('primary')} ({c.get('layer')}) [active wrong-skill match]",
                        "kind_degraded": True,
                    }
                )
            elif (
                c_cls == "wrong"
                and b_cls == "wrong"
                and (b.get("primary"), b.get("layer")) != (c.get("primary"), c.get("layer"))
            ):
                drift_warnings.append(
                    f"{query}: known-fail misroute {b.get('primary')}/{b.get('layer')} -> "
                    f"{c.get('primary')}/{c.get('layer')}"
                )
            elif b_cls == "wrong" and c_cls == "no_match":
                drift_warnings.append(
                    f"{query}: known-fail improved to no-match/fallback (refresh recommended)"
                )

    for query in base:
        if query not in cur:
            drift_warnings.append(f"{query}: in baseline but not in current dataset")

    exit_code = 1 if new_fails else 0
    reason = (
        f"{len(new_fails)} new top-1 fail(s)" if new_fails else f"{matched} entries match baseline"
    )
    return CheckOutcome(
        exit_code=exit_code,
        reason=reason,
        new_fails=new_fails,
        new_passes=new_passes,
        drift_warnings=drift_warnings,
        matched_entries=matched,
        known_fails=known_fails,
    )


def load_baseline(path: Path) -> dict[str, Any] | None:
    """Parse a baseline file; None when missing or unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("baseline unreadable (%s): %s", path, e)
        return None
    if not isinstance(data, dict):
        logger.warning("baseline is not a JSON object: %s", path)
        return None
    return data


def evaluate_against_baseline(
    baseline_path: Path,
    fingerprint: dict[str, Any],
    current_entries: list[dict[str, Any]],
) -> CheckOutcome:
    """Full gate evaluation: staleness first, then entry compare."""
    if not baseline_path.exists():
        return CheckOutcome(
            exit_code=3,
            reason=f"baseline missing: {baseline_path} — generate with --update-baseline",
        )
    baseline = load_baseline(baseline_path)
    if baseline is None:
        return CheckOutcome(
            exit_code=3,
            reason=f"baseline unreadable: {baseline_path} — regenerate with --update-baseline",
        )
    if baseline.get("version") != BASELINE_VERSION:
        return CheckOutcome(
            exit_code=3,
            reason=(
                f"baseline schema version {baseline.get('version')!r} != "
                f"{BASELINE_VERSION} — regenerate with --update-baseline"
            ),
        )
    baseline_fingerprint = baseline.get("fingerprint")
    if not isinstance(baseline_fingerprint, dict) or baseline_fingerprint.get(
        "sha"
    ) != fingerprint.get("sha"):
        return CheckOutcome(
            exit_code=3,
            reason=(
                "fingerprint mismatch — registry/skill/dataset content or posture "
                "changed; refresh with --update-baseline"
            ),
        )
    return compare_entries(baseline.get("entries", []), current_entries)


def check_update_absorption(
    baseline_path: Path,
    current_entries: list[dict[str, Any]],
) -> CheckOutcome | None:
    """Pre-refresh guard: refuse to silently absorb regressions.

    Review F-1 (laundering channel): a PR that changes router code AND any
    fingerprinted content lands as exit 3 (stale); the coached "refresh"
    would then fold genuine ok1 true→false regressions into the new
    baseline as known-fails. ``--update-baseline`` therefore compares the
    incoming entries against the old baseline FIRST and reports any flips.

    Returns a CheckOutcome (exit_code 1 when regressions would be
    absorbed) when the old baseline is readable and schema-compatible;
    None when there is nothing to compare against (missing/unreadable/
    version-mismatched old baseline — a first refresh). Fingerprint match
    is deliberately NOT required: absorption matters exactly when the
    fingerprint changed.
    """
    if not baseline_path.exists():
        return None
    baseline = load_baseline(baseline_path)
    if baseline is None or baseline.get("version") != BASELINE_VERSION:
        return None
    entries = baseline.get("entries", [])
    if not _entries_wellformed(entries):
        return None
    return compare_entries(entries, current_entries)


def write_baseline(path: Path, fingerprint: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    """Write a deterministic (insertion-ordered, indent=2) baseline file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": BASELINE_VERSION,
        "fingerprint": fingerprint,
        "entries": entries,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
