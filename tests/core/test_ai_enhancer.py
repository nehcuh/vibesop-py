"""Tests for AIEnhancer - AI-powered skill enhancement.

Tests AI enhancement functionality including fallback behavior
and edge cases.
"""

from unittest.mock import Mock, patch

import pytest

from vibesop.core.ai_enhancer import AIEnhancer, EnhancedSkill
from vibesop.core.session_analyzer import SkillSuggestion


class TestAIEnhancer:
    """Test AIEnhancer class."""

    def test_initialization(self):
        """Test enhancer initialization."""
        enhancer = AIEnhancer()
        assert enhancer._llm is not None

    @pytest.fixture
    def sample_suggestion(self):
        """Create a sample skill suggestion."""
        return SkillSuggestion(
            skill_name="请帮我优化这段代码的性能",
            description="Automatically generated from 3 queries",
            trigger_queries=[
                "请帮我优化这段代码的性能",
                "请帮我优化这个函数的效率",
                "请帮我优化一下性能",
            ],
            frequency=3,
            confidence=0.45,
            estimated_value="medium",
        )

    def test_enhance_suggestion_with_llm(self, sample_suggestion):
        """Test enhancing suggestion with LLM."""
        enhancer = AIEnhancer()

        # Mock LLM response
        mock_response_text = """```json
{
  "name": "Code Performance Optimization",
  "description": "Optimize code execution efficiency and performance",
  "category": "optimization",
  "tags": ["optimization", "performance", "code"],
  "trigger_conditions": [
    "User asks about code performance",
    "User requests optimization"
  ],
  "steps": [
    "Profile the code",
    "Identify bottlenecks",
    "Implement optimizations"
  ]
}
```"""

        mock_llm_response = Mock()
        mock_llm_response.content = mock_response_text

        with patch.object(enhancer._llm, "call", return_value=mock_llm_response):
            enhanced = enhancer.enhance_suggestion(sample_suggestion)

        # Verify enhancement
        assert isinstance(enhanced, EnhancedSkill)
        assert enhanced.name == "Code Performance Optimization"
        assert enhanced.category == "optimization"
        assert "optimization" in enhanced.tags
        assert len(enhanced.trigger_conditions) > 0
        assert len(enhanced.steps) > 0
        assert enhanced.original == sample_suggestion

    def test_enhance_suggestion_llm_error(self, sample_suggestion):
        """Test fallback when LLM fails."""
        enhancer = AIEnhancer()

        # Mock LLM failure
        with patch.object(enhancer._llm, "call", side_effect=Exception("LLM error")):
            enhanced = enhancer.enhance_suggestion(sample_suggestion)

        # Should fallback to basic enhancement
        assert isinstance(enhanced, EnhancedSkill)
        # Should have improved name
        assert "优化" in enhanced.name or "performance" in enhanced.name.lower()
        # Should have category
        assert enhanced.category in ["development", "testing", "debugging",
                                        "review", "documentation", "deployment",
                                        "security", "optimization"]

    def test_enhance_batch(self, sample_suggestion):
        """Test batch enhancement."""
        enhancer = AIEnhancer()

        suggestions = [sample_suggestion] * 3

        # Mock successful enhancement
        mock_response_text = """```json
{
  "name": "Test Skill",
  "description": "Test description",
  "category": "development",
  "tags": ["test"],
  "trigger_conditions": ["Test condition"],
  "steps": ["Step 1", "Step 2", "Step 3"]
}
```"""

        mock_llm_response = Mock()
        mock_llm_response.content = mock_response_text

        with patch.object(enhancer._llm, "call", return_value=mock_llm_response):
            enhanced_list = enhancer.enhance_batch(suggestions)

        # Should enhance all suggestions
        assert len(enhanced_list) == 3
        for enhanced in enhanced_list:
            assert isinstance(enhanced, EnhancedSkill)

    def test_enhance_batch_with_errors(self, sample_suggestion):
        """Test batch enhancement with some errors."""
        enhancer = AIEnhancer()

        suggestions = [sample_suggestion] * 3

        # Mock: first succeeds, second fails, third succeeds
        call_count = [0]

        def mock_call(prompt, max_tokens=None, temperature=None):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("LLM error")

            mock_response = Mock()
            mock_response.content = """```json
{
  "name": "Test Skill",
  "description": "Test",
  "category": "development",
  "tags": [],
  "trigger_conditions": [],
  "steps": []
}
```"""
            return mock_response

        with patch.object(enhancer._llm, "call", side_effect=mock_call):
            enhanced_list = enhancer.enhance_batch(suggestions)

        # Should handle errors gracefully
        assert len(enhanced_list) == 3
        # All should be EnhancedSkill instances (fallback or successful)
        for enhanced in enhanced_list:
            assert isinstance(enhanced, EnhancedSkill)


