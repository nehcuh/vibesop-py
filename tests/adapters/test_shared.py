"""Tests for shared adapter utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from vibesop.adapters._shared import (
    find_skill_content,
    generate_fallback_skill_content,
    is_pack_installed,
    normalize_skill_type,
    render_route_hook,
)


class TestFindSkillContent:
    """Test find_skill_content."""

    def test_find_existing_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "core" / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# Test Skill\n", encoding="utf-8")

        result = find_skill_content("test-skill", tmp_path)
        assert result == "# Test Skill\n"

    def test_find_in_skills_dir(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# Alt Location\n", encoding="utf-8")

        result = find_skill_content("test-skill", tmp_path)
        assert result == "# Alt Location\n"

    def test_not_found(self, tmp_path: Path) -> None:
        result = find_skill_content("nonexistent", tmp_path)
        assert result is None

    def test_read_error(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "core" / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("content", encoding="utf-8")

        with patch("pathlib.Path.read_text", side_effect=PermissionError("denied")):
            result = find_skill_content("test-skill", tmp_path)
        assert result is None


class TestIsPackInstalled:
    """Test is_pack_installed."""

    def test_no_namespace(self) -> None:
        assert is_pack_installed("simple-skill") is None

    def test_pack_found(self, tmp_path: Path) -> None:
        pack_dir = tmp_path / ".config" / "skills" / "gstack" / "review"
        pack_dir.mkdir(parents=True)
        (pack_dir / "SKILL.md").write_text("# Review\n", encoding="utf-8")

        with patch.object(Path, "home", return_value=tmp_path):
            result = is_pack_installed("gstack/review")
        assert result == pack_dir

    def test_pack_not_found(self, tmp_path: Path) -> None:
        with patch.object(Path, "home", return_value=tmp_path):
            result = is_pack_installed("gstack/review")
        assert result is None

    def test_pack_in_skills_subdir(self, tmp_path: Path) -> None:
        pack_dir = tmp_path / ".config" / "skills" / "gstack" / "skills" / "review"
        pack_dir.mkdir(parents=True)
        (pack_dir / "SKILL.md").write_text("# Review\n", encoding="utf-8")

        with patch.object(Path, "home", return_value=tmp_path):
            result = is_pack_installed("gstack/review")
        assert result == pack_dir


class TestNormalizeSkillType:
    """Test normalize_skill_type."""

    def test_no_frontmatter(self) -> None:
        content = "# Heading\n\nNo frontmatter here."
        assert normalize_skill_type(content) == content

    def test_already_standard(self) -> None:
        content = "---\ntype: standard\n---\n# Skill"
        assert normalize_skill_type(content) == content

    def test_prompt_to_standard(self) -> None:
        content = "---\nname: Test\ntype: prompt\n---\n# Skill"
        result = normalize_skill_type(content)
        assert "type: standard" in result
        assert "type: prompt" not in result

    def test_flow_unchanged(self) -> None:
        content = "---\ntype: flow\n---\n# Skill"
        assert normalize_skill_type(content) == content

    def test_invalid_yaml(self) -> None:
        content = "---\n{invalid: yaml: :::\n---\n# Skill"
        result = normalize_skill_type(content)
        assert result == content

    def test_empty_frontmatter(self) -> None:
        content = "---\n---\n# Skill"
        assert normalize_skill_type(content) == content

    def test_short_delimiter(self) -> None:
        content = "---\nname: test"
        assert normalize_skill_type(content) == content


class TestGenerateFallbackSkillContent:
    """Test generate_fallback_skill_content."""

    def test_from_dict(self) -> None:
        skill = {"id": "test", "name": "Test Skill", "description": "A test"}
        result = generate_fallback_skill_content(skill)
        assert "Test Skill" in result
        assert "A test" in result

    def test_from_object(self) -> None:
        skill = MagicMock()
        skill.id = "obj-test"
        skill.name = "Obj Skill"
        skill.description = "An object\nwith newlines"
        skill.trigger_when = ""
        result = generate_fallback_skill_content(skill)
        assert "Obj Skill" in result
        assert "An object with newlines" in result  # newlines collapsed

    def test_with_trigger(self) -> None:
        skill = {"id": "t", "name": "T", "description": "D", "trigger_when": "when asked"}
        result = generate_fallback_skill_content(skill)
        assert "## Trigger" in result
        assert "when asked" in result

    def test_dir_name_override(self) -> None:
        skill = {"id": "x", "name": "Y", "description": "Z"}
        result = generate_fallback_skill_content(skill, dir_name="Override")
        assert "Override" in result
        assert "Y" not in result

    def test_quote_escaping(self) -> None:
        skill = {"id": "q", "name": "Q", "description": 'Say "hello"'}
        result = generate_fallback_skill_content(skill)
        assert 'Say \\"hello\\"' in result


class TestRenderRouteHook:
    """Test render_route_hook."""

    def test_basic_render(self) -> None:
        result = render_route_hook(platform="opencode", platform_name="OpenCode")
        assert "#!/bin/bash" in result
        assert "VibeSOP" in result or "vibesop" in result.lower()

    def test_claude_code_platform(self) -> None:
        result = render_route_hook(
            platform="claude-code",
            platform_name="Claude Code",
            hook_event_name="UserPromptSubmit",
        )
        assert "claude-code" in result or "Claude" in result

    def test_with_options(self) -> None:
        result = render_route_hook(
            platform="kimi-cli",
            enable_explicit_overrides=True,
            enable_orchestration=True,
            no_match_message=True,
        )
        assert "vibe route" in result or "VibeSOP" in result
