"""Workflow execution engine for skill definitions.

This module provides the workflow model and execution engine for skills defined
in SKILL.md files. Workflows are sequences of steps that AI agents can execute.

**Positioning**: This is NOT a workflow execution system for VibeSOP itself.
VibeSOP does NOT execute workflows - it parses and validates them, then
provides structured definitions to AI agents (Claude Code, Cursor, etc.) for execution.

The WorkflowEngine in this module is provided for:
- Testing and validation of workflow definitions
- CI/CD automation
- Local development and debugging

Production execution should be done by AI agents using the workflow definition.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    import re

logger = logging.getLogger(__name__)


class StepType(StrEnum):
    """Type of workflow step."""

    INSTRUCTION = "instruction"  # Text instruction for AI
    VERIFICATION = "verification"  # Verification step
    TOOL_CALL = "tool_call"  # Call a specific tool
    CONDITIONAL = "conditional"  # Conditional branch
    LOOP = "loop"  # Loop construct


@dataclass
class WorkflowStep:
    """A single step in a workflow.

    Attributes:
        type: Step type
        description: Human-readable description
        instruction: Detailed instruction (for instruction steps)
        tool_name: Tool to call (for tool_call steps)
        tool_params: Parameters for tool call (for tool_call steps)
        condition: Condition expression (for conditional steps)
        condition_value: Value to compare (for conditional steps)
        max_iterations: Maximum loop iterations (for loop steps)
    """

    type: StepType
    description: str
    instruction: str | None = None
    tool_name: str | None = None
    tool_params: dict[str, Any] | None = None
    condition: str | None = None
    condition_value: Any = None
    max_iterations: int | None = None

    def validate(self) -> list[str]:
        """Validate step configuration.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Common validation
        if not self.description:
            errors.append("Step description is required")

        # Type-specific validation
        if self.type == StepType.INSTRUCTION:
            if not self.instruction:
                errors.append(f"Instruction step '{self.description}' missing instruction")

        elif self.type == StepType.TOOL_CALL:
            if not self.tool_name:
                errors.append(f"Tool call step '{self.description}' missing tool_name")
            if self.tool_params is None:
                self.tool_params = {}

        elif self.type == StepType.CONDITIONAL:
            if not self.condition:
                errors.append(f"Conditional step '{self.description}' missing condition")

        elif self.type == StepType.LOOP and (not self.max_iterations or self.max_iterations <= 0):
            errors.append(f"Loop step '{self.description}' requires max_iterations > 0")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "description": self.description,
            "instruction": self.instruction,
            "tool_name": self.tool_name,
            "tool_params": self.tool_params,
            "condition": self.condition,
            "condition_value": self.condition_value,
            "max_iterations": self.max_iterations,
        }


class Workflow(BaseModel):
    """Workflow definition for a skill.

    A workflow is a sequence of steps that define how a skill should be executed.
    This model represents the parsed workflow from SKILL.md files.

    Attributes:
        skill_id: Skill identifier
        name: Workflow name
        description: Workflow description
        steps: Sequence of workflow steps
        metadata: Additional metadata
    """

    skill_id: str
    name: str
    description: str
    steps: list[WorkflowStep] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("steps")
    @classmethod
    def steps_not_empty(cls, v: list[WorkflowStep]) -> list[WorkflowStep]:
        """Validate that workflow has at least one step."""
        if not v:
            raise ValueError("Workflow must have at least one step")
        return v

    def validate_workflow(self) -> list[str]:
        """Validate workflow configuration.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Validate each step
        for i, step in enumerate(self.steps):
            step_errors = step.validate()
            for error in step_errors:
                errors.append(f"Step {i + 1}: {error}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": self.metadata,
        }

    @classmethod
    def from_metadata(cls, definition: Any) -> Workflow:
        """Create minimal workflow from skill metadata.

        Used for built-in skills that don't have SKILL.md files.
        """
        return cls(
            skill_id=definition.id,
            name=definition.name,
            description=definition.description,
            steps=[
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description=definition.description,
                    instruction=definition.intent or definition.description,
                )
            ],
            metadata={
                "source": "metadata",
                "namespace": definition.namespace,
            },
        )


@dataclass
class ExecutionContext:
    """Context for workflow execution.

    Attributes:
        skill_id: Skill being executed
        variables: Variables accessible to workflow
        metadata: Execution metadata
        step_index: Current step index (during execution)
        outputs: Accumulated outputs from steps
    """

    skill_id: str
    variables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    step_index: int = 0
    outputs: list[str] = field(default_factory=list)

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get variable value."""
        return self.variables.get(name, default)

    def set_variable(self, name: str, value: Any) -> None:
        """Set variable value."""
        self.variables[name] = value

    def add_output(self, output: str) -> None:
        """Add output from a step."""
        self.outputs.append(output)


