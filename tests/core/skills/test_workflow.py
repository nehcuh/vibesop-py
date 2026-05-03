"""Tests for workflow models."""


from vibesop.core.skills.workflow import StepType, WorkflowStep


class TestStepType:
    """Test StepType enum."""

    def test_values(self):
        assert StepType.INSTRUCTION.value == "instruction"
        assert StepType.VERIFICATION.value == "verification"
        assert StepType.TOOL_CALL.value == "tool_call"
        assert StepType.CONDITIONAL.value == "conditional"
        assert StepType.LOOP.value == "loop"


class TestWorkflowStep:
    """Test WorkflowStep dataclass."""

    def test_creation(self):
        step = WorkflowStep(
            type=StepType.INSTRUCTION,
            description="Test step",
            instruction="Do something",
        )
        assert step.type == StepType.INSTRUCTION
        assert step.description == "Test step"
        assert step.instruction == "Do something"

    def test_validate_instruction_valid(self):
        step = WorkflowStep(
            type=StepType.INSTRUCTION,
            description="Test",
            instruction="Do it",
        )
        assert step.validate() == []

    def test_validate_instruction_missing(self):
        step = WorkflowStep(
            type=StepType.INSTRUCTION,
            description="Test",
        )
        errors = step.validate()
        assert any("missing instruction" in e for e in errors)

    def test_validate_tool_call_valid(self):
        step = WorkflowStep(
            type=StepType.TOOL_CALL,
            description="Call tool",
            tool_name="test_tool",
            tool_params={"key": "val"},
        )
        assert step.validate() == []

    def test_validate_tool_call_missing_name(self):
        step = WorkflowStep(
            type=StepType.TOOL_CALL,
            description="Call tool",
        )
        errors = step.validate()
        assert any("missing tool_name" in e for e in errors)

    def test_validate_tool_call_params_default(self):
        step = WorkflowStep(
            type=StepType.TOOL_CALL,
            description="Call tool",
            tool_name="test",
        )
        step.validate()
        assert step.tool_params == {}

    def test_validate_conditional_valid(self):
        step = WorkflowStep(
            type=StepType.CONDITIONAL,
            description="Check",
            condition="x > 0",
        )
        assert step.validate() == []

    def test_validate_conditional_missing(self):
        step = WorkflowStep(
            type=StepType.CONDITIONAL,
            description="Check",
        )
        errors = step.validate()
        assert any("missing condition" in e for e in errors)

    def test_validate_loop_valid(self):
        step = WorkflowStep(
            type=StepType.LOOP,
            description="Iterate",
            max_iterations=5,
        )
        assert step.validate() == []

    def test_validate_loop_invalid(self):
        step = WorkflowStep(
            type=StepType.LOOP,
            description="Iterate",
            max_iterations=0,
        )
        errors = step.validate()
        assert any("max_iterations" in e for e in errors)

    def test_validate_loop_missing(self):
        step = WorkflowStep(
            type=StepType.LOOP,
            description="Iterate",
        )
        errors = step.validate()
        assert any("max_iterations" in e for e in errors)

    def test_validate_description_required(self):
        step = WorkflowStep(
            type=StepType.INSTRUCTION,
            description="",
        )
        errors = step.validate()
        assert any("description is required" in e for e in errors)

    def test_to_dict(self):
        step = WorkflowStep(
            type=StepType.INSTRUCTION,
            description="Test",
            instruction="Do it",
        )
        d = step.to_dict()
        assert d["type"] == "instruction"
        assert d["description"] == "Test"
        assert d["instruction"] == "Do it"
