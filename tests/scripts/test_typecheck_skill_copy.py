"""Bundled diagnosis skill must not reinstall the basedpyright exit-3 fail-open."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "core" / "skills" / "deep-diagnosis-optimization" / "SKILL.md"


def test_deep_diagnosis_skill_does_not_accept_basedpyright_exit_3() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "|| [ $? -eq 3 ]" not in text
    assert "exits 3 for warnings-only" not in text
    assert "uv run basedpyright --level error" in text


def test_readme_typecheck_command_matches_ci_gate() -> None:
    for name in ("README.md", "README.zh-CN.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "uv run basedpyright --level error" in text
        assert re.search(r"^uv run basedpyright\s*$", text, re.M) is None
