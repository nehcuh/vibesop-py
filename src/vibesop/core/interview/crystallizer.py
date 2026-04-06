"""Artifact generation for deep-interview."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from vibesop.core.interview.ambiguity import AmbiguityResult
from vibesop.core.interview.stages import InterviewState


def write_interview_transcript(
    state: InterviewState,
    ambiguity: AmbiguityResult,
    output_dir: str | Path = ".vibe/interviews",
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"interview_{timestamp}.json"
    data = {
        "timestamp": datetime.now().isoformat(),
        "task": state.task_description,
        "project_type": state.project_type,
        "profile": state.profile,
        "final_ambiguity": ambiguity.to_dict(),
        "rounds": state.round_number,
        "questions": [
            {
                "round": q.round_number,
                "dimension": q.dimension,
                "question": q.question,
                "challenge_mode": q.challenge_mode,
            }
            for q in state.questions
        ],
        "answers": [
            {
                "round": a.question.round_number,
                "dimension": a.question.dimension,
                "answer": a.answer,
            }
            for a in state.answers
        ],
    }
    with filepath.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return filepath


def write_execution_spec(
    state: InterviewState,
    ambiguity: AmbiguityResult,
    output_dir: str | Path = ".vibe/specs",
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"spec_{timestamp}.json"
    spec: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "source_interview": state.task_description,
        "clarity_score": ambiguity.clarity,
        "project_type": state.project_type,
        "dimensions": {
            dim: getattr(ambiguity, dim).score
            for dim in ["intent", "outcome", "scope", "constraints", "success"]
        },
        "evidence": {
            dim: getattr(ambiguity, dim).evidence
            for dim in ["intent", "outcome", "scope", "constraints", "success"]
        },
        "missing": {
            dim: getattr(ambiguity, dim).missing
            for dim in ["intent", "outcome", "scope", "constraints", "success"]
        },
        "recommended_next": _recommend_next(state, ambiguity),
    }
    with filepath.open("w") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
    return filepath


def _recommend_next(state: InterviewState, ambiguity: AmbiguityResult) -> str:
    if ambiguity.clarity >= 0.8:
        return "ralph"
    if ambiguity.clarity >= 0.6:
        return "ralplan"
    if state.project_type == "greenfield":
        return "deep-interview (more rounds needed)"
    return "ralplan"
