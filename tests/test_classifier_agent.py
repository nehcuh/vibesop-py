"""Tests for ClassifierAgent — dynamic workflow pattern selection."""

from __future__ import annotations

import pytest

from vibesop.core.models import ClassifierResult, WorkflowPattern
from vibesop.core.orchestration.classifier import ClassifierAgent
from vibesop.core.orchestration.task_decomposer import SubTask


class TestClassifierAgentRuleClassification:
    """Fast-path keyword-based classification tests."""

    def test_review_query_selects_fan_out(self):
        agent = ClassifierAgent()
        result = agent.classify("review my code for bugs and performance issues")
        assert result.pattern == WorkflowPattern.FAN_OUT
        assert result.confidence >= 0.7

    def test_parallel_keyword_selects_parallel(self):
        agent = ClassifierAgent()
        result = agent.classify("同时优化性能并修复 bug")
        assert result.pattern == WorkflowPattern.PARALLEL
        assert result.confidence >= 0.7

    def test_verify_keyword_selects_adversarial(self):
        agent = ClassifierAgent()
        result = agent.classify("fix the bug and verify the fix")
        assert result.pattern == WorkflowPattern.ADVERSARIAL
        assert result.confidence >= 0.7

    def test_no_keywords_defaults_sequential(self):
        agent = ClassifierAgent()
        result = agent.classify("help me write a function")
        assert result.pattern == WorkflowPattern.SEQUENTIAL
        assert result.confidence < 0.7

    def test_task_type_review_selects_fan_out(self):
        agent = ClassifierAgent()
        sub_tasks = [
            SubTask(intent="review code", query="review code", task_type="review"),
        ]
        result = agent.classify("review my code", sub_tasks)
        assert result.pattern == WorkflowPattern.FAN_OUT

    def test_task_type_debug_selects_adversarial(self):
        agent = ClassifierAgent()
        sub_tasks = [
            SubTask(intent="debug error", query="debug error", task_type="debug"),
        ]
        result = agent.classify("debug this error", sub_tasks)
        assert result.pattern == WorkflowPattern.ADVERSARIAL


class TestClassifierAgentLLMClassification:
    """LLM-based classification tests with mocked client."""

    def test_llm_classifies_fan_out(self):
        class FakeLLM:
            def call(self, prompt, **kwargs):
                class Response:
                    content = '{"pattern": "fan_out", "confidence": 0.9, "reasoning": "Multiple review angles", "task_type": "review", "complexity": "medium"}'
                return Response()

        agent = ClassifierAgent(llm_client=FakeLLM())
        # Use a query with no rule-path keywords so we get pure LLM result
        result = agent.classify("examine all the details carefully")

        assert result.pattern == WorkflowPattern.FAN_OUT
        assert result.confidence == 0.9
        assert result.task_type == "review"

    def test_llm_invalid_pattern_fallback(self):
        class FakeLLM:
            def call(self, prompt, **kwargs):
                class Response:
                    content = '{"pattern": "invalid_pattern", "confidence": 0.5}'
                return Response()

        agent = ClassifierAgent(llm_client=FakeLLM())
        result = agent.classify("do something")

        assert result.pattern == WorkflowPattern.SEQUENTIAL

    def test_llm_malformed_json_fallback(self):
        class FakeLLM:
            def call(self, prompt, **kwargs):
                class Response:
                    content = "not valid json"
                return Response()

        agent = ClassifierAgent(llm_client=FakeLLM())
        result = agent.classify("do something")

        assert result.pattern == WorkflowPattern.SEQUENTIAL

    def test_blend_agreement_boosts_confidence(self):
        class FakeLLM:
            def call(self, prompt, **kwargs):
                class Response:
                    content = '{"pattern": "fan_out", "confidence": 0.8, "reasoning": "LLM agrees"}'
                return Response()

        agent = ClassifierAgent(llm_client=FakeLLM())
        # Query has "review" keyword (rule → fan_out), LLM also says fan_out
        result = agent.classify("review the code")

        assert result.pattern == WorkflowPattern.FAN_OUT
        # Blended confidence should be boosted above both individual scores
        assert result.confidence > 0.8

    def test_blend_disagreement_prefers_higher_confidence(self):
        class FakeLLM:
            def call(self, prompt, **kwargs):
                class Response:
                    content = '{"pattern": "adversarial", "confidence": 0.96, "reasoning": "LLM strongly disagrees"}'
                return Response()

        agent = ClassifierAgent(llm_client=FakeLLM())
        # Query has "review" keyword (rule → fan_out, confidence ~0.8), but LLM says adversarial with high confidence
        result = agent.classify("review the code")

        # LLM confidence (0.96) > rule confidence (~0.8) + 0.15 threshold
        assert result.pattern == WorkflowPattern.ADVERSARIAL


class TestClassifierResultModel:
    """ClassifierResult Pydantic model tests."""

    def test_default_values(self):
        result = ClassifierResult()
        assert result.pattern == WorkflowPattern.SEQUENTIAL
        assert result.confidence == 0.0
        assert result.reasoning == ""
        assert result.task_type == ""
        assert result.complexity == "simple"

    def test_to_dict(self):
        result = ClassifierResult(
            pattern=WorkflowPattern.FAN_OUT,
            confidence=0.85,
            reasoning="test",
            task_type="review",
            complexity="complex",
        )
        d = result.to_dict()
        assert d["pattern"] == "fan_out"
        assert d["confidence"] == 0.85
        assert d["reasoning"] == "test"
        assert d["task_type"] == "review"
        assert d["complexity"] == "complex"

    def test_confidence_bounds(self):
        with pytest.raises(ValueError):
            ClassifierResult(confidence=1.5)
        with pytest.raises(ValueError):
            ClassifierResult(confidence=-0.1)
