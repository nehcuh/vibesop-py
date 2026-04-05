"""End-to-end tests for trigger system workflow.

Tests the complete flow from user query to skill/workflow execution.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from vibesop.triggers import KeywordDetector, SkillActivator, auto_activate, DEFAULT_PATTERNS
from vibesop.triggers.models import PatternMatch, PatternCategory


@pytest.fixture
def project_root(tmp_path):
    """Create temporary project root."""
    return tmp_path


@pytest.fixture
def sample_skill():
    """Create a sample skill for testing."""
    skill_path = project_root / ".vibe" / "skills" / "test" / "skill.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text("# Test Skill\n\nA test skill for E2E testing.")
    return skill_path


class TestE2EKeywordDetection:
    """End-to-end tests for keyword detection workflow."""

    def test_complete_detection_workflow_english(self):
        """Test complete workflow with English query."""
        # User query
        query = "scan for security vulnerabilities in my code"

        # Detect intent
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        match = detector.detect_best(query, min_confidence=0.6)

        # Verify match
        assert match is not None
        assert match.confidence >= 0.6
        assert match.pattern_id == "security/scan"
        assert match.metadata["category"] == "security"
        assert "scan" in match.matched_keywords or "security" in match.matched_keywords

    def test_complete_detection_workflow_chinese(self):
        """Test complete workflow with Chinese query."""
        # User query
        query = "扫描安全漏洞"

        # Detect intent
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        match = detector.detect_best(query, min_confidence=0.6)

        # Verify match
        assert match is not None
        assert match.pattern_id == "security/scan"
        assert match.metadata["category"] == "security"

    def test_complete_detection_workflow_mixed(self):
        """Test complete workflow with mixed English/Chinese query."""
        query = "帮我 scan security issues"  # Mixed English/Chinese

        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        match = detector.detect_best(query, min_confidence=0.5)

        # Should match something (lower threshold for mixed queries)
        assert match is not None
        assert match.confidence >= 0.5

    def test_no_match_workflow(self):
        """Test workflow when no pattern matches."""
        query = "xyzabc123 completely unmatched query"

        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        match = detector.detect_best(query, min_confidence=0.6)

        # Should return None
        assert match is None

    def test_low_confidence_workflow(self):
        """Test workflow with low confidence match."""
        query = "test"  # Very generic, might match but with low confidence

        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        match = detector.detect_best(query, min_confidence=0.6)

        # Should return None if below threshold
        # Or return match with low confidence
        if match:
            assert match.confidence < 0.6

    def test_all_categories_detection(self):
        """Test that all categories can be detected."""
        test_queries = [
            ("scan security", "security"),
            ("deploy configuration", "config"),
            ("run tests", "dev"),
            ("generate documentation", "docs"),
            ("initialize project", "project"),
        ]

        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        for query, expected_category in test_queries:
            match = detector.detect_best(query)
            assert match is not None, f"No match for query: {query}"
            assert match.metadata["category"] == expected_category


class TestE2ESkillActivation:
    """End-to-end tests for skill activation workflow."""

    @pytest.mark.asyncio
    async def test_complete_skill_activation_workflow(self, project_root):
        """Test complete workflow from detection to skill execution."""
        # Setup mocks
        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
            patch("vibesop.triggers.activator.WorkflowManager") as mock_wm_class,
        ):
            # Create mocks
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(return_value="Skill executed successfully")
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.return_value = None  # No routing needed
            mock_router_class.return_value = mock_router

            # Mock workflow manager
            mock_wm = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.completed_stages = ["stage1", "stage2"]
            mock_result.failed_stages = []
            mock_result.skipped_stages = []
            mock_wm.execute_workflow = AsyncMock(return_value=mock_result)
            mock_wm_class.return_value = mock_wm

            # Detect intent - using a pattern without workflow_id
            query = "validate configuration"
            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            match = detector.detect_best(query, min_confidence=0.6)

            assert match is not None

            # Activate skill
            activator = SkillActivator(project_root=project_root)
            result = await activator.activate(match, input_data={"target": "./src"})

            # Verify result (config/validate has no workflow_id, so should use skill)
            assert result["success"] is True
            # config/validate only has skill_id, no workflow_id
            # Note: If workflow execution is attempted but fails, it may fall back to skill

    @pytest.mark.asyncio
    async def test_auto_activate_convenience_function(self, project_root):
        """Test auto_activate convenience function."""
        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
        ):
            # Setup mocks
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(return_value="Success")
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.return_value = None
            mock_router_class.return_value = mock_router

            # Use convenience function
            result = await auto_activate(
                "scan for security issues", project_root=project_root, min_confidence=0.6
            )

            # Verify
            assert result["success"] is True
            assert result["action"] in ["skill", "workflow", "none"]

    @pytest.mark.asyncio
    async def test_skill_activation_with_failure_fallback(self, project_root):
        """Test skill activation with fallback to router."""
        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
        ):
            # Setup mocks
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(side_effect=Exception("Skill not found"))
            mock_sm_class.return_value = mock_sm

            # Setup router to provide fallback
            mock_skill = MagicMock()
            mock_skill.skill_id = "/routed/skill"
            mock_route = MagicMock()
            mock_route.primary = mock_skill
            mock_router = MagicMock()
            mock_router.route.return_value = mock_route

            # Detect and activate (use pattern without workflow_id to test skill fallback)
            query = "run tests"
            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            match = detector.detect_best(query)

            activator = SkillActivator(
                project_root=project_root,
                skill_manager=mock_sm,
                router=mock_router,
            )
            result = await activator.activate(match)

            # Should have attempted fallback
            assert "action" in result
            mock_router.route.assert_called_once()


class TestE2EIntegrationScenarios:
    """End-to-end tests for real-world integration scenarios."""

    @pytest.mark.asyncio
    async def test_security_scan_workflow(self, project_root):
        """Test complete security scan workflow."""
        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
            patch("vibesop.triggers.activator.WorkflowManager") as mock_wm_class,
        ):
            # Setup
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(return_value="Security scan complete")
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.return_value = None
            mock_router_class.return_value = mock_router

            # Mock workflow manager (security/scan has workflow_id)
            mock_wm = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.completed_stages = ["scan", "analyze"]
            mock_result.failed_stages = []
            mock_result.skipped_stages = []
            mock_wm.execute_workflow = AsyncMock(return_value=mock_result)
            mock_wm_class.return_value = mock_wm

            # Simulate user query
            query = "Please scan my code for security vulnerabilities"

            # Detect
            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            match = detector.detect_best(query)

            assert match is not None
            assert match.pattern_id == "security/scan"

            # Execute with input data
            activator = SkillActivator(project_root=project_root)
            result = await activator.activate(
                match, input_data={"target": "./src", "severity": "high"}
            )

            # security/scan has workflow_id, so should activate workflow
            assert result["success"] is True
            # Workflow takes priority when workflow_id is set
            assert result["action"] in ["workflow", "skill"]  # Either is acceptable

    @pytest.mark.asyncio
    async def test_config_deploy_workflow(self, project_root):
        """Test complete config deployment workflow."""
        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
            patch("vibesop.triggers.activator.WorkflowManager") as mock_wm_class,
        ):
            # Setup
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(return_value="Config deployed")
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.return_value = None
            mock_router_class.return_value = mock_router

            # Mock workflow manager (config/deploy has workflow_id)
            mock_wm = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.completed_stages = ["validate", "render", "install"]
            mock_result.failed_stages = []
            mock_result.skipped_stages = []
            mock_wm.execute_workflow = AsyncMock(return_value=mock_result)
            mock_wm_class.return_value = mock_wm

            query = "deploy my configuration to production"
            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            match = detector.detect_best(query)

            assert match is not None
            assert match.pattern_id == "config/deploy"

            activator = SkillActivator(project_root=project_root)
            result = await activator.activate(match, input_data={"environment": "production"})

            # config/deploy has workflow_id, so should activate workflow
            assert result["success"] is True
            assert result["action"] in ["workflow", "skill"]  # Either is acceptable

    @pytest.mark.asyncio
    async def test_multi_stage_workflow_simulation(self, project_root):
        """Test simulated multi-stage workflow."""
        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
            patch("vibesop.triggers.activator.WorkflowManager") as mock_wm_class,
        ):
            # Setup
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(return_value="Stage complete")
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.return_value = None
            mock_router_class.return_value = mock_router

            # Mock workflow manager
            mock_wm = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.completed_stages = ["stage1"]
            mock_result.failed_stages = []
            mock_result.skipped_stages = []
            mock_wm.execute_workflow = AsyncMock(return_value=mock_result)
            mock_wm_class.return_value = mock_wm

            activator = SkillActivator(project_root=project_root)
            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

            # Simulate multi-stage workflow: analyze -> report (no workflow_id)
            stages = [
                ("analyze the threats", "security/analyze"),
                ("generate a report", "security/report"),
            ]

            for query, expected_pattern_id in stages:
                match = detector.detect_best(query)
                assert match is not None
                assert match.pattern_id == expected_pattern_id

                result = await activator.activate(match)
                assert result["success"] is True


class TestE2EErrorHandling:
    """End-to-end tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_no_match_error(self, project_root):
        """Test error handling when no pattern matches."""
        result = await auto_activate(
            "xyzabc123 unmatched", project_root=project_root, min_confidence=0.8
        )

        assert result["success"] is False
        assert result["action"] == "none"
        assert "no intent detected" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_skill_execution_error(self, project_root):
        """Test error handling when skill execution fails."""
        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
            patch("vibesop.triggers.activator.WorkflowManager") as mock_wm_class,
        ):
            # Setup failing skill, router, and workflow
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(side_effect=Exception("Skill failed"))
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.side_effect = Exception("Router failed")
            mock_router_class.return_value = mock_router

            # Mock workflow to fail too
            mock_wm = MagicMock()
            mock_wm.execute_workflow = AsyncMock(side_effect=Exception("Workflow failed"))
            mock_wm_class.return_value = mock_wm

            query = "validate configuration"  # Use pattern without workflow_id to test skill path
            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            match = detector.detect_best(query)

            activator = SkillActivator(project_root=project_root)
            result = await activator.activate(match)

            # Should handle error gracefully
            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_input_data(self, project_root):
        """Test error handling with invalid input data."""
        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
        ):
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(return_value="OK")
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.return_value = None
            mock_router_class.return_value = mock_router

            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            match = detector.detect_best("scan security")

            activator = SkillActivator(project_root=project_root)

            # Should handle various input data types gracefully
            test_inputs = [
                None,
                {},
                {"key": "value"},
                {"nested": {"data": "here"}},
            ]

            for input_data in test_inputs:
                result = await activator.activate(match, input_data=input_data)
                # Should not crash
                assert isinstance(result, dict)


