"""Tests for config-driven rendering system."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from vibesop.builder import ConfigDrivenRenderer, RenderRule


class TestRenderRule:
    """Test RenderRule dataclass."""

    def test_create_rule(self) -> None:
        """Test creating a render rule."""
        rule = RenderRule(
            name="test-rule",
            condition="platform == 'claude-code'",
            template="test.md.j2",
            output_path="test.md",
            context_vars={"key": "value"},
        )
        assert rule.name == "test-rule"
        assert rule.condition == "platform == 'claude-code'"
        assert rule.template == "test.md.j2"
        assert rule.output_path == "test.md"
        assert rule.context_vars == {"key": "value"}
        assert rule.enabled is True

    def test_create_disabled_rule(self) -> None:
        """Test creating a disabled rule."""
        rule = RenderRule(
            name="disabled-rule",
            condition="",
            template="test.md.j2",
            output_path="test.md",
            context_vars={},
            enabled=False,
        )
        assert not rule.enabled


class TestConfigDrivenRenderer:
    """Test ConfigDrivenRenderer functionality."""

    def test_create_renderer(self) -> None:
        """Test creating renderer."""
        renderer = ConfigDrivenRenderer()
        assert renderer is not None
        assert renderer._env is None
        assert renderer._rules == []

    def test_load_rules_nonexistent_file(self) -> None:
        """Test loading rules from non-existent file."""
        renderer = ConfigDrivenRenderer()
        rules = renderer.load_rules(Path("/nonexistent/rules.yaml"))
        assert rules == []

    @patch("builtins.open", new_callable=mock_open, read_data="rules: []")
    @patch("pathlib.Path.exists", return_value=True)
    def test_load_rules_empty_file(self, _mock_exists: MagicMock, _mock_file: MagicMock) -> None:
        """Test loading empty rules file."""
        renderer = ConfigDrivenRenderer()
        rules = renderer.load_rules(Path("rules.yaml"))
        assert rules == []

    def test_load_rules_valid_file(self, tmp_path: Path) -> None:
        """Test loading valid rules file."""
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text("""
rules:
  - name: test-rule
    condition: "platform == 'test'"
    template: test.md.j2
    output_path: test.md
    context:
      key: value
    enabled: true
