"""Autonomous experiment system for self-improvement.

This module implements the autoresearch philosophy:
- Run experiments automatically
- Record results
- Extract patterns (instincts)
- Improve over time

Inspired by karpathy/autoresearch - "研究即代码"
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class ExperimentStatus(Enum):
    """Status of an experiment iteration."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DISCARDED = "discarded"


@dataclass
class RubricScore:
    """Score for a single rubric dimension."""

    dimension: str
    score: float  # 0-10
    weight: float
    reasoning: str = ""

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class ExperimentResult:
    """Result of a single experiment iteration."""

    iteration: int
    hypothesis: str
    prediction: dict[str, float]  # dimension -> predicted score
    actual_scores: list[RubricScore]
    changes_made: list[str]
    commit_hash: str | None = None
    status: ExperimentStatus = ExperimentStatus.PENDING
    error_message: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def compound_score(self) -> float:
        """Calculate weighted compound score."""
        if not self.actual_scores:
            return 0.0
        return sum(s.weighted_score for s in self.actual_scores)

    @property
    def prediction_accuracy(self) -> float:
        """Calculate how accurate the prediction was."""
        if not self.actual_scores or not self.prediction:
            return 0.0

        total_error = 0.0
        count = 0
        for score in self.actual_scores:
            predicted = self.prediction.get(score.dimension, score.score)
            error = abs(score.score - predicted)
            total_error += error
            count += 1

        # Accuracy = 1 - normalized error (max error is 10)
        if count == 0:
            return 0.0
        avg_error = total_error / count
        return max(0.0, 1.0 - (avg_error / 10.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "hypothesis": self.hypothesis,
            "prediction": self.prediction,
            "actual_scores": [
                {
                    "dimension": s.dimension,
                    "score": s.score,
                    "weight": s.weight,
                    "reasoning": s.reasoning,
                }
                for s in self.actual_scores
            ],
            "compound_score": self.compound_score,
            "prediction_accuracy": self.prediction_accuracy,
            "changes_made": self.changes_made,
            "commit_hash": self.commit_hash,
            "status": self.status.value,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Belief:
    """A belief about what works."""

    id: str
    description: str
    evidence: list[tuple[int, bool]] = field(default_factory=list)  # (iteration, was_correct)
    confidence: float = 0.5  # 0-1
    created_at: datetime = field(default_factory=datetime.now)

    def update(self, iteration: int, was_correct: bool) -> None:
        """Update belief based on new evidence."""
        self.evidence.append((iteration, was_correct))
        # Simple confidence calculation: ratio of correct predictions
        if self.evidence:
            correct = sum(1 for _, was_right in self.evidence if was_right)
            self.confidence = correct / len(self.evidence)

    @property
    def is_reliable(self) -> bool:
        """Whether this belief is reliable (enough evidence and high confidence)."""
        return len(self.evidence) >= 3 and self.confidence >= 0.6


@dataclass
class ExperimentConfig:
    """Configuration for an autonomous experiment."""

    domain: str
    objective: str
    rubric: list[dict[str, Any]]  # Each has id, weight, description
    modifiable_files: list[str]
    readonly_files: list[str]
    test_command: str | None = None
    max_iterations: int = 15
    stale_threshold: int = 5
    must_pass_tests: bool = True

    @classmethod
    def from_yaml(cls, path: Path) -> ExperimentConfig:
        """Load config from experiment.yaml."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)

        return cls(
            domain=data["domain"],
            objective=data["objective"]["description"],
            rubric=data["objective"]["evaluator"]["rubric"],
            modifiable_files=data["scope"]["modifiable"],
            readonly_files=data["scope"].get("readonly", []),
            test_command=data["scope"].get("test_command"),
            max_iterations=data["constraints"].get("max_iterations", 15),
            stale_threshold=data["constraints"].get("stale_threshold", 5),
            must_pass_tests=data["constraints"].get("must_pass_tests", True),
        )


class AutonomousExperimentRunner:
    """Runner for autonomous experiments.

    Implements the predict-attribute cycle from autoresearch:
    1. Make prediction
    2. Modify code
    3. Measure results
    4. Compare prediction vs actual
    5. Keep or discard
    6. Update beliefs
    """

    def __init__(
        self,
        config: ExperimentConfig,
        experiment_dir: Path | None = None,
    ):
        self.config = config
        self.experiment_dir = experiment_dir or Path(".experiment")
        self.experiment_dir.mkdir(exist_ok=True)

        self.results_file = self.experiment_dir / "results.tsv"
        self.beliefs_file = self.experiment_dir / "beliefs.md"
        self.state_file = self.experiment_dir / "state.json"

        self.iteration = 0
        self.baseline_score: float | None = None
        self.best_score: float | None = None
        self.best_commit: str | None = None
        self.beliefs: list[Belief] = []
        self.results: list[ExperimentResult] = []
        self.consecutive_no_improvement = 0

        self._load_state()
        self._load_beliefs()

    def _load_state(self) -> None:
        """Load experiment state from disk."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                state = json.load(f)
                self.iteration = state.get("iteration", 0)
                self.baseline_score = state.get("baseline_score")
                self.best_score = state.get("best_score")
                self.best_commit = state.get("best_commit")
                self.consecutive_no_improvement = state.get("consecutive_no_improvement", 0)

    def _save_state(self) -> None:
        """Save experiment state to disk."""
        state = {
            "iteration": self.iteration,
            "baseline_score": self.baseline_score,
            "best_score": self.best_score,
            "best_commit": self.best_commit,
            "consecutive_no_improvement": self.consecutive_no_improvement,
            "domain": self.config.domain,
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _load_beliefs(self) -> None:
        """Load beliefs from beliefs.md."""
        if not self.beliefs_file.exists():
            return

        content = self.beliefs_file.read_text()

        # Parse beliefs from markdown
        # Format: ## Belief ID
        # Description
        # Evidence: iteration:result,iteration:result
        # Confidence: 0.75

        belief_pattern = r"##\s+(\w+)\n(.*?)(?=##\s+|\Z)"
        for match in re.finditer(belief_pattern, content, re.DOTALL):
            belief_id = match.group(1)
            belief_text = match.group(2)

            # Extract confidence
            confidence_match = re.search(r"Confidence:\s+(\d\.\d+)", belief_text)
            confidence = float(confidence_match.group(1)) if confidence_match else 0.5

            # Extract evidence
            evidence_match = re.search(r"Evidence:\s+(.*)", belief_text)
            evidence = []
            if evidence_match:
                for pair in evidence_match.group(1).split(","):
                    if ":" in pair:
                        it, result = pair.strip().split(":")
                        evidence.append((int(it), result.lower() == "true"))

            belief = Belief(
                id=belief_id,
                description=belief_text.split("\n")[0].strip(),
                evidence=evidence,
                confidence=confidence,
            )
            self.beliefs.append(belief)

    def _save_beliefs(self) -> None:
        """Save beliefs to beliefs.md."""
        lines = [
            "# Experiment Beliefs\n",
            f"Domain: {self.config.domain}\n",
            f"Updated: {datetime.now().isoformat()}\n\n",
        ]

        # Sort by confidence
        sorted_beliefs = sorted(self.beliefs, key=lambda b: b.confidence, reverse=True)

        for belief in sorted_beliefs[:20]:  # Keep max 20
            lines.append(f"## {belief.id}\n")
            lines.append(f"{belief.description}\n\n")
            lines.append(f"Confidence: {belief.confidence:.2f}\n")
            evidence_str = ",".join(f"{it}:{result}" for it, result in belief.evidence)
            lines.append(f"Evidence: {evidence_str}\n\n")

        self.beliefs_file.write_text("".join(lines))

    def _save_result_tsv(self, result: ExperimentResult) -> None:
        """Append result to results.tsv."""
        import csv

        file_exists = self.results_file.exists()

        with open(self.results_file, "a", newline="") as f:
            writer = csv.writer(f, delimiter="\t")

            if not file_exists:
                # Write header
                writer.writerow(
                    [
                        "iteration",
                        "hypothesis",
                        "compound_score",
                        "prediction_accuracy",
                        "status",
                        "timestamp",
                    ]
                )

            writer.writerow(
                [
                    result.iteration,
                    result.hypothesis[:100],  # Truncate
                    f"{result.compound_score:.2f}",
                    f"{result.prediction_accuracy:.2f}",
                    result.status.value,
                    result.timestamp.isoformat(),
                ]
            )

    def establish_baseline(self) -> float:
        """Run evaluator on unmodified code to establish baseline."""
        print("🔬 Establishing baseline...")

        scores = self._run_evaluator()
        self.baseline_score = sum(s.weighted_score for s in scores)
        self.best_score = self.baseline_score

        print(f"   Baseline score: {self.baseline_score:.2f}")

        # Save baseline result
        result = ExperimentResult(
            iteration=0,
            hypothesis="Baseline (no changes)",
            prediction={},
            actual_scores=scores,
            changes_made=[],
            status=ExperimentStatus.SUCCESS,
        )
        self.results.append(result)
        self._save_result_tsv(result)
        self._save_state()

        return self.baseline_score

    def _run_evaluator(self) -> list[RubricScore]:
        """Run evaluator and return scores."""
        scores = []

        for rubric_item in self.config.rubric:
            dimension = rubric_item["id"]
            weight = rubric_item.get("weight", 1.0 / len(self.config.rubric))
            description = rubric_item.get("description", "")

            # For now, use agent_judge mode - return placeholder
            # In real implementation, this would call the actual evaluator
            scores.append(
                RubricScore(
                    dimension=dimension,
                    score=5.0,  # Placeholder - should be actual evaluation
                    weight=weight,
                    reasoning=f"Evaluated: {description}",
                )
            )

        return scores

    def _run_tests(self) -> tuple[bool, str]:
        """Run tests if configured."""
        if not self.config.test_command:
            return True, ""

        try:
            result = subprocess.run(
                self.config.test_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Tests timed out"
        except Exception as e:
            return False, str(e)

    def _get_git_commit(self) -> str | None:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except Exception:
            return None

    def run_iteration(
        self, hypothesis: str, prediction: dict[str, float], changes: list[str]
    ) -> ExperimentResult:
        """Run a single experiment iteration.

        Args:
            hypothesis: What we're testing
            prediction: Predicted scores per dimension
            changes: List of files changed

        Returns:
            ExperimentResult with actual scores and comparison
        """
        self.iteration += 1
        print(f"\n🔄 Iteration {self.iteration}/{self.config.max_iterations}")
        print(f"   Hypothesis: {hypothesis}")
        print(f"   Prediction: {prediction}")

        # Run tests if required
        if self.config.must_pass_tests:
            tests_passed, test_output = self._run_tests()
            if not tests_passed:
                print(f"   ❌ Tests failed")
                result = ExperimentResult(
                    iteration=self.iteration,
                    hypothesis=hypothesis,
                    prediction=prediction,
                    actual_scores=[],
                    changes_made=changes,
                    status=ExperimentStatus.FAILED,
                    error_message=f"Tests failed: {test_output[:200]}",
                )
                self.results.append(result)
                self._save_result_tsv(result)
                return result

        # Run evaluator
        actual_scores = self._run_evaluator()
        commit_hash = self._get_git_commit()

        result = ExperimentResult(
            iteration=self.iteration,
            hypothesis=hypothesis,
            prediction=prediction,
            actual_scores=actual_scores,
            changes_made=changes,
            commit_hash=commit_hash,
            status=ExperimentStatus.SUCCESS,
        )

        print(f"   Actual score: {result.compound_score:.2f}")
        print(f"   Prediction accuracy: {result.prediction_accuracy:.2%}")

        # Decide keep or discard
        if self.best_score is None or result.compound_score > self.best_score:
            print(f"   ✅ KEEP - New best score!")
            self.best_score = result.compound_score
            self.best_commit = commit_hash
            self.consecutive_no_improvement = 0
        else:
            print(f"   ❌ DISCARD - No improvement")
            result.status = ExperimentStatus.DISCARDED
            self.consecutive_no_improvement += 1

        self.results.append(result)
        self._save_result_tsv(result)
        self._save_state()

        return result

    def update_beliefs(self, result: ExperimentResult) -> None:
        """Update beliefs based on experiment result."""
        # Extract beliefs from hypothesis
        # For now, simple approach: each hypothesis becomes a belief

        belief_id = f"belief_{self.iteration}"

        # Find or create belief
        belief = next((b for b in self.beliefs if b.description == result.hypothesis), None)
        if not belief:
            belief = Belief(
                id=belief_id,
                description=result.hypothesis,
            )
            self.beliefs.append(belief)

        # Update with evidence
        was_correct = result.prediction_accuracy > 0.7
        belief.update(self.iteration, was_correct)

        self._save_beliefs()

    def should_continue(self) -> bool:
        """Check if we should continue the experiment loop."""
        if self.iteration >= self.config.max_iterations:
            print(f"\n🏁 Max iterations ({self.config.max_iterations}) reached")
            return False

        if self.consecutive_no_improvement >= self.config.stale_threshold:
            print(f"\n⏹️  Stale threshold ({self.config.stale_threshold}) reached - no improvement")
            return False

        return True

    def get_summary(self) -> dict[str, Any]:
        """Get experiment summary."""
        successful = [r for r in self.results if r.status == ExperimentStatus.SUCCESS]
        kept = [
            r
            for r in self.results
            if r.status == ExperimentStatus.SUCCESS and r.compound_score == self.best_score
        ]

        # Top beliefs
        reliable_beliefs = [b for b in self.beliefs if b.is_reliable]

        return {
            "total_iterations": self.iteration,
            "baseline_score": self.baseline_score,
            "best_score": self.best_score,
            "improvement": (self.best_score or 0) - (self.baseline_score or 0),
            "successful_iterations": len(successful),
            "kept_iterations": len(kept),
            "reliable_beliefs": len(reliable_beliefs),
            "best_commit": self.best_commit,
            "beliefs": [
                {
                    "id": b.id,
                    "description": b.description,
                    "confidence": b.confidence,
                    "evidence_count": len(b.evidence),
                }
                for b in sorted(reliable_beliefs, key=lambda x: x.confidence, reverse=True)[:5]
            ],
        }

    def print_summary(self) -> None:
        """Print experiment summary."""
        summary = self.get_summary()

        print("\n" + "=" * 60)
        print("📊 EXPERIMENT SUMMARY")
        print("=" * 60)
        print(f"Total iterations: {summary['total_iterations']}")
        print(f"Baseline score: {summary['baseline_score']:.2f}")
        print(f"Best score: {summary['best_score']:.2f}")
        print(f"Improvement: {summary['improvement']:+.2f}")
        print(f"Reliable beliefs: {summary['reliable_beliefs']}")

        if summary["beliefs"]:
            print("\nTop beliefs:")
            for b in summary["beliefs"]:
                print(f"  • {b['description'][:60]}... (confidence: {b['confidence']:.2f})")

        if summary["best_commit"]:
            print(f"\n🏆 Best commit: {summary['best_commit'][:8]}")
            print(f"   To apply: git cherry-pick {summary['best_commit']}")


# Convenience functions


def create_experiment_config(
    domain: str,
    objective: str,
    rubric: list[dict[str, Any]],
    modifiable_files: list[str],
    **kwargs,
) -> ExperimentConfig:
    """Create an experiment configuration."""
    return ExperimentConfig(
        domain=domain,
        objective=objective,
        rubric=rubric,
        modifiable_files=modifiable_files,
        **kwargs,
    )


def run_autonomous_experiment(config: ExperimentConfig) -> AutonomousExperimentRunner:
    """Run a complete autonomous experiment.

    Example:
        config = create_experiment_config(
            domain="skill-optimization",
            objective="Optimize routing accuracy",
            rubric=[
                {"id": "accuracy", "weight": 0.5, "description": "Routing accuracy"},
                {"id": "speed", "weight": 0.3, "description": "Response time"},
                {"id": "clarity", "weight": 0.2, "description": "Output clarity"},
            ],
            modifiable_files=["src/vibesop/core/routing/unified.py"],
        )

        runner = run_autonomous_experiment(config)
        runner.establish_baseline()

        while runner.should_continue():
            result = runner.run_iteration(
                hypothesis="Increase TF-IDF weight",
                prediction={"accuracy": 8.5, "speed": 7.0, "clarity": 8.0},
                changes=["src/vibesop/core/routing/unified.py"],
            )
            runner.update_beliefs(result)

        runner.print_summary()
    """
    runner = AutonomousExperimentRunner(config)
    return runner
