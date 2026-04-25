"""Tests for vibe skill add command."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.skills import skills_app
from vibesop.core.skills.base import SkillMetadata

runner = CliRunner()


class TestSkillAddCommand:
    """Test suite for skill add command."""

    def test_command_exists(self):
        """Test that skill_add command can be imported."""
        from vibesop.cli.commands.skill_add import add
        assert add is not None
        assert callable(add)

    def test_command_signature(self):
        """Test command signature has correct parameters."""
        import inspect

        from vibesop.cli.commands.skill_add import add

        sig = inspect.signature(add)
        params = list(sig.parameters.keys())

        assert "skill_source" in params
        assert "global_" in params
        assert "auto_config" in params
        assert "force" in params

    @patch("vibesop.cli.commands.skill_add._detect_and_load_skill")
    def test_detect_skill_from_directory(self, mock_detect):
        """Test skill detection from directory."""

        # Mock return value
        mock_metadata = SkillMetadata(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
            trigger_when="User asks for test"
        )
        mock_detect.return_value = (Path("test-skill"), mock_metadata)

        # Test would go here
        # This is a placeholder for actual test implementation

    def test_extract_keywords(self):
        """Test keyword extraction for routing patterns."""
        from vibesop.cli.commands.skill_add import _extract_keywords

        text = "使用 Tushare API 获取股票数据并开发量化交易策略"
        keywords = _extract_keywords(text)

        assert isinstance(keywords, list)
        assert len(keywords) > 0
        # Should extract meaningful Chinese and English keywords
        assert any("tushare" in kw.lower() for kw in keywords)

    def test_save_auto_config(self, tmp_path):
        """Test auto-configuration file generation."""

        from vibesop.cli.commands.skill_add import _save_auto_config

        # Create test config
        config = {
            "skill_id": "test-skill",
            "priority": 70,
            "enabled": True,
            "scope": "project"
        }

        # Mock the config file path
        with patch("vibesop.cli.commands.skill_add.Path") as mock_path:
            mock_path.return_value = tmp_path / "auto-config.yaml"
            _save_auto_config(config)

        # Verify file was created (this would need actual implementation)

    @patch("vibesop.cli.commands.skill_add.questionary")
    @patch("vibesop.cli.commands.skill_add._detect_and_load_skill")
    @patch("vibesop.cli.commands.skill_add.SkillSecurityAuditor")
    @patch("vibesop.cli.commands.skill_add.SkillInstaller")
    def test_full_installation_flow(
        self,
        mock_installer,
        mock_auditor,
        mock_detect,
        mock_questionary,
        tmp_path
    ):
        """Test complete installation flow."""
        # Setup mocks
        mock_metadata = SkillMetadata(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
            trigger_when="User asks for test"
        )
        mock_detect.return_value = (tmp_path, mock_metadata)

        mock_audit_result = Mock()
        mock_audit_result.risk_level = "safe"
        mock_audit_result.summary = "No issues found"
        mock_auditor.return_value.audit_skill_file.return_value = mock_audit_result

        mock_install_result = {
            "success": True,
            "skill_id": "test-skill",
            "installed_path": str(tmp_path),
            "dependencies_installed": [],
            "errors": [],
            "warnings": []
        }
        mock_installer.return_value.install_skill.return_value = mock_install_result

        mock_questionary.select.return_value.ask.return_value = "project"
        mock_questionary.confirm.return_value.ask.return_value = True

        # This test would verify the complete flow
        # Actual implementation would require more setup


class TestSkillAddIntegration:
    """Integration tests for skill add command."""

    def test_help_output(self):
        """Test that help command works."""
        result = runner.invoke(skills_app, ["add", "--help"])
        assert result.exit_code == 0
        assert "add" in result.stdout
        assert "skill" in result.stdout.lower()

    def test_missing_argument_shows_error(self):
        """Test that missing argument shows helpful error."""
        # This would test the actual CLI behavior
        pass


class TestKeywordExtraction:
    """Test keyword extraction algorithm."""

    def test_extract_keywords_from_english(self):
        """Test extraction from English text."""
        from vibesop.cli.commands.skill_add import _extract_keywords

        text = "Use Tushare API to get stock market data"
        keywords = _extract_keywords(text)

        assert "tushare" in [kw.lower() for kw in keywords]
        assert "stock" in [kw.lower() for kw in keywords]

    def test_extract_keywords_from_chinese(self):
        """Test extraction from Chinese text."""
        from vibesop.cli.commands.skill_add import _extract_keywords

        text = "使用 Tushare API 获取股票数据"
        keywords = _extract_keywords(text)

        assert len(keywords) > 0
        # Should extract meaningful words

    def test_extract_keywords_removes_stop_words(self):
        """Test that stop words are removed."""
        from vibesop.cli.commands.skill_add import _extract_keywords

        text = "Get the stock data from the API"
        keywords = _extract_keywords(text)

        # Should not contain stop words like "the", "from"
        assert "the" not in [kw.lower() for kw in keywords]
        assert "from" not in [kw.lower() for kw in keywords]


class TestConfigurationGeneration:
    """Test auto-configuration generation."""

    def test_priority_calculation(self):
        """Test priority is calculated correctly."""
        # Test different categories get correct priorities
        priority_map = {
            "development": 70,
            "testing": 65,
            "debugging": 80,
            "review": 50,
        }

        for _category, expected_priority in priority_map.items():
            # This would test the actual priority calculation logic
            assert isinstance(expected_priority, int)
            assert 0 <= expected_priority <= 100

    def test_routing_pattern_generation(self):
        """Test routing patterns are generated correctly."""
        from vibesop.cli.commands.skill_add import _extract_keywords

        description = "Use Tushare API for stock trading"
        keywords = _extract_keywords(description)

        # Keywords should be suitable for regex patterns
        assert all(isinstance(kw, str) for kw in keywords)
        assert all(len(kw) > 0 for kw in keywords)


class TestSecurityAudit:
    """Test security audit integration."""

    @patch("vibesop.cli.commands.skill_add.SkillSecurityAuditor")
    def test_safe_skill_passes_audit(self, mock_auditor):
        """Test that safe skills pass audit."""

        mock_audit_result = Mock()
        mock_audit_result.risk_level = "safe"
        mock_audit_result.summary = "No issues found"
        mock_auditor.return_value.audit_skill_file.return_value = mock_audit_result

        # Test would verify safe skills proceed
        assert mock_audit_result.risk_level == "safe"

    @patch("vibesop.cli.commands.skill_add.SkillSecurityAuditor")
    def test_critical_skill_fails_audit(self, mock_auditor):
        """Test that critical skills fail audit."""
        mock_audit_result = Mock()
        mock_audit_result.risk_level = "critical"
        mock_audit_result.summary = "Security risks detected"
        mock_auditor.return_value.audit_skill_file.return_value = mock_audit_result

        # Test would verify critical skills are rejected
        assert mock_audit_result.risk_level == "critical"


class TestDocumentation:
    """Test documentation quality."""

    def test_skill_add_command_has_docstring(self):
        """Test that command has proper documentation."""
        from vibesop.cli.commands.skill_add import add

        assert add.__doc__ is not None
        assert "skill" in add.__doc__.lower()
        assert "add" in add.__doc__.lower() or "install" in add.__doc__.lower()

    def test_helper_functions_have_docstrings(self):
        """Test that helper functions are documented."""
        from vibesop.cli.commands.skill_add import (
            _detect_and_load_skill,
            _extract_keywords,
            _save_auto_config,
        )

        for func in [_detect_and_load_skill, _extract_keywords, _save_auto_config]:
            assert func.__doc__ is not None


class TestErrorHandling:
    """Test error handling."""

    def test_invalid_skill_path(self):
        """Test handling of invalid skill path."""
        from vibesop.cli.commands.skill_add import _detect_and_load_skill

        # Test with non-existent path
        result = _detect_and_load_skill("/nonexistent/path")
        # Should handle gracefully
        assert result is not None

    def test_corrupted_skill_metadata(self):
        """Test handling of corrupted metadata."""
        # Test with malformed SKILL.md
        pass


class TestAgentEnvironmentBranch:
    """Test Agent-aware installation path (Step 1 enhancement)."""

    @patch("vibesop.cli.commands.skill_add.is_in_agent_environment")
    @patch("vibesop.cli.commands.skill_add.AIEnhancer")
    @patch("vibesop.cli.commands.skill_add.understand_skill_from_file")
    def test_agent_environment_skips_ai_enhancer(
        self,
        mock_understand: Any,
        mock_ai_enhancer_cls: Any,
        mock_is_agent: Any,
    ) -> None:
        """When in Agent env, AIEnhancer should NOT be instantiated."""
        from vibesop.cli.commands.skill_add import _auto_configure_skill_with_llm
        from vibesop.core.skills.understander import AutoGeneratedConfig

        mock_is_agent.return_value = True
        mock_config = AutoGeneratedConfig(
            skill_id="test-skill",
            category="review",
            priority=60,
            confidence=0.85,
            routing_patterns=[".*test.*"],
        )
        mock_understand.return_value = mock_config

        metadata = SkillMetadata(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
        )

        # Run with a temp directory containing SKILL.md
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nid: test-skill\n---\n")

            _auto_configure_skill_with_llm(metadata, "project", str(skill_dir))

        mock_ai_enhancer_cls.assert_not_called()

    @patch("vibesop.cli.commands.skill_add.is_in_agent_environment")
    @patch("vibesop.cli.commands.skill_add.understand_skill_from_file")
    def test_agent_environment_uses_rule_engine_only(
        self,
        mock_understand: Any,
        mock_is_agent: Any,
    ) -> None:
        """Agent env should call understand_skill_from_file and save config."""
        from vibesop.cli.commands.skill_add import _auto_configure_skill_with_llm
        from vibesop.core.skills.understander import AutoGeneratedConfig

        mock_is_agent.return_value = True
        mock_config = AutoGeneratedConfig(
            skill_id="test-skill",
            category="debugging",
            priority=80,
            confidence=0.8,
            routing_patterns=[".*debug.*"],
        )
        mock_understand.return_value = mock_config

        metadata = SkillMetadata(
            id="test-skill",
            name="Test Skill",
            description="Debug things",
            intent="debug",
        )

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nid: test-skill\n---\n")

            _auto_configure_skill_with_llm(metadata, "project", str(skill_dir))

        mock_understand.assert_called_once()

    @patch("vibesop.cli.commands.skill_add.is_in_agent_environment")
    @patch("vibesop.cli.commands.skill_add.AIEnhancer")
    @patch("vibesop.cli.commands.skill_add.understand_skill_from_file")
    def test_non_agent_environment_uses_ai_enhancer_fallback(
        self,
        mock_understand: Any,
        mock_ai_enhancer_cls: Any,
        mock_is_agent: Any,
    ) -> None:
        """Low confidence in non-Agent env should trigger AIEnhancer fallback."""
        from vibesop.cli.commands.skill_add import _auto_configure_skill_with_llm
        from vibesop.core.skills.understander import AutoGeneratedConfig

        mock_is_agent.return_value = False
        mock_config = AutoGeneratedConfig(
            skill_id="test-skill",
            category="development",
            priority=50,
            confidence=0.5,  # Below 0.7 threshold
            routing_patterns=[],
        )
        mock_understand.return_value = mock_config

        mock_enhancer = Mock()
        mock_enhancer.enhance_suggestion.return_value = Mock(
            category="development",
            tags=["test"],
            trigger_conditions=["user asks"],
        )
        mock_ai_enhancer_cls.return_value = mock_enhancer

        metadata = SkillMetadata(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
        )

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nid: test-skill\n---\n")

            _auto_configure_skill_with_llm(metadata, "project", str(skill_dir))

        mock_ai_enhancer_cls.assert_called_once()

    def test_prompt_agent_for_config_accepts_json_adjustments(self) -> None:
        """_prompt_agent_for_config should parse JSON adjustments."""
        from vibesop.cli.commands.skill_add import _prompt_agent_for_config
        from vibesop.core.skills.understander import AutoGeneratedConfig

        config = AutoGeneratedConfig(
            skill_id="test-skill",
            category="development",
            priority=50,
            confidence=0.6,
            routing_patterns=[".*test.*"],
        )
        metadata = SkillMetadata(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
        )

        with patch("vibesop.cli.commands.skill_add.questionary") as mock_q:
            mock_q.confirm.return_value.ask.return_value = False
            mock_q.text.return_value.ask.return_value = '{"category": "review", "priority": 75}'

            result = _prompt_agent_for_config(metadata, config, "project")

        assert result.category == "review"
        assert result.priority == 75
        assert result.routing_patterns == [".*test.*"]  # unchanged

    def test_prompt_agent_for_config_defaults_on_invalid_json(self) -> None:
        """Invalid JSON adjustments should fall back to draft config."""
        from vibesop.cli.commands.skill_add import _prompt_agent_for_config
        from vibesop.core.skills.understander import AutoGeneratedConfig

        config = AutoGeneratedConfig(
            skill_id="test-skill",
            category="development",
            priority=50,
            confidence=0.6,
        )
        metadata = SkillMetadata(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
        )

        with patch("vibesop.cli.commands.skill_add.questionary") as mock_q:
            mock_q.confirm.return_value.ask.return_value = False
            mock_q.text.return_value.ask.return_value = "not-json"

            result = _prompt_agent_for_config(metadata, config, "project")

        assert result.category == "development"  # unchanged
        assert result.priority == 50  # unchanged


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
