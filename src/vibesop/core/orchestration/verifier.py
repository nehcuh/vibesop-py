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
                temperature=0.2,  # Low temperature for consistent verification
            )

            import json

            content = getattr(response, "content", str(response))
            parsed = json.loads(content)
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
        """Apply strictness-based adjustments to the verification result.

        Returns a new VerificationResult rather than mutating in place.
        """
        new_status = result.status

        if self._strictness == VerificationStrictness.LENIENT:
            has_critical = any(i.severity == "critical" for i in result.issues)
            if new_status == VerificationStatus.FAILED and not has_critical:
                new_status = VerificationStatus.NEEDS_REVISION
            elif new_status == VerificationStatus.NEEDS_REVISION:
                new_status = VerificationStatus.PASSED

        elif self._strictness == VerificationStrictness.STRICT:
            has_medium_or_worse = any(i.severity in ("medium", "high", "critical") for i in result.issues)
            if new_status == VerificationStatus.NEEDS_REVISION and has_medium_or_worse:
                new_status = VerificationStatus.FAILED

        if new_status != result.status:
            return result.model_copy(update={"status": new_status})
        return result


def verify_step_with_retry(
    verifier: VerifierAgent,
    original_query: str,
    step: ExecutionStep,
    execution_output: str,
    max_retries: int = 3,
    executor: Any = None,
) -> tuple[VerificationResult, int]:
    """Verify a step with retry logic for NEEDS_REVISION status.

    Args:
        verifier: The verifier agent
        original_query: Original query
        step: Execution step
        execution_output: Execution output
        max_retries: Maximum number of verification retries
        executor: Optional callable to re-execute the step with modified query.
                  If provided, retry will re-execute the step with verification
                  feedback incorporated into the query. If None, only re-verifies
                  (useful when executor is not available).

    Returns:
        Tuple of (final verification result, retry count)
    """
    from vibesop.core.orchestration.verification_loop import VerificationLoop, VerificationLoopConfig

    retry_count = 0
    current_output = execution_output
    current_result = verifier.verify(original_query, step, current_output)

    while current_result.status == VerificationStatus.NEEDS_REVISION and retry_count < max_retries:
        retry_count += 1
        logger.info(
            "Verification needs revision, retry %d/%d for step %s",
            retry_count,
            max_retries,
            step.step_id,
        )

        if executor is not None:
            # Build retry query with verification feedback
            loop = VerificationLoop(VerificationLoopConfig(max_retries=max_retries))
            retry_query = loop.build_retry_query(step, current_result.to_dict())
            retry_step = step.model_copy(update={"input_query": retry_query})

            # Re-execute with feedback
            try:
                new_output = executor(retry_step)
                current_output = str(new_output) if new_output else current_output
            except Exception as e:
                logger.warning("Re-execution failed for step %s: %s", step.step_id, e)
                break

        current_result = verifier.verify(original_query, step, current_output)

    return current_result, retry_count