@dataclass
class WorkflowResult:
    """Result of workflow execution.

    Attributes:
        success: Whether execution succeeded
        output: Combined output from all steps
        error: Error message (if failed)
        executed_steps: Number of steps executed
        final_context: Final execution context
    """

    success: bool
    output: str
    error: str | None = None
    executed_steps: int = 0
    final_context: ExecutionContext | None = None


class TimeoutError(Exception):
    """Raised when workflow execution times out."""


class WorkflowEngine:
    """Workflow execution engine.

    This engine executes workflows for testing and validation purposes.
    Production execution should be done by AI agents.

    Features:
    - Execute workflow steps sequentially
    - Handle conditional branches
    - Handle loops (with iteration limits)
    - Timeout enforcement
    - Error handling and recovery
    - Variable substitution
    - Expression evaluation

    Example:
        >>> engine = WorkflowEngine(timeout=30.0)
        >>> context = ExecutionContext(skill_id="test", variables={"x": 1})
        >>> result = engine.execute(workflow, context)
        >>> print(result.output)
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_steps: int = 100,
        enable_tools: bool = False,
    ) -> None:
        """Initialize workflow engine.

        Args:
            timeout: Maximum execution time (seconds)
            max_steps: Maximum number of steps to execute
            enable_tools: Whether to enable actual tool execution (vs. placeholders)
        """
        self.timeout = timeout
        self.max_steps = max_steps
        self.enable_tools = enable_tools
        self._execution_count = 0
        self._tool_registry: dict[str, Any] = {}

        # Register built-in tools
        self._register_builtin_tools()

    def _register_builtin_tools(self) -> None:
        """Register built-in tool implementations."""
        # Built-in tools for testing
        self._tool_registry = {
            "echo": self._tool_echo,
            "set": self._tool_set,
            "get": self._tool_get,
            "log": self._tool_log,
        }

    def _tool_echo(self, **kwargs: Any) -> str:
        """Echo tool - returns input as output."""
        return str(kwargs)

    def _tool_set(self, name: str, value: Any, context: ExecutionContext) -> str:
        """Set variable tool."""
        context.set_variable(name, value)
        return f"Set {name} = {value}"

    def _tool_get(self, name: str, context: ExecutionContext) -> str:
        """Get variable tool."""
        value = context.get_variable(name, "<not set>")
        return f"{name} = {value}"

    def _tool_log(self, message: str, **_kwargs: Any) -> str:
        """Log tool."""
        logger.info(f"Workflow log: {message}")
        return f"Logged: {message}"

    def register_tool(self, name: str, func: Any) -> None:
        """Register a custom tool.

        Args:
            name: Tool name
            func: Tool function (should accept **kwargs and return str)
        """
        self._tool_registry[name] = func
        logger.debug(f"Registered tool: {name}")

    def execute(
        self,
        workflow: Workflow,
        context: ExecutionContext,
    ) -> WorkflowResult:
        """Execute workflow with timeout using ThreadPoolExecutor.

        Args:
            workflow: Workflow to execute
            context: Execution context

        Returns:
            WorkflowResult

        Raises:
            ValueError: If workflow is invalid
        """
        # Validate workflow
        errors = workflow.validate_workflow()
        if errors:
            raise ValueError(f"Invalid workflow: {'; '.join(errors)}")

        # Define internal execution function
        def _execute_internal():
            """Internal execution in separate thread."""
            outputs = []
            executed_steps = 0

            for i, step in enumerate(workflow.steps):
                if i >= self.max_steps:
                    logger.warning(f"Reached max steps ({self.max_steps}), stopping")
                    break

                context.step_index = i
                logger.debug(f"Executing step {i + 1}/{len(workflow.steps)}: {step.description}")

                try:
                    step_output = self._execute_step(step, context)
                    if step_output:
                        outputs.append(step_output)
                        context.add_output(step_output)
                        executed_steps += 1
                except Exception as e:
                    logger.exception(f"Step {i + 1} failed: {step.description}")
                    # Continue with next step on error
                    outputs.append(f"[Step {i + 1} failed: {e}]")

            # Success
            return WorkflowResult(
                success=True,
                output="\n".join(outputs),
                executed_steps=executed_steps,
                final_context=context,
            )

        # Use ThreadPoolExecutor to execute with timeout
        from concurrent.futures import ThreadPoolExecutor
        from concurrent.futures import TimeoutError as FutureTimeoutError

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_execute_internal)

            try:
                result = future.result(timeout=self.timeout)
                return result

            except FutureTimeoutError:
                # Cancel the task (best effort)
                future.cancel()

                logger.error(f"Workflow execution timed out: {workflow.skill_id}")
                return WorkflowResult(
                    success=False,
                    output="",
                    error=f"Execution timed out after {self.timeout}s",
                    executed_steps=0,
                )

            except Exception as e:
                logger.exception(f"Workflow execution failed: {workflow.skill_id}")
                return WorkflowResult(
                    success=False,
                    output="",
                    error=str(e),
                    executed_steps=0,
                )

    def _execute_step(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
    ) -> str | None:
        """Execute a single workflow step.

        Args:
            step: Step to execute
            context: Execution context

        Returns:
            Step output (if any)
        """
        if step.type == StepType.INSTRUCTION:
            return self._execute_instruction(step, context)

        elif step.type == StepType.VERIFICATION:
            return self._execute_verification(step, context)

        elif step.type == StepType.TOOL_CALL:
            return self._execute_tool_call(step, context)

        elif step.type == StepType.CONDITIONAL:
            return self._execute_conditional(step, context)

        elif step.type == StepType.LOOP:
            return self._execute_loop(step, context)

        else:
            logger.warning(f"Unknown step type: {step.type}")
            return None

    def _execute_instruction(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
    ) -> str:
        """Execute instruction step.

        Instruction steps are for AI agents to follow.
        In local execution, we perform variable substitution and return the instruction.

        Args:
            step: Instruction step
            context: Execution context

        Returns:
            Processed instruction string
        """
        logger.debug(f"Instruction: {step.instruction}")

        instruction = step.instruction or step.description

        # Perform variable substitution
        instruction = self._substitute_variables(instruction, context)

        # In local execution, return instruction as output
        # In AI agent execution, agent would follow the instruction
        return instruction

    def _execute_verification(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
    ) -> str:
        """Execute verification step.

        Verification steps check conditions or validate results.
        Can evaluate simple expressions against context variables.

        Args:
            step: Verification step
            context: Execution context

        Returns:
            Verification result message
        """
        logger.debug(f"Verification: {step.description}")

        instruction = step.instruction or step.description

        # Check if instruction contains a condition to evaluate
        # Simple format: "Verify that {variable} == {value}"
        if "==" in instruction or "!=" in instruction or "in" in instruction:
            try:
                result = self._evaluate_condition(instruction, context)
                status = "✓" if result else "✗"
                return f"{status} Verified: {step.description} ({result})"
            except Exception as e:
                logger.debug(f"Could not evaluate verification: {e}")

        # For now, just return verification message
        # In production, this would check actual conditions
        return f"✓ Verified: {step.description}"

    def _execute_tool_call(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
    ) -> str:
        """Execute tool call step.

        If enable_tools is True, attempts to call actual registered tools.
        Otherwise, returns a placeholder message.

        Args:
            step: Tool call step
            context: Execution context

        Returns:
            Tool execution result
        """
        logger.debug(f"Tool call: {step.tool_name}")

        if not step.tool_name:
            return "Error: No tool specified"

        if self.enable_tools and step.tool_name in self._tool_registry:
            # Call actual tool
            tool_func = self._tool_registry[step.tool_name]
            params = step.tool_params or {}

            try:
                # Inject context if tool expects it
                import inspect

                sig = inspect.signature(tool_func)
                if "context" in sig.parameters:
                    result = tool_func(**params, context=context)
                else:
                    result = tool_func(**params)

                return f"[{step.tool_name}: {result}]"
            except Exception as e:
                return f"[{step.tool_name} error: {e}]"
        else:
            # Return placeholder
            params_str = ", ".join(f"{k}={v}" for k, v in (step.tool_params or {}).items())
            if params_str:
                return f"[Would call: {step.tool_name}({params_str})]"
            else:
                return f"[Would call: {step.tool_name}]"

    def _execute_conditional(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
    ) -> str | None:
        """Execute conditional step.

        Evaluates the condition and returns message if true.
        Supports simple equality checks and boolean logic.

        Args:
            step: Conditional step
            context: Execution context

        Returns:
            Condition result message, or None if condition not met
        """
        if not step.condition:
            # No condition specified, check instruction
            instruction = step.instruction or step.description
            if " if " in instruction.lower():
                return self._execute_conditional_from_instruction(instruction, context)
            return None

        logger.debug(f"Evaluating condition: {step.condition}")

        # Get variable value
        variable_value = context.get_variable(step.condition)

        # Evaluate condition
        condition_met = False
        if step.condition_value is not None:
            condition_met = variable_value == step.condition_value
        else:
            # Truthiness check
            condition_met = bool(variable_value)

        if condition_met:
            message = f"Condition met: {step.condition} = {variable_value}"
            if step.instruction:
                instruction = self._substitute_variables(step.instruction, context)
                message += f"\n{instruction}"
            return message
        else:
            logger.debug(
                f"Condition not met: {step.condition} = {variable_value} (expected {step.condition_value})"
            )
            return None

    def _execute_conditional_from_instruction(
        self,
        instruction: str,
        context: ExecutionContext,
    ) -> str | None:
        """Execute conditional from natural language instruction.

        Args:
            instruction: Instruction containing "if" clause
            context: Execution context

        Returns:
            Result message if condition met, None otherwise
        """
        # Simple pattern matching for common conditional patterns
        # e.g., "If x == 1, do something"
        import re

        pattern = r"if\s+(\w+)\s*(==|!=|>|<|>=|<=)\s*(\S+),?\s*(.+)"
        match = re.search(pattern, instruction, re.IGNORECASE)

        if match:
            var_name, op, value_str, action = match.groups()
            var_value = context.get_variable(var_name)

            # Try to convert value to appropriate type
            try:
                if value_str.isdigit():
                    value = int(value_str)
                elif value_str.replace(".", "", 1).isdigit():
                    value = float(value_str)
                elif value_str.lower() in ("true", "false"):
                    value = value_str.lower() == "true"
                else:
                    value = value_str.strip("\"'")
            except ValueError:
                value = value_str

            # Evaluate condition
            condition_met = False
            if op == "==":
                condition_met = var_value == value
            elif op == "!=":
                condition_met = var_value != value
            elif op == ">":
                condition_met = var_value is not None and bool(var_value > value)
            elif op == "<":
                condition_met = var_value is not None and bool(var_value < value)
            elif op == ">=":
                condition_met = var_value is not None and bool(var_value >= value)
            elif op == "<=":
                condition_met = var_value is not None and bool(var_value <= value)

            if condition_met:
                return f"Condition met: {var_name} {op} {value}\n{action}"
            else:
                logger.debug(f"Condition not met: {var_name} {op} {value} (actual: {var_value})")
                return None

        return None

    def _execute_loop(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
    ) -> str:
        """Execute loop step.

        Simulates loop execution by reporting what would happen.
        In production, would execute loop body multiple times.

        Args:
            step: Loop step
            context: Execution context

        Returns:
            Loop execution summary
        """
        if not step.max_iterations:
            return "Error: No max_iterations specified"

        logger.debug(f"Loop: {step.description} (max {step.max_iterations} iterations)")

        # Check if there's a variable to iterate over
        instruction = step.instruction or step.description
        loop_var = None
        items: list[Any] = []

        # Try to extract "for each {var} in {list}" pattern
        import re

        pattern = r"for\s+each\s+(\w+)\s+in\s+(\w+)"
        match = re.search(pattern, instruction, re.IGNORECASE)

        if match:
            loop_var = match.group(1)
            list_name = match.group(2)
            items = context.get_variable(list_name, [])

            if not isinstance(items, list):  # pyright: ignore[reportUnnecessaryIsInstance]
                return f"Error: {list_name} is not a list"

            # Simulate loop execution
            results = []
            for i, item in enumerate(items[: step.max_iterations]):
                context.set_variable(loop_var, item)
                results.append(f"  Iteration {i + 1}: {loop_var} = {item}")

            return f"Loop: {step.description}\n" + "\n".join(results)

        # Default: just return loop info
        # In production, would execute loop body
        return f"[Loop: {step.description} - would execute up to {step.max_iterations} times]"

    def _substitute_variables(
        self,
        text: str,
        context: ExecutionContext,
    ) -> str:
        """Substitute variables in text.

        Supports {variable} syntax.

        Args:
            text: Text with variable placeholders
            context: Execution context

        Returns:
            Text with variables substituted
        """
        import re

        def replace_var(match: re.Match[str]) -> str:
            var_name = match.group(1)
            value = context.get_variable(var_name, "")
            return str(value)

        return re.sub(r"\{(\w+)\}", replace_var, text)

    def _evaluate_condition(self, condition: str, context: ExecutionContext) -> bool:
        """Evaluate a simple condition string using safe AST parsing.

        Supports basic operators: ==, !=, >, <, >=, <=, in, and, or, not

        Args:
            condition: Condition string
            context: Execution context

        Returns:
            True if condition evaluates to True, False otherwise
        """
        # Substitute variables first
        condition = self._substitute_variables(condition, context)

        try:
            # Parse condition into AST
            tree = ast.parse(condition, mode="eval")

            # Define allowed AST node types (whitelist)
            ALLOWED_NODE_TYPES = {
                # Root node
                ast.Expression,
                # Literals and names
                ast.Constant,  # Numbers, strings, booleans, None
                ast.Name,  # Variable names
                ast.Load,  # Name loading context (required for variable access)
                # Operators
                ast.Compare,  # Comparisons (==, !=, <, >, <=, >=, in, not in, is, is not)
                ast.BoolOp,  # Boolean operations (and, or)
                ast.UnaryOp,  # Unary operations (not, +, -)
                ast.BinOp,  # Binary operations (+, -, *, /, //, %, **)
                # Operator types
                ast.And,  # and operator
                ast.Or,  # or operator
                ast.Not,  # not operator
                ast.Add,  # +
                ast.Sub,  # -
                ast.Mult,  # *
                ast.Div,  # /
                ast.FloorDiv,  # //
                ast.Mod,  # %
                ast.Pow,  # **
                ast.UAdd,  # unary +
                ast.USub,  # unary -
                ast.Eq,  # ==
                ast.NotEq,  # !=
                ast.Lt,  # <
                ast.LtE,  # <=
                ast.Gt,  # >
                ast.GtE,  # >=
                ast.In,  # in
                ast.Is,  # is
                ast.IsNot,  # is not
                # Function calls (restricted to safe functions)
                ast.Call,
                ast.Attribute,  # For accessing attributes (limited use)
                # Collection literals
                ast.List,  # List literals [1, 2, 3]
                ast.Tuple,  # Tuple literals (1, 2, 3)
                ast.Set,  # Set literals {1, 2, 3}
                ast.Dict,  # Dict literals {"key": "value"}
                ast.ListComp,  # List comprehensions [x for x in ...]
            }

            # Define allowed built-in functions
            ALLOWED_FUNCTIONS = {
                # Type conversions
                "len",
                "str",
                "int",
                "float",
                "bool",
                "list",
                "dict",
                "tuple",
                "set",
                # Math
                "abs",
                "min",
                "max",
                "sum",
                "round",
                "pow",
                # Iteration
                "any",
                "all",
                "enumerate",
                "zip",
                "filter",
                "map",
                # Type checks
                "isinstance",
                "hasattr",
                "getattr",
                # String operations
                "ord",
                "chr",
            }

            # Walk the AST and verify all nodes are safe
            for node in ast.walk(tree):
                if not isinstance(node, tuple(ALLOWED_NODE_TYPES)):
                    logger.error(f"Unsafe AST node type: {type(node).__name__}")
                    return False

                # Extra check for function calls
                if isinstance(node, ast.Call):
                    # Only allow calls to whitelisted functions
                    if isinstance(node.func, ast.Name):
                        if node.func.id not in ALLOWED_FUNCTIONS:
                            logger.error(f"Function not allowed: {node.func.id}")
                            return False

                        # Extra security for getattr: only allow literal string arguments
                        if node.func.id == "getattr":
                            # Require exactly 2 arguments
                            if len(node.args) < 2:
                                logger.error("getattr requires exactly 2 arguments")
                                return False

                            # Second argument MUST be a literal string (not a variable)
                            if not isinstance(node.args[1], ast.Constant):
                                logger.error(
                                    "getattr requires literal attribute name (not a variable)"
                                )
                                return False

                            # Check if the literal string is a special attribute
                            attr_name = str(node.args[1].value)
                            if attr_name.startswith("__"):
                                logger.error(f"getattr special attribute not allowed: {attr_name}")
                                return False
                    else:
                        # Don't allow complex calls like obj.method()
                        logger.error(f"Complex call not allowed: {ast.dump(node)}")
                        return False

                # Extra check for attribute access
                if (
                    isinstance(node, ast.Attribute)
                    and node.attr.startswith("__")
                    and node.attr.endswith("__")
                ):
                    logger.error(f"Special attribute access not allowed: {node.attr}")
                    return False

            # Prepare evaluation context
            eval_context = {
                "True": True,
                "False": False,
                "None": None,
            }

            # Add allowed built-in functions to context
            import builtins

            safe_builtins = {}
            for func_name in ALLOWED_FUNCTIONS:
                if hasattr(builtins, func_name):
                    safe_builtins[func_name] = getattr(builtins, func_name)

            # Add variables from context
            if context and context.variables:
                eval_context.update(context.variables)

            # Compile and evaluate the AST
            code = compile(tree, "<string>", "eval")
            result = eval(code, {"__builtins__": safe_builtins}, eval_context)

            return bool(result)

        except (SyntaxError, ValueError, TypeError) as e:
            logger.debug(f"Could not evaluate condition '{condition}': {e}")
            return False
        except Exception as exc:
            logger.exception(f"Unexpected error evaluating condition '{condition}': {exc}")
            return False


def parse_workflow_from_markdown(markdown_content: str, skill_id: str) -> Workflow:
    """Parse workflow from SKILL.md markdown content.

    Enhanced parser that extracts workflow information from markdown files.
    Supports multiple step formats and structures.

    Args:
        markdown_content: Raw markdown content
        skill_id: Skill identifier

    Returns:
        Parsed Workflow

    Example:
        >>> with open("SKILL.md") as f:
        ...     content = f.read()
        >>> workflow = parse_workflow_from_markdown(content, "my-skill")
    """
    lines = markdown_content.split("\n")

    # Extract metadata from frontmatter if present
    name = skill_id
    description = ""
    metadata = {}
    steps = []

    # Parse frontmatter
    if markdown_content.startswith("---"):
        try:
            from vibesop.core.skills.parser import extract_frontmatter

            frontmatter, _body = extract_frontmatter(markdown_content)
            if frontmatter:
                name = frontmatter.get("name", name)
                description = frontmatter.get("description", "")
                metadata.update(frontmatter)
        except (ValueError, TypeError, IndexError):
            # If frontmatter parsing fails, continue with body
            markdown_content.split("---", 2)[-1] if "---" in markdown_content else markdown_content

    # Look for sections
    current_section = None
    current_step_content = []  # Content for current step
    step_number = 0
    in_step = False
    last_step_was_numbered = False  # Track if last step was numbered

    for _i, line in enumerate(lines):
        stripped = line.strip()
        original = line  # Keep original for indentation check

        # Skip empty lines and frontmatter markers
        if not stripped or stripped == "---":
            continue

        # Headers
        if stripped.startswith("# "):
            if not name or name == skill_id:
                name = stripped[2:].strip()
        elif stripped.startswith("## "):
            current_section = stripped[3:].strip()
            current_step_content = []
            step_number = 0
            in_step = False
            last_step_was_numbered = False
            continue

        # Description (before first section)
        elif not current_section and not stripped.startswith("#"):
            if description:
                description += " " + stripped
            else:
                description = stripped
            in_step = False
            last_step_was_numbered = False

        # In a section (where steps live)
        elif current_section:
            # Check if this is a new step (numbered)
            is_numbered = any(stripped.startswith(f"{i}.") for i in range(1, 10))
            # Check if this is a bullet point (could be sub-step or independent step)
            is_bulleted = stripped.startswith(("-", "*")) and not stripped.startswith("--")

            # Check indentation to distinguish sub-steps from independent steps
            is_indented = original.startswith("    ") or original.startswith("\t")

            if is_numbered:
                # Save previous step if exists
                if step_number > 0 and current_step_content:
                    step_desc = current_step_content[0]
                    step_instruction = (
                        "\n".join(current_step_content[1:]) if len(current_step_content) > 1 else ""
                    )

                    # Detect step type
                    step_type = _detect_step_type(step_desc, step_instruction)

                    steps.append(
                        WorkflowStep(
                            type=step_type,
                            description=step_desc,
                            instruction=step_instruction or step_desc,
                        )
                    )

                # Start new numbered step
                step_number += 1
                current_step_content = []

                # Extract step description
                step_desc = stripped
                for num in range(1, 10):
                    if step_desc.startswith(f"{num}."):
                        step_desc = step_desc[2:].strip()
                        break
                current_step_content.append(step_desc)
                in_step = True
                last_step_was_numbered = True

            elif is_bulleted and not is_indented:
                # Non-indented bullet point
                # If the last step was numbered, this is a sub-step
                if last_step_was_numbered and step_number > 0:
                    # This is a sub-step (bullet point under a numbered step)
                    bullet_text = stripped[1:].strip()
                    current_step_content.append(bullet_text)
                else:
                    # This is an independent bullet-point step
                    # Save previous step if exists
                    if step_number > 0 and current_step_content:
                        step_desc = current_step_content[0]
                        step_instruction = (
                            "\n".join(current_step_content[1:])
                            if len(current_step_content) > 1
                            else ""
                        )

                        step_type = _detect_step_type(step_desc, step_instruction)

                        steps.append(
                            WorkflowStep(
                                type=step_type,
                                description=step_desc,
                                instruction=step_instruction or step_desc,
                            )
                        )

                    # Start new step
                    step_number += 1
                    current_step_content = [stripped[1:].strip()]
                    in_step = True
                    last_step_was_numbered = False

            # Content lines (after a step)
            elif in_step and step_number > 0:
                # Add to current step content
                # Include non-empty lines that aren't new steps
                if stripped:
                    current_step_content.append(stripped)

    # Don't forget the last step!
    if step_number > 0 and current_step_content:
        step_desc = current_step_content[0]
        step_instruction = (
            "\n".join(current_step_content[1:]) if len(current_step_content) > 1 else ""
        )

        step_type = _detect_step_type(step_desc, step_instruction)

        steps.append(
            WorkflowStep(
                type=step_type,
                description=step_desc,
                instruction=step_instruction or step_desc,
            )
        )

    # If no steps found, create single instruction step
    if not steps:
        # Try to extract steps from description
        if description:
            steps.append(
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description=name,
                    instruction=description,
                )
            )
        else:
            # Fallback
            steps.append(
                WorkflowStep(
                    type=StepType.INSTRUCTION,
                    description=skill_id,
                    instruction=f"Execute {skill_id}",
                )
            )

    return Workflow(
        skill_id=skill_id,
        name=name,
        description=description.strip(),
        steps=steps,
        metadata=metadata,
    )


def _detect_step_type(description: str, instruction: str) -> StepType:
    """Detect step type from description and instruction.

    Uses conservative matching to avoid false positives.
    Default to INSTRUCTION unless there's a clear signal.

    Args:
        description: Step description
        instruction: Step instruction

    Returns:
        Detected StepType
    """
    import re

    text = (description + " " + instruction).lower()

    # Flexible matching: call/invoke/use + [words] + tool (within 5 words)
    # This catches "Call the read tool" but avoids false positives
    tool_call_pattern = r"\b(call|invoke|use)\s+(\w+\s+){0,4}tool\b"
    if re.search(tool_call_pattern, text):
        return StepType.TOOL_CALL

    # Strict matching: must contain conditional keyword + structure
    if text.startswith(("if ", "when ")) and any(
        k in text for k in ["condition", "otherwise", "else"]
    ):
        return StepType.CONDITIONAL

    # Strict matching: loop patterns
    if any(pattern in text for pattern in ["for each", "while ", "repeat until", "loop through"]):
        return StepType.LOOP

    # Strict matching: verification patterns
    if any(
        pattern in text for pattern in ["verify that", "check that", "validate that", "ensure that"]
    ):
        return StepType.VERIFICATION

    return StepType.INSTRUCTION