class TestFallbackEnhancement:
    """Test fallback enhancement without AI."""

    @pytest.fixture
    def sample_suggestion(self):
        """Create a sample skill suggestion."""
        return SkillSuggestion(
            skill_name="请帮我优化这段代码的性能",
            description="Automatically generated from 3 queries",
            trigger_queries=[
                "请帮我优化这段代码的性能",
                "请帮我优化这个函数的效率",
            ],
            frequency=3,
            confidence=0.45,
            estimated_value="medium",
        )

    def test_improve_name(self, sample_suggestion):
        """Test name improvement."""
        enhancer = AIEnhancer()
        improved = enhancer._improve_name(sample_suggestion.skill_name)

        # Should remove common prefixes
        assert not improved.startswith("请帮我")
        # Should be capitalized
        assert improved[0].isupper() or improved[0].isalnum()

    def test_improve_description(self, sample_suggestion):
        """Test description improvement."""
        enhancer = AIEnhancer()
        improved = enhancer._improve_description(sample_suggestion)

        # Should not start with "Handle", "Help", etc.
        assert not improved.startswith(("Handle", "Help", "Assist"))

    def test_detect_category(self):
        """Test category detection."""
        enhancer = AIEnhancer()

        # Test various queries
        assert enhancer._detect_category(["优化代码", "提高性能"]) == "optimization"
        assert enhancer._detect_category(["测试代码", "验证功能"]) == "testing"
        assert enhancer._detect_category(["调试错误", "修复bug"]) == "debugging"
        assert enhancer._detect_category(["审查代码", "检查质量"]) == "review"

    def test_extract_action(self):
        """Test action extraction."""
        enhancer = AIEnhancer()

        assert enhancer._extract_action("请帮我优化代码") == "Optimize"
        assert enhancer._extract_action("帮我测试这个") == "Test"
        assert enhancer._extract_action("检查代码安全性") == "Check"

    def test_extract_tags(self):
        """Test tag extraction."""
        enhancer = AIEnhancer()

        # Extract tags from queries
        tags = enhancer._extract_tags([
            "Optimize Python code performance",
            "Review JavaScript code",
            "Test API endpoints",
        ])

        # Should extract capitalized words and technical terms
        assert isinstance(tags, list)
        assert len(tags) <= 5  # Max 5 tags


