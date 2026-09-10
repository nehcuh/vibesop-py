"""Tests for SlashCommandExecutor."""

import pytest

from vibesop.agent.runtime import (
    IntentInterceptor,
    InterceptionMode,
    SlashCommandExecutor,
    SlashCommandResult,
)


class TestSlashCommandExecutor:
    """Test SlashCommandExecutor functionality."""

    def test_execute_help_command(self) -> None:
        """Execute /vibe-help via executor."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("/vibe-help")

        executor = SlashCommandExecutor()
        result = executor.execute(decision)

        assert isinstance(result, SlashCommandResult)
        assert result.success is True
        assert result.command == "/vibe-help"
        assert "/vibe-route" in result.message
        assert result.structured is not None
        assert result.structured["command"] == "/vibe-help"

    def test_execute_query_directly(self) -> None:
        """Execute slash command directly without interceptor."""
        executor = SlashCommandExecutor()
        result = executor.execute_query("/vibe-help")

        assert result.success is True
        assert result.command == "/vibe-help"

    def test_execute_unknown_command(self) -> None:
        """Unknown command returns error."""
        executor = SlashCommandExecutor()
        result = executor.execute_query("/vibe-unknown")

        assert result.success is False
        assert "Unknown command" in result.message

    def test_handler_router_has_plan_annotator(self) -> None:
        """8.3.1 (K-10): the executor injects the plan annotator so
        /vibe-orchestrate persists carry the truthful execution_ready
        verdict in the first JSONL snapshot."""
        executor = SlashCommandExecutor()
        router = executor._handler.router
        assert router.plan_annotator is not None

    def test_orchestrate_blocked_plan_refused(self, tmp_path) -> None:
        """8.3.1 (K-10): a blocked plan must not render as "Execution Plan"
        on the slash path either."""
        from types import SimpleNamespace

        from vibesop.core.models import (
            ExecutionPlan,
            ExecutionStep,
            OrchestrationMode,
            OrchestrationResult,
        )

        executor = SlashCommandExecutor(project_root=tmp_path)
        handler = executor._handler
        plan = ExecutionPlan(
            plan_id="slash-blocked",
            original_query="do the thing",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="missing-skill",
                    skill_file="/nonexistent/missing-skill/SKILL.md",
                    intent="Implement",
                    input_query="do the thing",
                )
            ],
            metadata={
                "execution_ready": False,
                "blocked_steps": [{"step_number": 1, "reason": "not found or empty"}],
            },
        )
        blocked_result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query="do the thing",
            execution_plan=plan,
        )
        handler._router = SimpleNamespace(orchestrate=lambda query, context=None: blocked_result)

        result = executor.execute_query("/vibe-orchestrate do the thing")
        assert result.success is False
        assert "blocked" in result.message
        assert "Execution Plan" not in result.message

    def test_rejects_non_slash_decision(self) -> None:
        """Executor rejects non-SLASH_COMMAND decisions."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("review my code")

        assert decision.mode != InterceptionMode.SLASH_COMMAND

        executor = SlashCommandExecutor()
        with pytest.raises(ValueError, match="SLASH_COMMAND"):
            executor.execute(decision)

    def test_is_slash_command_helper(self) -> None:
        """is_slash_command correctly identifies slash commands."""
        executor = SlashCommandExecutor()

        assert executor.is_slash_command("/vibe-help") is True
        assert executor.is_slash_command("/vibe-route test") is True
        assert executor.is_slash_command("  /vibe-list  ") is True
        assert executor.is_slash_command("review code") is False
        assert executor.is_slash_command("") is False

    def test_execute_with_args(self) -> None:
        """Execute command with arguments."""
        executor = SlashCommandExecutor()
        result = executor.execute_query('/vibe-route "test query"')

        assert result.command == "/vibe-route"
        assert result.structured is not None
        assert result.structured["args"] == ["test query"]

    def test_result_structure(self) -> None:
        """Result contains expected structured data."""
        executor = SlashCommandExecutor()
        result = executor.execute_query("/vibe-help")

        assert result.structured is not None
        assert "command" in result.structured
        assert "args" in result.structured
        assert "raw_output" in result.structured
