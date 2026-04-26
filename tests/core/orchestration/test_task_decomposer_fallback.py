"""Tests for TaskDecomposer fallback decomposition (no LLM)."""


from vibesop.core.orchestration.task_decomposer import TaskDecomposer


class TestTaskDecomposerFallback:
    """Test the non-LLM fallback decomposition path."""

    def test_single_intent_returns_one_task(self):
        decomposer = TaskDecomposer()  # No LLM → uses fallback
        tasks = decomposer.decompose("帮我调试这个数据库错误")
        assert len(tasks) == 1
        assert "debug" in tasks[0].intent

    def test_multi_intent_with_chinese_conjunctions(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("先分析项目架构然后评审代码质量最后给出优化方案")
        assert len(tasks) >= 2

    def test_multi_intent_english(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("review the code and then deploy to production")
        assert len(tasks) >= 2

    def test_short_query_returns_single_task(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("a b")
        assert len(tasks) == 1
        assert tasks[0].intent == "single task"

    def test_intent_detection_debug(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("修复这个数据库连接超时的错误")
        assert len(tasks) == 1
        assert "debug" in tasks[0].intent

    def test_intent_detection_review(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("评审一下我的代码质量")
        assert len(tasks) == 1
        assert "review" in tasks[0].intent

    def test_intent_detection_security(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("扫描安全漏洞")
        assert len(tasks) == 1
        assert "security" in tasks[0].intent

    def test_no_duplicate_sub_tasks(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("review the code, review the code")
        unique_queries = {t.query.lower().strip() for t in tasks}
        assert len(unique_queries) == len(tasks)

    def test_max_sub_tasks_limit(self):
        decomposer = TaskDecomposer()
        query = "分析架构, 审查代码, 优化性能, 修复错误, 添加测试, 更新文档, 部署上线"
        tasks = decomposer.decompose(query)
        assert len(tasks) <= decomposer.MAX_SUB_TASKS

    def test_contextualized_short_segments(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("深入分析当前项目架构 然后对后续优化工作提出指导意见")
        assert len(tasks) >= 1
        # Segments from the split should be self-contained enough to route
        for task in tasks:
            assert len(task.query) >= decomposer.MIN_QUERY_LENGTH

    def test_fallback_without_llm_no_exception(self):
        decomposer = TaskDecomposer()  # No LLM client = uses fallback
        tasks = decomposer.decompose("just a normal query about something")
        assert len(tasks) >= 1
        assert isinstance(tasks[0].intent, str)

    def test_intent_detection_architecture(self):
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("分析项目架构设计")
        assert len(tasks) == 1
        # Should match analyze_architecture domain
        assert "architecture" in tasks[0].intent or "single" in tasks[0].intent

    def test_implicit_intent_boundaries_without_conjunctions(self):
        """Queries spanning multiple domains without conjunctions should still split."""
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("帮我审查代码安全性并优化性能瓶颈")
        intents = {t.intent for t in tasks}
        assert len(intents) >= 2 or len(tasks) >= 2

    def test_single_domain_query_not_over_split(self):
        """Single-domain queries should not be incorrectly split."""
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("调试数据库连接池泄漏")
        assert len(tasks) <= 2
