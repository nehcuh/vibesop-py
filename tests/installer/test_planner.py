"""Tests for installation planner."""

from pathlib import Path

import pytest

from vibesop.installer.planner import InstallPlan, InstallPlanner


class FakeRepoAnalysis:
    """Minimal fake for RepoAnalysis."""

    def __init__(self):
        self.pack_name = "superpowers"
        self.source_url = "https://github.com/example/superpowers"
        self.readme_install_hint = "Copy skills/ to target"
        self.skill_files = []
        self.setup_scripts = []


@pytest.fixture
def fake_analysis():
    analysis = FakeRepoAnalysis()
    analysis.skill_files = [
        Path("/tmp/superpowers/skills/debug/SKILL.md"),
        Path("/tmp/superpowers/skills/review/SKILL.md"),
    ]
    return analysis


def test_install_plan_to_dict():
    plan = InstallPlan(
        pack_name="test-pack",
        source_url="https://example.com",
        target_path=Path("/target"),
        skills=[{"id": "debug", "path": "skills/debug"}],
        readme_hint="Hint",
        setup_steps=["step1"],
        post_install=["audit"],
    )
    d = plan.to_dict()
    assert d["pack_name"] == "test-pack"
    assert d["source_url"] == "https://example.com"
    assert d["target_path"] == "/target"
    assert d["skills"] == [{"id": "debug", "path": "skills/debug"}]
    assert "readme_hint" in d


def test_install_plan_summary():
    plan = InstallPlan(
        pack_name="test-pack",
        source_url="https://example.com",
        target_path=Path("/target"),
        skills=[{"id": "debug", "path": "skills/debug"}],
        readme_hint="Hint\nMore hint",
        setup_steps=["step1"],
    )
    summary = plan.summary()
    assert "test-pack" in summary
    assert "debug" in summary
    assert "step1" in summary


def test_planner_default_base_target():
    planner = InstallPlanner()
    assert planner.base_target == Path.home() / ".config" / "skills"


def test_planner_plan_basic(fake_analysis):
    planner = InstallPlanner(base_target=Path("/tmp/target"))
    plan = planner.plan(fake_analysis)

    assert plan.pack_name == "superpowers"
    assert plan.target_path == Path("/tmp/target/superpowers")
    assert len(plan.skills) == 2
    assert plan.skills[0]["id"] == "debug"
    assert plan.skills[1]["id"] == "review"


def test_planner_plan_setup_steps(fake_analysis):
    planner = InstallPlanner(base_target=Path("/tmp/target"))
    fake_analysis.setup_scripts = ["requirements.txt", "package.json", "Makefile"]
    plan = planner.plan(fake_analysis)

    assert any("pip install" in step for step in plan.setup_steps)
    assert any("npm install" in step for step in plan.setup_steps)
    assert any("make setup" in step for step in plan.setup_steps)


def test_planner_plan_post_install(fake_analysis):
    planner = InstallPlanner(base_target=Path("/tmp/target"))
    plan = planner.plan(fake_analysis)

    assert any("security audit" in step for step in plan.post_install)
    assert any("Update registry" in step for step in plan.post_install)
