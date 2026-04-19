"""Tests for enhanced WorkflowEngine."""

from __future__ import annotations

import pytest

from vibesop.core.skills.workflow import (
    ExecutionContext,
    StepType,
    Workflow,
    WorkflowEngine,
    WorkflowStep,
)


class TestWorkflowEngineEnhanced:
    """Test enhanced workflow engine features."""

    def test_init_with_tools(self) -> None:
        """Test engine initialization with tool support."""
        engine = WorkflowEngine(enable_tools=True)

        assert engine.enable_tools is True
        assert "echo" in engine._tool_registry
        assert "set" in engine._tool_registry
        assert "get" in engine._tool_registry
        assert "log" in engine._tool_registry

    def test_register_custom_tool(self) -> None:
        """Test registering custom tools."""
        engine = WorkflowEngine()

        def custom_tool(message: str) -> str:
            return f"Custom: {message}"

        engine.register_tool("custom", custom_tool)

        assert "custom" in engine._tool_registry

    def test_variable_substitution(self) -> None:
        """Test variable substitution in instructions."""
        engine = WorkflowEngine()

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Test substitution",
                    instruction="Hello {name}, you are {age} years old",
                )
            ],
        )

        context = ExecutionContext(
            skill_id="test",
            variables={"name": "Alice", "age": "30"},
        )

        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Alice" in result.output
        assert "30" in result.output

    def test_verification_with_condition(self) -> None:
        """Test verification step with condition evaluation."""
        engine = WorkflowEngine()

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.VERIFICATION,
                    description="Check value",
                    instruction="Verify that {status} == success",
                )
            ],
        )

        context = ExecutionContext(
            skill_id="test",
            variables={"status": "success"},
        )

        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Verified" in result.output

    def test_conditional_step_met(self) -> None:
        """Test conditional step when condition is met."""
        engine = WorkflowEngine()

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.CONDITIONAL,
                    description="Check x",
                    condition="x",
                    condition_value=1,
                    instruction="x is 1!",
                )
            ],
        )

        context = ExecutionContext(skill_id="test", variables={"x": 1})
        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Condition met" in result.output
        assert "x is 1!" in result.output

    def test_conditional_step_not_met(self) -> None:
        """Test conditional step when condition is not met."""
        engine = WorkflowEngine()

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.CONDITIONAL,
                    description="Check x",
                    condition="x",
                    condition_value=1,
                )
            ],
        )

        context = ExecutionContext(skill_id="test", variables={"x": 2})
        result = engine.execute(workflow, context)

        assert result.success is True
        # Condition not met, so no output for this step
        # But overall workflow succeeds
        assert result.executed_steps == 0

    def test_conditional_from_instruction(self) -> None:
        """Test conditional with instruction containing natural language."""
        engine = WorkflowEngine()

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.CONDITIONAL,
                    description="Conditional check",
                    condition="x",
                    condition_value=10,
                    instruction="x is 10, do the thing",
                )
            ],
        )

        context = ExecutionContext(skill_id="test", variables={"x": 10})
        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Condition met" in result.output
        assert "x is 10, do the thing" in result.output

    def test_tool_call_placeholder(self) -> None:
        """Test tool call with placeholder (tools disabled)."""
        engine = WorkflowEngine(enable_tools=False)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.TOOL_CALL,
                    description="Call tool",
                    tool_name="read",
                    tool_params={"file": "test.txt"},
                )
            ],
        )

        context = ExecutionContext(skill_id="test")
        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Would call" in result.output
        assert "read" in result.output

    def test_tool_call_enabled(self) -> None:
        """Test tool call with actual execution (tools enabled)."""
        engine = WorkflowEngine(enable_tools=True)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.TOOL_CALL,
                    description="Echo tool",
                    tool_name="echo",
                    tool_params={"message": "Hello"},
                )
            ],
        )

        context = ExecutionContext(skill_id="test")
        result = engine.execute(workflow, context)

        assert result.success is True
        assert "echo" in result.output.lower()
        assert "Hello" in result.output

    def test_set_and_get_tools(self) -> None:
        """Test set and get tools with context."""
        engine = WorkflowEngine(enable_tools=True)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.TOOL_CALL,
                    description="Set variable",
                    tool_name="set",
                    tool_params={"name": "x", "value": 42},
                ),
                WorkflowStep(
                    type=StepType.TOOL_CALL,
                    description="Get variable",
                    tool_name="get",
                    tool_params={"name": "x"},
                ),
            ],
        )

        context = ExecutionContext(skill_id="test")
        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Set x = 42" in result.output
        assert "x = 42" in result.output

    def test_loop_with_list(self) -> None:
        """Test loop with actual list iteration."""
        engine = WorkflowEngine()

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.LOOP,
                    description="Process items",
                    instruction="For each item in items, process it",
                    max_iterations=10,
                )
            ],
        )

        context = ExecutionContext(
            skill_id="test",
            variables={"items": ["apple", "banana", "cherry"]},
        )

        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Loop" in result.output
        assert "apple" in result.output
        assert "banana" in result.output
        assert "cherry" in result.output

    def test_error_recovery(self) -> None:
        """Test that workflow continues after step error."""
        engine = WorkflowEngine(enable_tools=True)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Good step",
                    instruction="This works",
                ),
                WorkflowStep(
                    type=StepType.TOOL_CALL,
                    description="Bad step",
                    tool_name="nonexistent",  # This tool doesn't exist
                ),
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Recovery step",
                    instruction="This also works",
                ),
            ],
        )

        context = ExecutionContext(skill_id="test")
        result = engine.execute(workflow, context)

        assert result.success is True  # Overall success
        assert "This works" in result.output
        assert "This also works" in result.output
        # The tool call should fail when enable_tools=True
        assert "error" in result.output.lower() or "nonexistent" in result.output.lower()

    def test_max_steps_limit(self) -> None:
        """Test max_steps limit enforcement."""
        engine = WorkflowEngine(max_steps=3)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description=f"Step {i}",
                    instruction=f"Step {i}",
                )
                for i in range(10)
            ],
        )

        context = ExecutionContext(skill_id="test")
        result = engine.execute(workflow, context)

        assert result.success is True
        assert result.executed_steps <= 3

    def test_complex_workflow(self) -> None:
        """Test complex workflow with multiple step types."""
        engine = WorkflowEngine(enable_tools=True)

        workflow = Workflow(
            skill_id="test",
            name="Complex Workflow",
            description="A complex test workflow",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Initialize",
                    instruction="Setting up {project}",
                ),
                WorkflowStep(
                    type=StepType.TOOL_CALL,
                    description="Set status",
                    tool_name="set",
                    tool_params={"name": "status", "value": "ready"},
                ),
                WorkflowStep(
                    type=StepType.VERIFICATION,
                    description="Check status",
                    instruction="Verify that status == ready",
                ),
                WorkflowStep(
                    type=StepType.CONDITIONAL,
                    description="If ready",
                    condition="status",
                    condition_value="ready",
                    instruction="Proceed with execution",
                ),
            ],
        )

        context = ExecutionContext(skill_id="test", variables={"project": "TestProject"})
        result = engine.execute(workflow, context)

        assert result.success is True
        assert "TestProject" in result.output
        assert "ready" in result.output
        assert "Verified" in result.output

    def test_log_tool(self) -> None:
        """Test log tool."""
        engine = WorkflowEngine(enable_tools=True)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.TOOL_CALL,
                    description="Log message",
                    tool_name="log",
                    tool_params={"message": "Test log message"},
                )
            ],
        )

        context = ExecutionContext(skill_id="test")
        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Logged" in result.output
        assert "Test log message" in result.output

    def test_nested_variable_substitution(self) -> None:
        """Test variable substitution with multiple variables."""
        engine = WorkflowEngine()

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Complex substitution",
                    instruction="User {user} is {age} years old and lives in {city}",
                )
            ],
        )

        context = ExecutionContext(
            skill_id="test",
            variables={
                "user": "Bob",
                "age": "25",
                "city": "Paris",
            },
        )

        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Bob" in result.output
        assert "25" in result.output
        assert "Paris" in result.output

    def test_empty_variable_fallback(self) -> None:
        """Test variable substitution with missing variables."""
        engine = WorkflowEngine()

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Missing var",
                    instruction="Value is {missing}",
                )
            ],
        )

        context = ExecutionContext(skill_id="test", variables={})
        result = engine.execute(workflow, context)

        assert result.success is True
        # Missing variables are replaced with empty string
        assert "Value is" in result.output

    def test_loop_iteration_limit(self) -> None:
        """Test that loop respects max_iterations."""
        engine = WorkflowEngine()

        # Create a list with more items than max_iterations
        items = [f"item_{i}" for i in range(20)]

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.LOOP,
                    description="Process items",
                    instruction="For each item in items, process {item}",
                    max_iterations=5,  # Only process first 5
                )
            ],
        )

        context = ExecutionContext(skill_id="test", variables={"items": items})
        result = engine.execute(workflow, context)

        assert result.success is True
        # Should only process first 5 items
        assert "item_0" in result.output
        assert "item_4" in result.output
        # Should NOT have items beyond max_iterations
        assert "item_5" not in result.output
        assert "item_19" not in result.output
