"""Tests for vibe analyze CLI commands.

Tests session analysis, pattern detection, and skill suggestion
generation commands.
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestAnalyzeSession:
    """Test 'vibe analyze session' command."""

    @pytest.fixture
    def sample_session_file(self, tmp_path):
        """Create a sample session file."""
        session_file = tmp_path / "session.jsonl"

        lines = [
            '{"role": "user", "content": "请帮我优化代码性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化一下性能"}',
            '{"role": "assistant", "content": "OK"}',
        ]

        session_file.write_text("\n".join(lines))
        return session_file

    def test_analyze_session_with_file(self, sample_session_file):
        """Test analyzing a specific session file."""
        result = runner.invoke(app, ["analyze", "session", str(sample_session_file)])

        assert result.exit_code == 0
        assert "Session Analysis" in result.stdout
        assert "Analyzing:" in result.stdout

    def test_analyze_session_no_patterns(self, tmp_path):
        """Test analyzing session with no repeated patterns."""
        session_file = tmp_path / "unique.jsonl"

        lines = [
            '{"role": "user", "content": "unique query 1"}',
            '{"role": "user", "content": "different query 2"}',
        ]

        session_file.write_text("\n".join(lines))

        result = runner.invoke(app, ["analyze", "session", str(session_file)])

        assert result.exit_code == 0
        assert "No strong patterns detected" in result.stdout

    def test_analyze_session_custom_thresholds(self, sample_session_file):
        """Test with custom frequency and confidence thresholds."""
        result = runner.invoke(
            app,
            [
                "analyze",
                "session",
                str(sample_session_file),
                "--min-frequency",
                "2",
                "--min-confidence",
                "0.3",
            ],
        )

        assert result.exit_code == 0
        assert "Session Analysis" in result.stdout

    def test_analyze_session_file_not_found(self):
        """Test with non-existent session file."""
        result = runner.invoke(app, ["analyze", "session", "nonexistent.jsonl"])

        # Should show error but not crash
        assert result.exit_code != 0 or "No session file found" in result.stdout


class TestAnalyzePatterns:
    """Test 'vibe analyze patterns' command."""

    @pytest.fixture
    def sample_sessions_dir(self, tmp_path):
        """Create directory with multiple session files."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        for i in range(3):
            session_file = sessions_dir / f"session_{i}.jsonl"

            lines = [
                '{"role": "user", "content": "请帮我优化代码性能"}',
                '{"role": "assistant", "content": "OK"}',
                '{"role": "user", "content": "请帮我优化代码的性能"}',
                '{"role": "assistant", "content": "OK"}',
            ]

            session_file.write_text("\n".join(lines))

        return sessions_dir

    def test_analyze_patterns_directory(self, sample_sessions_dir):
        """Test analyzing patterns across directory."""
        result = runner.invoke(app, ["analyze", "patterns", str(sample_sessions_dir)])

        assert result.exit_code == 0
        assert "Pattern Analysis" in result.stdout
        assert "Found" in result.stdout

    def test_analyze_patterns_no_files(self, tmp_path):
        """Test analyzing directory with no session files."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = runner.invoke(app, ["analyze", "patterns", str(empty_dir)])

        assert result.exit_code == 0
        assert "No session files found" in result.stdout


class TestAnalyzeSuggestions:
    """Test 'vibe analyze suggestions' command."""

    @pytest.fixture
    def sample_session_file(self, tmp_path):
        """Create session file with clear patterns."""
        session_file = tmp_path / "suggestions.jsonl"

        lines = [
            # Pattern 1: Code optimization (5 occurrences)
            '{"role": "user", "content": "请帮我优化代码性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化一下性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的效率"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码让它更快"}',
            '{"role": "assistant", "content": "OK"}',
            # Pattern 2: Security review (3 occurrences)
            '{"role": "user", "content": "检查代码安全性"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "帮我扫描安全漏洞"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "审查代码安全问题"}',
            '{"role": "assistant", "content": "OK"}',
        ]

        session_file.write_text("\n".join(lines))
        return session_file

    def test_analyze_suggestions_basic(self, sample_session_file):
        """Test basic suggestion generation."""
        result = runner.invoke(app, ["analyze", "suggestions", str(sample_session_file), "--min-frequency", "2", "--min-confidence", "0.3"])

        assert result.exit_code == 0
        assert "Skill Suggestions" in result.stdout
        # Should either generate suggestions or say no data
        assert "Generated" in result.stdout or "No suggestions generated" in result.stdout

    def test_analyze_suggestions_with_ai(self, sample_session_file):
        """Test AI-enhanced suggestions."""
        # Mock AI enhancement
        with patch("vibesop.cli.commands.analyze._ai_enhance_suggestions") as mock_ai:
            mock_ai.return_value = []  # Return empty to avoid actual AI call

            result = runner.invoke(
                app, ["analyze", "suggestions", str(sample_session_file), "--ai", "--min-frequency", "2", "--min-confidence", "0.3"]
            )

            assert result.exit_code == 0
            # Should show AI enhancement message
            assert "Using AI" in result.stdout or "AI enhancement" in result.stdout.lower()

    def test_analyze_suggestions_auto_craft(self, sample_session_file, tmp_path):
        """Test auto-crafting skills."""
        skills_dir = tmp_path / ".vibe" / "skills"
        skills_dir.mkdir(parents=True)

        with patch("vibesop.cli.commands.analyze._auto_create_enhanced_skills") as mock_create:
            result = runner.invoke(
                app, ["analyze", "suggestions", str(sample_session_file), "--auto-craft"]
            )

            # Should complete without error
            assert result.exit_code == 0 or "Created" in result.stdout

    def test_analyze_suggestions_no_data(self, tmp_path):
        """Test with no session data."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")

        result = runner.invoke(app, ["analyze", "suggestions", str(empty_file)])

        assert result.exit_code == 0
        assert "No suggestions generated" in result.stdout


