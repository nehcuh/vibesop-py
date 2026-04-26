"""Tests for multi-intent detection."""

from __future__ import annotations

from vibesop.core.models import RoutingLayer, RoutingResult, SkillRoute
from vibesop.core.orchestration.multi_intent_detector import MultiIntentDetector


class TestMultiIntentDetector:
    """Test multi-intent detection heuristics."""

    def test_short_query_rejected(self) -> None:
        detector = MultiIntentDetector()
        result = RoutingResult(query="review code")
        assert not detector.should_decompose("review code", result)

    def test_conjunction_query_accepted(self) -> None:
        detector = MultiIntentDetector(min_query_length=10)
        query = "分析并优化代码中的性能问题"
        result = RoutingResult(query=query)
        assert detector.should_decompose(query, result)

    def test_low_confidence_with_strong_alternatives(self) -> None:
        detector = MultiIntentDetector()
        result = RoutingResult(
            primary=SkillRoute(skill_id="review", confidence=0.5, layer=RoutingLayer.KEYWORD),
            alternatives=[
                SkillRoute(skill_id="architect", confidence=0.65, layer=RoutingLayer.AI_TRIAGE),
                SkillRoute(skill_id="optimize", confidence=0.62, layer=RoutingLayer.AI_TRIAGE),
            ],
        )
        assert detector.should_decompose("help me with this project", result)

    def test_high_confidence_single_skill_rejected(self) -> None:
        detector = MultiIntentDetector()
        result = RoutingResult(
            primary=SkillRoute(skill_id="review", confidence=0.95, layer=RoutingLayer.EXPLICIT),
            alternatives=[
                SkillRoute(skill_id="debug", confidence=0.3, layer=RoutingLayer.KEYWORD),
            ],
        )
        assert not detector.should_decompose("review my code", result)

    def test_close_confidence_gap(self) -> None:
        detector = MultiIntentDetector()
        result = RoutingResult(
            primary=SkillRoute(skill_id="review", confidence=0.75, layer=RoutingLayer.AI_TRIAGE),
            alternatives=[
                SkillRoute(skill_id="architect", confidence=0.70, layer=RoutingLayer.AI_TRIAGE),
            ],
        )
        assert detector.should_decompose("analyze and optimize", result)

    def test_english_conjunctions(self) -> None:
        detector = MultiIntentDetector()
        result = RoutingResult()
        assert detector.should_decompose("analyze the code and then optimize it", result)
        assert detector.should_decompose("first review, then refactor", result)

    def test_chinese_conjunctions(self) -> None:
        detector = MultiIntentDetector(min_query_length=10)
        result = RoutingResult()
        assert detector.should_decompose(
            "请帮我分析项目架构然后提出具体的优化建议", result
        )
        assert detector.should_decompose(
            "同时评审代码质量和安全性，找出潜在漏洞", result
        )

    def test_short_query_with_conjunction_single_domain_rejected(self) -> None:
        detector = MultiIntentDetector(min_query_length=10)
        result = RoutingResult()
        assert not detector.should_decompose("分析并测试", result)

    def test_long_query_with_conjunction_multiple_domains_accepted(self) -> None:
        detector = MultiIntentDetector(min_query_length=10)
        result = RoutingResult()
        assert detector.should_decompose("分析项目架构，然后审查代码质量", result)

    def test_long_single_domain_query_rejected(self) -> None:
        detector = MultiIntentDetector(min_query_length=10)
        result = RoutingResult()
        assert not detector.should_decompose("帮我review这段代码", result)

    def test_sequential_markers_multiple_domains_accepted(self) -> None:
        detector = MultiIntentDetector(min_query_length=10)
        result = RoutingResult()
        assert detector.should_decompose("先review代码，再设计优化方案", result)

    def test_llm_confirms_multi_intent(self) -> None:
        """When LLM confirms, multi-intent is detected."""
        detector = MultiIntentDetector(min_query_length=10)

        class MockLLM:
            def call(self, prompt: str, max_tokens: int = 100, temperature: float = 0.1) -> object:
                return type("Response", (), {"content": "YES"})()

        result = RoutingResult(
            primary=SkillRoute(skill_id="test", confidence=0.5, layer=RoutingLayer.KEYWORD),
            alternatives=[
                SkillRoute(skill_id="alt1", confidence=0.5, layer=RoutingLayer.KEYWORD),
            ],
        )
        assert detector.should_decompose(
            "分析项目架构然后给出代码优化建议",
            result,
            llm_client=MockLLM(),
        )

    def test_llm_rejects_false_multi_intent(self) -> None:
        """When LLM says NO, even heuristic-positive queries stay single."""
        detector = MultiIntentDetector(min_query_length=10)

        class MockLLM:
            def call(self, prompt: str, max_tokens: int = 100, temperature: float = 0.1) -> object:
                return type("Response", (), {"content": "NO"})()

        result = RoutingResult(
            primary=SkillRoute(skill_id="test", confidence=0.5, layer=RoutingLayer.KEYWORD),
            alternatives=[
                SkillRoute(skill_id="alt1", confidence=0.5, layer=RoutingLayer.KEYWORD),
            ],
        )
        assert not detector.should_decompose(
            "分析项目架构然后给出代码优化建议",
            result,
            llm_client=MockLLM(),
        )

    def test_llm_unavailable_falls_back_to_heuristic(self) -> None:
        """When LLM raises, trust heuristic to avoid blocking."""
        detector = MultiIntentDetector(min_query_length=10)

        class BrokenLLM:
            def call(self, prompt: str, max_tokens: int = 100, temperature: float = 0.1) -> None:
                raise RuntimeError("LLM unavailable")

        result = RoutingResult(
            primary=SkillRoute(skill_id="test", confidence=0.5, layer=RoutingLayer.KEYWORD),
            alternatives=[
                SkillRoute(skill_id="alt1", confidence=0.5, layer=RoutingLayer.KEYWORD),
            ],
        )
        assert detector.should_decompose(
            "分析项目架构然后给出代码优化建议",
            result,
            llm_client=BrokenLLM(),
        )
