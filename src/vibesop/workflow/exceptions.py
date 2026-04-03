"""
Workflow exception definitions.

This module defines all exceptions used throughout the workflow system.
"""

from pydantic import BaseModel
from typing import Any
from datetime import datetime


class WorkflowError(Exception):
    """Base exception for workflow errors."""

    def __init__(
        self,
        message: str,
        workflow_name: str | None = None,
        context: dict[str, Any] | None = None
    ):
        self.message = message
        self.workflow_name = workflow_name
        self.context = context or {}
        self.timestamp = datetime.now()
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.workflow_name:
            return f"[{self.workflow_name}] {self.message}"
        return self.message


class StageError(WorkflowError):
    """Exception raised when a stage fails."""

    def __init__(
        self,
        message: str,
        stage_name: str,
        workflow_name: str | None = None,
        context: dict[str, Any] | None = None
    ):
        self.stage_name = stage_name
        super().__init__(message, workflow_name, context)

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} (Stage: {self.stage_name})"


class WorkflowValidationError(WorkflowError):
    """Exception raised when workflow validation fails."""

    def __init__(
        self,
        message: str,
        validation_errors: list[str] | None = None,
        workflow_name: str | None = None
    ):
        self.validation_errors = validation_errors or []
        super().__init__(message, workflow_name, {"validation_errors": self.validation_errors})


class WorkflowRecoveryError(WorkflowError):
    """Exception raised when workflow recovery fails."""

    def __init__(
        self,
        message: str,
        workflow_id: str | None = None,
        recovery_action: str | None = None
    ):
        self.workflow_id = workflow_id
        self.recovery_action = recovery_action
        context = {
            "workflow_id": workflow_id,
            "recovery_action": recovery_action
        }
        super().__init__(message, None, context)


__all__ = [
    "WorkflowError",
    "StageError",
    "WorkflowValidationError",
    "WorkflowRecoveryError",
]
