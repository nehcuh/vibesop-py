"""Tests for project-level routing configuration."""

import tempfile
from pathlib import Path

from vibesop.core.routing.project_config import (
    create_default_project_routing,
    load_merged_scenario_config,
    load_merged_scenarios,
    load_project_routing,
    merge_scenario_keywords,
    merge_scenarios,
)


class TestProjectRouting:
    """Test project-level routing configuration."""

    def test_load_empty_project_routing(self):
        """Test loading from non-existent project config."""
        with tempfile.TemporaryDirectory() as tmp:
            result = load_project_routing(tmp)
            assert result == {}

    def test_create_default_project_routing(self):
        """Test creating default project routing file."""
        with tempfile.TemporaryDirectory() as tmp:
            result = create_default_project_routing(tmp)
            assert result is not None
            assert result.exists()
            assert result.name == "skill-routing.yaml"

            # Check content
            content = result.read_text(encoding="utf-8")
            assert "schema_version" in content
            assert "scenario_patterns" in content
            assert "routing_hints" in content

    def test_create_existing_project_routing(self):
        """Test creating when file already exists."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create existing file
            vibe_dir = Path(tmp) / ".vibe"
            vibe_dir.mkdir()
            existing_file = vibe_dir / "skill-routing.yaml"
            existing_file.write_text("existing: content", encoding="utf-8")

            # Should return None
            result = create_default_project_routing(tmp)
            assert result is None

    def test_merge_scenarios_with_overrides(self):
        """Test merging with scenario overrides."""
        global_scenarios = [
            {"id": "test1", "skill_id": "skill1", "keywords": ["test"]},
            {"id": "test2", "skill_id": "skill2", "keywords": ["other"]},
        ]

        project_routing = {"scenario_overrides": [{"id": "test1", "skill_id": "overridden_skill"}]}

        result = merge_scenarios(global_scenarios, project_routing)

        assert len(result) == 2
        assert result[0]["skill_id"] == "overridden_skill"
        assert result[1]["skill_id"] == "skill2"

    def test_merge_scenarios_with_disabled(self):
        """Test merging with disabled scenarios."""
        global_scenarios = [
            {"id": "test1", "name": "scenario1", "skill_id": "skill1"},
            {"id": "test2", "name": "scenario2", "skill_id": "skill2"},
        ]

        project_routing = {"disabled_scenarios": ["test1"]}

        result = merge_scenarios(global_scenarios, project_routing)

        assert len(result) == 1
        assert result[0]["id"] == "test2"

    def test_merge_scenarios_with_new_scenarios(self):
        """Test merging with project-specific scenarios."""
        global_scenarios = [
            {"id": "global1", "skill_id": "skill1"},
        ]

        project_routing = {"scenario_patterns": [{"id": "project1", "skill_id": "project_skill"}]}

        result = merge_scenarios(global_scenarios, project_routing)

        assert len(result) == 2
        assert result[0]["id"] == "global1"
        assert result[1]["id"] == "project1"

    def test_merge_scenarios_with_null_list_keys(self):
        """Keys present but null (YAML empty) must coalesce to empty, not crash.

        Regression: ``vibe init`` writes ``disabled_scenarios:`` etc. with only
        commented examples, which parses as explicit None. ``set(None)`` raised
        TypeError and every first route in a fresh project degraded to
        "No matching skill found" — found via docker A/B treatment probe
        (2026-08-28).
        """
        global_scenarios = [{"id": "test1", "skill_id": "skill1"}]
        project_routing = {
            "disabled_scenarios": None,
            "scenario_overrides": None,
            "scenario_patterns": None,
        }

        result = merge_scenarios(global_scenarios, project_routing)

        assert result == global_scenarios

    def test_init_template_null_keys_end_to_end(self):
        """The real init template must route-merge without crashing."""
        from vibesop.core.routing.project_config import get_project_routing_hints

        with tempfile.TemporaryDirectory() as tmp:
            assert create_default_project_routing(tmp) is not None
            loaded = load_project_routing(tmp)
            # Membership + None pins "key present, value null" — a plain
            # ``.get(k) is None`` would stay green if the keys were deleted.
            for key in ("disabled_scenarios", "scenario_overrides", "scenario_patterns"):
                assert key in loaded and loaded[key] is None

            result = merge_scenarios([{"id": "g1", "skill_id": "s1"}], loaded)
            assert [s["id"] for s in result] == ["g1"]
            assert get_project_routing_hints(tmp) == []

    def test_merge_scenario_keywords(self):
        """Test merging global keywords with project overrides."""
        global_keywords = {"debugging": ["debug", "bug"], "planning": ["plan"]}
        project_routing = {
            "scenario_keywords": {"debugging": ["crash", "segfault"], "new_scenario": ["deploy"]}
        }

        result = merge_scenario_keywords(global_keywords, project_routing)

        assert set(result["debugging"]) == {"debug", "bug", "crash", "segfault"}
        assert result["planning"] == ["plan"]
        assert set(result["new_scenario"]) == {"deploy"}

    def test_load_merged_scenarios(self):
        """Test loading merged scenarios."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create global registry config
            core_dir = Path(tmp) / "core"
            core_dir.mkdir(parents=True)
            global_config = core_dir / "registry.yaml"
            global_config.write_text(
                """
schema_version: 1
conflict_resolution:
  enabled: true
  strategies:
    - scenario: global_test
      id: global_test
      skill_id: global_skill
      keywords: ["global"]
  scenario_keywords:
    global_test: ["global"]
""",
                encoding="utf-8",
            )

            # Create project config
            vibe_dir = Path(tmp) / ".vibe"
            vibe_dir.mkdir()
            project_config = vibe_dir / "skill-routing.yaml"
            project_config.write_text(
                """
schema_version: 1
scenario_patterns:
  - id: project_test
    skill_id: project_skill
    keywords: ["project"]
scenario_keywords:
  global_test:
    - "project_global"
""",
                encoding="utf-8",
            )

            result = load_merged_scenarios(tmp)

            assert len(result) >= 2
            ids = [s.get("id") for s in result]
            assert "global_test" in ids
            assert "project_test" in ids

    def test_load_merged_scenario_config(self):
        """Test loading merged scenario config including keywords."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create global registry config
            core_dir = Path(tmp) / "core"
            core_dir.mkdir(parents=True)
            global_config = core_dir / "registry.yaml"
            global_config.write_text(
                """
schema_version: 1
conflict_resolution:
  enabled: true
  strategies:
    - scenario: global_test
      id: global_test
      skill_id: global_skill
  scenario_keywords:
    global_test: ["global"]
""",
                encoding="utf-8",
            )

            # Create project config
            vibe_dir = Path(tmp) / ".vibe"
            vibe_dir.mkdir()
            project_config = vibe_dir / "skill-routing.yaml"
            project_config.write_text(
                """
schema_version: 1
scenario_keywords:
  global_test:
    - "project_global"
""",
                encoding="utf-8",
            )

            config = load_merged_scenario_config(tmp)

            assert "strategies" in config
            assert "keywords" in config
            assert any(s.get("id") == "global_test" for s in config["strategies"])
            assert set(config["keywords"]["global_test"]) == {"global", "project_global"}
