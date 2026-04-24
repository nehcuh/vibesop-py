"""Tests for TaskDecomposer."""

import pytest

from vibesop.core.orchestration.task_decomposer import SubTask, TaskDecomposer


class TestTaskDecomposer:
    def test_single_intent_query_returns_one_subtask(self):
        decomposer = TaskDecomposer()
        result = decomposer.decompose("修复数据库连接错误")
        assert len(result) == 1
        assert result[0].intent == "debug_error"
        assert result[0].query == "修复数据库连接错误"

    def test_chinese_multi_intent_query_decomposes(self):
        decomposer = TaskDecomposer()
        result = decomposer.decompose("分析项目架构，然后审查代码质量")
        assert len(result) >= 2
        intents = [st.intent for st in result]
        assert "analyze_architecture" in intents
        assert "code_review" in intents

    def test_parallel_intent_query_produces_parallel_tasks(self):
        decomposer = TaskDecomposer()
        result = decomposer.decompose("同时审查前端和后端代码")
        assert len(result) >= 1
        assert all(st.intent != "single task" for st in result)

    def test_noisy_segments_filtered(self):
        decomposer = TaskDecomposer()
        result = decomposer.decompose("帮我review代码")
        assert len(result) == 1
        assert result[0].intent == "code_review"
        assert "帮我" not in result[0].query

    def test_fallback_returns_subtasks_for_multi_intent(self):
        decomposer = TaskDecomposer()
        result = decomposer._fallback_decomposition("优化性能并修复bug")
        assert len(result) >= 2
        intents = [st.intent for st in result]
        assert "optimize" in intents
        assert "debug_error" in intents

    def test_short_segment_merged_with_next(self):
        decomposer = TaskDecomposer()
        result = decomposer._fallback_decomposition("帮我 review 代码")
        assert len(result) == 1
        assert result[0].intent == "code_review"

    def test_unknown_intent_segments_skipped(self):
        decomposer = TaskDecomposer()
        result = decomposer._fallback_decomposition("请帮我看看")
        assert len(result) == 1
        assert result[0].intent == "single task"

    def test_guardrails_deduplicate(self):
        decomposer = TaskDecomposer()
        result = decomposer._apply_guardrails([
            SubTask(intent="a", query="query one"),
            SubTask(intent="b", query="query one"),
            SubTask(intent="c", query="query two"),
        ])
        assert len(result) == 2

    def test_guardrails_max_subtasks(self):
        decomposer = TaskDecomposer()
        tasks = [SubTask(intent=f"t{i}", query=f"query {i}") for i in range(10)]
        result = decomposer._apply_guardrails(tasks)
        assert len(result) == 5

    def test_guardrails_min_query_length(self):
        decomposer = TaskDecomposer()
        result = decomposer._apply_guardrails([
            SubTask(intent="a", query="hi"),
            SubTask(intent="b", query="this is long enough"),
        ])
        assert len(result) == 1
        assert result[0].intent == "b"
