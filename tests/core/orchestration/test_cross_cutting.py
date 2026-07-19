"""Tests for cross-cutting workflow definitions."""

from pathlib import Path

from vibesop.core.orchestration.cross_cutting import (
    CrossCuttingDiscovery,
    CrossCuttingWorkflow,
    parse_cross_cutting_workflow,
)


class TestCrossCuttingWorkflow:
    def test_creation(self):
        wf = CrossCuttingWorkflow(
            id="cross-cutting/test",
            name="test",
            description="A test workflow",
            depends_on=["skill-a", "skill-b"],
            steps=[
                {"skill": "skill-a", "intent": "First step", "order": 1},
                {"skill": "skill-b", "intent": "Second step", "order": 2},
            ],
        )
        assert wf.skill_count == 2
        assert wf.step_count == 2
        assert "skill-a" in wf.depends_on

    def test_to_dict(self):
        wf = CrossCuttingWorkflow(
            id="cross-cutting/test",
            name="Test",
            description="Desc",
            depends_on=["a", "b"],
            tags=["workflow"],
        )
        d = wf.to_dict()
        assert d["id"] == "cross-cutting/test"
        assert d["depends_on"] == ["a", "b"]
        assert "workflow" in d["tags"]


class TestParseCrossCutting:
    def test_parse_valid_workflow(self, tmp_path: Path):
        wf_dir = tmp_path / "test-wf"
        wf_dir.mkdir()
        skill_md = wf_dir / "SKILL.md"
        skill_md.write_text(
            """---
id: cross-cutting/test
name: Test Workflow
description: A test cross-cutting workflow
type: cross-cutting
depends_on:
  - skill-a
  - skill-b
steps:
  - skill: skill-a
    intent: Do the first thing
    order: 1
  - skill: skill-b
    intent: Do the second thing
    order: 2
tags: [workflow, test]
---

# Test Workflow

Test content.
""",
            encoding="utf-8",
        )
        wf = parse_cross_cutting_workflow(skill_md)
        assert wf is not None
        assert wf.id == "cross-cutting/test"
        assert wf.name == "Test Workflow"
        assert len(wf.depends_on) == 2
        assert "skill-a" in wf.depends_on
        assert len(wf.steps) == 2
        assert "workflow" in wf.tags

    def test_parse_non_workflow_skipped(self, tmp_path: Path):
        """Regular skill SKILL.md should not be parsed as workflow."""
        wf_dir = tmp_path / "regular-skill"
        wf_dir.mkdir()
        skill_md = wf_dir / "SKILL.md"
        skill_md.write_text(
            """---
id: namespace/skill
name: Regular Skill
description: A regular skill
type: prompt
---
# Regular skill content
""",
            encoding="utf-8",
        )
        wf = parse_cross_cutting_workflow(skill_md)
        assert wf is None  # type is "prompt", not "cross-cutting"

    def test_parse_missing_file(self, tmp_path: Path):
        assert parse_cross_cutting_workflow(tmp_path / "nonexistent" / "SKILL.md") is None

    def test_parse_depends_on_string(self, tmp_path: Path):
        wf_dir = tmp_path / "string-deps"
        wf_dir.mkdir()
        skill_md = wf_dir / "SKILL.md"
        skill_md.write_text(
            """---
id: cross-cutting/simple
name: Simple
description: Test
type: cross-cutting
depends_on: skill-a, skill-b, skill-c
---
Content
""",
            encoding="utf-8",
        )
        wf = parse_cross_cutting_workflow(skill_md)
        assert wf is not None
        assert wf.depends_on == ["skill-a", "skill-b", "skill-c"]


class TestCrossCuttingDiscovery:
    def test_discover_empty(self, tmp_path: Path):
        discovery = CrossCuttingDiscovery(project_root=tmp_path)
        assert discovery.discover_all() == []

    def test_discover_workflows(self, tmp_path: Path):
        wf_dir = tmp_path / ".vibe" / "skills" / "cross-cutting" / "test-wf"
        wf_dir.mkdir(parents=True)
        (wf_dir / "SKILL.md").write_text(
            """---
id: cross-cutting/test
name: Test
description: Test workflow
type: cross-cutting
depends_on:
  - skill-a
---
# Test
""",
            encoding="utf-8",
        )
        discovery = CrossCuttingDiscovery(project_root=tmp_path)
        workflows = discovery.discover_all()
        assert len(workflows) == 1
        assert workflows[0].id == "cross-cutting/test"

    def test_find_for_skills(self, tmp_path: Path):
        # Create two workflows
        for name, deps in [
            ("wf-a", ["skill-1", "skill-2", "skill-3"]),
            ("wf-b", ["skill-3", "skill-4"]),
        ]:
            wf_dir = tmp_path / ".vibe" / "skills" / "cross-cutting" / name
            wf_dir.mkdir(parents=True)
            deps_yaml = "\n".join(f"  - {d}" for d in deps)
            (wf_dir / "SKILL.md").write_text(
                f"""---
id: cross-cutting/{name}
name: {name}
description: Test
type: cross-cutting
depends_on:
{deps_yaml}
---
""",
                encoding="utf-8",
            )

        discovery = CrossCuttingDiscovery(project_root=tmp_path)
        # skill-3 covers 1/2 of wf-b (50%) and 1/3 of wf-a (33% — below threshold)
        matching = discovery.find_for_skills(["skill-3"])
        assert len(matching) == 1  # only wf-b at 50% coverage
        assert matching[0].id == "cross-cutting/wf-b"

        # skill-4 alone covers 1/2 of wf-b (50%)
        matching = discovery.find_for_skills(["skill-4"])
        assert len(matching) == 1

        # skill-1 + skill-2 covers 2/3 of wf-a (67% — above threshold)
        matching = discovery.find_for_skills(["skill-1", "skill-2"])
        assert len(matching) >= 1
        assert any(w.id == "cross-cutting/wf-a" for w in matching)

    def test_create_workflow(self, tmp_path: Path):
        discovery = CrossCuttingDiscovery(project_root=tmp_path)
        wf = discovery.create_workflow(
            name="full-stack",
            description="Design + implement + review",
            depends_on=["gstack/review", "mattpocock/tdd", "superpowers/refactor"],
            steps=[
                {"skill": "mattpocock/tdd", "intent": "Write tests first", "order": 1},
                {"skill": "superpowers/refactor", "intent": "Refactor with safety", "order": 2},
                {"skill": "gstack/review", "intent": "Review changes", "order": 3},
            ],
            tags=["full-stack", "quality"],
        )
        assert wf.id == "cross-cutting/full-stack"
        assert wf.skill_count == 3
        assert wf.step_count == 3

        # Verify file was created
        skill_md = tmp_path / ".vibe" / "skills" / "cross-cutting" / "full-stack" / "SKILL.md"
        assert skill_md.exists()

        # Verify it can be re-parsed
        wf2 = parse_cross_cutting_workflow(skill_md)
        assert wf2 is not None
        assert wf2.id == "cross-cutting/full-stack"
