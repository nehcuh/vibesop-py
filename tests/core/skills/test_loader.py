"""Tests for SkillLoader — skill discovery and loading."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from vibesop.core.skills.base import PromptSkill, SkillMetadata, SkillType, WorkflowSkill
from vibesop.core.skills.external_loader import ExternalSkillMetadata, SkillSource
from vibesop.core.skills.loader import LoadedSkill, SkillLoader


def _make_meta(skill_id="test", **kwargs):
    return SkillMetadata(
        id=skill_id, name="Test", description="Desc", intent=kwargs.pop("intent", "Do things"), **kwargs
    )


class TestLoadedSkill:
    """Test LoadedSkill dataclass."""

    def test_creation(self):
        meta = _make_meta()
        skill = LoadedSkill(metadata=meta, content="hello")
        assert skill.metadata.id == "test"
        assert skill.content == "hello"
        assert skill.source_file is None

    def test_creation_with_source(self, tmp_path: Path):
        source = tmp_path / "skill.md"
        source.write_text("# Test")
        meta = _make_meta()
        skill = LoadedSkill(metadata=meta, content="hello", source_file=source)
        assert skill.source_file == source


class TestSkillLoaderInit:
    """Test SkillLoader initialization."""

    def test_default_init(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path)
        assert loader.project_root == tmp_path.resolve()
        assert loader._enable_external is True
        assert loader._require_audit is True

    def test_disable_external(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        assert loader._enable_external is False
        assert loader._external_loader is None

    def test_custom_search_paths(self, tmp_path: Path):
        custom = tmp_path / "custom"
        loader = SkillLoader(project_root=tmp_path, search_paths=[custom])
        assert custom in loader._search_paths

    def test_project_hash_deterministic(self, tmp_path: Path):
        loader1 = SkillLoader(project_root=tmp_path)
        loader2 = SkillLoader(project_root=tmp_path)
        assert loader1.project_hash == loader2.project_hash
        assert len(loader1.project_hash) == 12


class TestGenerateIdFromPath:
    """Test _generate_id_from_path."""

    def test_markdown_file(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path)
        path = tmp_path / "skills" / "review.md"
        result = loader._generate_id_from_path(path)
        # parts[-1] = "review.md", name = "review"
        # parts[idx+1] = parts[1] = "review.md" (raw, not stripped)
        assert result == "project/review.md/review"

    def test_yaml_file(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path)
        path = tmp_path / "skills" / "deploy" / "deploy.yaml"
        result = loader._generate_id_from_path(path)
        assert result == "project/deploy/deploy"

    def test_yml_file(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path)
        path = tmp_path / ".vibe" / "skills" / "test.yml"
        result = loader._generate_id_from_path(path)
        # parts: (".vibe", "skills", "test.yml")
        # parts[idx+1] = parts[2] = "test.yml"
        assert result == "project/test.yml/test"

    def test_outside_project_root(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path)
        path = Path("/outside/skills/custom.md")
        result = loader._generate_id_from_path(path)
        assert "custom" in result

    def test_none_path(self):
        loader = SkillLoader(project_root=Path("."))
        result = loader._generate_id_from_path(None)
        assert result == "unknown/skill"

    def test_no_extension(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path)
        path = tmp_path / "skills" / "review" / "SKILL"
        result = loader._generate_id_from_path(path)
        assert result == "project/review/SKILL"


class TestDiscoverAll:
    """Test discover_all method."""

    def test_discovers_markdown_skills(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "my-skill.md").write_text("""---
