"""Tests for Workflow models and engine."""

from __future__ import annotations

import pytest

from vibesop.core.skills.workflow import (
    ExecutionContext,
    StepType,
    Workflow,
    WorkflowEngine,
    WorkflowResult,
    WorkflowStep,
    parse_workflow_from_markdown,
)


class TestWorkflowStep:
    """Test WorkflowStep model."""

    def test_instruction_step_valid(self) -> None:
        """Test valid instruction step."""
        step = WorkflowStep(
            type=StepType.INSTRUCTION,
            description="Test step",
            instruction="Do something",
        )

        errors = step.validate()
        assert len(errors) == 0

    def test_instruction_step_missing_instruction(self) -> None:
        """Test instruction step without instruction."""
        step = WorkflowStep(
            type=StepType.INSTRUCTION,
            description="Test step",
        )

        errors = step.validate()
        assert len(errors) > 0
        assert "missing instruction" in errors[0]

    def test_tool_call_step_valid(self) -> None:
        """Test valid tool call step."""
        step = WorkflowStep(
            type=StepType.TOOL_CALL,
            description="Call tool",
            tool_name="read_file",
            tool_params={"path": "test.txt"},
        )

        errors = step.validate()
        assert len(errors) == 0

    def test_tool_call_step_missing_tool(self) -> None:
        """Test tool call step without tool name."""
        step = WorkflowStep(
            type=StepType.TOOL_CALL,
            description="Call tool",
        )

        errors = step.validate()
        assert len(errors) > 0
        assert "missing tool_name" in errors[0]

    def test_loop_step_valid(self) -> None:
        """Test valid loop step."""
        step = WorkflowStep(
            type=StepType.LOOP,
            description="Repeat",
            max_iterations=10,
        )

        errors = step.validate()
        assert len(errors) == 0

    def test_loop_step_missing_max(self) -> None:
        """Test loop step without max_iterations."""
        step = WorkflowStep(
            type=StepType.LOOP,
            description="Repeat",
        )

        errors = step.validate()
        assert len(errors) > 0
        assert "requires max_iterations" in errors[0]

    def test_to_dict(self) -> None:
        """Test converting step to dict."""
        step = WorkflowStep(
            type=StepType.INSTRUCTION,
            description="Test",
            instruction="Do it",
        )

        data = step.to_dict()

        assert data["type"] == "instruction"
        assert data["description"] == "Test"
        assert data["instruction"] == "Do it"


class TestWorkflow:
    """Test Workflow model."""

    def test_create_workflow(self) -> None:
        """Test creating a workflow."""
        workflow = Workflow(
            skill_id="test",
            name="Test Workflow",
            description="A test workflow",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Step 1",
                    instruction="Do step 1",
                ),
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Step 2",
                    instruction="Do step 2",
                ),
            ],
        )

        assert workflow.skill_id == "test"
        assert workflow.name == "Test Workflow"
        assert len(workflow.steps) == 2

    def test_workflow_requires_steps(self) -> None:
        """Test that workflow must have at least one step."""
        with pytest.raises(ValueError, match="must have at least one step"):
            Workflow(
                skill_id="test",
                name="Test",
                description="Test",
                steps=[],
            )

    def test_validate_valid_workflow(self) -> None:
        """Test validating a valid workflow."""
        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Step",
                    instruction="Do it",
                )
            ],
        )

        errors = workflow.validate_workflow()
        assert len(errors) == 0

    def test_validate_invalid_workflow(self) -> None:
        """Test validating an invalid workflow."""
        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Step",
                    # Missing instruction
                )
            ],
        )

        errors = workflow.validate_workflow()
        assert len(errors) > 0

    def test_to_dict(self) -> None:
        """Test converting workflow to dict."""
        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test workflow",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Step",
                    instruction="Do it",
                )
            ],
        )

        data = workflow.to_dict()

        assert data["skill_id"] == "test"
        assert data["name"] == "Test"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["type"] == "instruction"

    def test_from_metadata(self) -> None:
        """Test creating workflow from metadata."""
        from vibesop.core.skills.base import SkillMetadata

        metadata = SkillMetadata(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test something",
            namespace="builtin",
            version="1.0.0",
        )

        workflow = Workflow.from_metadata(metadata)

        assert workflow.skill_id == "test-skill"
        assert workflow.name == "Test Skill"
        assert len(workflow.steps) == 1
        assert workflow.steps[0].type == StepType.INSTRUCTION


class TestExecutionContext:
    """Test ExecutionContext model."""

    def test_context_variables(self) -> None:
        """Test context variable management."""
        context = ExecutionContext(
            skill_id="test",
            variables={"x": 1, "y": 2},
        )

        assert context.get_variable("x") == 1
        assert context.get_variable("z") is None
        assert context.get_variable("z", default="default") == "default"

        context.set_variable("z", 3)
        assert context.get_variable("z") == 3

    def test_context_outputs(self) -> None:
        """Test context output management."""
        context = ExecutionContext(skill_id="test")

        context.add_output("Output 1")
        context.add_output("Output 2")

        assert len(context.outputs) == 2
        assert context.outputs[0] == "Output 1"
        assert context.outputs[1] == "Output 2"


