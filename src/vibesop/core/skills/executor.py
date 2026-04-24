"""External skill executor - Execute skills from external SKILL.md files.

This module provides the ability to execute skills from external skill packages
(superpowers, gstack, omx, or any third-party package), not just detect them.

**Positioning**: VibeSOP provides intelligent ROUTING and lightweight EXECUTION.

### Core Capabilities

1. **Intelligent Routing** (Primary Function):
   - Understand user intent (natural language, English + Chinese)
   - Find the best skill from 45+ available skills (94% accuracy)
   - Learn user preferences (gets better over time)

2. **Lightweight Execution** (Secondary Function):
   - Quick skill validation and testing
   - Local development and debugging
   - CI/CD automation testing

**Recommendation**: For complex production scenarios, use native AI agents
(Claude Code, Cursor, Continue.dev) which have more sophisticated execution
environments. VibeSOP's execution is optimized for quick validation and testing.

Example:
    >>> # Get skill definition (for AI agents)
    >>> executor = ExternalSkillExecutor(project_root=".")
    >>> result = executor.get_skill_definition("superpowers/tdd")
    >>> print(result.workflow.steps)  # Workflow steps for AI agent
    >>>
    >>> # Or execute locally (for testing/validation)
    >>> result = executor.execute_skill("superpowers/tdd", context={})
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from vibesop.core.exceptions import SkillNotFoundError
from vibesop.core.skills.loader import SkillLoader
from vibesop.core.skills.parser import SkillParser
from vibesop.core.skills.workflow import (
    ExecutionContext,
    Workflow,
    WorkflowEngine,
)
from vibesop.security.skill_auditor import SkillSecurityAuditor

logger = logging.getLogger(__name__)


class SkillExecutionError(Exception):
    """Raised when skill execution fails."""

    def __init__(self, message: str, skill_id: str, step: str | None = None) -> None:
        self.skill_id = skill_id
        self.step = step
        super().__init__(message)


class SecurityViolationError(Exception):
    """Raised when skill violates security policies."""

    def __init__(self, message: str, skill_id: str, violation_type: str) -> None:
        self.skill_id = skill_id
        self.violation_type = violation_type
        super().__init__(message)


class SkillResult:
    """Result of skill execution or definition retrieval.

    Attributes:
        success: Whether the operation succeeded
        skill_id: The skill identifier
        workflow: Workflow definition (if retrieved)
        output: Execution output (if executed)
        error: Error message (if failed)
        execution_time: Time taken for execution (ms)
        executed_steps: Number of steps executed (for execution results)
    """

    def __init__(
        self,
        success: bool,
        skill_id: str,
        workflow: Workflow | None = None,
        output: str | None = None,
        error: str | None = None,
        execution_time: float = 0.0,
        executed_steps: int = 0,
    ) -> None:
        self.success = success
        self.skill_id = skill_id
        self.workflow = workflow
        self.output = output
        self.error = error
        self.execution_time = execution_time
        self.executed_steps = executed_steps

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "skill_id": self.skill_id,
            "workflow": self.workflow.model_dump() if self.workflow else None,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time,
            "executed_steps": self.executed_steps,
        }


class ExternalSkillExecutor:
    """Executor for external skills from skill packages.

    This class provides two main capabilities:

    1. **Get Skill Definition**: Parse and return workflow definition
       for AI agents to execute:

       ```python
       executor = ExternalSkillExecutor()
       result = executor.get_skill_definition("superpowers/tdd")
       # Returns Workflow that AI agent can execute
       ```

    2. **Execute Skill**: Execute skill locally (for testing/validation):

       ```python
       result = executor.execute_skill("superpowers/tdd", context={})
       # Executes workflow and returns result
       ```

    **Security**:
    - All external skills are audited before loading
    - Sandboxed execution with timeout and resource limits
    - Dangerous operations are blocked

    **Architecture**:
    - Uses SkillLoader for discovery
    - Uses SkillParser for parsing SKILL.md
    - Uses WorkflowEngine for execution
    - Uses SkillAuditor for security checks
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        enable_execution: bool = True,
        execution_timeout: float = 30.0,
        loader: SkillLoader | None = None,
    ) -> None:
        """Initialize the external skill executor.

        Args:
            project_root: Project root directory
            enable_execution: Whether to enable local execution (vs. definition-only)
            execution_timeout: Maximum execution time per skill (seconds)
            loader: Optional external SkillLoader instance (for dependency injection)
        """
        self.project_root = Path(project_root).resolve()
        self.enable_execution = enable_execution
        self.execution_timeout = execution_timeout

        # Initialize dependencies (use injected loader or create new one)
        self._loader = loader or SkillLoader(project_root=self.project_root)
        self._parser = SkillParser()
        self._auditor = SkillSecurityAuditor(project_root=self.project_root)
        self._workflow_engine: WorkflowEngine | None = None

        if enable_execution:
            self._workflow_engine = WorkflowEngine(
                timeout=execution_timeout,
            )

        logger.info(
            f"ExternalSkillExecutor initialized (execution={'enabled' if enable_execution else 'disabled'})"
        )

    def get_skill_definition(self, skill_id: str) -> SkillResult:
        """Get skill workflow definition for AI agent execution.

        This method parses the skill's SKILL.md and returns the workflow
        definition that an AI agent can execute. Does NOT execute the skill.

        Args:
            skill_id: Skill identifier (e.g., "superpowers/tdd", "gstack/review")

        Returns:
            SkillResult with workflow definition

        Raises:
            SkillNotFoundError: If skill not found
            SecurityViolationError: If skill violates security policies

        Example:
            >>> executor = ExternalSkillExecutor()
            >>> result = executor.get_skill_definition("superpowers/tdd")
            >>> if result.success:
            ...     workflow = result.workflow
            ...     for step in workflow.steps:
            ...         print(f"Step: {step.type} - {step.description}")
        """
        start_time = time.time()

        try:
            # Step 1: Find skill
            logger.debug(f"Getting skill definition for: {skill_id}")
            loaded = self._loader.get_skill(skill_id)
            if not loaded:
                raise SkillNotFoundError(
                    f"Skill not found: {skill_id}. "
                    f"Use `vibe skills list` to see available skills."
                )

            # Step 2: Security audit
            if loaded.source_file:
                audit_result = self._auditor.audit_skill_file(loaded.source_file)
                if not audit_result.is_safe:
                    # Allow trusted packs through with non-critical audit issues.
                    is_trusted = (
                        loaded.external_metadata is not None
                        and getattr(loaded.external_metadata, "is_trusted", False)
                    )
                    from vibesop.security.skill_auditor import ThreatLevel

                    if is_trusted and audit_result.risk_level != ThreatLevel.CRITICAL:
                        logger.warning(
                            "Allowing trusted skill '%s' despite audit warning: %s",
                            skill_id,
                            audit_result.reason,
                        )
                    else:
                        raise SecurityViolationError(
                            f"Skill failed security audit: {audit_result.reason}",
                            skill_id=skill_id,
                            violation_type="security_audit_failed",
                        )

            # Step 3: Parse workflow
            if not loaded.source_file:
                # Built-in skill without SKILL.md file
                # Return minimal workflow from metadata
                workflow = Workflow.from_metadata(loaded.metadata)
            else:
                # External skill with SKILL.md file
                workflow = self._parser.parse_workflow(loaded.source_file)

            # Step 4: Return result
            execution_time = (time.time() - start_time) * 1000  # ms

            return SkillResult(
                success=True,
                skill_id=skill_id,
                workflow=workflow,
                execution_time=execution_time,
            )

        except (SkillNotFoundError, SecurityViolationError):
            raise
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.exception(f"Failed to get skill definition: {skill_id}")

            return SkillResult(
                success=False,
                skill_id=skill_id,
                error=str(e),
                execution_time=execution_time,
            )

    def execute_skill(
        self,
        skill_id: str,
        context: dict[str, Any] | None = None,
    ) -> SkillResult:
        """Execute skill locally (for testing/validation).

        This method executes the skill workflow locally. Primarily intended for:
        - Testing skill definitions
        - Validating workflow logic
        - CI/CD automation

        For production use, workflows should be executed by AI agents
        (Claude Code, Cursor, etc.) using get_skill_definition() instead.

        Args:
            skill_id: Skill identifier
            context: Execution context (variables, inputs, etc.)

        Returns:
            SkillResult with execution output

        Raises:
            SkillExecutionError: If execution fails
            SecurityViolationError: If skill violates security policies
            RuntimeError: If execution is disabled

        Example:
            >>> executor = ExternalSkillExecutor()
            >>> result = executor.execute_skill("superpowers/tdd", context={
            ...     "feature": "authentication",
            ... })
            >>> if result.success:
            ...     print(f"Output: {result.output}")
        """
        start_time = time.time()

        # Check if execution is enabled
        if not self.enable_execution:
            raise RuntimeError(
                "Skill execution is disabled. "
                "Use get_skill_definition() to get workflow for AI agent execution. "
                "Enable execution by passing enable_execution=True to constructor."
            )

        if not self._workflow_engine:
            raise RuntimeError("Workflow engine not initialized")

        try:
            # Step 1: Get skill definition
            logger.debug(f"Executing skill: {skill_id}")
            definition_result = self.get_skill_definition(skill_id)

            if not definition_result.success or not definition_result.workflow:
                raise SkillExecutionError(
                    f"Failed to get skill definition: {definition_result.error}",
                    skill_id=skill_id,
                )

            workflow = definition_result.workflow

            # Step 2: Create execution context
            exec_context = ExecutionContext(
                skill_id=skill_id,
                variables=context or {},
                metadata={
                    "executor": "vibesop",
                    "version": "4.1.0",
                },
            )

            # Step 3: Execute workflow
            workflow_result = self._workflow_engine.execute(workflow, exec_context)

            # Step 4: Return result
            execution_time = (time.time() - start_time) * 1000  # ms

            return SkillResult(
                success=workflow_result.success,
                skill_id=skill_id,
                workflow=workflow,
                output=workflow_result.output,
                error=workflow_result.error,
                execution_time=execution_time,
            )

        except (SkillExecutionError, SecurityViolationError):
            raise
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.exception(f"Failed to execute skill: {skill_id}")

            raise SkillExecutionError(
                f"Unexpected error during execution: {e}",
                skill_id=skill_id,
            ) from e

    def validate_skill(self, skill_id: str) -> tuple[bool, list[str]]:
        """Validate skill without executing.

        Checks:
        - Skill exists
        - SKILL.md is valid
        - Workflow is well-formed
        - Security audit passes

        Args:
            skill_id: Skill identifier

        Returns:
            (is_valid, list_of_errors)

        Example:
            >>> executor = ExternalSkillExecutor()
            >>> is_valid, errors = executor.validate_skill("superpowers/tdd")
            >>> if not is_valid:
            ...     for error in errors:
            ...         print(f"Error: {error}")
        """
        errors = []

        try:
            # Try to get skill definition
            result = self.get_skill_definition(skill_id)

            if not result.success:
                errors.append(result.error or "Unknown error")
                return False, errors

            if not result.workflow:
                errors.append("No workflow found")
                return False, errors

            # Validate workflow
            workflow_errors = result.workflow.validate_workflow()
            errors.extend(workflow_errors)

            return len(errors) == 0, errors

        except Exception as e:
            errors.append(str(e))
            return False, errors

    def list_executable_skills(self) -> list[str]:
        """List all executable skills (built-in + external).

        Returns:
            List of skill IDs that can be executed

        Example:
            >>> executor = ExternalSkillExecutor()
            >>> skills = executor.list_executable_skills()
            >>> for skill in skills:
            ...     print(f"- {skill}")
        """
        # Get all skills from loader
        loaded_skills = self._loader.list_skills()

        skill_ids = [d.metadata.id for d in loaded_skills]
        logger.debug(f"Found {len(skill_ids)} executable skills")

        return skill_ids
