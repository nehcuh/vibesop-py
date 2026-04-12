"""Base skill class and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class SkillType(Enum):
    """Types of skills."""

    PROMPT = "prompt"  # LLM prompt-based skill
    WORKFLOW = "workflow"  # Multi-step workflow
    COMMAND = "command"  # Shell command
    HYBRID = "hybrid"  # Combination of types


@dataclass
class SkillMetadata:
    """Metadata for a skill.

    Attributes:
        id: Unique skill identifier (e.g., "gstack/review")
        name: Human-readable name
        description: Short description
        intent: What the skill does (used for routing)
        namespace: Skill namespace (builtin, gstack, superpowers, project)
        version: Skill version
        author: Skill author
        tags: List of tags for categorization
        skill_type: Type of skill
        trigger_when: When to trigger this skill (extracted from description)
    """

    id: str
    name: str
    description: str
    intent: str
    namespace: str = "builtin"
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] | None = None
    skill_type: SkillType = SkillType.PROMPT
    trigger_when: str = ""
    algorithms: list[str] | None = None

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []
        if self.algorithms is None:
            self.algorithms = []


@dataclass
class SkillContext:
    """Context provided to a skill during execution.

    Attributes:
        query: User's original query
        working_dir: Current working directory
        env: Environment variables
        metadata: Additional metadata
    """

    query: str
    working_dir: Path
    env: dict[str, str] | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.env is None:
            self.env = {}
        if self.metadata is None:
            self.metadata = {}


@dataclass
class SkillResult:
    """Result from skill execution.

    Attributes:
        success: Whether execution succeeded
        output: Main output content
        error: Error message if failed
        metadata: Additional result metadata
    """

    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


class Skill(ABC):
    """Base class for all skills.

    A skill represents a reusable capability that can be invoked
    to handle specific user requests.
    """

    def __init__(self, metadata: SkillMetadata) -> None:
        """Initialize the skill.

        Args:
            metadata: Skill metadata
        """
        self._metadata = metadata

    @property
    def metadata(self) -> SkillMetadata:
        """Get skill metadata."""
        return self._metadata

    @property
    def id(self) -> str:
        """Get skill ID."""
        return self._metadata.id

    @abstractmethod
    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute the skill.

        Args:
            context: Execution context

        Returns:
            Skill execution result
        """
        ...

    def validate_context(self, context: SkillContext) -> bool:
        """Validate that the context has all required data.

        Args:
            context: Context to validate

        Returns:
            True if valid, False otherwise
        """
        return context.query is not None

    def get_prompt_template(self) -> str | None:
        """Get the prompt template for this skill.

        Returns:
            Prompt template string or None if not a prompt skill
        """
        return None


class PromptSkill(Skill):
    """A skill that uses an LLM prompt.

    Prompt skills have a template that is filled with context
    and sent to an LLM for processing.
    """

    def __init__(
        self,
        metadata: SkillMetadata,
        prompt_template: str,
        system_prompt: str | None = None,
    ) -> None:
        """Initialize the prompt skill.

        Args:
            metadata: Skill metadata
            prompt_template: Template for the user prompt
            system_prompt: Optional system prompt
        """
        super().__init__(metadata)
        self._prompt_template = prompt_template
        self._system_prompt = system_prompt

    def get_prompt_template(self) -> str:
        """Get the prompt template."""
        return self._prompt_template

    def get_system_prompt(self) -> str | None:
        """Get the system prompt."""
        return self._system_prompt

    def render_prompt(self, context: SkillContext) -> str:
        """Render the prompt template with context.

        Args:
            context: Execution context

        Returns:
            Rendered prompt string
        """
        # Simple template rendering - can be enhanced with jinja2
        prompt = self._prompt_template
        prompt = prompt.replace("{query}", context.query)
        prompt = prompt.replace("{working_dir}", str(context.working_dir))
        return prompt

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute the prompt skill.

        Note: Actual LLM calling should be done by the executor.
        This just returns the rendered prompt.

        Args:
            context: Execution context

        Returns:
            Result with rendered prompt
        """
        try:
            rendered = self.render_prompt(context)
            return SkillResult(
                success=True,
                output=rendered,
                metadata={"rendered_prompt": rendered},
            )
        except Exception as e:
            return SkillResult(
                success=False,
                output="",
                error=str(e),
            )


class WorkflowSkill(Skill):
    """A skill that executes a multi-step workflow.

    Workflow skills define a sequence of steps to execute.
    """

    def __init__(
        self,
        metadata: SkillMetadata,
        steps: list[dict[str, Any]],
    ) -> None:
        """Initialize the workflow skill.

        Args:
            metadata: Skill metadata
            steps: List of workflow steps
        """
        super().__init__(metadata)
        self._steps = steps

    @property
    def steps(self) -> list[dict[str, Any]]:
        """Get workflow steps."""
        return self._steps

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute the workflow skill.

        Args:
            context: Execution context

        Returns:
            Result from workflow execution
        """
        _ = context  # Unused in current implementation
        results = []
        for step in self._steps:
            step_type = step.get("type", "prompt")
            step_name = step.get("name", "unnamed")

            match step_type:
                case "prompt":
                    prompt = step.get("prompt", "")
                    results.append(f"[{step_name}] {prompt}")
                case "command":
                    command = step.get("command", "")
                    results.append(f"[{step_name}] Command: {command}")
                case _:
                    results.append(f"[{step_name}] Unknown step type: {step_type}")

        return SkillResult(
            success=True,
            output="\n".join(results),
            metadata={"steps_executed": len(self._steps)},
        )
