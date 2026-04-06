"""Deep-interview implementation for oh-my-codex integration."""

from vibesop.core.interview.ambiguity import (
    WEIGHTS,
    AmbiguityResult,
    DimensionScore,
    compute_ambiguity,
)
from vibesop.core.interview.crystallizer import (
    write_execution_spec,
    write_interview_transcript,
)
from vibesop.core.interview.pressure import (
    CHALLENGE_PROMPTS,
    generate_challenge_question,
)
from vibesop.core.interview.stages import (
    InterviewAnswer,
    InterviewQuestion,
    InterviewStage,
    InterviewState,
)

__all__ = [
    "CHALLENGE_PROMPTS",
    "WEIGHTS",
    "AmbiguityResult",
    "DimensionScore",
    "InterviewAnswer",
    "InterviewQuestion",
    "InterviewStage",
    "InterviewState",
    "compute_ambiguity",
    "generate_challenge_question",
    "write_execution_spec",
    "write_interview_transcript",
]
