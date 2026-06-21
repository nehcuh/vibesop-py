"""Tests for Phase 3: adapter build_prompt_chain and CLI integration."""

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


def _make_chain_plan() -> ExecutionPlan:
    s1 = _make_step(1, "core/router", "路由层改造")
    s2 = _make_step(2, "core/engine", "引擎重写", dependencies=[s1.step_id])
    s3 = _make_step(3, "core/adapter", "适配器扩展", dependencies=[s2.step_id])
    return ExecutionPlan(
        plan_id="test-plan-002",
        original_query="重构路由引擎并扩展适配器",
        steps=[s1, s2, s3],
        detected_intents=["router", "engine", "adapter"],
        reasoning="test",
        status=PlanStatus.PENDING,
        workflow_pattern=WorkflowPattern.PROMPT_CHAIN,
    )


def _make_step(
    step_number: int,
    skill_id: str,
    intent: str,
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


def _generate_prompts() -> list[PromptFile]:
    gen = PromptChainGenerator()
    return gen.generate(_make_chain_plan())


# ── Claude Code Adapter ─────────────────────────────────────────────────────


class TestClaudeCodeAdapterPromptChain:
    def test_build_prompt_chain_writes_files(self):
        from vibesop.adapters.claude_code import ClaudeCodeAdapter

        adapter = ClaudeCodeAdapter()
        prompts = _generate_prompts()

        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = adapter.build_prompt_chain(prompts, tmpdir)
            assert Path(readme_path).exists()
            assert Path(readme_path).name == "README.md"

            # All prompt files written
            for pf in prompts:
                assert (Path(tmpdir) / pf.filename).exists()

    def test_readme_contains_execution_order(self):
        from vibesop.adapters.claude_code import ClaudeCodeAdapter

        adapter = ClaudeCodeAdapter()
        prompts = _generate_prompts()

        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = adapter.build_prompt_chain(prompts, tmpdir)
            content = Path(readme_path).read_text()
            assert "Execution Order" in content
            assert "phase-0" in content.lower() or "Phase 0" in content

    def test_readme_contains_how_to_execute(self):
        from vibesop.adapters.claude_code import ClaudeCodeAdapter

        adapter = ClaudeCodeAdapter()
        prompts = _generate_prompts()

        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = adapter.build_prompt_chain(prompts, tmpdir)
            content = Path(readme_path).read_text()
            assert "pbcopy" in content or "Claude Code" in content


# ── OpenCode Adapter ────────────────────────────────────────────────────────


class TestOpenCodeAdapterPromptChain:
    def test_build_prompt_chain_writes_files(self):
        from vibesop.adapters.opencode import OpenCodeAdapter

        adapter = OpenCodeAdapter()
        prompts = _generate_prompts()

        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = adapter.build_prompt_chain(prompts, tmpdir)
            assert Path(readme_path).exists()
            for pf in prompts:
                assert (Path(tmpdir) / pf.filename).exists()

    def test_readme_mentions_opencode(self):
        from vibesop.adapters.opencode import OpenCodeAdapter

        adapter = OpenCodeAdapter()
        prompts = _generate_prompts()

        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = adapter.build_prompt_chain(prompts, tmpdir)
            content = Path(readme_path).read_text()
            assert "OpenCode" in content


# ── Kimi CLI Adapter ────────────────────────────────────────────────────────


class TestKimiCliAdapterPromptChain:
    def test_build_prompt_chain_writes_files(self):
        from vibesop.adapters.kimi_cli import KimiCliAdapter

        adapter = KimiCliAdapter()
        prompts = _generate_prompts()

        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = adapter.build_prompt_chain(prompts, tmpdir)
            assert Path(readme_path).exists()
            for pf in prompts:
                assert (Path(tmpdir) / pf.filename).exists()

    def test_readme_contains_chinese_instructions(self):
        from vibesop.adapters.kimi_cli import KimiCliAdapter

        adapter = KimiCliAdapter()
        prompts = _generate_prompts()

        with tempfile.TemporaryDirectory() as tmpdir:
            readme_path = adapter.build_prompt_chain(prompts, tmpdir)
            content = Path(readme_path).read_text()
            # Kimi CLI README should have Chinese instructions
            assert "阶段" in content or "Phase" in content


# ── CLI Integration ──────────────────────────────────────────────────────────


class TestCLIPromptChainOutput:
    def test_handle_prompt_chain_output_json(self, capsys):
        from rich.console import Console

        from vibesop.cli.main import _handle_prompt_chain_output

        plan = _make_chain_plan()

        class FakeResult:
            execution_plan = plan
            mode = type("M", (), {"value": "orchestrated"})()

        console = Console(width=120)
        _handle_prompt_chain_output(FakeResult(), json_output=True, console=console)

        captured = capsys.readouterr()
        import json

        output = json.loads(captured.out)
        assert output["pattern"] == "prompt_chain"
        assert output["total_phases"] >= 5
        assert "files" in output

    def test_handle_prompt_chain_output_creates_files(self):
        from rich.console import Console

        from vibesop.cli.main import _handle_prompt_chain_output

        plan = _make_chain_plan()

        class FakeResult:
            execution_plan = plan
            mode = type("M", (), {"value": "orchestrated"})()

        with tempfile.TemporaryDirectory() as tmpdir:
            console = Console(width=120)
            _handle_prompt_chain_output(
                FakeResult(),
                json_output=False,
                console=console,
                output_dir=tmpdir,
            )

            # Files should be written
            written_files = list(Path(tmpdir).glob("phase-*.md"))
            assert len(written_files) >= 5

    def test_handle_prompt_chain_no_plan(self):
        from rich.console import Console

        from vibesop.cli.main import _handle_prompt_chain_output

        class FakeResult:
            execution_plan = None
            mode = type("M", (), {"value": "orchestrated"})()

        console = Console(width=120)
        # Should not crash
        _handle_prompt_chain_output(FakeResult(), json_output=False, console=console)
