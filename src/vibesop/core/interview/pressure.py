"""Pressure ladder and challenge modes for deep-interview."""

from __future__ import annotations

from vibesop.core.interview.stages import InterviewQuestion

CHALLENGE_PROMPTS = {
    "contrarian": [
        "What if the opposite approach is actually better?",
        "What assumptions are you making that might be wrong?",
        "If this fails, what's the most likely reason?",
    ],
    "simplifier": [
        "Can this be done in half the steps?",
        "What's the simplest thing that could work?",
        "What parts can you remove without losing value?",
    ],
    "ontologist": [
        "What category of problem is this really?",
        "Are you solving the right problem or just the visible symptom?",
        "What would need to be true for this to be trivial?",
    ],
}


def generate_challenge_question(mode: str, dimension: str, round_number: int) -> InterviewQuestion:
    prompts = CHALLENGE_PROMPTS.get(mode, CHALLENGE_PROMPTS["contrarian"])
    prompt = prompts[(round_number - 1) % len(prompts)]
    return InterviewQuestion(
        dimension=dimension,
        question=f"[{mode.upper()} CHALLENGE] {prompt}",
        round_number=round_number,
        challenge_mode=mode,
    )
