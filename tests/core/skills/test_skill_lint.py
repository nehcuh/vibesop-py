"""Tests for vibesop.core.skills.skill_lint (gate37 L1 minimal lint).

Each rule carries must-NOT-catch counter-example tests (repo convention):
the lint is advisory-only, so a false positive is pure noise.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.skill_commands import app as skill_app
from vibesop.core.skills.skill_lint import lint_skill, lint_skill_path

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parents[3]

_GOOD_SKILL = """---
id: demo/good-skill
name: good-skill
description: Diagnose flaky CI failures and propose minimal fixes.
triggers:
  - "flaky ci"
  - "diagnose test failure"
---

## Overview

Investigate the failing job, reproduce locally, propose the smallest fix.

## Steps

1. Read the CI log.
2. Reproduce the failure locally.
3. Propose a minimal patch.
"""


def _write_skill(tmp_path: Path, content: str) -> Path:
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8")
    return skill_md


# ---------------------------------------------------------------------------
# must-NOT-catch counter-examples
# ---------------------------------------------------------------------------


def test_clean_skill_has_no_findings(tmp_path: Path) -> None:
    assert lint_skill(_write_skill(tmp_path, _GOOD_SKILL)) == []


def test_real_builtin_skill_has_no_findings() -> None:
    """A shipped builtin skill with hand-written triggers/body must lint clean."""
    skill_md = REPO_ROOT / "core" / "skills" / "deep-diagnosis-optimization" / "SKILL.md"
    assert lint_skill(skill_md) == []


def test_single_handwritten_todo_is_not_a_skeleton(tmp_path: Path) -> None:
    """One hand-written TODO note is NOT the gate31 auto-draft skeleton."""
    content = _GOOD_SKILL + "\n## Notes\n\n- TODO: cover the Windows path case\n"
    assert lint_skill(_write_skill(tmp_path, content)) == []


def test_mixed_triggers_are_not_flagged(tmp_path: Path) -> None:
    """One real intent phrase among hygiene-shaped triggers is acceptable —
    the rule only fires when EVERY trigger is machine-shaped."""
    content = _GOOD_SKILL.replace(
        '  - "diagnose test failure"',
        '  - "You are an adversarial SKEPTIC reviewing this change"',
    )
    assert lint_skill(_write_skill(tmp_path, content)) == []


# ---------------------------------------------------------------------------
# Rule ①: triggers present and not all hygiene-shaped
# ---------------------------------------------------------------------------


def test_missing_triggers_flagged(tmp_path: Path) -> None:
    content = _GOOD_SKILL.replace('triggers:\n  - "flaky ci"\n  - "diagnose test failure"\n', "")
    findings = lint_skill(_write_skill(tmp_path, content))
    assert len(findings) == 1
    assert "trigger" in findings[0].lower()


def test_all_agent_prompt_triggers_flagged(tmp_path: Path) -> None:
    content = _GOOD_SKILL.replace(
        'triggers:\n  - "flaky ci"\n  - "diagnose test failure"',
        'triggers:\n  - "You are an adversarial SKEPTIC reviewing this"\n'
        '  - "<system-reminder> do the thing </system-reminder>"',
    )
    findings = lint_skill(_write_skill(tmp_path, content))
    assert len(findings) == 1
    assert "machine-generated" in findings[0]


# ---------------------------------------------------------------------------
# Rule ②: gate31 TODO skeleton residue
# ---------------------------------------------------------------------------


def test_gate31_skeleton_comment_flagged(tmp_path: Path) -> None:
    content = _GOOD_SKILL + (
        "\n## When NOT to Apply\n\n<!-- gate31 skeleton: name the adjacent-but-different "
        "requests this skill must NOT fire on. -->\n"
    )
    findings = lint_skill(_write_skill(tmp_path, content))
    assert len(findings) == 1
    assert "auto-draft template" in findings[0]


def test_multiple_todo_slots_flagged(tmp_path: Path) -> None:
    content = _GOOD_SKILL + (
        "\n## Acceptance Checklist\n\n- [ ] TODO: verifiable outcome 1\n"
        "- [ ] TODO: verifiable outcome 2\n\n## Anti-patterns\n\n- TODO: known failure mode 1\n"
    )
    findings = lint_skill(_write_skill(tmp_path, content))
    assert len(findings) == 1
    assert "auto-draft template" in findings[0]


# ---------------------------------------------------------------------------
# Rule ③: description existence (>=10 chars, _is_valid_skill bar)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "desc_line",
    [
        "description: short",
        "description: ''",
        "",
    ],
)
def test_missing_or_short_description_flagged(tmp_path: Path, desc_line: str) -> None:
    content = _GOOD_SKILL.replace(
        "description: Diagnose flaky CI failures and propose minimal fixes.", desc_line
    )
    findings = lint_skill(_write_skill(tmp_path, content))
    assert len(findings) == 1
    assert "Description" in findings[0]


# ---------------------------------------------------------------------------
# fail-soft contract + path handling
# ---------------------------------------------------------------------------


def test_unparseable_frontmatter_reports_description_only(tmp_path: Path) -> None:
    """Garbage frontmatter must not raise; it degrades to findings."""
    findings = lint_skill(_write_skill(tmp_path, "---\n: [not a dict\n---\nbody\n"))
    assert any("Description" in f for f in findings)


def test_missing_skill_md_reported_not_raised(tmp_path: Path) -> None:
    findings = lint_skill_path(tmp_path / "no-such-skill")
    assert len(findings) == 1
    assert "not found" in findings[0]


def test_lint_skill_path_accepts_dir_and_file(tmp_path: Path) -> None:
    skill_md = _write_skill(tmp_path, _GOOD_SKILL)
    assert lint_skill_path(tmp_path) == []
    assert lint_skill_path(skill_md) == []


# ---------------------------------------------------------------------------
# CLI: vibe skill lint (advisory — exit code always 0)
# ---------------------------------------------------------------------------


def test_cli_lint_clean(tmp_path: Path) -> None:
    _write_skill(tmp_path, _GOOD_SKILL)
    result = runner.invoke(skill_app, ["lint", str(tmp_path)])
    assert result.exit_code == 0
    assert "no lint findings" in result.output


def test_cli_lint_findings_still_exit_zero(tmp_path: Path) -> None:
    content = _GOOD_SKILL.replace('triggers:\n  - "flaky ci"\n  - "diagnose test failure"\n', "")
    _write_skill(tmp_path, content)
    result = runner.invoke(skill_app, ["lint", str(tmp_path)])
    assert result.exit_code == 0  # advisory only — never blocks
    # Whitespace-normalized: Rich wraps at 80 cols when COLUMNS is unset
    # (CI runners have no tty), splitting phrases mid-line.
    flat = " ".join(result.output.split())
    assert "advisory finding" in flat
    assert "block nothing" in flat