""")
        renderer = ConfigDrivenRenderer()
        rules = renderer.load_rules(rules_file)
        assert len(rules) == 1
        assert rules[0].name == "test-rule"
        assert rules[0].condition == "platform == 'test'"
        assert rules[0].context_vars == {"key": "value"}

    def test_evaluate_condition_empty(self) -> None:
        """Test evaluating empty condition."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        result = renderer._evaluate_condition("", manifest)
        assert result is True

    def test_evaluate_condition_valid(self) -> None:
        """Test evaluating valid condition."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        result = renderer._evaluate_condition("platform == 'claude-code'", manifest)
        assert result is True

    def test_evaluate_condition_invalid(self) -> None:
        """Test evaluating invalid condition."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "opencode"
        result = renderer._evaluate_condition("platform == 'claude-code'", manifest)
        assert result is False

    def test_evaluate_condition_error(self) -> None:
        """Test evaluating condition that raises error."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        # Invalid Python expression
        result = renderer._evaluate_condition("invalid syntax !!!", manifest)
        assert result is False  # Should return False on error

    def test_get_default_rules_claude_code(self) -> None:
        """Test getting default rules for Claude Code."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"

        rules = renderer._get_default_rules(manifest)
        assert len(rules) == 2
        assert rules[0].name == "claude-md"
        assert rules[1].name == "settings-json"

    def test_get_default_rules_opencode(self) -> None:
        """Test getting default rules for OpenCode."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "opencode"

        rules = renderer._get_default_rules(manifest)
        assert len(rules) == 1
        assert rules[0].name == "config-yaml"

    def test_get_default_rules_unknown_platform(self) -> None:
        """Test getting default rules for unknown platform."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "unknown"

        rules = renderer._get_default_rules(manifest)
        assert len(rules) == 0

    def test_render_with_rules_no_rules(self) -> None:
        """Test rendering with no rules."""
        renderer = ConfigDrivenRenderer()
        renderer._rules = []
        manifest = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = renderer.render_with_rules(manifest, Path(tmpdir))
            assert result["success"]
            assert len(result["files_created"]) == 0
            assert len(result["rules_applied"]) == 0

    def test_render_with_rules_disabled_rule(self) -> None:
        """Test that disabled rules are not applied."""
        renderer = ConfigDrivenRenderer()
        renderer._rules = [
            RenderRule(
                name="disabled-rule",
                condition="",
                template="test.md.j2",
                output_path="test.md",
                context_vars={},
                enabled=False,
            )
        ]
        manifest = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = renderer.render_with_rules(manifest, Path(tmpdir))
            assert result["success"]
            assert len(result["rules_applied"]) == 0

    def test_render_with_rules_condition_mismatch(self) -> None:
        """Test that rules with mismatched conditions are not applied."""
        renderer = ConfigDrivenRenderer()
        from ruamel.yaml import YAML

        with tempfile.TemporaryDirectory() as tmpdir:
            rules_file = Path(tmpdir) / "rules.yaml"
            rules_config = {
                "rules": [
                    {
                        "name": "mismatched-rule",
                        "condition": "platform == 'other-platform'",
                        "template": "test.md.j2",
                        "output_path": "test.md",
                        "context": {},
                        "enabled": True,
                    }
                ]
            }
            yaml = YAML()
            with rules_file.open("w") as f:
                yaml.dump(rules_config, f)

            manifest = MagicMock()
            manifest.metadata.platform = "claude-code"

            result = renderer.render_with_rules(manifest, Path(tmpdir), rules_config=rules_file)
            assert result["success"]
            assert len(result["rules_applied"]) == 0

    def test_should_generate_file_no_conditions(self) -> None:
        """Test file generation check with no conditions."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        file_spec = {"path": "test.md", "enabled": True}

        result = renderer._should_generate_file(file_spec, manifest)
        assert result is True

    def test_should_generate_file_with_conditions_match(self) -> None:
        """Test file generation check with matching conditions."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        file_spec = {
            "path": "test.md",
            "enabled": True,
            "conditions": {"platform": "claude-code"},
        }

        result = renderer._should_generate_file(file_spec, manifest)
        assert result is True

    def test_should_generate_file_with_conditions_mismatch(self) -> None:
        """Test file generation check with mismatched conditions."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "opencode"
        file_spec = {
            "path": "test.md",
            "enabled": True,
            "conditions": {"platform": "claude-code"},
        }

        result = renderer._should_generate_file(file_spec, manifest)
        assert result is False

    def test_should_generate_file_disabled(self) -> None:
        """Test file generation check for disabled file."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        file_spec = {"path": "test.md", "enabled": False}

        result = renderer._should_generate_file(file_spec, manifest)
        assert result is False

    def test_render_file_content_static(self) -> None:
        """Test rendering file content with static content."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        file_spec = {"content": "Static content"}

        result = renderer._render_file_content(file_spec, manifest)
        assert result == "Static content"

    def test_render_file_content_empty_spec(self) -> None:
        """Test rendering file content with empty spec."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        file_spec = {}

        result = renderer._render_file_content(file_spec, manifest)
        assert result == ""

    def test_render_dynamic_config_empty_spec(self) -> None:
        """Test rendering dynamic config with empty spec."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = renderer.render_dynamic_config(manifest, {}, Path(tmpdir))
            assert result["success"]
            assert len(result["files_created"]) == 0

    def test_render_dynamic_config_with_files(self) -> None:
        """Test rendering dynamic config with files."""
        renderer = ConfigDrivenRenderer()
        manifest = MagicMock()
        config_spec = {
            "files": [
                {
                    "path": "test.txt",
                    "enabled": True,
                    "content": "Test content",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = renderer.render_dynamic_config(manifest, config_spec, Path(tmpdir))
            assert result["success"]
            assert len(result["files_created"]) == 1
            assert (Path(tmpdir) / "test.txt").exists()
            assert (Path(tmpdir) / "test.txt").read_text() == "Test content"
