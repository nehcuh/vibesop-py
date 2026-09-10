"""Blocked plans must never exit any orchestration path as handoff-ready.

Covers the 8.3.1 fail-close invariant for CLI/persist/read exits:
orchestrate post-process, prompt-chain generation, `vibe plan` list /
complete-step, and the OrchestrationResult.has_match contract.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
import typer
from rich.console import Console

from vibesop.cli.commands import plan_cmd
from vibesop.cli.main import (
    _execute_plan_interactive,
    _handle_prompt_chain_output,
    _orchestration_confirmation_flow,
    _orchestration_post_process,
)
from vibesop.core.models import (
    ExecutionPlan,
    ExecutionStep,
    OrchestrationMode,
    OrchestrationResult,
)
from vibesop.core.orchestration import PlanTracker


def make_plan(tmp_path: Path, *, healthy: bool) -> ExecutionPlan:
    path = tmp_path / "impl-skill" / "SKILL.md"
    if healthy:
        path.parent.mkdir()
        path.write_text("# Workflow\nInspect inputs and verify the result.\n", encoding="utf-8")
    step = ExecutionStep(
        step_id="s1",
        step_number=1,
        skill_id="impl-skill",
        skill_file=str(path),
        intent="Implement",
        input_query="Build the thing",
    )
    return ExecutionPlan(
        plan_id="blocked-exit-plan", original_query="Build the thing", steps=[step]
    )


def make_result(tmp_path: Path, *, healthy: bool) -> OrchestrationResult:
    return OrchestrationResult(
        mode=OrchestrationMode.ORCHESTRATED,
        original_query="Build the thing",
        execution_plan=make_plan(tmp_path, healthy=healthy),
    )


class TestHasMatchContract:
    def test_blocked_plan_is_not_a_match(self, tmp_path):
        plan = make_plan(tmp_path, healthy=False)
        plan.metadata["execution_ready"] = False
        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query="q",
            execution_plan=plan,
        )
        assert result.has_match is False

    def test_ready_plan_is_a_match(self, tmp_path):
        plan = make_plan(tmp_path, healthy=True)
        plan.metadata["execution_ready"] = True
        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query="q",
            execution_plan=plan,
        )
        assert result.has_match is True

    def test_unannotated_plan_defaults_to_no_match(self, tmp_path):
        plan = make_plan(tmp_path, healthy=True)
        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query="q",
            execution_plan=plan,
        )
        assert result.has_match is False


class TestPostProcess:
    def test_blocked_human_path_persists_truth_and_skips_plan_ready(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = make_result(tmp_path, healthy=False)
        console = Console(file=io.StringIO(), force_terminal=False)
        _orchestration_post_process(result, router=None, json_output=False, console=console)
        output = console.file.getvalue()
        assert "Plan ready" not in output
        assert "Do not execute" in output

        lines = (
            (tmp_path / ".vibe" / "execution_plans.jsonl").read_text(encoding="utf-8").splitlines()
        )
        assert lines
        persisted = json.loads(lines[-1])
        assert persisted["metadata"]["execution_ready"] is False
        assert persisted["metadata"]["blocked_steps"]

    def test_blocked_json_path_demotes(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        result = make_result(tmp_path, healthy=False)
        console = Console(file=io.StringIO(), force_terminal=False)
        _orchestration_post_process(result, router=None, json_output=True, console=console)
        payload = json.loads(capsys.readouterr().out)
        assert payload["has_match"] is False
        assert payload["notice_only"] is True
        assert "Do not execute" in payload["notice"]

    def test_ready_human_path_prints_plan_ready(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = make_result(tmp_path, healthy=True)
        console = Console(file=io.StringIO(), force_terminal=False)
        _orchestration_post_process(result, router=None, json_output=False, console=console)
        assert "Plan ready" in console.file.getvalue()


class TestConfirmationFlowGate:
    def test_blocked_plan_never_offered_for_confirmation(self, tmp_path):
        result = make_result(tmp_path, healthy=False)
        console = Console(file=io.StringIO(), force_terminal=False)
        confirmed = _orchestration_confirmation_flow(
            result, yes=False, execute=False, json_output=False, console=console, router=None
        )
        assert confirmed is False
        assert "Do not execute" in console.file.getvalue()


class TestExecuteInteractiveGate:
    def test_blocked_plan_prints_notice_and_returns(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = make_result(tmp_path, healthy=False)
        console = Console(file=io.StringIO(), force_terminal=False)
        _execute_plan_interactive(result, console)
        assert "Do not execute" in console.file.getvalue()

    def test_manifest_refusal_persists_blocked_state(self, tmp_path, monkeypatch):
        """K-3: a post-gate build_manifest refusal must persist the blocked
        snapshot so `vibe plan show/status` see the truth, not a stale
        ready snapshot."""
        monkeypatch.chdir(tmp_path)
        plan = make_plan(tmp_path, healthy=True)
        plan.metadata["execution_ready"] = True
        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query="Build the thing",
            execution_plan=plan,
        )

        class _RefusingExecutor:
            def __init__(self, project_root):
                pass

            def build_manifest(self, plan):
                # Mimic block_plan_step: record the refusal on the plan, then
                # raise the same diagnostic PlanExecutor raises.
                plan.metadata["execution_ready"] = False
                plan.metadata["blocked_steps"] = [
                    {"step_number": 1, "skill_id": "impl-skill", "reason": "unsafe content"}
                ]
                raise ValueError("blocked notice text")

        monkeypatch.setattr("vibesop.agent.runtime.plan_executor.PlanExecutor", _RefusingExecutor)
        console = Console(file=io.StringIO(), force_terminal=False)
        _execute_plan_interactive(result, console)
        assert "blocked notice text" in console.file.getvalue()

        lines = (
            (tmp_path / ".vibe" / "execution_plans.jsonl").read_text(encoding="utf-8").splitlines()
        )
        assert lines
        persisted = json.loads(lines[-1])
        assert persisted["metadata"]["execution_ready"] is False


class TestMinimalFormatGate:
    def test_format_result_blocked_plan_is_no_match(self, tmp_path):
        """8.3.1 (G-1): the minimal formatter itself gates on execution_ready —
        LightweightRouter.route() consumers get no attach-based demote."""
        from vibesop.core.routing.lightweight_api import LightweightRouter

        plan = make_plan(tmp_path, healthy=False)
        plan.metadata["execution_ready"] = False
        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query="Build the thing",
            execution_plan=plan,
        )
        formatted = LightweightRouter._format_result(result)
        assert formatted["mode"] == "no_match"
        assert formatted["skill_id"] == ""
        assert formatted["has_match"] is False
        assert formatted["notice_only"] is True
        assert "blocked" in formatted["notice"].lower()

    def test_format_result_ready_plan_keeps_orchestrated_shape(self, tmp_path):
        from vibesop.core.routing.lightweight_api import LightweightRouter

        plan = make_plan(tmp_path, healthy=True)
        plan.metadata["execution_ready"] = True
        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query="Build the thing",
            execution_plan=plan,
        )
        formatted = LightweightRouter._format_result(result)
        assert formatted["mode"] == "orchestrated"
        assert "has_match" not in formatted or formatted.get("skill_id")


class TestPromptChainExit:
    def test_blocked_plan_writes_no_prompt_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = make_result(tmp_path, healthy=False)
        console = Console(file=io.StringIO(), force_terminal=False)
        _handle_prompt_chain_output(result, json_output=False, console=console)
        output = console.file.getvalue()
        assert "Do not execute" in output
        assert not (tmp_path / ".vibe" / "prompts").exists()

    def test_ready_plan_still_generates(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = make_result(tmp_path, healthy=True)
        result.execution_plan.metadata["execution_ready"] = True
        console = Console(file=io.StringIO(), force_terminal=False)
        _handle_prompt_chain_output(result, json_output=False, console=console)
        assert "Do not execute" not in console.file.getvalue()


class TestPlanCommands:
    def _persist(self, tmp_path: Path, *, blocked: bool) -> ExecutionPlan:
        plan = make_plan(tmp_path, healthy=not blocked)
        plan.metadata["execution_ready"] = not blocked
        if blocked:
            plan.metadata["blocked_steps"] = [
                {"step_number": 1, "skill_id": "impl-skill", "reason": "not found or empty"}
            ]
        PlanTracker(storage_dir=tmp_path / ".vibe").create_plan(plan)
        return plan

    def test_complete_step_refused_on_blocked(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        plan = self._persist(tmp_path, blocked=True)
        with pytest.raises(typer.Exit) as excinfo:
            plan_cmd.plan_complete_step(step_id="s1", result=None, plan_id=plan.plan_id)
        assert excinfo.value.exit_code == 1
        out = capsys.readouterr().out
        assert "blocked" in out
        reloaded = PlanTracker(storage_dir=tmp_path / ".vibe").get_plan(plan.plan_id)
        assert reloaded.steps[0].status.value == "pending"

    def test_complete_step_works_on_ready(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        plan = self._persist(tmp_path, blocked=False)
        plan_cmd.plan_complete_step(step_id="s1", result=None, plan_id=plan.plan_id)
        reloaded = PlanTracker(storage_dir=tmp_path / ".vibe").get_plan(plan.plan_id)
        assert reloaded.steps[0].status.value == "completed"

    def test_list_marks_blocked(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        self._persist(tmp_path, blocked=True)
        plan_cmd.plan_list(limit=10)
        out = capsys.readouterr().out
        assert "blocked" in out

    def test_show_blocked_prints_notice(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        plan = self._persist(tmp_path, blocked=True)
        with pytest.raises(typer.Exit) as excinfo:
            plan_cmd.plan_show(plan_id=plan.plan_id)
        assert excinfo.value.exit_code == 1
        assert "Do not execute" in capsys.readouterr().out

    def test_status_blocked_prints_notice(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        self._persist(tmp_path, blocked=True)
        with pytest.raises(typer.Exit) as excinfo:
            plan_cmd.plan_status()
        assert excinfo.value.exit_code == 1
        assert "Do not execute" in capsys.readouterr().out
