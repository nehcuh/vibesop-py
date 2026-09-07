"""D5: generated routing copy must not demand a skill match."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_adapter_templates_do_not_mandate_best_skill() -> None:
    forbidden = "find the best skill"
    hits: list[str] = []
    for path in (ROOT / "src" / "vibesop" / "adapters").rglob("*"):
        if path.suffix not in {".py", ".j2", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        if forbidden in text:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == [], f"adapter copy still says {forbidden!r}: {hits}"


def test_grok_rules_state_no_match_is_success() -> None:
    text = (ROOT / ".grok" / "rules" / "routing.md").read_text(encoding="utf-8")
    assert "find the best skill" not in text
    assert "successful outcome" in text or "正常" in text
