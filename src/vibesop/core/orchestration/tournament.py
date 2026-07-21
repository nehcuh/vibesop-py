"""Tournament pattern — multiple contestants, judge picks champion.

Multiple subagents solve the same problem with different approaches.
An independent judge compares their outputs and selects the champion.

Uses the same isolated-context pattern as VerifierAgent to prevent bias.

Phase 3 (v6.2.0): Full Execution Dynamic
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class TournamentConfig:
    """Configuration for tournament execution."""

    num_contestants: int = 3
    judge_rubric: list[str] = field(
        default_factory=lambda: ["completeness", "correctness", "clarity", "efficiency"]
    )


class ComparisonResult(BaseModel):
    """Result of a pairwise comparison between two contestants."""

    winner_index: int = Field(
        ...,
        description="Index of the winning contestant (>=0), or -1 if comparison was inconclusive",
    )
    scores: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Rubric scores for each contestant: {rubric: {a: score, b: score}}",
    )
    reasoning: str = Field(default="", description="Why the winner was chosen")


class TournamentResult(BaseModel):
    """Result of a tournament execution."""

    champion_index: int = Field(..., description="Index of the champion contestant")
    champion_output: str = Field(default="", description="Output from the champion")
    scores: dict[int, float] = Field(
        default_factory=dict,
        description="Total scores per contestant: {index: total_score}",
    )
    comparison_reasoning: str = Field(default="", description="Why the champion was selected")
    all_outputs: list[str] = Field(default_factory=list, description="All contestant outputs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "champion_index": self.champion_index,
            "champion_output": self.champion_output,
            "scores": self.scores,
            "comparison_reasoning": self.comparison_reasoning,
        }


class TournamentRunner:
    """Runs a tournament between multiple contestant outputs.

    Uses pairwise comparison via an independent judge. The judge receives
    only the problem description and the outputs — never the execution
    reasoning — ensuring unbiased evaluation.
    """

    def __init__(self, llm_client: Any, config: TournamentConfig | None = None):
        """Initialize the tournament runner.

        Args:
            llm_client: LLM client for judge comparisons
            config: Tournament configuration
        """
        self._llm = llm_client
        self._config = config or TournamentConfig()

    def run_tournament(
        self,
        original_query: str,
        problem_description: str,
        contestant_outputs: list[str],
    ) -> TournamentResult:
        """Run a tournament between contestant outputs.

        Args:
            original_query: The user's original query
            problem_description: The specific problem being solved
            contestant_outputs: List of outputs from each contestant

        Returns:
            TournamentResult with champion and scores
        """
        if not contestant_outputs:
            return TournamentResult(
                champion_index=0,
                champion_output="",
                scores={},
                comparison_reasoning="No contestant outputs provided",
            )

        if len(contestant_outputs) == 1:
            return TournamentResult(
                champion_index=0,
                champion_output=contestant_outputs[0],
                scores={0: 1.0},
                comparison_reasoning="Single contestant, no comparison needed",
                all_outputs=contestant_outputs,
            )

        # Run pairwise comparisons
        scores: dict[int, float] = dict.fromkeys(range(len(contestant_outputs)), 0.0)
        all_reasoning: list[str] = []

        for i in range(len(contestant_outputs)):
            for j in range(i + 1, len(contestant_outputs)):
                result = self._pairwise_compare(
                    original_query,
                    problem_description,
                    contestant_outputs[i],
                    contestant_outputs[j],
                    i,
                    j,
                )
                if result.winner_index >= 0:
                    scores[result.winner_index] += 1.0
                all_reasoning.append(
                    f"Contestant {i} vs {j}: winner={result.winner_index} ({result.reasoning})"
                )

        # Select champion (highest score)
        champion_index = max(scores, key=lambda k: scores[k])

        return TournamentResult(
            champion_index=champion_index,
            champion_output=contestant_outputs[champion_index],
            scores=scores,
            comparison_reasoning="\n".join(all_reasoning),
            all_outputs=contestant_outputs,
        )

    def _pairwise_compare(
        self,
        original_query: str,
        problem_description: str,
        output_a: str,
        output_b: str,
        index_a: int,
        index_b: int,
    ) -> ComparisonResult:
        """Compare two contestant outputs using an independent judge.

        The judge receives only the problem and outputs — no execution reasoning.
        """
        rubric_text = ", ".join(self._config.judge_rubric)
        prompt = (
            f"You are an independent judge comparing two solutions.\n\n"
            f"Original problem: {original_query}\n"
            f"Specific task: {problem_description}\n\n"
            f"Solution A (contestant {index_a}):\n{output_a[:1000]}\n\n"
            f"Solution B (contestant {index_b}):\n{output_b[:1000]}\n\n"
            f"Evaluate each solution on: {rubric_text}\n"
            f"Score each dimension 0.0-1.0 for both solutions.\n\n"
            f"Output JSON:\n"
            f'{{"winner_index": {index_a} or {index_b}, '
            f'"reasoning": "brief explanation", '
            f'"scores": {{"dimension": {{"a": score, "b": score}}}}}}\n'
            f"No markdown."
        )

        try:
            response = self._llm.call(prompt, temperature=0.1)
            content = getattr(response, "content", str(response))

            import json

            parsed = json.loads(content)
            winner = int(parsed.get("winner_index", index_a))
            if winner not in (index_a, index_b):
                winner = index_a

            return ComparisonResult(
                winner_index=winner,
                scores=parsed.get("scores", {}),
                reasoning=parsed.get("reasoning", ""),
            )
        except Exception as e:
            logger.error("Tournament pairwise comparison failed: %s", e)
            return ComparisonResult(
                winner_index=-1,
                reasoning=f"Judge failed; comparison inconclusive: {e}",
            )
