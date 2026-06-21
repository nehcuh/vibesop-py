"""Tests for PromptChainGenerator."""

from __future__ import annotations

import tempfile
from pathlib import Path

from vibesop.core.models import (
    AgentRole,
    AgentSquad,
    ExecutionPlan,
    ExecutionStep,
    PlanStatus,
    SquadStep,
    StepStatus,
    WorkflowPattern,
)
from vibesop.core.orchestration.prompt_chain_generator import (
    AgentPrompt,
    PromptChainGenerator,
    PromptFile,
    SquadPromptGenerator,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_step(
    step_number: int = 1,
    skill_id: str = "test/skill",
    intent: str = "test intent",
    dependencies: list[str] | None = None,
    source_files: list[str] | None = None,
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
        source_files=source_files or [f"src/vibesop/{skill_id.replace('/', '/')}/main.py"],
    )


def _make_chain_plan(
    steps: list[ExecutionStep] | None = None,
    pattern: WorkflowPattern = WorkflowPattern.PROMPT_CHAIN,
) -> ExecutionPlan:
    if steps is None:
        s1 = _make_step(
            1, "core/router", "路由层改造", source_files=["src/vibesop/core/routing/unified.py"]
        )
        s2 = _make_step(
            2,
            "core/engine",
            "引擎重写",
            dependencies=[s1.step_id],
            source_files=["src/vibesop/core/engine.py"],
        )
        s3 = _make_step(
            3,
            "core/adapter",
            "适配器扩展",
            dependencies=[s2.step_id],
            source_files=["src/vibesop/adapters/base.py"],
        )
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

    def test_phase_1_quick_wins_only_when_step_type_matches(self):
        # Steps without step_type="quick_win" should NOT appear in Phase 1
        s1 = _make_step(1, "core/a", "独立任务A")
        s2 = _make_step(2, "core/b", "独立任务B")
        plan = _make_chain_plan(steps=[s1, s2])
        gen = PromptChainGenerator()
        result = gen.generate(plan)
        # No quick_win steps → Phase 1 skipped → Phase 0 + Phase 1 (s1) + Phase 2 (s2) + Final = 4
        assert len(result) == 4
        assert result[1].phase == 1
        assert "quick" not in result[1].name.lower()

    def test_phase_1_appears_for_quick_win_steps(self):
        s1 = _make_step(1, "core/a", "快速修复A")
        s1.step_type = "quick_win"
        s2 = _make_step(2, "core/b", "独立任务B")
        plan = _make_chain_plan(steps=[s1, s2])
        gen = PromptChainGenerator()
        result = gen.generate(plan)
        # Phase 0 + Phase 1 (quick win) + Phase 2 (s2) + Final = 4
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

    def test_write_files_blocks_path_traversal(self):
        """Malicious filenames must be sanitized to basename and contained."""
        from vibesop.core.orchestration.prompt_chain_generator import PromptFile

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "prompts"
            gen = PromptChainGenerator(output_dir=str(output))
            malicious_names = [
                "../../../etc/passwd",
                "../../.ssh/authorized_keys",
                "subdir/../../evil",
                "..\\..\\windows\\system32\\evil",
                "normal-filename",  # control case
            ]
            prompt_files = [
                PromptFile(phase=0, name="x", filename=name, content=f"content for {name}")
                for name in malicious_names
            ]
            written = gen.write_files(prompt_files)

            # The control file (basename-only) should be written; traversal
            # variants are sanitized to their basename and still land inside
            # the output dir (with .md suffix appended).
            written_names = {p.name for p in written}
            assert "passwd.md" in written_names
            assert "authorized_keys.md" in written_names
            assert "evil.md" in written_names
            assert "normal-filename.md" in written_names

            # Critical: every written path must live inside the output dir
            # (no escape via traversal or prefix collision).
            output_resolved = output.resolve()
            for path in written:
                assert str(path.resolve()).startswith(str(output_resolved) + "/") or str(
                    path.resolve()
                ) == str(output_resolved), f"Path escaped output dir: {path}"

            # No file should have been written outside the output dir.
            # Walk tmpdir and assert no `etc/passwd` style files exist.
            outside_artifacts = list((Path(tmpdir) / "..").resolve().glob("passwd"))
            assert not outside_artifacts

    def test_write_files_rejects_null_byte_filename(self):
        """NUL bytes in filenames must be rejected (potential ANSI/XSI bypass)."""
        from vibesop.core.orchestration.prompt_chain_generator import PromptFile

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "prompts"
            gen = PromptChainGenerator(output_dir=str(output))
            prompt_files = [
                PromptFile(phase=0, name="x", filename="evil\x00.md", content="payload"),
                PromptFile(phase=0, name="x", filename="safe.md", content="ok"),
            ]
            written = gen.write_files(prompt_files)
            # Only the safe file is written; NUL byte is rejected.
            assert len(written) == 1
            assert written[0].name == "safe.md"

    def test_write_files_prefix_collision_safety(self):
        """output_dir /tmp/foo must not match destination /tmp/foobar/x.md."""
        from vibesop.core.orchestration.prompt_chain_generator import PromptFile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create output_dir = tmpdir/foo, then attempt to write a file
            # whose basename collides with a sibling dir name.
            output = Path(tmpdir) / "foo"
            sibling = Path(tmpdir) / "foobar"
            sibling.mkdir(parents=True)
            (sibling / "secret.md").write_text("secret")

            gen = PromptChainGenerator(output_dir=str(output))
            prompt_files = [
                PromptFile(phase=0, name="x", filename="bar", content="ok"),  # → foo/bar.md
            ]
            written = gen.write_files(prompt_files)
            assert len(written) == 1
            assert written[0].resolve() == (output / "bar.md").resolve()
            # The sibling file must remain untouched.
            assert (sibling / "secret.md").read_text() == "secret"


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


class TestSquadPromptGenerator:
    """Per-role prompt generation for agent squads."""

    def _make_squad(self) -> AgentSquad:
        return AgentSquad(
            squad_id="squad-test",
            roles=[
                AgentRole(
                    role_id="architect", name="架构师", required_skills=["architecture-analysis"]
                ),
                AgentRole(role_id="implementer", name="实现者", required_skills=["python-coding"]),
            ],
            steps=[
                SquadStep(
                    step_id="arch",
                    role_id="architect",
                    agent_platform="claude-code",
                    skill_ids=["architecture-analysis", "design-doc"],
                    input_from=[],
                ),
                SquadStep(
                    step_id="impl",
                    role_id="implementer",
                    agent_platform="opencode",
                    skill_ids=["python-coding", "microservice"],
                    input_from=["arch"],
                ),
            ],
            collaboration_protocol="sequential",
            execution_order=["arch", "impl"],
        )

    def test_generate_for_squad_returns_one_prompt_per_step(self) -> None:
        squad = self._make_squad()
        generator = SquadPromptGenerator()
        prompts = generator.generate_for_squad(squad, "design a microservice")

        assert len(prompts) == 2
        assert all(isinstance(p, AgentPrompt) for p in prompts)

    def test_prompt_contains_role_template_and_skills(self) -> None:
        squad = self._make_squad()
        generator = SquadPromptGenerator()
        prompts = generator.generate_for_squad(squad, "design a microservice")

        architect_prompt = next(p for p in prompts if p.role.role_id == "architect")
        assert "architecture-analysis" in architect_prompt.prompt
        assert "design-doc" in architect_prompt.prompt
        assert "原始需求" in architect_prompt.prompt
        assert architect_prompt.agent_id == "architect@claude-code"

    def test_prompt_includes_handoff_context(self) -> None:
        squad = self._make_squad()
        generator = SquadPromptGenerator()
        prompts = generator.generate_for_squad(squad, "design a microservice")

        implementer_prompt = next(p for p in prompts if p.role.role_id == "implementer")
        assert implementer_prompt.input_from == "arch"
        assert "输入上下文" in implementer_prompt.prompt
        assert "architect" in implementer_prompt.prompt

    def test_prompt_chain_generator_exposes_squad_prompts(self) -> None:
        squad = self._make_squad()
        plan = ExecutionPlan(
            plan_id="plan-squad",
            original_query="design a microservice",
            workflow_pattern=WorkflowPattern.PROMPT_CHAIN,
            metadata={"agent_squad": squad.to_dict()},
        )
        generator = PromptChainGenerator()
        prompts = generator.generate_squad_prompts(plan)

        assert len(prompts) == 2
        assert prompts[0].role.role_id == "architect"
        assert prompts[1].role.role_id == "implementer"
