"""Tests for scripts/parse_gate_findings.py (evo lane C).

All fixtures are synthetic (tests/fixtures/gate_findings/) and pin parser
behavior only. No claim is made here about repeat rates in the real gate
corpus — that alignment belongs to the Cgold gold-label comparison.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "parse_gate_findings.py"
spec = importlib.util.spec_from_file_location("parse_gate_findings", SCRIPT)
pgf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pgf)

FIXTURES = ROOT / "tests" / "fixtures" / "gate_findings"


def test_p1_style_extracts_two_p1_and_one_nit():
    report = pgf.scan(FIXTURES / "p1_style")
    findings = report["findings"]
    assert report["summary"]["n_raw"] == 3
    assert report["summary"]["files_scanned"] == 1
    assert [f["severity"] for f in findings] == ["P1", "P1", "NIT"]
    assert findings[0]["gate"] == "gate1"
    assert findings[0]["reviewer"] == "claude"
    assert findings[0]["raw_title"] == "重放 join 系统性失配"
    assert findings[0]["title"] == "重放 join 系统性失配"
    assert report["observational"] is True


def test_major_nits_style_maps_to_p1_and_nit():
    report = pgf.scan(FIXTURES / "major_nits")
    findings = report["findings"]
    assert report["summary"]["n_raw"] == 4
    severities = [f["severity"] for f in findings]
    assert severities == ["P1", "P1", "NIT", "NIT"]
    # "BLOCKS: - none" is a placeholder, not a finding.
    assert all(f["severity"] != "P0" for f in findings)
    # NOTES: section items are not findings.
    assert all("note line" not in f["raw_title"] for f in findings)
    # Path fragments are stripped from the normalized title, kept in raw_title.
    nit = findings[2]
    assert "docs/roadmap.md" in nit["raw_title"]
    assert "docs/roadmap.md" not in nit["title"]
    assert "purge reminder" in nit["title"]
    assert findings[0]["gate"] == "gate10"
    assert findings[0]["reviewer"] == "claude"


def test_exact_duplicate_titles_dedup_across_files():
    report = pgf.scan(FIXTURES / "duplicates")
    summary = report["summary"]
    assert summary["files_scanned"] == 2
    assert summary["n_raw"] == 2
    assert summary["n_unique_exact"] == 1
    assert summary["repeat_rate_low"] == 0.5
    by_p2 = summary["by_severity"]["P2"]
    assert by_p2["n_raw"] == 2
    assert by_p2["n_unique_exact"] == 1


def test_prose_without_labels_yields_zero_findings():
    report = pgf.scan(FIXTURES / "prose")
    summary = report["summary"]
    assert summary["n_raw"] == 0
    assert summary["files_with_zero_findings"] == 1
    assert summary["zero_finding_files"] == [str(FIXTURES / "prose" / "gate4-review-pi.md")]
    assert summary["repeat_rate_low"] is None
    assert summary["repeat_rate_high"] is None


def test_jaccard_merges_near_identical_titles():
    report = pgf.scan(FIXTURES / "jaccard")
    summary = report["summary"]
    assert summary["n_raw"] == 2
    # Not exact-equal: normalization keeps the extra word.
    assert summary["n_unique_exact"] == 2
    # Token Jaccard = 5/6 >= 0.8 -> merged into one cluster.
    assert summary["n_unique_jaccard"] == 1
    assert summary["repeat_rate_low"] == 0.0
    assert summary["repeat_rate_high"] == 0.5
