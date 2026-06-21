"""Tests for PromptChainGenerator."""

from __future__ import annotations

from pathlib import Path

from vibesop.core.prompt_chain import (
    DiagnosisReport,
    PhasePrompt,
    PromptChainGenerator,
)


class TestSlugify:
    """ASCII-only slug generation with Chinese fallback."""

    def test_ascii_lowercase(self) -> None:
        assert PromptChainGenerator._slugify("Fan-Out Diagnosis") == "fan-out-diagnosis"

    def test_punctuation_stripped(self) -> None:
        assert PromptChainGenerator._slugify("hello, world!") == "hello-world"

    def test_pure_chinese_returns_empty(self) -> None:
        assert PromptChainGenerator._slugify("扇出诊断") == ""

    def test_mixed_keeps_ascii_only(self) -> None:
        # Chinese chars dropped, English kept.
        assert PromptChainGenerator._slugify("Phase 0 扇出诊断") == "phase-0"

    def test_length_cap(self) -> None:
        long = "a" * 100
        assert len(PromptChainGenerator._slugify(long)) == 50


class TestDiagnose:
    """Phase 0 file expansion."""

    def test_diagnose_empty_files(self, tmp_path: Path) -> None:
        gen = PromptChainGenerator(project_root=tmp_path)
        report = gen.diagnose(files=[], feature_context="test")
        assert isinstance(report, DiagnosisReport)
        assert report.files_read == []

    def test_diagnose_expands_glob(self, tmp_path: Path) -> None:
        # Create a few .py files
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("# a")
        (tmp_path / "src" / "b.py").write_text("# b")
        (tmp_path / "src" / "c.txt").write_text("ignore me")

        gen = PromptChainGenerator(project_root=tmp_path)
        report = gen.diagnose(files=["src/*.py"], feature_context="test")
        assert sorted(report.files_read) == ["src/a.py", "src/b.py"]

    def test_diagnose_rejects_parent_traversal(self, tmp_path: Path) -> None:
        gen = PromptChainGenerator(project_root=tmp_path)
        report = gen.diagnose(files=["../etc/passwd"], feature_context="x")
        # ../ is explicitly skipped — no files matched
        assert report.files_read == []

    def test_diagnose_deduplicates(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("# a")
        gen = PromptChainGenerator(project_root=tmp_path)
        report = gen.diagnose(files=["src/a.py", "src/*.py"], feature_context="x")
        # Same file matched twice via direct + glob → only once in output
        assert report.files_read == ["src/a.py"]


class TestGenerate:
    """Phase 1-N prompt file generation."""

    def test_generate_creates_seven_files(self, tmp_path: Path) -> None:
        gen = PromptChainGenerator(project_root=tmp_path)
        out = tmp_path / "prompts"
        prompts = gen.generate(feature="X", output_dir=out)
        assert len(prompts) == 7
        # Output dir created
        assert out.is_dir()
        # All phase numbers in order
        phases = [p.phase for p in prompts]
        assert phases == [0, 1, 2, 3, 4, 5, 6]

    def test_generate_filenames_are_ascii(self, tmp_path: Path) -> None:
        gen = PromptChainGenerator(project_root=tmp_path)
        out = tmp_path / "prompts"
        prompts = gen.generate(feature="X", output_dir=out)
        for prompt in prompts:
            name = prompt.output_path.name
            # Pure ASCII (CI / Windows / SSH safe)
            assert name.isascii(), f"Non-ASCII filename: {name}"

    def test_generate_final_phase_named_consistently(self, tmp_path: Path) -> None:
        gen = PromptChainGenerator(project_root=tmp_path)
        out = tmp_path / "prompts"
        prompts = gen.generate(feature="X", output_dir=out)
        final = prompts[-1]
        assert final.phase == 6
        assert final.output_path.name == "final-e2e-validation.md"

    def test_generate_phase_zero_includes_files_table(self, tmp_path: Path) -> None:
        gen = PromptChainGenerator(project_root=tmp_path)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "router.py").write_text("# router")
        report = gen.diagnose(files=["src/*.py"], feature_context="test")

        out = tmp_path / "prompts"
        prompts = gen.generate(feature="X", diagnosis=report, output_dir=out)
        phase_zero = prompts[0]
        assert phase_zero.phase == 0
        assert "src/router.py" in phase_zero.content

    def test_generate_phase_n_includes_feature_name(self, tmp_path: Path) -> None:
        gen = PromptChainGenerator(project_root=tmp_path)
        out = tmp_path / "prompts"
        prompts = gen.generate(feature="Multi-Agent Squad", output_dir=out)
        for prompt in prompts[1:6]:  # Phase 1-5
            assert "Multi-Agent Squad" in prompt.content

    def test_generate_final_includes_validation_steps(self, tmp_path: Path) -> None:
        gen = PromptChainGenerator(project_root=tmp_path)
        out = tmp_path / "prompts"
        prompts = gen.generate(feature="X", output_dir=out)
        final = prompts[-1]
        # Baseline tokens (kept across v7.3.3 rewrite)
        assert "vibe build" in final.content
        assert "pytest" in final.content
        assert "ubuntu:22.04" in final.content

    def test_generate_final_includes_round3_lessons(self, tmp_path: Path) -> None:
        """v7.3.3 expanded prompt — covers lessons from 3 rounds of e2e validation.

        Round 1 found: hook JSON envelope used wrong field name (.user_prompt vs .prompt)
        Round 2 found: indexer _llm_factory bypassed ~/.vibe/config.toml
        Round 3 found: AgentRuntime ORCHESTRATE branch doesn't propagate analysis
        """
        gen = PromptChainGenerator(project_root=tmp_path)
        out = tmp_path / "prompts"
        prompts = gen.generate(feature="X", output_dir=out)
        final = prompts[-1]
        # Round 2 P1: hook must parse .prompt field (not .user_prompt)
        assert '"prompt":' in final.content, "JSON envelope must use .prompt field"
        # Round 2 P2a fix: jq must be installed (hook depends on it)
        assert "jq" in final.content, "jq install step missing"
        # Round 2 P2b: Node 20 explicit (Ubuntu 22.04 default is Node 12)
        assert "setup_20.x" in final.content, "Node 20 NodeSource setup missing"
        # Round 3: LLM provider config step (without it, indexer fails 100%)
        assert "DEEPSEEK_API_KEY" in final.content, "DeepSeek API key propagation missing"
        assert "host.docker.internal" in final.content, "host oMLX option missing"
        # Round 3: skill index build step (without it, AI_TRIAGE always empty)
        assert "indexed_count" in final.content, "skill index verification missing"
        # Round 3 P0: hook → skill recommendation check (not just file exists)
        assert "G4_hook_returns_skill" in final.content, "hook→skill verification missing"
        # Round 3 P0 known bug documented
        assert "P0-hook-routing" in final.content, "known P0 issue not documented"
        # Kimi Code install (Round 2 addition)
        assert "code.kimi.com/kimi-code/install.sh" in final.content, "Kimi install missing"

    def test_generate_uses_project_name_from_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "my-test-project"\nversion = "0.1.0"\n'
        )
        gen = PromptChainGenerator(project_root=tmp_path)
        out = tmp_path / "prompts"
        prompts = gen.generate(feature="X", output_dir=out)
        assert "my-test-project" in prompts[0].content

    def test_generate_falls_back_to_dirname(self, tmp_path: Path) -> None:
        # No pyproject.toml → use directory name
        gen = PromptChainGenerator(project_root=tmp_path)
        out = tmp_path / "prompts"
        prompts = gen.generate(feature="X", output_dir=out)
        assert tmp_path.name in prompts[0].content


class TestPhasePromptDataclass:
    def test_phase_prompt_fields(self, tmp_path: Path) -> None:
        p = PhasePrompt(phase=2, title="X", content="c", output_path=tmp_path / "x.md")
        assert p.phase == 2
        assert p.title == "X"
        assert p.content == "c"
        assert isinstance(p.output_path, Path)
