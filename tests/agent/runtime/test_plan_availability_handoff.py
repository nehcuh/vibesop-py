"""Final handoff checks use files and payloads produced by real plan models."""

import json

import pytest

from vibesop.agent.runtime.agent_runtime import AgentRuntimeResult
from vibesop.agent.runtime.plan_executor import PlanExecutor
from vibesop.agent.runtime.skill_injector import PlatformType, SkillInjector
from vibesop.cli.render import attach_skill_file_payload
from vibesop.core.models import ExecutionPlan, ExecutionStep, OrchestrationMode, OrchestrationResult
from vibesop.core.routing.lightweight_api import LightweightRouter


def make_plan(tmp_path):
    steps = []
    for number, sid in enumerate(("handoff-implementation", "handoff-verification"), 1):
        path = tmp_path / sid / "SKILL.md"
        path.parent.mkdir()
        path.write_text("# Workflow\nInspect inputs and verify the result.\n", encoding="utf-8")
        steps.append(
            ExecutionStep(
                step_id=f"s{number}",
                step_number=number,
                skill_id=sid,
                skill_file=str(path),
                intent="Implement" if number == 1 else "Verify",
                input_query="Check acceptance",
                is_verification_step=number == 2,
            )
        )
    return ExecutionPlan(plan_id="handoff-plan", original_query="Implement and verify", steps=steps)


@pytest.mark.parametrize("failure", ["deleted", "empty", "placeholder", "fallback"])
def test_required_verifier_blocks_every_handoff(tmp_path, monkeypatch, failure):
    plan = make_plan(tmp_path)
    verifier = plan.steps[1]
    from pathlib import Path

    path = Path(verifier.skill_file)
    if failure == "deleted":
        path.unlink()
    elif failure == "empty":
        path.write_text(" \n")
    elif failure == "placeholder":
        path.write_text(f"# Skill: {verifier.skill_id}\n\n*Skill content not found here.*")
    else:
        verifier.skill_id = "fallback-llm"
    injector = SkillInjector(tmp_path)
    injection = injector.inject_execution_plan(plan, PlatformType.GENERIC)
    assert injection.notice_only is True
    assert "Do not execute" in injection.payload
    assert len(plan.steps) == 2
    assert plan.steps[1].is_verification_step is True
    assert plan.metadata["execution_ready"] is False

    guide = PlanExecutor(tmp_path).build_guide(plan)
    assert guide.step_markers == []
    assert "[StepCompleted:" not in guide.prompt
    with pytest.raises(ValueError, match="Execution plan blocked"):
        PlanExecutor(tmp_path).build_manifest(plan)

    result = AgentRuntimeResult(
        intercepted=True,
        mode="orchestrate",
        plan=plan.to_dict(),
        project_root=tmp_path,
        router_matched=True,
    )
    hook = json.loads(result.to_hook_response())
    assert "Do not execute" in hook["systemMessage"]
    assert "Execution plan injected" not in hook["systemMessage"]
    assert result.has_match is False
    assert result.router_matched is False
    assert json.loads(result.to_hook_json())["has_match"] is False

    monkeypatch.chdir(tmp_path)
    routed = OrchestrationResult(mode=OrchestrationMode.ORCHESTRATED, execution_plan=plan)
    payload = routed.to_dict()
    attach_skill_file_payload(payload, routed)
    assert payload["has_match"] is False
    assert payload["notice_only"] is True
    assert payload["execution_plan"]["steps"][1]["is_verification_step"] is True


def test_ready_plan_preserves_injection_guide_and_manifest(tmp_path, monkeypatch):
    plan = make_plan(tmp_path)
    injector = SkillInjector(tmp_path)
    injection = injector.inject_execution_plan(plan, PlatformType.CLAUDE_CODE)
    assert injection.notice_only is False
    assert plan.metadata["execution_ready"] is True
    assert "additionalContext" in injection.payload
    assert len(PlanExecutor(tmp_path).build_guide(plan).step_markers) == 2
    manifest = PlanExecutor(tmp_path).build_manifest(plan)
    assert len(manifest.steps) == 2
    assert "Inspect inputs" in manifest.steps[1].skill_content
    result = AgentRuntimeResult(
        intercepted=True,
        mode="orchestrate",
        plan=plan.to_dict(),
        project_root=tmp_path,
        router_matched=True,
    )
    assert "Execution plan injected" in json.loads(result.to_hook_response())["systemMessage"]
    assert result.has_match is True
    monkeypatch.chdir(tmp_path)
    routed = OrchestrationResult(mode=OrchestrationMode.ORCHESTRATED, execution_plan=plan)
    payload = routed.to_dict()
    attach_skill_file_payload(payload, routed)
    assert payload["has_match"] is True
    assert "notice_only" not in payload


