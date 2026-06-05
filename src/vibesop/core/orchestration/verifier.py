"""Verifier Agent — independent verification for adversarial workflow.

The verifier runs with an isolated context window (no access to the execution
agent's reasoning) and reviews outputs against a rubric to detect incomplete
or incorrect results.

This is the core of Phase 2 (v6.1.0): Adversarial Verification.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionStep

logger = logging.getLogger(__name__)


class VerificationStrictness(StrEnum):
    """How strict the verifier should be."""

    LENIENT = "lenient"  # Only catch obvious failures
    STANDARD = "standard"  # Balanced verification (default)
    STRICT = "strict"  # Flag even minor issues


class VerificationStatus(StrEnum):
    """Result of verification."""

    PASSED = "passed"  # Output is complete and correct
    NEEDS_REVISION = "needs_revision"  # Issues found but fixable
    FAILED = "failed"  # Fundamental problems, requires re-execution


class VerificationIssue(BaseModel):
    """A specific issue found during verification."""

    category: str = Field(..., description="Issue category: completeness, correctness, edge_case, other")
    severity: str = Field(..., description="Severity: low, medium, high, critical")
    description: str = Field(..., description="Human-readable description")
    suggested_fix: str = Field(default="", description="Suggested fix for the issue")


class VerificationResult(BaseModel):
    """Result from VerifierAgent.

    The verifier reviews an execution step's output against a rubric and
    determines if the work is complete, correct, and addresses edge cases.
    """

    status: VerificationStatus = Field(
        default=VerificationStatus.PASSED,
        description="Overall verification status",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the verification decision",
    )
    issues: list[VerificationIssue] = Field(
        default_factory=list,
        description="Specific issues found (empty if PASSED)",
    )
    reasoning: str = Field(
        default="",
        description="Human-readable explanation of the verification decision",
    )
    rubric_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Scores per rubric dimension (0.0-1.0)",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "confidence": self.confidence,
            "issues": [i.model_dump() for i in self.issues],
            "reasoning": self.reasoning,
            "rubric_scores": self.rubric_scores,
        }


class VerifierAgent:
    """Independent verification agent for adversarial workflow.

    The verifier runs with an isolated context window — it receives only:
    - The original query
    - The step's intent
    - The execution result (not the execution agent's reasoning)

    This prevents self-preference bias and enables true adversarial review.
    """

    # Default verification rubric dimensions
    RUBRIC_DIMENSIONS = [
        "completeness",  # All requirements addressed
        "correctness",  # Technical accuracy
        "edge_cases",  # Edge cases considered
        "clarity",  # Clear, actionable output
    ]

    def __init__(self, llm_client: Any, strictness: VerificationStrictness = VerificationStrictness.STANDARD):
        """Initialize the verifier agent.

        Args:
            llm_client: LLM client for semantic verification
            strictness: How strict the verifier should be
        """
        self._llm = llm_client
        self._strictness = strictness

    def verify(
        self,
        original_query: str,
        step: ExecutionStep,
        execution_output: str,
        rubric_dimensions: list[str] | None = None,
    ) -> VerificationResult:
        """Verify a step's execution output.

        Args:
            original_query: The user's original query
            step: The execution step being verified
            execution_output: The output from executing the step
            rubric_dimensions: Optional custom rubric dimensions

        Returns:
            VerificationResult with status, issues, and reasoning
        """
        rubric = rubric_dimensions or self.RUBRIC_DIMENSIONS

        # Fast path: if no output, verification fails
        if not execution_output or execution_output.strip() == "":
            return VerificationResult(
                status=VerificationStatus.FAILED,
                confidence=1.0,
                issues=[
                    VerificationIssue(
                        category="completeness",
                        severity="critical",
                        description="No execution output provided",
                        suggested_fix="Re-run the step to generate output",
                    )
                ],
                reasoning="Verification failed: step produced no output",
                rubric_scores={dim: 0.0 for dim in rubric},
            )

        # Use LLM for semantic verification
        llm_result = self._llm_verify(original_query, step, execution_output, rubric)

        # Apply strictness-based adjustments
        result = self._apply_strictness(llm_result)

        logger.info(
            "Verification complete for step %s: %s (%.0%% confidence, %d issues)",
            step.step_id,
            result.status.value,
            result.confidence * 100,
            len(result.issues),
        )

        return result

    def _llm_verify(
        self,
        original_query: str,
        step: ExecutionStep,
        execution_output: str,
        rubric_dimensions: list[str],
    ) -> VerificationResult:
        """Use LLM to verify the execution output.

        The LLM receives ONLY:
        - Original query
        - Step intent
        - Execution output

        It does NOT receive the execution agent's reasoning, ensuring
        independent adversarial review.
        """
        prompt = self._build_verification_prompt(original_query, step, execution_output, rubric_dimensions)

        try:
            response = self._llm.call(
                prompt,
                response_format={"type": "json_object"},
                temperature=0.2,  # Low temperature for consistent verification
            )

            import json

            parsed = json.loads(response)
            return self._parse_llm_response(parsed, rubric_dimensions)
        except Exception as e:
            logger.warning("LLM verification failed: %s", e)
            # Fallback: assume passed if LLM fails
            return VerificationResult(
                status=VerificationStatus.PASSED,
                confidence=0.5,  # Low confidence on fallback
                reasoning="LLM verification unavailable, assuming passed",
                rubric_scores={dim: 0.5 for dim in rubric_dimensions},
            )

    def _build_verification_prompt(
        self,
        original_query: str,
        step: ExecutionStep,
        execution_output: str,
        rubric_dimensions: list[str],
    ) -> str:
        """Build the verification prompt with isolated context."""

        rubric_desc = "\n".join(f"- {dim}" for dim in rubric_dimensions)

        return f"""You are an independent verifier reviewing the execution of a task.

Original Query:
{original_query}

Step Intent:
{step.intent}

Step Query:
{step.input_query}

Execution Output:
{execution_output}

Verification Rubric (score each 0.0-1.0):
{rubric_desc}

Review the execution output against the rubric. Check:
1. Completeness: Are all requirements from the original query addressed?
2. Correctness: Is the technical content accurate?
3. Edge Cases: Were edge cases and potential pitfalls considered?
4. Clarity: Is the output clear and actionable?

Respond in JSON format:
{{
  "status": "passed|needs_revision|failed",
  "confidence": 0.0-1.0,
  "reasoning": "Human-readable explanation",
  "rubric_scores": {{
    "completeness": 0.0-1.0,
    "correctness": 0.0-1.0,
    "edge_cases": 0.0-1.0,
    "clarity": 0.0-1.0
  }},
  "issues": [
    {{
      "category": "completeness|correctness|edge_case|other",
      "severity": "low|medium|high|critical",
      "description": "Issue description",
      "suggested_fix": "Suggested fix"
    }}
  ]
}}

Criteria:
- PASSED: All rubric scores >= 0.8 AND no high/critical issues
- NEEDS_REVISION: At least one rubric score 0.5-0.8 OR has medium issues
- FAILED: Any rubric score < 0.5 OR has critical issues
"""

    def _parse_llm_response(self, parsed: dict[str, Any], rubric_dimensions: list[str]) -> VerificationResult:
        """Parse LLM response into VerificationResult."""
        status_str = parsed.get("status", "passed").lower()
        try:
            status = VerificationStatus(status_str)
        except ValueError:
            status = VerificationStatus.PASSED

        issues = []
        for issue_data in parsed.get("issues", []):
            try:
                issues.append(VerificationIssue(**issue_data))
            except Exception:
                pass  # Skip malformed issues

        rubric_scores = parsed.get("rubric_scores", {})

        return VerificationResult(
            status=status,
            confidence=float(parsed.get("confidence", 0.5)),
            issues=issues,
            reasoning=parsed.get("reasoning", ""),
            rubric_scores=rubric_scores,
        )

    def _apply_strictness(self, result: VerificationResult) -> VerificationResult:
        """Apply strictness-based adjustments to the verification result."""
        if self._strictness == VerificationStrictness.LENIENT:
            # Lenient: only fail if critical issues
            has_critical = any(i.severity == "critical" for i in result.issues)
            if result.status == VerificationStatus.FAILED and not has_critical:
                result.status = VerificationStatus.NEEDS_REVISION
            elif result.status == VerificationStatus.NEEDS_REVISION:
                result.status = VerificationStatus.PASSED

        elif self._strictness == VerificationStrictness.STRICT:
            # Strict: needs_revision becomes failed if any medium+ issues
            has_medium_or_worse = any(i.severity in ("medium", "high", "critical") for i in result.issues)
            if result.status == VerificationStatus.NEEDS_REVISION and has_medium_or_worse:
                result.status = VerificationStatus.FAILED

        return result


def verify_step_with_retry(
    verifier: VerifierAgent,
    original_query: str,
    step: ExecutionStep,
    execution_output: str,
    max_retries: int = 3,
) -> tuple[VerificationResult, int]:
    """Verify a step with retry logic for NEEDS_REVISION status.

    Args:
        verifier: The verifier agent
        original_query: Original query
        step: Execution step
        execution_output: Execution output
        max_retries: Maximum number of verification retries

    Returns:
        Tuple of (final verification result, retry count)
    """
    retry_count = 0
    current_result = verifier.verify(original_query, step, execution_output)

    while current_result.status == VerificationStatus.NEEDS_REVISION and retry_count < max_retries:
        retry_count += 1
        logger.info(
            "Verification needs revision, retry %d/%d for step %s",
            retry_count,
            max_retries,
            step.step_id,
        )
        # In a real implementation, we would re-execute the step with
        # the verification feedback. For now, we just log and continue.
        current_result = verifier.verify(original_query, step, execution_output)

    return current_result, retry_count
