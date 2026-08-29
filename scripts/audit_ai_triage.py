#!/usr/bin/env python3
"""Live AI-triage precision audit against a held-out probe set.

Runs ``vibe route --yes`` per probe through the real routing pipeline
(prefilter, multi-intent detector, AI triage, min_confidence gate) with a
real LLM provider, then asserts:

  - every negative probe (review-only / analysis / summarize / chat /
    explain / translate / QA / factual / advice) produces NO injection
  - every positive probe (genuine dev request) routes (skill or plan)

Statistical power (kimi review F11): a 0-FP run over n negatives bounds the
one-sided 95% false-positive upper at ~3/n (rule of three) — 22 probes
=> ~13%, vs ~35% for the original 7-probe audit.

The persistent triage cache (.vibe/triage_cache.json) is moved aside for
the run and restored afterwards: cached negatives would short-circuit the
LLM and silently weaken the audit; the run must leave no trace.

Usage:
    uv run python scripts/audit_ai_triage.py            # fresh cache (default)
    uv run python scripts/audit_ai_triage.py --no-fresh # reuse cache

Requires a configured LLM provider (~/.vibe/config.toml [llm] with an API
key). Exit codes: 0 = pass, 1 = regression or unparseable output, 2 = env
error (missing deps / dataset).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = Path(__file__).resolve().parent / "ai_triage_probes.yaml"
CACHE_PATH = REPO_ROOT / ".vibe" / "triage_cache.json"
CACHE_BACKUP = CACHE_PATH.with_suffix(".json.audit-bak")

ROUTED_SINGLE_RE = re.compile(r"Selected:\s*(\S+)")
ROUTED_PLAN_RE = re.compile(r"Steps:\s*\d+|Step\s+1:")
NO_MATCH_RE = re.compile(r"no skill matched|No matching skill", re.IGNORECASE)

MIN_NEGATIVES = 20
MIN_POSITIVES = 5


@dataclass
class Probe:
    id: str
    query: str


@dataclass
class Verdict:
    outcome: str  # "routed" | "no_match" | "unknown"
    detail: str


def load_probes(path: Path) -> tuple[list[Probe], list[Probe]]:
    """Load and validate the probe dataset."""
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError(f"unsupported dataset version: {data.get('version')!r}")

    def _parse(section: str) -> list[Probe]:
        probes = [Probe(str(p["id"]), str(p["query"])) for p in data.get(section, [])]
        if len(probes) < (MIN_NEGATIVES if section == "negatives" else MIN_POSITIVES):
            raise ValueError(
                f"{section}: need >= "
                f"{MIN_NEGATIVES if section == 'negatives' else MIN_POSITIVES} probes, got {len(probes)}"
            )
        for p in probes:
            if len(p.query) < 20:
                raise ValueError(f"{p.id}: query <20 chars would bypass AI triage: {p.query!r}")
        return probes

    negatives, positives = _parse("negatives"), _parse("positives")
    ids = [p.id for p in negatives + positives]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate probe ids")
    if len({p.query for p in negatives + positives}) != len(ids):
        raise ValueError("duplicate probe queries")
    return negatives, positives


def classify(output: str) -> Verdict:
    """Map a ``vibe route`` run to routed / no_match / unknown."""
    selected = ROUTED_SINGLE_RE.search(output)
    plan = ROUTED_PLAN_RE.search(output)
    no_match = bool(NO_MATCH_RE.search(output))
    if selected or plan:
        detail = selected.group(1) if selected else "plan"
        return Verdict("routed", detail)
    if no_match:
        return Verdict("no_match", "fallback")
    return Verdict("unknown", "")


def fp_upper_bound(n: int, alpha: float = 0.05) -> float:
    """Rule-of-three one-sided 95% upper bound for the FP rate given 0 FPs
    in n trials: 1 - alpha^(1/n) (~3/n)."""
    if n <= 0:
        raise ValueError("n must be positive")
    return 1.0 - alpha ** (1.0 / n)


def run_probe(query: str, timeout: int = 120) -> str:
    proc = subprocess.run(
        ["uv", "run", "vibe", "route", "--yes", query],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=REPO_ROOT,
        check=False,
    )
    return proc.stdout + proc.stderr


def park_cache() -> bool:
    """Move the triage cache aside; returns True if it existed."""
    if CACHE_PATH.exists():
        CACHE_PATH.replace(CACHE_BACKUP)
        return True
    return False


def restore_cache(parked: bool) -> None:
    if parked:
        CACHE_BACKUP.replace(CACHE_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--no-fresh", action="store_true", help="keep .vibe/triage_cache.json in place"
    )
    args = parser.parse_args()

    try:
        negatives, positives = load_probes(args.dataset)
    except Exception as e:
        print(f"dataset error: {e}", file=sys.stderr)
        return 2

    parked = False
    if not args.no_fresh:
        parked = park_cache()

    fp: list[str] = []
    misses: list[str] = []
    unknown: list[str] = []
    try:
        for probe in negatives:
            v = classify(run_probe(probe.query))
            mark = "ok " if v.outcome == "no_match" else "FP "
            if v.outcome == "routed":
                fp.append(probe.id)
            elif v.outcome == "unknown":
                unknown.append(probe.id)
            print(f"{probe.id} [neg] {mark} {v.detail}")
        for probe in positives:
            v = classify(run_probe(probe.query))
            mark = "ok " if v.outcome == "routed" else "MISS"
            if v.outcome == "no_match":
                misses.append(probe.id)
            elif v.outcome == "unknown":
                unknown.append(probe.id)
            print(f"{probe.id} [pos] {mark} {v.detail}")
    except subprocess.TimeoutExpired:
        print("probe timed out", file=sys.stderr)
        return 1
    finally:
        restore_cache(parked)

    n_neg = len(negatives)
    print("\n==== SUMMARY ====")
    print(f"negative false-positives: {len(fp)}/{n_neg} {fp}")
    if not fp:
        print(f"one-sided 95% FP upper bound: {fp_upper_bound(n_neg):.1%}")
    print(f"positive routed: {len(positives) - len(misses)}/{len(positives)} {misses}")
    if unknown:
        print(f"unparseable: {unknown}")

    if fp or misses or unknown:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
