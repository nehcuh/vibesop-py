"""Tests for TaskDecomposer."""

from __future__ import annotations

from unittest.mock import Mock

from vibesop.core.orchestration.task_decomposer import TaskDecomposer


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


class TestDecomposeWithSkillCatalog:
    """The decomposer must surface the skill list to the LLM and preserve skill_id.

    Without the catalog the LLM can't pre-assign sub-tasks, and PlanBuilder is
    forced to fall through to the cheap (skip_ai_triage) routing layers — which
    is what made every sub-task land at the same wrong skill.
    """

    def test_skills_appear_in_prompt(self) -> None:
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content='{"tasks": [{"intent": "x", "query": "do x", "skill_id": "gstack/review"}]}'
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        decomposer.decompose(
            "review and test",
            skills=["gstack/review: Code review", "gstack/test: Test runner"],
        )

        # Inspect the prompt that was sent to the LLM.
        prompt = mock_llm.call.call_args.kwargs.get("prompt") or mock_llm.call.call_args.args[0]
        assert "Available skills" in prompt
        assert "gstack/review: Code review" in prompt
        assert "gstack/test: Test runner" in prompt

    def test_skill_id_round_trips_into_subtask(self) -> None:
        """When the LLM assigns skill_id, decompose() must surface it on SubTask."""
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content=(
                '{"tasks": ['
                '{"intent": "analyze", "query": "analyze architecture", "skill_id": "superpowers/architect"},'
                '{"intent": "review", "query": "review security", "skill_id": "gstack/review"}'
                "]}"
            )
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose(
            "analyze and review",
            skills=["superpowers/architect: arch", "gstack/review: review"],
        )

        assert len(result) == 2
        assert result[0].skill_id == "superpowers/architect"
        assert result[1].skill_id == "gstack/review"

    def test_null_skill_id_normalized_to_none(self) -> None:
        """Both literal "null" string and JSON null collapse to Python None."""
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content=(
                '{"tasks": ['
                '{"intent": "a", "query": "do a thing", "skill_id": "null"},'
                '{"intent": "b", "query": "do another", "skill_id": null}'
                "]}"
            )
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("a and b", skills=["x: y"])

        assert len(result) == 2
        assert all(t.skill_id is None for t in result)

    def test_no_skills_kw_still_works(self) -> None:
        """Backward-compat: callers that don't pass skills= still get a decomposition."""
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content='{"tasks": [{"intent": "x", "query": "investigate this thing"}]}'
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("investigate this thing")

        assert len(result) == 1
        prompt = mock_llm.call.call_args.kwargs.get("prompt") or mock_llm.call.call_args.args[0]
        # Without skills, the "Available skills" preamble must NOT appear.
        assert "Available skills" not in prompt


class TestDeterministicDecomposition:
    """Decomposition must be deterministic — temperature=0.0 is mandatory."""

    def test_llm_called_with_zero_temperature(self) -> None:
        """Temperature must be 0.0 to eliminate sampling variance across runs."""
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content='{"tasks": [{"intent": "x", "query": "do x"}]}'
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        decomposer.decompose("do x")

        _, kwargs = mock_llm.call.call_args
        assert kwargs.get("temperature") == 0.0

    def test_fallback_decomposition_is_deterministic(self) -> None:
        """Rule-based fallback must return identical results for identical input."""
        decomposer = TaskDecomposer(llm_client=None)
        query = "分析系统架构并优化数据库性能"

        result1 = decomposer.decompose(query)
        result2 = decomposer.decompose(query)

        assert len(result1) == len(result2)
        for a, b in zip(result1, result2):
            assert a.intent == b.intent
            assert a.query == b.query


class TestDeriveIntentFallback:
    """The decomposer must not produce SubTasks with empty intent.

    LLMs occasionally return tasks with `intent: ""` while still emitting a real
    query. Downstream (PlanBuilder, ExecutionStep) treats intent as a label and
    asserts non-empty in e2e tests, so we derive a short intent from the query.
    """

    def test_empty_intent_falls_back_to_query_prefix(self) -> None:
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content='{"tasks": [{"intent": "", "query": "analyze the architecture"}]}'
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("analyze the architecture")

        assert len(result) == 1
        assert result[0].intent  # non-empty
        assert "analyze" in result[0].intent

    def test_whitespace_intent_treated_as_empty(self) -> None:
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content='{"tasks": [{"intent": "   ", "query": "audit the auth flow"}]}'
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("audit the auth flow")

        assert len(result) == 1
        assert result[0].intent.strip()

    def test_derive_intent_truncates_long_query(self) -> None:
        long = "x" * 200
        derived = TaskDecomposer._derive_intent(long, max_len=60)

        assert len(derived) <= 61  # 60 + ellipsis
        assert derived.endswith("…")

    def test_derive_intent_stops_at_punctuation(self) -> None:
        derived = TaskDecomposer._derive_intent("review the auth flow. then deploy")

        assert derived == "review the auth flow"

    def test_derive_intent_handles_empty_query(self) -> None:
        derived = TaskDecomposer._derive_intent("")

        assert derived == "sub-task"


class TestCleanIntentMarkdown:
    """Markdown artifacts from LLM output must be stripped from intent labels."""

    def test_clean_intent_strips_bold_markers(self) -> None:
        assert TaskDecomposer._clean_intent("**Input") == "Input"
        assert TaskDecomposer._clean_intent("**Translation/Understanding**") == "Translation/Understanding"
        assert TaskDecomposer._clean_intent("*italic*") == "italic"

    def test_clean_intent_strips_mixed_markers(self) -> None:
        assert TaskDecomposer._clean_intent("** *Mixed**") == "Mixed"

    def test_clean_intent_preserves_normal_text(self) -> None:
        assert TaskDecomposer._clean_intent("analyze architecture") == "analyze architecture"

    def test_json_parser_strips_markdown_intent(self) -> None:
        """LLM returns JSON with markdown-wrapped intent — cleaned before use."""
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content='{"tasks": [{"intent": "**Input", "query": "analyze this"}]}'
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("analyze this")

        assert len(result) == 1
        assert result[0].intent == "Input"

    def test_regex_fallback_strips_markdown_intent(self) -> None:
        """Regex fallback catches markdown headers — strips them."""
        mock_llm = Mock()
        mock_llm.call.return_value = Mock(
            content="**Translation/Understanding**: analyze the code\n**Output**: fix the bug"
        )

        decomposer = TaskDecomposer(llm_client=mock_llm)
        result = decomposer.decompose("analyze and fix")

        assert len(result) == 2
        assert result[0].intent == "Translation/Understanding"
        assert result[1].intent == "Output"
