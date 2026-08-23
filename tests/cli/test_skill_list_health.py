"""Tests for `vibe skill list` health summary columns (gate37 L2-lite)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import vibesop.core.skills.skill_health as health
from vibesop.cli.commands import skill_commands
from vibesop.cli.commands.skill_commands import app as skill_app

runner = CliRunner()


@pytest.fixture
def patched_health(monkeypatch: pytest.MonkeyPatch) -> None:
    # Wide terminal so rich doesn't wrap footnote lines mid-phrase.
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr(
        skill_commands,
        "_load_skills",
        lambda: [
            {
                "id": "demo/review",
                "name": "Review",
                "lifecycle": "active",
                "scope": "global",
                "version": "1.0.0",
                "enabled": True,
                "source": "builtin",
            },
            {
                "id": "pack-skill",
                "name": "Pack Skill",
                "lifecycle": "active",
                "scope": "global",
                "version": "0.1.0",
                "enabled": True,
                "source": "external",
            },
        ],
    )
    monkeypatch.setattr(health, "count_skill_fires", lambda *a, **k: {"demo/review": 3})
    monkeypatch.setattr(health, "count_skill_feedback", lambda *a, **k: {"demo/review": (2, 1)})


def test_list_renders_health_columns(patched_health: None) -> None:
    result = runner.invoke(skill_app, ["list"])
    assert result.exit_code == 0
    out = result.output
    assert "Source" in out
    assert "Fire 30d" in out
    assert "Feedback" in out
    assert "+2/-1" in out
    # A skill with no feedback records must say so — never imply neutral.
    assert "no records" in out


def test_list_footnotes_disclose_caveats(patched_health: None) -> None:
    out = runner.invoke(skill_app, ["list"]).output
    # n<30 discipline, CLI inclusion, rename/normalisation chain break,
    # partial-counts-as-no, global-store gap, pack→external fold.
    assert "n<30 proves nothing" in out
    assert "CLI" in out
    assert "partial" in out
    assert "global store" in out
    assert "pack-installed skills show as external" in out


def test_real_loader_populates_source_key() -> None:
    """claude NIT (contract test): the REAL candidate loader
    (UnifiedRouter.get_candidates via the command's own _load_skills)
    must fill the `source` key — otherwise the column's "external"
    default silently masks a loader that dropped the key."""
    skills = skill_commands._load_skills()
    assert skills, "no candidates loaded — source contract is untestable"
    for skill in skills:
        assert skill.get("source") in {"builtin", "project", "external"}, (
            f"skill {skill.get('id')!r} missing/invalid source: {skill.get('source')!r}"
        )