class TestConfidenceCalculation:
    """Test confidence score calculation."""

    def test_perfect_confidence(self):
        """Test perfect confidence score."""
        enhancer = AIEnhancer()

        data = {
            "name": "Test Skill Name",
            "description": "This is a comprehensive description",
            "category": "development",
            "tags": ["tag1", "tag2", "tag3"],
            "trigger_conditions": ["Condition 1", "Condition 2"],
            "steps": ["Step 1", "Step 2", "Step 3"],
        }

        confidence = enhancer._calculate_confidence(data)

        # Should have high confidence
        assert confidence >= 0.9

    def test_low_confidence(self):
        """Test low confidence score."""
        enhancer = AIEnhancer()

        data = {
            "name": "TS",  # Too short
            "description": "Short",  # Too short
            "category": "invalid",  # Invalid category
            "tags": [],  # Empty
            "trigger_conditions": [],  # Empty
            "steps": [],  # Empty
        }

        confidence = enhancer._calculate_confidence(data)

        # Should have low confidence
        assert confidence < 0.5


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_trigger_queries(self):
        """Test enhancement with empty trigger queries."""
        suggestion = SkillSuggestion(
            skill_name="test",
            description="test",
            trigger_queries=[],
            frequency=1,
            confidence=0.1,
            estimated_value="low",
        )

        enhancer = AIEnhancer()
        enhanced = enhancer._fallback_enhancement(suggestion)

        # Should still create EnhancedSkill
        assert isinstance(enhanced, EnhancedSkill)
        assert enhanced.name == "Test"

    def test_invalid_json_response(self):
        """Test handling invalid JSON from LLM."""
        enhancer = AIEnhancer()

        suggestion = SkillSuggestion(
            skill_name="test",
            description="test",
            trigger_queries=["test query"],
            frequency=1,
            confidence=0.5,
            estimated_value="low",
        )

        # Mock invalid JSON response
        mock_response = Mock()
        mock_response.content = "Invalid JSON"

        with patch.object(enhancer._llm, "call", return_value=mock_response):
            enhanced = enhancer.enhance_suggestion(suggestion)

        # Should fallback to basic enhancement
        assert isinstance(enhanced, EnhancedSkill)

    def test_malformed_json_response(self):
        """Test handling malformed JSON from LLM."""
        enhancer = AIEnhancer()

        suggestion = SkillSuggestion(
            skill_name="test",
            description="test",
            trigger_queries=["test query"],
            frequency=1,
            confidence=0.5,
            estimated_value="low",
        )

        # Mock partial JSON
        mock_response = Mock()
        mock_response.content = '{"name": "Partial"'

        with patch.object(enhancer._llm, "call", return_value=mock_response):
            enhanced = enhancer.enhance_suggestion(suggestion)

        # Should handle gracefully
        assert isinstance(enhanced, EnhancedSkill)


class TestIntegration:
    """Integration tests for AI enhancement."""

    def test_end_to_end_enhancement(self):
        """Test complete enhancement workflow."""
        # Create realistic suggestion
        suggestion = SkillSuggestion(
            skill_name="请帮我重构代码结构",
            description="Automatically generated skill",
            trigger_queries=[
                "请帮我重构代码结构",
                "请帮我重构这个函数",
                "请帮我重构一下代码",
                "请帮我重构代码让它更清晰",
                "请帮我重构这个类",
            ],
            frequency=5,
            confidence=0.72,
            estimated_value="high",
        )

        enhancer = AIEnhancer()

        # Mock LLM response
        mock_response_text = """```json
{
  "name": "Code Refactoring",
  "description": "Restructure code to improve clarity, maintainability, and organization",
  "category": "development",
  "tags": ["refactoring", "code-structure", "maintainability"],
  "trigger_conditions": [
    "User requests code restructuring",
    "User asks to improve code organization"
  ],
  "steps": [
    "Analyze current code structure",
    "Identify refactoring opportunities",
    "Apply refactoring patterns",
    "Verify improvements"
  ]
}
```"""

        mock_response = Mock()
        mock_response.content = mock_response_text

        with patch.object(enhancer._llm, "call", return_value=mock_response):
            enhanced = enhancer.enhance_suggestion(suggestion)

        # Verify complete enhancement
        assert enhanced.name == "Code Refactoring"
        assert "clarity" in enhanced.description.lower()
        assert enhanced.category == "development"
        assert "refactoring" in enhanced.tags
        assert len(enhanced.trigger_conditions) >= 2
        assert len(enhanced.steps) == 4
        assert enhanced.confidence > 0.8  # High quality

    def test_llm_unavailable_scenario(self):
        """Test behavior when LLM is not configured."""
        suggestion = SkillSuggestion(
            skill_name="test",
            description="test",
            trigger_queries=["test query"],
            frequency=1,
            confidence=0.5,
            estimated_value="low",
        )

        # Mock LLM initialization error
        with patch('vibesop.core.ai_enhancer.create_from_env', side_effect=ImportError):
            # AIEnhancer.__init__ will fail, which is expected
            with pytest.raises(ImportError):
                enhancer = AIEnhancer()

        # Test that fallback enhancement method works
        # Create a real AIEnhancer (outside the mock context)
        enhancer = AIEnhancer()
        enhanced = enhancer._fallback_enhancement(suggestion)

        assert isinstance(enhanced, EnhancedSkill)
        assert enhanced.category  # Should have category
        assert isinstance(enhanced.tags, list)  # Should have tags (even if empty)
