"""AI slop detection and cleaning."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SlopPattern:
    """A pattern that indicates AI-generated slop."""

    name: str
    pattern: re.Pattern[str]
    severity: str  # low, medium, high


# Common AI slop patterns
SLOP_PATTERNS = [
    SlopPattern("excessive_commenting", re.compile(r"^ {0,4}# .{50,}$", re.MULTILINE), "low"),
    SlopPattern(
        "redundant_explanation",
        re.compile(r"# This (function|method|class) (is|does|creates)", re.MULTILINE),
        "medium",
    ),
    SlopPattern(
        "unnecessary_abstractmethod", re.compile(r"raise NotImplementedError", re.MULTILINE), "high"
    ),
    SlopPattern(
        "boilerplate_docstring",
        re.compile(r'"""[A-Z][a-z]+ (class|function|method) (for|that|to|which)', re.MULTILINE),
        "low",
    ),
    SlopPattern(
        "over_engineered_import",
        re.compile(r"^from \w+\.\w+\.\w+\.\w+ import", re.MULTILINE),
        "medium",
    ),
]


@dataclass
class SlopReport:
    """Report of detected slop in a file."""

    file_path: str
    findings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_slop(self) -> bool:
        return len(self.findings) > 0

    @property
    def severity(self) -> str:
        if not self.findings:
            return "clean"
        severities = [f["severity"] for f in self.findings]
        if "high" in severities:
            return "high"
        if "medium" in severities:
            return "medium"
        return "low"


def scan_file(file_path: str | Path) -> SlopReport:
    """Scan a file for AI slop patterns."""
    file_path = Path(file_path)
    if not file_path.exists():
        return SlopReport(file_path=str(file_path))

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return SlopReport(file_path=str(file_path))

    findings = []
    for pattern in SLOP_PATTERNS:
        for match in pattern.pattern.finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            findings.append(
                {
                    "pattern": pattern.name,
                    "severity": pattern.severity,
                    "line": line_num,
                    "text": match.group()[:80],
                }
            )

    return SlopReport(file_path=str(file_path), findings=findings)


def scan_files(file_paths: list[str | Path]) -> list[SlopReport]:
    """Scan multiple files for AI slop."""
    return [scan_file(fp) for fp in file_paths]