class TestWorkflowEngine:
    """Test WorkflowEngine."""

    def test_init(self) -> None:
        """Test engine initialization."""
        engine = WorkflowEngine(timeout=10.0, max_steps=50)

        assert engine.timeout == 10.0
        assert engine.max_steps == 50

    def test_execute_simple_workflow(self) -> None:
        """Test executing a simple workflow."""
        engine = WorkflowEngine(timeout=10.0)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Step 1",
                    instruction="Do step 1",
                ),
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Step 2",
                    instruction="Do step 2",
                ),
            ],
        )

        context = ExecutionContext(skill_id="test")
        result = engine.execute(workflow, context)

        assert result.success is True
        assert result.executed_steps == 2
        assert "Do step 1" in result.output
        assert "Do step 2" in result.output

    def test_execute_invalid_workflow(self) -> None:
        """Test executing an invalid workflow."""
        engine = WorkflowEngine(timeout=10.0)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description="Step",
                    # Missing instruction
                )
            ],
        )

        context = ExecutionContext(skill_id="test")

        with pytest.raises(ValueError, match="Invalid workflow"):
            engine.execute(workflow, context)

    def test_execute_with_max_steps(self) -> None:
        """Test execution with max steps limit."""
        engine = WorkflowEngine(timeout=10.0, max_steps=2)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description=f"Step {i}",
                    instruction=f"Do step {i}",
                )
                for i in range(5)
            ],
        )

        context = ExecutionContext(skill_id="test")
        result = engine.execute(workflow, context)

        assert result.success is True
        assert result.executed_steps == 2  # Limited by max_steps

    def test_execute_conditional_step(self) -> None:
        """Test executing conditional step."""
        engine = WorkflowEngine(timeout=10.0)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.CONDITIONAL,
                    description="Check condition",
                    condition="x",
                    condition_value=1,
                )
            ],
        )

        context = ExecutionContext(skill_id="test", variables={"x": 1})
        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Condition met" in result.output

    def test_execute_tool_call_step(self) -> None:
        """Test executing tool call step."""
        engine = WorkflowEngine(timeout=10.0)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.TOOL_CALL,
                    description="Read file",
                    tool_name="read",
                    tool_params={"path": "test.txt"},
                )
            ],
        )

        context = ExecutionContext(skill_id="test")
        result = engine.execute(workflow, context)

        assert result.success is True
        assert "read" in result.output

    def test_execute_loop_step(self) -> None:
        """Test executing loop step."""
        engine = WorkflowEngine(timeout=10.0)

        workflow = Workflow(
            skill_id="test",
            name="Test",
            description="Test",
            steps=[
                WorkflowStep(
                    type=StepType.LOOP,
                    description="Repeat",
                    max_iterations=5,
                )
            ],
        )

        context = ExecutionContext(skill_id="test")
        result = engine.execute(workflow, context)

        assert result.success is True
        assert "Loop" in result.output
        assert "5" in result.output


class TestParseWorkflow:
    """Test workflow parsing from markdown."""

    def test_parse_simple_workflow(self) -> None:
        """Test parsing simple workflow from markdown."""
        markdown = """# Test Skill

This is a test skill.

## Steps

1. First step
   Do something first

2. Second step
   Do something second
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert workflow.skill_id == "test"
        assert workflow.name == "Test Skill"
        assert len(workflow.steps) == 2
        assert workflow.steps[0].description == "First step"
        assert workflow.steps[1].description == "Second step"

    def test_parse_workflow_without_steps(self) -> None:
        """Test parsing workflow without explicit steps."""
        markdown = """# Test Skill

This is a test skill that does something.
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert workflow.skill_id == "test"
        assert len(workflow.steps) == 1
        assert workflow.steps[0].type == StepType.INSTRUCTION

    def test_parse_workflow_with_description(self) -> None:
        """Test parsing workflow with detailed description."""
        markdown = """# Test Skill

This is a detailed description.

## Steps

1. Execute
   Run the task
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert "detailed description" in workflow.description
        assert len(workflow.steps) == 1

    def test_parse_workflow_with_numbered_steps(self) -> None:
        """Test parsing workflow with numbered steps."""
        markdown = """# Test Skill

## Execution Steps

1. Prepare
2. Execute
3. Verify
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert len(workflow.steps) == 3
        assert workflow.steps[0].description == "Prepare"
        assert workflow.steps[1].description == "Execute"
        assert workflow.steps[2].description == "Verify"

    def test_parse_workflow_with_bullet_steps(self) -> None:
        """Test parsing workflow with bullet points."""
        markdown = """# Test Skill

## Steps

- First task
- Second task
- Third task
"""

        workflow = parse_workflow_from_markdown(markdown, "test")

        assert len(workflow.steps) == 3
        assert workflow.steps[0].description == "First task"
        assert workflow.steps[1].description == "Second task"
        assert workflow.steps[2].description == "Third task"
