#!/usr/bin/env python3
"""Parse historical gate-review findings into structured JSON — no model.

Reads gate artifacts (``.omx/artifacts/gate*.md``) and deterministically
extracts review findings as (gate, reviewer, severity, title, source)
records. Two heterogeneous label families are mapped onto one severity
scale (spec: docs/specs/2026-09-11-evo-lane-C.md):

    [P0] / P0            -> P0
    [P1] / P1 / MAJOR    -> P1
    [P2] / P2 / MINOR    -> P2
    [nit] / NIT / items under a "NITS:" section header -> NIT

Additionally, items under a "BLOCKS:" section header map to P0 (the
VERDICT-style counterpart of the P-family's highest severity); "none"
placeholder items are skipped.

Dedup runs over the whole scanned set on normalized titles (lowercase,
punctuation stripped, path fragments like ``src/foo/bar.py:12`` removed):
exact-match gives the conservative lower bound; token-Jaccard >= 0.8
(union-find clustering) gives the upper bound.

OBSERVATIONAL ONLY: reviewer/model assignment across historical gates was
not randomized, so repeat rates describe the corpus, not causes. The
output carries ``"observational": true`` and must not be read causally.

Usage:
    uv run python scripts/parse_gate_findings.py \
        --root .omx/artifacts --glob 'gate*.md' --json-out PATH
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

JACCARD_THRESHOLD = 0.8

_LABEL_SEVERITY = {
    "p0": "P0",
    "p1": "P1",
    "p2": "P2",
    "nit": "NIT",
    "major": "P1",
    "minor": "P2",
}

_SECTION_SEVERITY = {
    "major": "P1",
    "majors": "P1",
    "minor": "P2",
    "minors": "P2",
    "nit": "NIT",
    "nits": "NIT",
    "block": "P0",
    "blocks": "P0",
    "p0": "P0",
    "p1": "P1",
    "p2": "P2",
}

# List items: "- ...", "* ...", "1. ...", "2) ...".
_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d{1,2}[.)])\s+(.*\S)\s*$")

# Inline severity label at the start of an item, e.g. "**[P1] title**：...",
# "[nit] title", "MAJOR: title", "P1: title".
_INLINE_LABEL_RE = re.compile(
    r"^\*{0,2}\s*(?:\[(?P<bracketed>P0|P1|P2|NIT)\]|(?P<bare>MAJOR|MINOR|P0|P1|P2|NIT))"
    r"\s*\*{0,2}\s*[:：]?\s+",
    re.IGNORECASE,
)

# A line consisting solely of a section header, e.g. "NITS:", "MAJOR".
_SECTION_RE = re.compile(r"^\s*(MAJORS?|MINORS?|NITS?|BLOCKS?|P0|P1|P2)\s*[:：]?\s*$", re.IGNORECASE)

# Title/body split: a CJK colon always splits; an ASCII colon only when
# followed by whitespace (so "file.py:12" and "yaml:1 (header)" survive).
_TITLE_SPLIT_RE = re.compile(r"\*{0,2}\s*(?::(?=\s)|：)\s*")

# Path fragments removed during normalization: "src/foo/bar.py:12",
# "unified.py:842-846", "tests/benchmark/routing_eval.yaml".
_PATH_RE = re.compile(
    r"[\w.~-]*(?:/[\w.~-]+)+(?::\d+(?:-\d+)?)?"
    r"|[\w~-]+\.(?:py|md|ya?ml|jsonl?|toml|sh|txt|js|ts|tsx|ps1)(?::\d+(?:-\d+)?)?"
)

_NAME_RE = re.compile(r"^(gate\d+)(?:-(.+))?\.md$", re.IGNORECASE)
# Trailing filename segments that are document roles, not reviewers.
_NON_REVIEWER_SEGMENTS = {
    "review",
    "packet",
    "instructions",
    "context",
    "notes",
    "summary",
    "report",
    "baseline",
}

_NONE_ITEMS = {"none", "none.", "无", "（none）", "(none)"}


def infer_source_meta(path: Path) -> tuple[str, str]:
    """Infer (gate, reviewer) from a filename; "unknown" when not inferable."""
    m = _NAME_RE.match(path.name)
    if not m:
        return "unknown", "unknown"
    gate = m.group(1).lower()
    rest = m.group(2)
    if not rest:
        return gate, "unknown"
    reviewer = rest.split("-")[-1].lower()
    if reviewer in _NON_REVIEWER_SEGMENTS:
        return gate, "unknown"
    return gate, reviewer


def normalize_title(raw: str) -> str:
    """Lowercase, drop path fragments, strip punctuation, collapse spaces.

    CJK characters are word characters, so unsegmented Chinese survives as
    single tokens; that is fine for exact-match dedup and acceptable for
    the Jaccard upper bound.
    """
    s = _PATH_RE.sub(" ", raw.lower().replace("`", " "))
    s = re.sub(r"[^\w]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _clean_title(text: str) -> str:
    m = _TITLE_SPLIT_RE.search(text)
    title = text[: m.start()] if m else text
    title = title.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", title).strip()


def extract_findings(text: str, source: Path) -> list[dict]:
    """Extract findings from one gate file. Never raises on weird input."""
    gate, reviewer = infer_source_meta(source)
    findings: list[dict] = []
    section: str | None = None
    for line in text.splitlines():
        header = _SECTION_RE.match(line)
        if header:
            section = _SECTION_SEVERITY[header.group(1).lower()]
            continue
        item = _ITEM_RE.match(line)
        if not item:
            section = None
            continue
        content = item.group(1)
        labeled = _INLINE_LABEL_RE.match(content)
        if labeled:
            label = (labeled.group("bracketed") or labeled.group("bare")).lower()
            severity = _LABEL_SEVERITY[label]
            content = content[labeled.end() :]
        elif section:
            severity = section
        else:
            continue
        raw_title = _clean_title(content)
        if not raw_title or raw_title.lower() in _NONE_ITEMS:
            continue
        findings.append(
            {
                "gate": gate,
                "reviewer": reviewer,
                "severity": severity,
                "title": normalize_title(raw_title),
                "raw_title": raw_title,
                "source": str(source),
            }
        )
    return findings


def _tokens(title: str) -> frozenset:
    return frozenset(title.split())


def _jaccard(a: frozenset, b: frozenset) -> float:
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def count_jaccard_clusters(titles: list[str], threshold: float = JACCARD_THRESHOLD) -> int:
    """Union-find clustering: two titles merge when token Jaccard >= threshold.

    Similarity is not transitive, so chaining can merge titles that are not
    mutually similar; this is the intended upper bound. Deterministic:
    pairs are visited in index order over a stable sort.
    """
    order = sorted(range(len(titles)), key=lambda i: (titles[i], i))
    parent = list(range(len(titles)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    toks = [_tokens(titles[i]) for i in order]
    for a in range(len(order)):
        for b in range(a + 1, len(order)):
            if _jaccard(toks[a], toks[b]) >= threshold:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra
    return len({find(i) for i in range(len(order))})


def _rates(findings: list[dict]) -> dict:
    n_raw = len(findings)
    titles = [f["title"] for f in findings]
    n_exact = len(set(titles))
    n_jaccard = count_jaccard_clusters(titles)
    return {
        "n_raw": n_raw,
        "n_unique_exact": n_exact,
        "n_unique_jaccard": n_jaccard,
        "repeat_rate_low": (1 - n_exact / n_raw) if n_raw else None,
        "repeat_rate_high": (1 - n_jaccard / n_raw) if n_raw else None,
    }


def build_report(findings: list[dict], files_scanned: list[str], zero_files: list[str]) -> dict:
    rates = _rates(findings)
    return {
        "observational": True,
        "note": (
            "Observational only: reviewer/model assignment across historical gates was "
            "not randomized; repeat rates describe this corpus and support no causal claim."
        ),
        "summary": {
            "files_scanned": len(files_scanned),
            "files_with_zero_findings": len(zero_files),
            "zero_finding_files": zero_files,
            **rates,
            "by_severity": {
                sev: _rates([f for f in findings if f["severity"] == sev])
                for sev in ("P0", "P1", "P2", "NIT")
            },
        },
        "findings": findings,
    }


def scan(root: Path, pattern: str = "gate*.md") -> dict:
    """Scan a file or directory and return the full report dict."""
    paths = [root] if root.is_file() else sorted(p for p in root.glob(pattern) if p.is_file())
    findings: list[dict] = []
    zero_files: list[str] = []
    for path in paths:
        file_findings = extract_findings(path.read_text(encoding="utf-8"), path)
        findings.extend(file_findings)
        if not file_findings:
            zero_files.append(str(path))
    return build_report(findings, [str(p) for p in paths], zero_files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse historical gate findings without a model (observational, report-only)."
    )
    parser.add_argument("--root", default=".omx/artifacts", help="gate file or directory to scan")
    parser.add_argument("--glob", default="gate*.md", help="filename glob when --root is a directory")
    parser.add_argument(
        "--json-out",
        "--out",
        dest="json_out",
        default=None,
        help="write JSON report here (default: stdout)",
    )
    args = parser.parse_args(argv)

    report = scan(Path(args.root), args.glob)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        Path(args.json_out).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
