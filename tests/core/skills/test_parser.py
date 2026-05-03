"""Tests for skill markdown parser."""

from pathlib import Path

from vibesop.core.skills.parser import extract_frontmatter, parse_skill_md


class TestExtractFrontmatter:
    """Test frontmatter extraction."""

    def test_valid_frontmatter(self):
        content = "---\nid: test\nname: Test\n---\n# Body\n"
        frontmatter, body = extract_frontmatter(content)
        assert frontmatter is not None
        assert frontmatter["id"] == "test"
        assert frontmatter["name"] == "Test"
        assert "# Body" in body

    def test_no_frontmatter(self):
        content = "# Just markdown\nNo frontmatter here.\n"
        frontmatter, body = extract_frontmatter(content)
        assert frontmatter is None
        assert body == content

    def test_incomplete_frontmatter(self):
        content = "---\nid: test\n"
        frontmatter, _body = extract_frontmatter(content)
        assert frontmatter is None

    def test_empty_frontmatter(self):
        content = "---\n---\n# Body\n"
        frontmatter, _body = extract_frontmatter(content)
        # Empty frontmatter parses as None with ruamel.yaml
        assert frontmatter is None

    def test_invalid_yaml(self):
        content = "---\n{invalid yaml: [\n---\n# Body\n"
        frontmatter, _body = extract_frontmatter(content)
        assert frontmatter is None


class TestParseSkillMd:
    """Test full skill markdown parsing."""

    def test_parse_valid_skill(self, tmp_path: Path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "id: test/skill\n"
            "name: Test Skill\n"
            "description: A test skill\n"
            "version: 1.0.0\n"
            "---\n"
            "# Test Skill\n"
        )

        meta = parse_skill_md(skill_dir)
        assert meta is not None
        assert meta.id == "test/skill"
        assert meta.name == "Test Skill"
        assert meta.description == "A test skill"
        assert meta.version == "1.0.0"

    def test_parse_missing_file(self, tmp_path: Path):
        meta = parse_skill_md(tmp_path / "missing")
        assert meta is None

    def test_parse_file_directly(self, tmp_path: Path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "id: direct\n"
            "name: Direct\n"
            "---\n"
        )

        meta = parse_skill_md(skill_file)
        assert meta is not None
        assert meta.id == "direct"

    def test_parse_no_frontmatter(self, tmp_path: Path):
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# No frontmatter\n")

        meta = parse_skill_md(skill_dir)
        assert meta is None

    def test_parse_with_tags_string(self, tmp_path: Path):
        skill_dir = tmp_path / "tagged-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "id: tagged\n"
            "tags: a, b, c\n"
            "---\n"
        )

        meta = parse_skill_md(skill_dir)
        assert meta is not None
        assert "a" in meta.tags
        assert "b" in meta.tags
        assert "c" in meta.tags

    def test_parse_with_triggers_string(self, tmp_path: Path):
        skill_dir = tmp_path / "triggered-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\n"
            "id: triggered\n"
            "triggers: debug, fix\n"
            "---\n"
        )

        meta = parse_skill_md(skill_dir)
        assert meta is not None
        assert "debug" in meta.triggers
        assert "fix" in meta.triggers