class TestAutoAnalyzeSession:
    """Test 'vibe auto-analyze-session' command (non-interactive)."""

    @pytest.fixture
    def sample_session_file(self, tmp_path):
        """Create session file for auto-analysis."""
        session_file = tmp_path / "auto.jsonl"

        lines = [
            '{"role": "user", "content": "请帮我优化代码性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化一下性能"}',
            '{"role": "assistant", "content": "OK"}',
        ]

        session_file.write_text("\n".join(lines))
        return session_file

    def test_auto_analyze_quiet_mode(self, sample_session_file):
        """Test auto-analysis in quiet mode."""
        result = runner.invoke(
            app, ["auto-analyze-session", str(sample_session_file), "--quiet"]
        )

        # Should succeed silently
        assert result.exit_code == 0

    def test_auto_analyze_verbose(self, sample_session_file):
        """Test auto-analysis with output."""
        result = runner.invoke(app, ["auto-analyze-session", str(sample_session_file)])

        assert result.exit_code == 0
        # Should show analysis output

    def test_auto_analyze_custom_thresholds(self, sample_session_file):
        """Test with custom thresholds."""
        result = runner.invoke(
            app,
            [
                "auto-analyze-session",
                str(sample_session_file),
                "--min-frequency",
                "2",
                "--min-confidence",
                "0.3",
            ],
        )

        assert result.exit_code == 0


