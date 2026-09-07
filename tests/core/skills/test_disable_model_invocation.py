"""D1: disable-model-invocation is a first-class SkillSpec field."""

from __future__ import annotations

from pathlib import Path

from vibesop.core.skills.parser import build_spec, parse_skill_md
from vibesop.spec.models import SkillSpec


def test_spec_defaults_false() -> None:
    spec = SkillSpec(id="t", name="t", description="d")
    assert spec.disable_model_invocation is False


def test_parser_reads_kebab_key(tmp_path: Path) -> None:
    skill_dir = tmp_path / "grill-me"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: grill-me\n"
        "description: probe spec gaps\n"
        "disable-model-invocation: true\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    spec = parse_skill_md(skill_dir)
    assert spec is not None
    assert spec.disable_model_invocation is True


def test_parser_reads_snake_key() -> None:
    spec = build_spec(
        {"id": "x", "name": "x", "description": "d", "disable_model_invocation": True},
        "x",
        Path("x/SKILL.md"),
    )
    assert spec.disable_model_invocation is True


def test_absent_key_is_false() -> None:
    spec = build_spec(
        {"id": "x", "name": "x", "description": "d"},
        "x",
        Path("x/SKILL.md"),
    )
    assert spec.disable_model_invocation is False