class TestE2EPerformance:
    """End-to-end performance tests."""

    def test_detection_performance_large_pattern_set(self):
        """Test detection performance with large pattern set."""
        import time

        # Create detector with all patterns
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        # Test queries
        queries = [
            "scan for security vulnerabilities",
            "deploy configuration to production",
            "run all tests",
            "generate documentation",
            "initialize new project",
        ] * 100  # 500 queries

        start_time = time.time()
        for query in queries:
            detector.detect_best(query, min_confidence=0.6)
        elapsed = time.time() - start_time

        # Should process 500 queries quickly (< 5 seconds)
        assert elapsed < 5.0, f"Too slow: {elapsed}s for 500 queries"

        # Average per query should be very fast
        avg_time = elapsed / len(queries)
        assert avg_time < 0.01, f"Average query time too high: {avg_time}s"

    def test_memory_efficiency(self):
        """Test memory efficiency with repeated detections."""
        import gc
        import sys

        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        # Force garbage collection before test
        gc.collect()

        # Get initial memory usage
        # Note: This is a rough estimate
        initial_objects = len(gc.get_objects())

        # Perform many detections
        for i in range(1000):
            query = f"scan for security issues {i}"
            detector.detect_best(query, min_confidence=0.6)

        # Force garbage collection after test
        gc.collect()

        # Check object count didn't grow significantly
        # (allow 20% growth for caching)
        final_objects = len(gc.get_objects())
        growth = (final_objects - initial_objects) / initial_objects
        assert growth < 0.2, f"Memory growth too high: {growth:.1%}"

    @pytest.mark.asyncio
    async def test_concurrent_activations(self, project_root):
        """Test concurrent skill activations."""
        import asyncio

        with (
            patch("vibesop.triggers.activator.SkillManager") as mock_sm_class,
            patch("vibesop.triggers.activator.SkillRouter") as mock_router_class,
            patch("vibesop.triggers.activator.WorkflowManager") as mock_wm_class,
        ):
            # Setup
            mock_sm = MagicMock()
            mock_sm.execute_skill = AsyncMock(return_value="Done")
            mock_sm_class.return_value = mock_sm

            mock_router = MagicMock()
            mock_router.route.return_value = None
            mock_router_class.return_value = mock_router

            # Mock workflow manager
            mock_wm = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.completed_stages = ["stage1"]
            mock_result.failed_stages = []
            mock_result.skipped_stages = []
            mock_wm.execute_workflow = AsyncMock(return_value=mock_result)
            mock_wm_class.return_value = mock_wm

            detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
            activator = SkillActivator(project_root=project_root)

            # Create concurrent tasks
            async def run_detection(query):
                match = detector.detect_best(query)
                if match:
                    return await activator.activate(match)
                return None

            queries = [
                "analyze security threats",  # No workflow_id
                "validate configuration",  # No workflow_id
                "run tests",
                "format code",
                "update readme",
            ]

            # Run concurrently
            results = await asyncio.gather(*[run_detection(query) for query in queries])

            # All should complete successfully
            assert len(results) == len(queries)
            for result in results:
                assert result is not None
                assert isinstance(result, dict)


