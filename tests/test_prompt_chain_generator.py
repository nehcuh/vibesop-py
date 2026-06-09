"""Tests for PromptChainGenerator."""

from __future__ import annotations

import tempfile
from pathlib import Path

from vibesop.core.models import (
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    StepStatus,
    WorkflowPattern,
)
from vibesop.core.orchestration.prompt_chain_generator import (
    PromptChainGenerator,
    PromptFile,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_step(
    step_number: int = 1,
    skill_id: str = "test/skill",
    intent: str = "test intent",
    dependencies: list[str] | None = None,
) -> ExecutionStep:
    return ExecutionStep(
        step_id=f"step-{step_number}",
        step_number=step_number,
        skill_id=skill_id,
        intent=intent,
        input_query=f"query for {intent}",
        output_as=f"step_{step_number}_result",
        status=StepStatus.PENDING,
        dependencies=dependencies or [],
    )


def _make_chain_plan(
    steps: list[ExecutionStep] | None = None,
    pattern: WorkflowPattern = WorkflowPattern.PROMPT_CHAIN,
) -> ExecutionPlan:
    if steps is None:
        s1 = _make_step(1, "core/router", "路由层改造")
        s2 = _make_step(2, "core/engine", "引擎重写", dependencies=[s1.step_id])
        s3 = _make_step(3, "core/adapter", "适配器扩展", dependencies=[s2.step_id])
        steps = [s1, s2, s3]
    return ExecutionPlan(
        plan_id="test-plan-001",
        original_query="重构路由引擎并扩展适配器支持",
        steps=steps,
        detected_intents=["router", "engine", "adapter"],
        reasoning="test plan",
        status=PlanStatus.PENDING,
        workflow_pattern=pattern,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPromptFileModel:
    def test_prompt_file_creation(self):
        pf = PromptFile(
            phase=0,
            name="test",
            filename="phase-0-test.md",
            content="# Hello",
        )
        assert pf.phase == 0
        assert pf.name == "test"
        assert pf.filename == "phase-0-test.md"
        assert pf.content == "# Hello"
        assert pf.prerequisites == []
        assert pf.required_files == []
        assert pf.verification_checklist == []


class TestNonChainPlans:
    def test_sequential_plan_returns_empty(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan(pattern=WorkflowPattern.SEQUENTIAL)
        result = gen.generate(plan)
        assert result == []

    def test_parallel_plan_returns_empty(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan(pattern=WorkflowPattern.PARALLEL)
        result = gen.generate(plan)
        assert result == []

    def test_fan_out_plan_returns_empty(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan(pattern=WorkflowPattern.FAN_OUT)
        result = gen.generate(plan)
        assert result == []

    def test_adversarial_plan_returns_empty(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan(pattern=WorkflowPattern.ADVERSARIAL)
        result = gen.generate(plan)
        assert result == []

    def test_loop_until_dry_returns_empty(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan(pattern=WorkflowPattern.LOOP_UNTIL_DRY)
        result = gen.generate(plan)
        assert result == []

    def test_tournament_returns_empty(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan(pattern=WorkflowPattern.TOURNAMENT)
        result = gen.generate(plan)
        assert result == []


class TestPromptChainGeneration:
    def test_generates_5_plus_files(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan()
        result = gen.generate(plan)
        # Phase 0 + Phase 1 + Phase 2 + Phase 3 + Final = 5
        assert len(result) >= 5

    def test_phase_ordering(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan()
        result = gen.generate(plan)
        phases = [pf.phase for pf in result]
        # Phase 0 first, then 1, 2, 3, ..., then final (-1)
        assert phases[0] == 0
        # Final phase is last with phase=-1
        assert phases[-1] == -1
        # Middle phases are in ascending order
        middle = phases[1:-1]
        assert middle == sorted(middle)

    def test_phase_0_contains_diagnosis_template(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan()
        result = gen.generate(plan)
        phase0 = result[0]
        assert phase0.phase == 0
        assert "扇出诊断" in phase0.content
        assert "Phase 0" in phase0.filename or "phase-0" in phase0.filename

    def test_final_phase_contains_adversarial_review(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan()
        result = gen.generate(plan)
        final = result[-1]
        assert final.phase == -1
        assert "对抗式审查" in final.content
        assert "安全审查" in final.content

    def test_every_prompt_contains_routing_hint(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan()
        result = gen.generate(plan)
        for pf in result:
            assert "vibe route" in pf.content

    def test_phase_0_prerequisites_not_empty(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan()
        result = gen.generate(plan)
        assert len(result[0].prerequisites) > 0

    def test_phase_0_required_files_from_steps(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan()
        result = gen.generate(plan)
        # Should reference skill_ids from steps
        phase0 = result[0]
        assert len(phase0.required_files) > 0

    def test_phase_1_quick_wins_independent_steps(self):
        s1 = _make_step(1, "core/a", "独立任务A")
        s2 = _make_step(2, "core/b", "独立任务B")
        plan = _make_chain_plan(steps=[s1, s2])
        gen = PromptChainGenerator()
        result = gen.generate(plan)
        # Phase 0 + Phase 1 (both independent) + Final = 3
        phase1 = result[1]
        assert phase1.phase == 1
        assert "quick" in phase1.name.lower() or "Quick" in phase1.content

    def test_phase_n_includes_dependencies(self):
        s1 = _make_step(1, "core/a", "基础改造")
        s2 = _make_step(2, "core/b", "依赖A的改造", dependencies=[s1.step_id])
        plan = _make_chain_plan(steps=[s1, s2])
        gen = PromptChainGenerator()
        result = gen.generate(plan)
        # Find the phase that covers step 2 (dependent)
        dependent_phases = [pf for pf in result if pf.phase >= 2]
        assert len(dependent_phases) >= 1
        dep_phase = dependent_phases[0]
        assert len(dep_phase.prerequisites) > 1  # Has dependency prereqs

    def test_context_project_name(self):
        gen = PromptChainGenerator()
        plan = _make_chain_plan()
        result = gen.generate(plan, context={"project_name": "MyProject"})
        assert "MyProject" in result[0].content


class TestWriteFiles:
    def test_write_files_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "prompts"
            gen = PromptChainGenerator(output_dir=str(output))
            plan = _make_chain_plan()
            prompt_files = gen.generate(plan)
            written = gen.write_files(prompt_files)
            assert output.exists()
            assert len(written) == len(prompt_files)

    def test_write_files_content_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "prompts"
            gen = PromptChainGenerator(output_dir=str(output))
            plan = _make_chain_plan()
            prompt_files = gen.generate(plan)
            written = gen.write_files(prompt_files)
            for pf, path in zip(prompt_files, written, strict=True):
                assert path.read_text(encoding="utf-8") == pf.content

    def test_write_files_custom_output_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = Path(tmpdir) / "custom"
            gen = PromptChainGenerator()
            plan = _make_chain_plan()
            prompt_files = gen.generate(plan)
            written = gen.write_files(prompt_files, output_dir=custom)
            assert custom.exists()
            assert len(written) == len(prompt_files)


class TestWorkflowEnginePromptChain:
    def test_engine_dispatches_prompt_chain(self):
        from vibesop.core.orchestration.workflow_engine import WorkflowEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = WorkflowEngine(prompt_chain_output_dir=tmpdir)
            plan = _make_chain_plan()
            result = engine._run_prompt_chain(plan)
            assert result.pattern == WorkflowPattern.PROMPT_CHAIN
            assert result.final_status == "prompts_generated"
            assert "prompt_files" in result.results
            assert len(result.results["prompt_files"]) >= 5

    def test_is_dynamic_includes_prompt_chain(self):
        from vibesop.core.orchestration.workflow_engine import WorkflowEngine

        plan = _make_chain_plan()
        assert WorkflowEngine.is_dynamic(plan)

    def test_engine_run_dispatches_prompt_chain(self):
        from vibesop.core.orchestration.workflow_engine import WorkflowEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = WorkflowEngine(prompt_chain_output_dir=tmpdir)
            plan = _make_chain_plan()
            result = engine.run(plan, executor=None)
            assert result.pattern == WorkflowPattern.PROMPT_CHAIN
            assert result.final_status == "prompts_generated"
