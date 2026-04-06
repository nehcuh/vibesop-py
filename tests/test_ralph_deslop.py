"""Tests for ralph deslop engine."""

import pytest
from pathlib import Path
from vibesop.core.ralph.deslop import SLOP_PATTERNS, SlopPattern, SlopReport, scan_file, scan_files


def test_scan_clean_file(tmp_path):
    clean_file = tmp_path / "clean.py"
    clean_file.write_text("def hello():\n    return 'world'\n")
    report = scan_file(clean_file)
    assert report.file_path == str(clean_file)
    assert not report.has_slop
    assert report.severity == "clean"


def test_scan_file_with_slop(tmp_path):
    slop_file = tmp_path / "sloppy.py"
    slop_file.write_text(
        '"""Class function for that creates things."""\n\ndef foo():\n    # This function does the thing that creates the output\n    pass\n'
    )
    report = scan_file(slop_file)
    assert report.has_slop
    assert report.severity in ("low", "medium")


def test_scan_nonexistent_file():
    report = scan_file("/nonexistent/file.py")
    assert not report.has_slop
    assert report.severity == "clean"


def test_scan_multiple_files(tmp_path):
    f1 = tmp_path / "a.py"
    f1.write_text("x = 1\n")
    f2 = tmp_path / "b.py"
    f2.write_text('"""Class function for that creates things."""\n')

    reports = scan_files([f1, f2])
    assert len(reports) == 2
    assert not reports[0].has_slop
    assert reports[1].has_slop


def test_slop_report_severity_high(tmp_path):
    slop_file = tmp_path / "bad.py"
    slop_file.write_text("def abstract():\n    raise NotImplementedError\n")
    report = scan_file(slop_file)
    assert report.has_slop
    assert report.severity == "high"


def test_slop_pattern_names():
    for pattern in SLOP_PATTERNS:
        assert pattern.name
        assert pattern.severity in ("low", "medium", "high")
