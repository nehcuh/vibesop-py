"""Tests for TaskDecomposer."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from vibesop.core.orchestration.task_decomposer import SubTask, TaskDecomposer


class TestTaskDecomposer:
    """Test task decomposition with LLM and fallback."""

    def test_no_llm_fallback_single_task(self) -> None:
        """Without LLM, short simple query returns single task."""
        decomposer = TaskDecomposer(llm_client=None)
        result = decomposer.decompose("debug this code")

        assert len(result) == 1
        # v5.1: intent-aware fallback detects "debug" keyword
        assert result[0].intent in ("single task", "debug_error")
        assert result[0].query == "debug this code"

    def test_no_llm_fallback_multi_task(self) -> None:
        """Without LLM, query with conjunctions splits into sub-tasks."""
        decomposer = TaskDecomposer(llm_client=None)
        result = decomposer.decompose("分析系统架构并优化数据库性能")

        assert len(result) >= 2
        # Should split on "并"
        queries = [st.query for st in result]
        assert any("分析" in q for q in queries)
        assert any("优化" in q for q in queries)

    def test_llm_decompose_success(self) -> None:
        """LLM returns structured JSON — parsed correctly."""
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content='{"tasks": [{"intent": "analyze", "query": "analyze architecture"}, {"intent": "optimize", "query": "optimize performance"}]}'
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("analyze architecture and optimize performance")

        assert len(result) == 2
        assert result[0].intent == "analyze"
        assert result[1].intent == "optimize"

    def test_llm_decompose_regex_fallback(self) -> None:
        """LLM returns non-JSON — fallback to regex parsing."""
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content="1. analyze: analyze the architecture\n2. optimize: optimize the performance"
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("analyze and optimize")

        assert len(result) >= 1

    def test_llm_exception_fallback(self) -> None:
        """LLM raises exception — fallback to regex split."""
        mock_llm = Mock()
        mock_llm.call.side_effect = RuntimeError("LLM error")

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("task A, then task B")

        assert len(result) >= 1

    def test_guardrails_max_subtasks(self) -> None:
        """Guardrails limit to MAX_SUB_TASKS."""
        mock_llm = Mock()
        # Return 10 tasks
        tasks = [{"intent": f"task {i}", "query": f"query {i}"} for i in range(10)]
        mock_llm.call.return_value = Mock(content=f'{{"tasks": {tasks}}}')

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("big query")

        assert len(result) <= decomposer.MAX_SUB_TASKS

    def test_guardrails_deduplicate(self) -> None:
        """Guardrails remove duplicate sub-tasks."""
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content='{"tasks": [{"intent": "a", "query": "same query"}, {"intent": "b", "query": "same query"}]}'
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("query")

        assert len(result) == 1

    def test_chinese_multi_intent(self) -> None:
        """Chinese query with 并/然后 splits correctly."""
        decomposer = TaskDecomposer(llm_client=None)
        result = decomposer.decompose("分析系统架构然后优化数据库性能")

        assert len(result) >= 2

    def test_english_multi_intent(self) -> None:
        """English query with 'and then' splits correctly."""
        decomposer = TaskDecomposer(llm_client=None)
        result = decomposer.decompose("analyze architecture and then optimize performance")

        assert len(result) >= 2
