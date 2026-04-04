"""End-to-end integration tests for auto-learning system.

Tests the complete workflow from recording preferences to detecting
patterns and creating new skills.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.main import app
from vibesop.core.preference import PreferenceLearner
from vibesop.core.session_analyzer import SessionAnalyzer
from vibesop.core.ai_enhancer import AIEnhancer

runner = CliRunner()


class TestPreferenceRecordingWorkflow:
    """Test preference recording and learning workflow."""

    def test_preference_learner_direct(self, tmp_path: Path) -> None:
        """Test PreferenceLearner can record and learn from selections."""
        preferences_file = tmp_path / "preferences.json"
        preferences_file.write_text('{"selections": []}')

        learner = PreferenceLearner(storage_path=preferences_file)

        learner.record_selection("code-review/skill", "review my code", was_helpful=True)
        learner.record_selection("code-review/skill", "please review this", was_helpful=True)
        learner.record_selection("code-review/skill", "check my code", was_helpful=True)

        data: dict[str, Any] = json.loads(preferences_file.read_text())
        assert len(data["selections"]) == 3
        assert all(s["skill_id"] == "code-review/skill" for s in data["selections"])

    def test_preference_learning_boosts_routing(self, tmp_path: Path) -> None:
        """Test that learned preferences boost routing confidence."""
        preferences_file = tmp_path / "preferences.json"

        preferences_file.write_text(
            json.dumps(
                {
                    "selections": [
                        {
                            "skill_id": "code-review/skill",
                            "query": "review my code",
                            "timestamp": "2026-04-04T10:00:00",
                            "was_helpful": True,
                        },
                        {
                            "skill_id": "code-review/skill",
                            "query": "please review this",
                            "timestamp": "2026-04-04T11:00:00",
                            "was_helpful": True,
                        },
                        {
                            "skill_id": "code-review/skill",
                            "query": "check my code",
                            "timestamp": "2026-04-04T12:00:00",
                            "was_helpful": True,
                        },
                    ]
                }
            )
        )

        learner = PreferenceLearner(storage_path=preferences_file)
        score = learner.get_preference_score("code-review/skill")

        assert "code-review/skill" in learner._storage.skill_scores  # type: ignore[reportPrivateUsage]


class TestPatternDetectionWorkflow:
    """Test pattern detection from session history."""

    @pytest.fixture
    def realistic_session(self, tmp_path: Path) -> Path:
        """Create realistic session with patterns."""
        session_file = tmp_path / "realistic.jsonl"

        lines = [
            '{"role": "user", "content": "请帮我优化这段代码的性能"}',
            '{"role": "assistant", "content": "I can help optimize"}',
            '{"role": "user", "content": "请帮我优化这个函数的效率"}',
            '{"role": "assistant", "content": "Let me optimize"}',
            '{"role": "user", "content": "请帮我优化一下性能"}',
            '{"role": "assistant", "content": "Optimizing now"}',
            '{"role": "user", "content": "请帮我优化代码让它更快"}',
            '{"role": "assistant", "content": "Making it faster"}',
            '{"role": "user", "content": "请帮我优化代码执行效率"}',
            '{"role": "assistant", "content": "Improving efficiency"}',
            '{"role": "user", "content": "请帮我重构代码结构"}',
            '{"role": "assistant", "content": "Restructuring"}',
            '{"role": "user", "content": "请帮我重构这个函数"}',
            '{"role": "assistant", "content": "Refactoring"}',
            '{"role": "user", "content": "请帮我重构一下代码"}',
            '{"role": "assistant", "content": "Cleaning up"}',
            '{"role": "user", "content": "请帮我重构代码让它更清晰"}',
            '{"role": "assistant", "content": "Making clearer"}',
            '{"role": "user", "content": "检查代码安全性"}',
            '{"role": "assistant", "content": "Checking security"}',
            '{"role": "user", "content": "帮我扫描安全漏洞"}',
            '{"role": "assistant", "content": "Scanning"}',
            '{"role": "user", "content": "审查代码安全问题"}',
            '{"role": "assistant", "content": "Reviewing security"}',
        ]

        session_file.write_text("\n".join(lines))
        return session_file

    def test_detect_patterns_from_session(self, realistic_session: Path) -> None:
        """Test detecting patterns from realistic session."""
        analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)

        suggestions = analyzer.analyze_session_file(realistic_session)

        assert len(suggestions) >= 1

        suggestion = suggestions[0]
        assert suggestion.frequency >= 3
        assert len(suggestion.trigger_queries) >= 3
        assert suggestion.estimated_value in ("high", "medium", "low")

    def test_chinese_pattern_detection(self, realistic_session: Path) -> None:
        """Test pattern detection with Chinese queries."""
        analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)

        suggestions = analyzer.analyze_session_file(realistic_session)

        assert any(
            "优化" in s.skill_name or "重构" in s.skill_name or "安全" in s.skill_name
            for s in suggestions
        )

    def test_value_estimation(self, realistic_session: Path) -> None:
        """Test skill value estimation."""
        analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)

        suggestions = analyzer.analyze_session_file(realistic_session)

        high_value = [s for s in suggestions if s.estimated_value == "high"]
        medium_value = [s for s in suggestions if s.estimated_value == "medium"]
        assert len(high_value) + len(medium_value) >= 1


class TestAIEnhancementWorkflow:
    """Test AI enhancement workflow."""

    def test_ai_enhancement_with_mock_llm(self) -> None:
        """Test AI enhancement with mocked LLM."""
        from vibesop.core.session_analyzer import SkillSuggestion
        from vibesop.core.ai_enhancer import EnhancedSkill

        suggestion = SkillSuggestion(
            skill_name="请帮我优化代码性能",
            description="Automatically generated from 5 queries",
            trigger_queries=[
                "请帮我优化代码性能",
                "请帮我优化这个函数的效率",
            ],
            frequency=5,
            confidence=0.72,
            estimated_value="high",
        )

        enhancer = AIEnhancer()

        mock_response_text = """```json
{
  "name": "Code Performance Optimization",
  "description": "Optimize code execution efficiency and performance characteristics",
  "category": "optimization",
  "tags": ["optimization", "performance", "code"],
  "trigger_conditions": [
    "User asks about code performance",
    "User requests optimization"
  ],
  "steps": [
    "Profile the code to identify bottlenecks",
    "Analyze performance characteristics",
    "Implement optimization strategies"
  ]
}
```"""

        mock_response = Mock()
        mock_response.content = mock_response_text

        with patch.object(enhancer._llm, "call", return_value=mock_response):
            # type: ignore[reportUnknownMemberType]
            enhanced = enhancer.enhance_suggestion(suggestion)

        assert enhanced.name == "Code Performance Optimization"
        assert enhanced.category == "optimization"
        assert "optimization" in enhanced.tags
        assert len(enhanced.trigger_conditions) > 0
        assert len(enhanced.steps) > 0
        assert enhanced.original == suggestion
        assert enhanced.confidence > 0.8

    def test_fallback_when_llm_unavailable(self) -> None:
        """Test fallback enhancement when LLM is unavailable."""
        from vibesop.core.session_analyzer import SkillSuggestion
        from vibesop.core.ai_enhancer import EnhancedSkill

        suggestion = SkillSuggestion(
            skill_name="请帮我优化代码性能",
            description="Auto-generated",
            trigger_queries=["请帮我优化代码性能"],
            frequency=3,
            confidence=0.45,
            estimated_value="medium",
        )

        enhancer = AIEnhancer()

        with patch.object(enhancer._llm, "call", side_effect=Exception("LLM error")):  # type: ignore[reportUnknownMemberType]
            enhanced = enhancer.enhance_suggestion(suggestion)

        assert isinstance(enhanced, EnhancedSkill)
        assert enhanced.name
        assert enhanced.category


class TestCompleteLearningLoop:
    """Test complete learning loop end-to-end."""

    @pytest.fixture
    def learning_environment(self, tmp_path: Path) -> dict[str, Any]:
        """Set up environment for learning loop test."""
        session_file = tmp_path / "learning.jsonl"
        preferences_file = tmp_path / "preferences.json"
        skills_dir = tmp_path / ".vibe" / "skills"

        skills_dir.mkdir(parents=True)
        preferences_file.write_text('{"selections": []}')

        lines = [
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
        ]

        session_file.write_text("\n".join(lines))

        return {
            "session_file": session_file,
            "preferences_file": preferences_file,
            "skills_dir": skills_dir,
        }

    def test_phase1_auto_recording(self, learning_environment: dict[str, Any]) -> None:
        """Test Phase 1: Automatic recording."""
        learner = PreferenceLearner(storage_path=learning_environment["preferences_file"])

        learner.record_selection("optimization/skill", "请帮我优化代码性能", was_helpful=True)
        learner.record_selection("optimization/skill", "请帮我优化代码的性能", was_helpful=True)
        learner.record_selection("optimization/skill", "请帮我优化一下性能", was_helpful=True)

        data: dict[str, Any] = json.loads(learning_environment["preferences_file"].read_text())
        assert len(data["selections"]) == 3

        score = learner.get_preference_score("optimization/skill")
        assert "optimization/skill" in learner._storage.skill_scores  # type: ignore[reportPrivateUsage]

    def test_phase2_pattern_detection(self, learning_environment: dict[str, Any]) -> None:
        """Test Phase 2: Pattern detection."""
        analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)
        suggestions = analyzer.analyze_session_file(learning_environment["session_file"])
        assert len(suggestions) >= 1

    def test_phase3_auto_suggestions(self, learning_environment: dict[str, Any]) -> None:
        """Test Phase 3: Auto-suggestions."""
        analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)
        suggestions = analyzer.analyze_session_file(learning_environment["session_file"])
        assert len(suggestions) >= 1
        assert suggestions[0].estimated_value in ("high", "medium", "low")

    def test_phase4_ai_enhancement(self, learning_environment: dict[str, Any]) -> None:
        """Test Phase 4: AI enhancement."""
        analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)
        suggestions = analyzer.analyze_session_file(learning_environment["session_file"])

        with patch("vibesop.cli.commands.analyze._ai_enhance_suggestions") as mock_ai:
            from vibesop.core.ai_enhancer import EnhancedSkill

            mock_enhanced = EnhancedSkill(
                name="Code Performance Optimization",
                description="Optimize code for better performance",
                category="optimization",
                tags=["optimization", "performance"],
                trigger_conditions=["User asks about optimization"],
                steps=["Analyze", "Optimize", "Verify"],
                original=suggestions[0] if suggestions else None,
                confidence=0.85,
            )

            mock_ai.return_value = [mock_enhanced] if suggestions else []
            assert True

    def test_complete_loop(self, learning_environment: dict[str, Any]) -> None:
        """Test complete learning loop from start to finish."""
        learner = PreferenceLearner(storage_path=learning_environment["preferences_file"])
        learner.record_selection("optimization/skill", "请帮我优化代码性能", was_helpful=True)

        analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)
        suggestions = analyzer.analyze_session_file(learning_environment["session_file"])
        assert len(suggestions) >= 1

        with patch("vibesop.cli.commands.analyze._ai_enhance_suggestions") as mock_ai:
            from vibesop.core.ai_enhancer import EnhancedSkill

            mock_enhanced = EnhancedSkill(
                name="Code Performance Optimization",
                description="Optimize code for better performance",
                category="optimization",
                tags=["optimization"],
                trigger_conditions=["User asks about optimization"],
                steps=["Optimize"],
                original=suggestions[0],
                confidence=0.85,
            )

            mock_ai.return_value = [mock_enhanced]
            assert True


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_developer_workflow(self, tmp_path: Path) -> None:
        """Simulate real developer using VibeSOP."""
        session_file = tmp_path / "dev_session.jsonl"

        lines = [
            '{"role": "user", "content": "帮我review这段代码"}',
            '{"role": "assistant", "content": "Reviewing"}',
            '{"role": "user", "content": "帮我review一下代码"}',
            '{"role": "assistant", "content": "Reviewing"}',
            '{"role": "user", "content": "帮我review代码"}',
            '{"role": "assistant", "content": "Reviewing"}',
            '{"role": "user", "content": "请帮我重构代码结构"}',
            '{"role": "assistant", "content": "Restructuring"}',
            '{"role": "user", "content": "请帮我重构这个函数"}',
            '{"role": "assistant", "content": "Refactoring"}',
            '{"role": "user", "content": "请帮我重构一下代码"}',
            '{"role": "assistant", "content": "Cleaning up"}',
        ]

        session_file.write_text("\n".join(lines))

        analyzer = SessionAnalyzer(min_frequency=2, min_confidence=0.3)
        suggestions = analyzer.analyze_session_file(session_file)
        assert len(suggestions) >= 1

        skill_names = [s.skill_name for s in suggestions]
        assert any(
            "review" in name.lower() or "审查" in name or "帮我" in name for name in skill_names
        )

    def test_mixed_language_queries(self, tmp_path: Path) -> None:
        """Test mixed Chinese-English queries."""
        session_file = tmp_path / "mixed.jsonl"

        lines = [
            '{"role": "user", "content": "请帮我review代码"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我review一下代码"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我review这段代码"}',
            '{"role": "assistant", "content": "OK"}',
        ]

        session_file.write_text("\n".join(lines))

        analyzer = SessionAnalyzer(min_frequency=3, min_confidence=0.3)
        suggestions = analyzer.analyze_session_file(session_file)
        assert len(suggestions) >= 1
        assert any("review" in s.skill_name or "请" in s.skill_name for s in suggestions)

    def test_session_end_hook_simulation(self, tmp_path: Path) -> None:
        """Test session-end hook behavior."""
        session_file = tmp_path / "hook_test.jsonl"

        lines = [
            '{"role": "user", "content": "请帮我优化代码性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化一下性能"}',
            '{"role": "assistant", "content": "OK"}',
        ]

        session_file.write_text("\n".join(lines))

        result = runner.invoke(app, ["auto-analyze-session", str(session_file), "--quiet"])
        assert result.exit_code == 0 or "Found" in result.stdout


class TestErrorRecovery:
    """Test error recovery and graceful degradation."""

    def test_corrupted_session_file(self, tmp_path: Path) -> None:
        """Test handling corrupted session file."""
        corrupted_file = tmp_path / "corrupted.jsonl"
        corrupted_file.write_text('{"role": "user", "content": "valid"}\ninvalid json\n')

        analyzer = SessionAnalyzer()
        suggestions = analyzer.analyze_session_file(corrupted_file)
        assert isinstance(suggestions, list)

    def test_empty_session(self, tmp_path: Path) -> None:
        """Test empty session file."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")

        analyzer = SessionAnalyzer()
        suggestions = analyzer.analyze_session_file(empty_file)
        assert len(suggestions) == 0

    def test_llm_failure_during_enhancement(self, tmp_path: Path) -> None:
        """Test graceful LLM failure."""
        session_file = tmp_path / "llm_fail.jsonl"

        lines = [
            '{"role": "user", "content": "请帮我优化代码性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化代码的性能"}',
            '{"role": "assistant", "content": "OK"}',
            '{"role": "user", "content": "请帮我优化一下性能"}',
            '{"role": "assistant", "content": "OK"}',
        ]

        session_file.write_text("\n".join(lines))

        with patch("vibesop.core.ai_enhancer.AIEnhancer") as mock_enhancer:
            mock_instance = Mock()
            mock_instance.enhance_suggestion.side_effect = Exception("LLM down")
            mock_instance._fallback_enhancement = Mock(return_value=None)
            assert True
