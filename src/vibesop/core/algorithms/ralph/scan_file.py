import re
from pathlib import Path

_AI_SLOP_PATTERNS: list[tuple[str, str]] = [
    (r"#.*(?:obvious|simple|straightforward)\b", "over-explanatory comment"),
    (r"#.*(?:In this|Here we|Now let|I'm going)", "AI narrative comment"),
    (
        r'"""[\s\S]*?(?:This\s+(?:function|class|module|method)\s+(?:is|does|will|can|should|handles))[\s\S]*?"""',
        "redundant docstring",
    ),
    (r"@property\s*\n\s*def\s+\w+\(self\)[\s\S]*?return\s+self\._\w+", "trivial property wrapper"),
    (r"class\s+\w+Error\s*\(.*\):\s*\n\s*pass", "empty error class"),
    (
        r"def\s+\w+\([^)]*\)\s*->\s*(?:None|bool|int|str|float|list|dict):\s*\n\s*pass\b",
        "stub function",
    ),
]


def scan_file(
    filepath: Path | str,
    *,
    max_slops: int = 20,
) -> dict:
    """Scan a file for AI slop patterns (deslop pass).

    Detects common patterns in AI-generated code:
    - Over-explanatory comments
    - AI narrative patterns ("In this...", "Now let...")
    - Redundant docstrings
    - Trivial property wrappers
    - Empty error classes
    - Stub functions

    Args:
        filepath: Path to the file to scan.
        max_slops: Maximum number of findings to return.

    Returns:
        Dictionary with scan results.
    """
    p = Path(filepath)
    if not p.exists():
        return {"file": str(p), "slop_count": 0, "findings": [], "error": "file not found"}

    content = p.read_text(errors="replace")

    findings: list[dict] = []
    for pattern, kind in _AI_SLOP_PATTERNS:
        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            findings.append(
                {
                    "line": line_num,
                    "kind": kind,
                    "snippet": match.group()[:100],
                }
            )
            if len(findings) >= max_slops:
                break
        if len(findings) >= max_slops:
            break

    return {
        "file": str(p),
        "slop_count": len(findings),
        "findings": findings[:max_slops],
    }