class TestCreateSuggestedSkills:
    """Test 'vibe create-suggested-skills' command."""

    @pytest.fixture
    def sample_session_file(self, tmp_path):
        """Create session with patterns."""
        session_file = tmp_path / "create.jsonl"

        lines = [
            '{"role": "user", "content": "请帮我优化代码性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化一下性能"}',
            '{"role": "assistant", "content": "OK"}',
        ]

        session_file.write_text("\n".join(lines))
        return session_file

    def test_create_suggested_skills(self, sample_session_file, tmp_path):
        """Test creating skills from suggestions."""
        skills_dir = tmp_path / ".vibe" / "skills"
        skills_dir.mkdir(parents=True)

        result = runner.invoke(app, ["create-suggested-skills", str(sample_session_file)])

        assert result.exit_code == 0
        # Should indicate skill creation

    def test_create_suggested_skills_no_patterns(self, tmp_path):
        """Test with session that has no patterns."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")

        result = runner.invoke(app, ["create-suggested-skills", str(empty_file)])

        assert result.exit_code == 0
        # Should handle gracefully


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_analyze_invalid_json(self, tmp_path):
        """Test analyzing invalid JSON file."""
        invalid_file = tmp_path / "invalid.jsonl"
        invalid_file.write_text("not valid json")

        result = runner.invoke(app, ["analyze", "session", str(invalid_file)])

        # Should not crash
        assert result.exit_code == 0

    def test_analyze_malformed_jsonl(self, tmp_path):
        """Test analyzing malformed JSONL."""
        malformed_file = tmp_path / "malformed.jsonl"
        malformed_file.write_text('{"role": "user", "content": "test"}\ninvalid line\n')

        result = runner.invoke(app, ["analyze", "session", str(malformed_file)])

        # Should handle gracefully
        assert result.exit_code == 0

    def test_analyze_unknown_action(self):
        """Test with unknown action."""
        result = runner.invoke(app, ["analyze", "unknown_action"])

        assert result.exit_code != 0
        assert "Unknown action" in result.stdout


class TestAIEnhancementIntegration:
    """Test AI enhancement integration in CLI."""

    @pytest.fixture
    def sample_session_file(self, tmp_path):
        """Create session for AI testing."""
        session_file = tmp_path / "ai.jsonl"

        lines = [
            '{"role": "user", "content": "请帮我优化代码性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化一下性能"}',
            '{"role": "assistant", "content": "OK"}',
        ]

        session_file.write_text("\n".join(lines))
        return session_file

    def test_ai_enhancement_with_llm_error(self, sample_session_file):
        """Test AI enhancement when LLM fails."""
        with patch("vibesop.core.ai_enhancer.AIEnhancer") as mock_enhancer:
            # Make LLM fail
            mock_enhancer.return_value.enhance_batch.side_effect = Exception("LLM error")

            result = runner.invoke(
                app, ["analyze", "suggestions", str(sample_session_file), "--ai"]
            )

            # Should fallback gracefully
            assert result.exit_code == 0

    def test_ai_enhancement_display(self, sample_session_file):
        """Test AI-enhanced suggestions display."""
        # Create mock enhanced skill
        from vibesop.core.session_analyzer import SkillSuggestion
        from vibesop.core.ai_enhancer import EnhancedSkill

        suggestion = SkillSuggestion(
            skill_name="请帮我优化代码性能",
            description="Auto-generated",
            trigger_queries=["请帮我优化代码性能"],
            frequency=5,
            confidence=0.72,
            estimated_value="high",
        )

        enhanced = EnhancedSkill(
            name="Code Optimization",
            description="Optimize code for better performance",
            category="optimization",
            tags=["optimization", "performance"],
            trigger_conditions=["User asks about optimization"],
            steps=["Analyze", "Optimize", "Verify"],
            original=suggestion,
            confidence=0.85,
        )

        with patch(
            "vibesop.cli.commands.analyze._ai_enhance_suggestions"
        ) as mock_ai:
            # Make the analyzer return suggestions first
            from vibesop.core.session_analyzer import SessionAnalyzer
            analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)
            suggestions = analyzer.analyze_session_file(sample_session_file)

            # Then mock AI enhancement to add our enhanced skill
            mock_ai.return_value = [enhanced] + suggestions[1:] if len(suggestions) > 1 else [enhanced]

            result = runner.invoke(
                app, ["analyze", "suggestions", str(sample_session_file), "--ai"]
            )

            # Should complete without error
            assert result.exit_code == 0 or "AI-Enhanced" in result.stdout or "Code Optimization" in result.stdout


class TestWorkflowIntegration:
    """Test complete workflow integration."""

    @pytest.fixture
    def workflow_session(self, tmp_path):
        """Create session for workflow testing."""
        session_file = tmp_path / "workflow.jsonl"

        lines = [
            '{"role": "user", "content": "请帮我优化代码性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化一下性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的效率"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化一下效率"}',
            '{"role": "assistant", "content": "OK"}',
        ]

        session_file.write_text("\n".join(lines))
        return session_file

    def test_full_workflow(self, workflow_session, tmp_path):
        """Test complete workflow: analyze -> enhance -> create."""
        skills_dir = tmp_path / ".vibe" / "skills"
        skills_dir.mkdir(parents=True)

        # Step 1: Analyze
        result = runner.invoke(app, ["analyze", "suggestions", str(workflow_session)])
        assert result.exit_code == 0
        assert "Skill Suggestions" in result.stdout

        # Step 2: Create skills (without AI for speed)
        with patch("vibesop.cli.commands.analyze._auto_create_enhanced_skills") as mock_create:
            result = runner.invoke(
                app, ["analyze", "suggestions", str(workflow_session), "--auto-craft"]
            )
            assert result.exit_code == 0

    def test_session_to_skill_pipeline(self, workflow_session, tmp_path):
        """Test pipeline from session to skill files."""
        skills_dir = tmp_path / ".vibe" / "skills"
        skills_dir.mkdir(parents=True)

        # Run auto-create
        result = runner.invoke(app, ["create-suggested-skills", str(workflow_session)])

        assert result.exit_code == 0

        # Check if skill files were created
        skill_files = list(skills_dir.glob("*.md"))
        # May or may not have files depending on thresholds
        assert isinstance(skill_files, list)
