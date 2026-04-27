"""Step context injector — manages context passing between orchestration steps.

When a StepManifest says "step 2 depends on step 1's output",
this module resolves that dependency by:
1. Reading the output saved from upstream steps
2. Injecting it into the downstream step's context
3. Generating a single execution sequence file the agent can follow

This bridges the gap between "here's a plan" and "here's everything
you need to execute it, including upstream results".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibesop.core.models import ExecutionManifest


DEFAULT_MARKER_TEMPLATE = "<!-- {marker} --> {summary}"


@dataclass
class StepOutput:
    """Captured output from a completed step."""

    step_number: int
    skill_id: str
    completion_marker: str
    summary: str
    full_output: str


class StepContextInjector:
    """Manages context injection and output collection for orchestration.

    Works with ExecutionManifest to:
    - Generate a self-contained execution sequence file
    - Save step outputs for downstream consumption
    - Prepare enriched context for each step

    Example:
        >>> injector = StepContextInjector(project_root=Path.cwd())
        >>> # Generate the sequence file for an agent to follow
        >>> seq_file = injector.build_sequence_file(manifest)
        >>> print(seq_file.read_text())
        >>> # After step 1 completes, save its output
        >>> injector.save_step_output(manifest.plan_id, 1, "Architecture: 9 modules found")
        >>> # Step 2 now gets step 1's output as input_context
        >>> ctx = injector.prepare_step_context(manifest, 2)
    """

    def __init__(self, project_root: str | Path = "."):
        self._project_root = Path(project_root).resolve()
        self._plans_dir = self._project_root / ".vibe" / "plans"

    def build_sequence_file(self, manifest: ExecutionManifest) -> Path:
        """Generate a self-contained execution sequence file.

        Writes a markdown file at `.vibe/plans/{plan_id}/execution_sequence.md`
        that contains every step's SKILL.md content and dependency annotations.
        The AI agent can read this single file to execute all steps.

        Args:
            manifest: The execution manifest to serialize

        Returns:
            Path to the generated sequence file
        """
        plan_dir = self._plan_dir(manifest.plan_id)
        plan_dir.mkdir(parents=True, exist_ok=True)

        seq_file = plan_dir / "execution_sequence.md"
        seq_file.write_text(manifest.to_markdown(), encoding="utf-8")

        return seq_file

    def save_step_output(
        self,
        plan_id: str,
        step_number: int,
        summary: str,
        full_output: str = "",
        skill_id: str = "",
        marker: str = "",
    ) -> StepOutput:
        """Save a step's output to disk for downstream steps.

        Args:
            plan_id: Plan UUID
            step_number: Which step completed
            summary: Brief summary of the step's result
            full_output: Complete step output text
            skill_id: The skill that was executed
            marker: The completion marker that was matched

        Returns:
            StepOutput dataclass
        """
        output = StepOutput(
            step_number=step_number,
            skill_id=skill_id,
            completion_marker=marker,
            summary=summary,
            full_output=full_output,
        )

        plan_dir = self._plan_dir(plan_id)
        plan_dir.mkdir(parents=True, exist_ok=True)

        output_file = plan_dir / f"step_{step_number}_output.json"
        output_file.write_text(
            json.dumps(
                {
                    "step_number": output.step_number,
                    "skill_id": output.skill_id,
                    "completion_marker": output.completion_marker,
                    "summary": output.summary,
                    "full_output": output.full_output,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return output

    def load_step_output(self, plan_id: str, step_number: int) -> StepOutput | None:
        """Load a previously saved step output.

        Args:
            plan_id: Plan UUID
            step_number: Which step to load

        Returns:
            StepOutput if found, None otherwise
        """
        output_file = self._plan_dir(plan_id) / f"step_{step_number}_output.json"
        if not output_file.exists():
            return None

        try:
            data = json.loads(output_file.read_text(encoding="utf-8"))
            return StepOutput(
                step_number=data.get("step_number", step_number),
                skill_id=data.get("skill_id", ""),
                completion_marker=data.get("completion_marker", ""),
                summary=data.get("summary", ""),
                full_output=data.get("full_output", ""),
            )
        except (json.JSONDecodeError, OSError):
            return None

    def prepare_step_context(
        self,
        manifest: ExecutionManifest,
        step_number: int,
    ) -> str:
        """Prepare enriched context for executing a specific step.

        Resolves upstream dependencies by loading saved outputs
        and injecting them as input context.

        Args:
            manifest: The execution manifest
            step_number: Which step to prepare context for (1-based)

        Returns:
            Enriched context string for the agent prompt
        """
        step = None
        for s in manifest.steps:
            if s.step_number == step_number:
                step = s
                break

        if step is None:
            return f"[Error: step {step_number} not found in manifest]"

        parts: list[str] = []

        if step.input_context:
            parts.append(f"## Input Context (from upstream steps)\n\n{step.input_context}\n")

        parts.append(f"## Step {step_number}: {step.skill_id}\n")

        if step.skill_name:
            parts.append(f"**Skill**: {step.skill_name}\n")

        parts.append(f"\n{step.instruction}\n")

        if step.skill_content:
            parts.append(
                f"\n## Skill Definition ({step.skill_id})\n\n```markdown\n{step.skill_content}\n```\n"
            )

        parts.append(
            f"\nWhen done, output: `<!-- {step.completion_marker} -->` followed by a summary.\n"
        )

        return "\n".join(parts)

    def get_step_output_summaries(self, plan_id: str) -> dict[int, str]:
        """Get summaries of all completed steps in a plan.

        Args:
            plan_id: Plan UUID

        Returns:
            Dict mapping step_number -> summary string
        """
        plan_dir = self._plan_dir(plan_id)
        summaries: dict[int, str] = {}

        if not plan_dir.exists():
            return summaries

        for output_file in sorted(plan_dir.glob("step_*_output.json")):
            step_num = int(output_file.stem.split("_")[1])
            output = self.load_step_output(plan_id, step_num)
            if output:
                summaries[step_num] = output.summary

        return summaries

    def build_final_summary(self, plan_id: str, manifest: ExecutionManifest) -> str:
        """Build a final execution summary combining all step outputs.

        Args:
            plan_id: Plan UUID
            manifest: The execution manifest

        Returns:
            Final summary markdown
        """
        summaries = self.get_step_output_summaries(plan_id)

        lines = [
            f"# Orchestration Complete: {manifest.original_query}",
            "",
            f"**Plan**: {manifest.plan_id}",
            f"**Steps completed**: {len(summaries)}/{manifest.total_steps}",
            "",
            "---",
            "",
        ]

        for i in range(1, manifest.total_steps + 1):
            step = manifest.steps[i - 1]
            status = "completed" if i in summaries else "pending"
            icon = "\u2705" if status == "completed" else "\u23f3"
            lines.append(f"### {icon} Step {i}: {step.skill_id}")
            if i in summaries:
                lines.append(f"**Result**: {summaries[i]}")
            else:
                lines.append("**Result**: Not completed")
            lines.append("")

        return "\n".join(lines)

    def _plan_dir(self, plan_id: str) -> Path:
        return self._plans_dir / plan_id


__all__ = [
    "DEFAULT_MARKER_TEMPLATE",
    "StepContextInjector",
    "StepOutput",
]