def test_deleted_authoritative_source_cannot_be_replaced_at_serialization(tmp_path):
    plan = make_plan(tmp_path)
    sid = plan.steps[1].skill_id
    authoritative = tmp_path / "authoritative" / "SKILL.md"
    authoritative.parent.mkdir()
    authoritative.write_text("# Verify\nRun all acceptance checks.\n")
    guessed = tmp_path / ".vibe" / "skills" / sid / "SKILL.md"
    guessed.parent.mkdir(parents=True)
    guessed.write_text("# Another copy\nThis is not the routed source.\n")
    injector = SkillInjector(tmp_path)
    payload = plan.to_dict()
    # A newer authoritative lookup must supersede even a prefilled stale path.
    from pathlib import Path

    Path(plan.steps[1].skill_file).unlink()
    injector.annotate_plan_dict(
        payload, source_lookup=lambda key: str(authoritative) if key == sid else None
    )
    assert payload["steps"][1]["skill_file"] == authoritative.as_posix()
    authoritative.unlink()
    result = AgentRuntimeResult(
        intercepted=True,
        mode="orchestrate",
        plan=payload,
        project_root=tmp_path,
        router_matched=True,
    )
    result.to_hook_response()
    assert result.has_match is False
    assert result.plan["steps"][1]["skill_file"] == ""
    # Repeated annotation must not fall back to an unrelated installed copy.
    result.to_hook_response()
    assert result.has_match is False
    assert result.plan["metadata"]["execution_ready"] is False


def test_minimal_cli_payload_is_blocked_and_keeps_verifier(tmp_path, monkeypatch):
    from pathlib import Path

    plan = make_plan(tmp_path)
    Path(plan.steps[1].skill_file).unlink()
    routed = OrchestrationResult(mode=OrchestrationMode.ORCHESTRATED, execution_plan=plan)
    payload = LightweightRouter._format_result(routed)
    monkeypatch.chdir(tmp_path)
    attach_skill_file_payload(payload, routed)
    assert payload["has_match"] is False
    assert payload["notice_only"] is True
    assert len(payload["steps"]) == 2
    assert payload["steps"][1]["skill_id"] == "handoff-verification"
    assert payload["steps"][1]["is_verification_step"] is True
    assert payload["metadata"]["execution_ready"] is False


def test_minimal_cli_ready_plan_keeps_authoritative_paths(tmp_path, monkeypatch):
    from pathlib import Path

    plan = make_plan(tmp_path)
    routed = OrchestrationResult(mode=OrchestrationMode.ORCHESTRATED, execution_plan=plan)
    payload = LightweightRouter._format_result(routed)
    monkeypatch.chdir(tmp_path)
    attach_skill_file_payload(payload, routed)
    assert payload["metadata"]["execution_ready"] is True
    assert "notice_only" not in payload
    assert payload["steps"][1]["skill_file"] == Path(plan.steps[1].skill_file).as_posix()


def test_manifest_body_uses_same_source_as_annotated_path(tmp_path):
    plan = make_plan(tmp_path)
    duplicate = tmp_path / ".vibe" / "skills" / plan.steps[1].skill_id / "SKILL.md"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text("# Duplicate\nUnrelated old workflow.\n")
    manifest = PlanExecutor(tmp_path).build_manifest(plan)
    assert manifest.steps[1].skill_path == plan.steps[1].skill_file
    assert "Inspect inputs" in manifest.steps[1].skill_content
    assert "Unrelated old workflow" not in manifest.steps[1].skill_content


def test_same_skill_id_keeps_each_steps_actual_source(tmp_path):
    from pathlib import Path

    plan = make_plan(tmp_path)
    original_paths = [Path(step.skill_file).as_posix() for step in plan.steps]
    plan.steps[1].skill_id = plan.steps[0].skill_id
    injector = SkillInjector(tmp_path)
    injector.annotate_plan_skill_files(plan)
    assert [step.skill_file for step in plan.steps] == original_paths
    injector.annotate_plan_skill_files(plan)
    assert [step.skill_file for step in plan.steps] == original_paths


def test_ready_squad_uses_plan_envelope(tmp_path):
    plan = make_plan(tmp_path)
    result = AgentRuntimeResult(
        intercepted=True,
        mode="multi_agent_squad",
        plan=plan.to_dict(),
        project_root=tmp_path,
        router_matched=True,
    )
    hook = json.loads(result.to_hook_response())
    assert "Execution plan injected" in hook["systemMessage"]
    assert "[VibeSOP Execution Plan]" in hook["hookSpecificOutput"]["additionalContext"]
    assert result.has_match is True


@pytest.mark.parametrize("field,bad", [("steps", None), ("metadata", []), ("sources", [])])
def test_corrupt_plan_cannot_keep_previously_ready_flag(tmp_path, field, bad):
    plan = make_plan(tmp_path).to_dict()
    plan["metadata"]["execution_ready"] = True
    if field == "sources":
        plan["metadata"]["skill_sources"] = bad
    else:
        plan[field] = bad
    result = AgentRuntimeResult(
        intercepted=True, mode="orchestrate", plan=plan, project_root=tmp_path, router_matched=True
    )
    hook = json.loads(result.to_hook_response())
    assert result.has_match is False
    assert "Do not execute" in hook["systemMessage"]
    assert plan["metadata"]["execution_ready"] is False
