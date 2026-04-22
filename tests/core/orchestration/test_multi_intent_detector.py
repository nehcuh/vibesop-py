"""Tests for multi-intent detection."""

from __future__ import annotations

import pytest

from vibesop.core.models import RoutingResult, SkillRoute, RoutingLayer
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