id: my-skill
name: My Skill
description: A test skill
---
# Content
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        skills = loader.discover_all()
        assert "my-skill" in skills

    def test_discovers_yaml_skills(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test-skill.yaml").write_text("""id: test-skill
name: Test Skill
description: A YAML skill
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        skills = loader.discover_all()
        assert len(skills) > 0

    def test_discovers_yml_skills(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test-skill.yml").write_text("""id: test-skill
name: Test Skill
description: A YML skill
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        skills = loader.discover_all()
        assert len(skills) > 0

    def test_cache_returns_same(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test.md").write_text("""---
id: test
name: Test
description: Desc
---
# Body
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        first = loader.discover_all()
        second = loader.discover_all()
        assert first is second

    def test_force_reload(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test.md").write_text("""---
id: test
name: Test
description: Desc
---
# Body
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        first = loader.discover_all()
        second = loader.discover_all(force_reload=True)
        assert first is not second

    def test_skips_invalid_markdown(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "no-frontmatter.md").write_text("# No frontmatter here")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        skills = loader.discover_all()
        assert len(skills) == 0

    def test_empty_search_paths(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        skills = loader.discover_all()
        assert isinstance(skills, dict)

    def test_missing_search_path(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        skills = loader.discover_all()
        assert skills == {}


class TestGetSkill:
    """Test get_skill method."""

    def test_get_existing_skill(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test.md").write_text("""---
id: test
name: Test
description: Desc
---
Body
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        skill = loader.get_skill("test")
        assert skill is not None
        assert skill.metadata.id == "test"

    def test_get_missing_skill(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        assert loader.get_skill("nonexistent") is None


class TestReadSkillContent:
    """Test read_skill_content method."""

    def test_reads_from_source_file(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test.md").write_text("""---
id: test
name: Test
description: Desc
---
Body content here
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        content = loader.read_skill_content("test")
        assert "Body content here" in content

    def test_returns_empty_for_missing_skill(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        assert loader.read_skill_content("nonexistent") == ""

    def test_falls_back_to_content_field(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        meta = _make_meta()
        skill = LoadedSkill(metadata=meta, content="inline content")
        loader._skill_cache["test"] = skill
        result = loader.read_skill_content("test")
        assert result == "inline content"


class TestListSkills:
    """Test list_skills method."""

    def test_list_all_skills(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "a.md").write_text("""---
id: a
name: A
description: DescA
---
A
""")
        (skills_dir / "b.md").write_text("""---
id: b
name: B
description: DescB
---
B
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        skills = loader.list_skills()
        assert len(skills) == 2

    def test_list_filter_by_namespace(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "a.md").write_text("""---
id: a
name: A
description: DescA
namespace: ns1
---
A
""")
        (skills_dir / "b.md").write_text("""---
id: b
name: B
description: DescB
namespace: ns2
---
B
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        filtered = loader.list_skills(namespace="ns1")
        assert len(filtered) == 1
        assert filtered[0].metadata.id == "a"


class TestInstantiate:
    """Test instantiate method."""

    def test_instantiate_prompt_skill_string(self, tmp_path: Path):
        meta = _make_meta(skill_type=SkillType.PROMPT)
        skill = LoadedSkill(metadata=meta, content="Do the thing")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._skill_cache["test"] = skill
        instance = loader.instantiate("test")
        assert isinstance(instance, PromptSkill)
        assert instance._prompt_template == "Do the thing"

    def test_instantiate_prompt_skill_dict(self, tmp_path: Path):
        meta = _make_meta(skill_type=SkillType.PROMPT)
        skill = LoadedSkill(
            metadata=meta,
            content={"prompt": "Do X", "system_prompt": "You are helpful"},
        )
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._skill_cache["test"] = skill
        instance = loader.instantiate("test")
        assert isinstance(instance, PromptSkill)
        assert instance._prompt_template == "Do X"

    def test_instantiate_workflow_skill(self, tmp_path: Path):
        meta = _make_meta(skill_type=SkillType.WORKFLOW)
        skill = LoadedSkill(
            metadata=meta,
            content={"steps": [{"name": "step1"}, {"name": "step2"}]},
        )
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._skill_cache["test"] = skill
        instance = loader.instantiate("test")
        assert isinstance(instance, WorkflowSkill)
        assert len(instance.steps) == 2  # type: ignore[attr-defined]

    def test_instantiate_workflow_skill_string_content(self, tmp_path: Path):
        meta = _make_meta(skill_type=SkillType.WORKFLOW)
        skill = LoadedSkill(metadata=meta, content="not a dict")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._skill_cache["test"] = skill
        instance = loader.instantiate("test")
        assert instance is None

    def test_instantiate_missing_skill(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        assert loader.instantiate("nonexistent") is None


class TestClearCache:
    """Test clear_cache."""

    def test_clear_cache(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test.md").write_text("""---
id: test
name: Test
description: Desc
---
Body
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader.discover_all()
        assert len(loader._skill_cache) > 0
        loader.clear_cache()
        assert len(loader._skill_cache) == 0


class TestValidateAlgorithms:
    """Test _validate_algorithms."""

    def test_unknown_algorithm_warns(self, tmp_path: Path, caplog):
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        meta = _make_meta(algorithms=["nonexistent_algo_xyz"])
        import logging
        with caplog.at_level(logging.WARNING):
            loader._validate_algorithms(meta)
        assert len(caplog.records) >= 1

    def test_no_algorithms_no_warning(self, tmp_path: Path, caplog):
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        meta = _make_meta()
        import logging
        with caplog.at_level(logging.WARNING):
            loader._validate_algorithms(meta)
        assert len(caplog.records) == 0


class TestConvertExternalSkill:
    """Test _convert_external_skill."""

    def test_converts_with_pack_name(self, tmp_path: Path):
        base_meta = _make_meta("my-skill")
        ext_meta = ExternalSkillMetadata(
            base_metadata=base_meta,
            source=SkillSource.PACK,
            pack_name="superpowers",
        )
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        result = loader._convert_external_skill(ext_meta)
        assert result is not None
        assert result.metadata.id == "superpowers/my-skill"

    def test_converts_without_pack_name(self, tmp_path: Path):
        base_meta = _make_meta("my-skill")
        ext_meta = ExternalSkillMetadata(
            base_metadata=base_meta,
            source=SkillSource.EXTERNAL,
        )
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        result = loader._convert_external_skill(ext_meta)
        assert result is not None
        assert result.metadata.id == "my-skill"

    def test_rejects_non_external_metadata(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        result = loader._convert_external_skill(MagicMock())
        assert result is None

    def test_converts_unknown_skill_type_to_prompt(self, tmp_path: Path):
        base_meta = _make_meta("test", skill_type="nonexistent_type")
        ext_meta = ExternalSkillMetadata(
            base_metadata=base_meta,
            source=SkillSource.PACK,
            pack_name="test-pack",
        )
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        result = loader._convert_external_skill(ext_meta)
        assert result is not None
        assert result.metadata.skill_type == SkillType.PROMPT


class TestLoadMarkdownSkill:
    """Test _load_markdown_skill internal method."""

    def test_loads_valid_markdown(self, tmp_path: Path):
        md = tmp_path / "test.md"
        md.write_text("""---
id: test
name: Test
description: A test skill
---
# Do this
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._load_markdown_skill(md)
        assert "test" in loader._skill_cache
        assert loader._skill_cache["test"].content == "# Do this"

    def test_skips_duplicate_id(self, tmp_path: Path):
        md1 = tmp_path / "first.md"
        md1.write_text("""---
id: dup
name: First
description: First skill
---
First body
""")
        md2 = tmp_path / "second.md"
        md2.write_text("""---
id: dup
name: Second
description: Second skill
---
Second body
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._load_markdown_skill(md1)
        loader._load_markdown_skill(md2)
        assert loader._skill_cache["dup"].metadata.name == "First"

    def test_skips_file_without_frontmatter(self, tmp_path: Path):
        md = tmp_path / "no-frontmatter.md"
        md.write_text("# Just a heading")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._load_markdown_skill(md)
        assert len(loader._skill_cache) == 0

    def test_workflow_type_parses_steps(self, tmp_path: Path):
        md = tmp_path / "workflow.md"
        md.write_text("""---
id: workflow
name: Workflow
description: A workflow skill
type: workflow
---
steps:
  - name: Step 1
    action: do_something
  - name: Step 2
    action: verify
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._load_markdown_skill(md)
        skill = loader._skill_cache.get("workflow")
        assert skill is not None
        assert isinstance(skill.content, dict)
        assert len(skill.content["steps"]) == 2


class TestLoadYamlSkill:
    """Test _load_yaml_skill internal method."""

    def test_loads_valid_yaml(self, tmp_path: Path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("""id: test-yaml
name: Test YAML
description: A YAML-defined skill
prompt: Do this thing
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._load_yaml_skill(yaml_file)
        assert "test-yaml" in loader._skill_cache

    def test_skips_duplicate_id(self, tmp_path: Path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("""id: dup-yaml
name: Duplicate
description: A duplicate
""")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._skill_cache["dup-yaml"] = LoadedSkill(
            metadata=_make_meta("dup-yaml"),
            content="existing",
        )
        loader._load_yaml_skill(yaml_file)
        assert loader._skill_cache["dup-yaml"].content == "existing"

    def test_skips_non_dict_yaml(self, tmp_path: Path):
        yaml_file = tmp_path / "list.yaml"
        yaml_file.write_text("- item1\n- item2\n")
        loader = SkillLoader(project_root=tmp_path, enable_external=False)
        loader._load_yaml_skill(yaml_file)
        assert len(loader._skill_cache) == 0


class TestMetadataKeys:
    """Test _metadata_keys property."""

    def test_metadata_keys_contains_expected(self, tmp_path: Path):
        loader = SkillLoader(project_root=tmp_path)
        keys = loader._metadata_keys()
        assert "id" in keys
        assert "name" in keys
        assert "description" in keys
        assert "type" in keys