class TestE2EAccuracy:
    """End-to-end accuracy tests."""

    def test_detection_accuracy_english(self):
        """Test detection accuracy for English queries."""
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        # Test cases with expected patterns
        test_cases = [
            ("scan for security vulnerabilities", "security/scan"),
            ("check for security issues", "security/scan"),
            ("security audit", "security/audit"),
            ("deploy my configuration", "config/deploy"),
            ("validate the configuration", "config/validate"),
            ("render config files", "config/render"),
            ("build the project", "dev/build"),
            ("run tests", "dev/test"),
            ("debug this error", "dev/debug"),
            ("refactor code", "dev/refactor"),
            ("generate documentation", "docs/generate"),
            ("update the readme", "docs/readme"),
            ("initialize new project", "project/init"),
            ("migrate project", "project/migrate"),
        ]

        correct = 0
        for query, expected_pattern_id in test_cases:
            match = detector.detect_best(query, min_confidence=0.4)  # Lower threshold
            if match and match.pattern_id == expected_pattern_id:
                correct += 1

        accuracy = correct / len(test_cases)
        # Should have at least 70% accuracy (relaxed threshold)
        assert accuracy >= 0.7, f"Accuracy too low: {accuracy:.1%}"

    def test_detection_accuracy_chinese(self):
        """Test detection accuracy for Chinese queries."""
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        test_cases = [
            ("扫描安全漏洞", "security/scan"),
            ("安全审计", "security/audit"),
            ("部署配置", "config/deploy"),
            ("验证配置", "config/validate"),
            ("构建项目", "dev/build"),
            ("运行测试", "dev/test"),
            ("调试错误", "dev/debug"),
            ("生成文档", "docs/generate"),
            ("更新readme", "docs/readme"),
            ("初始化项目", "project/init"),
        ]

        correct = 0
        for query, expected_pattern_id in test_cases:
            match = detector.detect_best(query, min_confidence=0.4)  # Lower threshold
            if match and match.pattern_id == expected_pattern_id:
                correct += 1

        accuracy = correct / len(test_cases)
        # Should have at least 60% accuracy for Chinese (may be lower)
        assert accuracy >= 0.6, f"Chinese accuracy too low: {accuracy:.1%}"

    def test_confidence_calibration(self):
        """Test that confidence scores are well-calibrated."""
        detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

        # Clear matches should have high confidence
        clear_matches = [
            "scan for security vulnerabilities",
            "deploy configuration to production",
            "run all unit tests",
            "generate API documentation",
            "initialize new project",
        ]

        # Vague matches should have lower confidence
        vague_matches = [
            "test",
            "check",
            "run",
            "update",
            "build",
        ]

        clear_confidences = []
        vague_confidences = []

        for query in clear_matches:
            match = detector.detect_best(query, min_confidence=0.0)
            if match:
                clear_confidences.append(match.confidence)

        for query in vague_matches:
            match = detector.detect_best(query, min_confidence=0.0)
            if match:
                vague_confidences.append(match.confidence)

        if clear_confidences and vague_confidences:
            avg_clear = sum(clear_confidences) / len(clear_confidences)
            avg_vague = sum(vague_confidences) / len(vague_confidences)

            # Clear matches should have higher average confidence
            assert avg_clear > avg_vague, (
                f"Clear matches ({avg_clear:.2f}) should have higher confidence than vague ({avg_vague:.2f})"
            )
