"""End-to-end tests for Agent Runtime layer.

These tests verify the complete Agent Runtime workflow:
  User Query -> IntentInterceptor -> SkillInjector -> DecisionPresenter -> PlanExecutor

They simulate the full call chain that platform adapters (Claude Code / OpenCode / Kimi CLI)
would orchestrate in production, without requiring actual AI Agent platform connections.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from vibesop.adapters import Manifest, ManifestMetadata
from vibesop.adapters.claude_code import ClaudeCodeAdapter
from vibesop.adapters.kimi_cli import KimiCliAdapter
from vibesop.adapters.models import PolicySet, RoutingPolicy, SecurityPolicy
from vibesop.agent.runtime import (
    DecisionPresenter,
    ExecutionGuide,
    InjectionMethod,
    IntentInterceptor,
    InterceptionContext,
    InterceptionMode,
    PlanExecutor,
    PlatformType,
    SkillInjector,
    SlashCommandExecutor,
)
from vibesop.core.models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    OrchestrationMode,
    OrchestrationResult,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)


class TestAgentRuntimeFullChain:
    """E2E: Full Agent Runtime chain from query to execution guide."""

    def test_single_skill_routing_chain(self) -> None:
        """E2E: User asks for code review -> full chain routes to review skill."""
        query = "review my code please"

        interceptor = IntentInterceptor()
        context = InterceptionContext(platform="claude-code")
        decision = interceptor.should_intercept(query, context)

        assert decision.should_route is True
        assert decision.mode in (InterceptionMode.SINGLE, InterceptionMode.ORCHESTRATE)
        assert len(decision.query) > 0

        route_result = RoutingResult(
            primary=SkillRoute(
                skill_id="gstack-review",
                confidence=0.92,
                layer=RoutingLayer.AI_TRIAGE,
                description="Code review skill",
            ),
            alternatives=[
                SkillRoute(
                    skill_id="riper-workflow",
                    confidence=0.65,
                    layer=RoutingLayer.TFIDF,
                ),
            ],
            routing_path=[RoutingLayer.AI_TRIAGE],
            query=query,
        )

        injector = SkillInjector()
        injection = injector.inject_single_skill(
            skill_id="gstack-review",
            platform=PlatformType.CLAUDE_CODE,
        )

        assert injection.method == InjectionMethod.ADDITIONAL_CONTEXT
        assert "gstack-review" in injection.payload.get("additionalContext", "")

        presenter = DecisionPresenter()
        present_result = presenter.present_single_result(
            result=route_result,
            platform=PlatformType.CLAUDE_CODE,
        )

        assert present_result.message != ""
        assert "gstack-review" in present_result.message
        assert "accept" in present_result.actions
        assert present_result.structured is not None
        assert present_result.structured.get("primary", {}).get("skill_id") == "gstack-review"

    def test_multi_intent_orchestration_chain(self) -> None:
        """E2E: User asks multi-intent query -> orchestration plan generated."""
        query = "分析项目架构并优化整体性能"

        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept(query)

        assert decision.should_route is True
        assert decision.mode == InterceptionMode.ORCHESTRATE
        assert "multi-intent" in decision.reason.lower() or "multi" in decision.reason.lower()

        plan = ExecutionPlan(
            plan_id="plan-test-001",
            original_query=query,
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_number=1,
                    skill_id="superpowers-architect",
                    intent="Analyze project architecture",
                    input_query="Analyze current project architecture",
                    output_as="architecture_analysis",
                ),
                ExecutionStep(
                    step_id="s2",
                    step_number=2,
                    skill_id="superpowers-optimize",
                    intent="Optimize performance based on architecture analysis",
                    input_query="Optimize performance using architecture_analysis",
                    output_as="optimization_results",
                ),
            ],
            detected_intents=["architecture_analysis", "performance_optimization"],
            reasoning="Query contains sequential intents connected by marker",
            execution_mode=ExecutionMode.SEQUENTIAL,
        )

        orch_result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            original_query=query,
            execution_plan=plan,
            single_fallback=SkillRoute(
                skill_id="superpowers-architect",
                confidence=0.87,
                layer=RoutingLayer.AI_TRIAGE,
            ),
        )

        presenter = DecisionPresenter()
        present_result = presenter.present_orchestration_result(
            result=orch_result,
            platform=PlatformType.CLAUDE_CODE,
        )

        assert present_result.message != ""
        assert "superpowers-architect" in present_result.message
        assert "superpowers-optimize" in present_result.message
        assert "execute_plan" in present_result.actions or "accept" in present_result.actions

        executor = PlanExecutor()
        guide = executor.build_guide(plan)

        assert isinstance(guide, ExecutionGuide)
        assert len(guide.prompt) > 100
        assert len(guide.step_markers) >= 2
        assert "superpowers-architect" in guide.prompt
        assert "superpowers-optimize" in guide.prompt
        assert guide.completion_check != ""

        transition = executor.build_step_transition_prompt(plan, 1)
        assert "步骤" in transition or "step" in transition.lower()

        progress = executor.build_progress_summary(plan)
        assert "1" in progress

    def test_short_query_bypass(self) -> None:
        """E2E: Short query like 'ok' should NOT trigger routing."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("ok")

        assert decision.should_route is False
        assert decision.mode == InterceptionMode.NONE
        assert "short" in decision.reason.lower() or "too short" in decision.reason.lower()

    def test_explicit_skill_override(self) -> None:
        """E2E: User explicitly requests a skill with /skill syntax."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("/review this code")

        assert decision.should_route is True
        assert decision.mode == InterceptionMode.SINGLE
        assert "explicit" in decision.reason.lower() or "override" in decision.reason.lower()

        injector = SkillInjector()
        injection = injector.inject_single_skill(
            skill_id="gstack-review",
            platform=PlatformType.KIMI_CLI,
        )

        assert injection.method == InjectionMethod.INSTRUCTION
        assert "gstack-review" in str(injection.payload)

    def test_meta_query_bypass(self) -> None:
        """E2E: Meta queries about VibeSOP itself should NOT trigger routing."""
        interceptor = IntentInterceptor()

        meta_queries = [
            "how does vibe route work",
            "vibe skill configuration",
            "how does routing work",
        ]

        for query in meta_queries:
            decision = interceptor.should_intercept(query)
            assert decision.should_route is False, f"Meta query should bypass: {query}"
            assert decision.mode == InterceptionMode.NONE

    def test_fallback_no_match(self) -> None:
        """E2E: No skill matches -> transparent fallback with suggestions."""
        route_result = RoutingResult(
            primary=None,
            alternatives=[],
            routing_path=[
                RoutingLayer.AI_TRIAGE,
                RoutingLayer.EXPLICIT,
                RoutingLayer.SCENARIO,
                RoutingLayer.TFIDF,
                RoutingLayer.LEVENSHTEIN,
            ],
            query="something completely unrelated xyz123",
        )

        presenter = DecisionPresenter()
        present_result = presenter.present_single_result(
            result=route_result,
            platform=PlatformType.CLAUDE_CODE,
        )

        assert present_result.message != ""
        assert "fallback" in present_result.message.lower() or "no match" in present_result.message.lower()
        assert present_result.structured is not None
        assert present_result.structured.get("primary") is None


class TestPlatformAdapterAgentRuntime:
    """E2E: Platform adapters generate correct Agent Runtime artifacts."""

    def test_claude_code_generates_agent_runtime_hooks(self, tmp_path: Path) -> None:
        """E2E: Claude Code adapter generates Agent Runtime hook scripts."""
        adapter = ClaudeCodeAdapter()
        metadata = ManifestMetadata(platform="claude-code", version="1.0.0")
        manifest = Manifest(metadata=metadata, skills=[])

        result = adapter.render_config(manifest, tmp_path)

        assert result.success is True

        route_hook = tmp_path / "hooks" / "vibesop-route.sh"
        track_hook = tmp_path / "hooks" / "vibesop-track.sh"

        assert route_hook.exists(), "vibesop-route.sh should be generated"
        assert track_hook.exists(), "vibesop-track.sh should be generated"

        import stat
        route_stat = route_hook.stat()
        track_stat = track_hook.stat()
        assert route_stat.st_mode & stat.S_IXUSR, "vibesop-route.sh should be executable"
        assert track_stat.st_mode & stat.S_IXUSR, "vibesop-track.sh should be executable"

        route_content = route_hook.read_text()
        assert "vibe route" in route_content
        assert "additionalContext" in route_content
        assert "orchestrate" in route_content or "orchestrated" in route_content

        track_content = track_hook.read_text()
        assert "tool" in track_content
        assert "step" in track_content.lower() or "Step" in track_content

    def test_claude_code_routing_md_has_agent_runtime_rules(self, tmp_path: Path) -> None:
        """E2E: Claude Code routing.md includes Agent Runtime behavior rules."""
        adapter = ClaudeCodeAdapter()
        metadata = ManifestMetadata(platform="claude-code", version="1.0.0")
        manifest = Manifest(metadata=metadata, skills=[])

        result = adapter.render_config(manifest, tmp_path)
        assert result.success is True

        routing_md = tmp_path / "rules" / "routing.md"
        assert routing_md.exists()

        content = routing_md.read_text()
        assert "Agent Runtime Rules" in content
        assert "ACTIVE SKILL" in content
        assert "EXECUTION PLAN" in content
        assert "EXPLICIT SKILL" in content

    def test_claude_code_install_hooks_deploys_all_hooks(self, tmp_path: Path) -> None:
        """E2E: install_hooks deploys all 3 hooks including Agent Runtime hooks."""
        adapter = ClaudeCodeAdapter()
        results = adapter.install_hooks(tmp_path)

        assert "pre-session-end" in results
        assert "vibesop-route" in results
        assert "vibesop-track" in results

        assert results["pre-session-end"] is True
        assert results["vibesop-route"] is True
        assert results["vibesop-track"] is True

        assert (tmp_path / "hooks" / "pre-session-end.sh").exists()
        assert (tmp_path / "hooks" / "vibesop-route.sh").exists()
        assert (tmp_path / "hooks" / "vibesop-track.sh").exists()

    def test_kimi_cli_generates_agents_md(self, tmp_path: Path) -> None:
        """E2E: Kimi CLI adapter generates AGENTS.md with mandatory routing rules."""
        from vibesop.core.models import SkillDefinition

        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli", version="1.0.0")

        skill = SkillDefinition(
            id="systematic-debugging",
            name="Systematic Debugging",
            description="Debug errors systematically",
            trigger_when="error or test failure",
        )
        manifest = Manifest(metadata=metadata, skills=[skill])

        result = adapter.render_config(manifest, tmp_path)
        assert result.success is True

        agents_md = tmp_path / "AGENTS.md"
        assert agents_md.exists(), "AGENTS.md should be generated for Kimi CLI"

        content = agents_md.read_text()
        assert "vibe route" in content
        assert "SKILL.md" in content
        assert "MANDATORY" in content or "必须" in content
        assert "multi-intent" in content.lower() or "步骤" in content
        assert "fallback" in content.lower() or "降级" in content or "候选" in content

    def test_kimi_cli_agents_md_lists_skills(self, tmp_path: Path) -> None:
        """E2E: AGENTS.md contains the list of available skills."""
        from vibesop.core.models import SkillDefinition

        adapter = KimiCliAdapter()
        metadata = ManifestMetadata(platform="kimi-cli", version="1.0.0")

        skills = [
            SkillDefinition(id="skill-a", name="Skill A", description="Desc A", trigger_when="Trigger A"),
            SkillDefinition(id="skill-b", name="Skill B", description="Desc B", trigger_when="Trigger B"),
        ]
        manifest = Manifest(metadata=metadata, skills=skills)

        result = adapter.render_config(manifest, tmp_path)
        assert result.success is True

        content = (tmp_path / "AGENTS.md").read_text()
        assert "skill-a" in content
        assert "skill-b" in content
        assert "Skill A" in content
        assert "Skill B" in content

    def test_opencode_plugin_template_exists(self) -> None:
        """E2E: OpenCode plugin template files exist as reference implementation."""
        template_dir = (
            Path(__file__).parent.parent.parent
            / "src" / "vibesop" / "adapters" / "templates" / "opencode" / "plugin" / "vibesop"
        )

        index_ts = template_dir / "index.ts"
        readme_md = template_dir / "README.md"

        assert index_ts.exists(), "OpenCode plugin template (index.ts) should exist"
        assert readme_md.exists(), "OpenCode plugin README should exist"

        index_content = index_ts.read_text()
        assert "experimental.chat.system.transform" in index_content
        assert "chat.message" in index_content
        assert "tool.execute.before" in index_content
        assert "vibesop-skill" in index_content
        assert "vibesop-plan" in index_content

        readme_content = readme_md.read_text()
        assert "VibeSOP" in readme_content
        assert "OpenCode" in readme_content


class TestSlashCommandExecutionChain:
    """E2E: Full slash command chain from detection to execution."""

    def test_slash_command_help_full_chain(self) -> None:
        """E2E: /vibe-help detected and executed through full chain."""
        query = "/vibe-help"

        # Step 1: IntentInterceptor detects slash command
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept(query)

        assert decision.should_route is True
        assert decision.mode == InterceptionMode.SLASH_COMMAND
        assert "slash command" in decision.reason.lower()

        # Step 2: SlashCommandExecutor executes the command
        executor = SlashCommandExecutor()
        result = executor.execute(decision)

        assert result.success is True
        assert result.command == "/vibe-help"
        assert "/vibe-route" in result.message
        assert "/vibe-install" in result.message
        assert result.structured is not None
        assert result.structured["command"] == "/vibe-help"

    def test_slash_command_list_full_chain(self) -> None:
        """E2E: /vibe-list detected and executed."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("/vibe-list")

        assert decision.mode == InterceptionMode.SLASH_COMMAND

        executor = SlashCommandExecutor()
        result = executor.execute(decision)

        assert result.success is True
        assert result.command == "/vibe-list"

    def test_slash_command_unknown(self) -> None:
        """E2E: Unknown /vibe-* command returns helpful error."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("/vibe-unknown")

        assert decision.mode == InterceptionMode.SLASH_COMMAND

        executor = SlashCommandExecutor()
        result = executor.execute(decision)

        assert result.success is False
        assert "Unknown command" in result.message
        assert "/vibe-route" in result.message  # Suggests available commands

    def test_slash_command_direct_query(self) -> None:
        """E2E: Execute slash command directly without interceptor."""
        executor = SlashCommandExecutor()
        result = executor.execute_query("/vibe-help")

        assert result.success is True
        assert result.command == "/vibe-help"
        assert "vibe-route" in result.message.lower()

    def test_non_slash_command_rejected_by_executor(self) -> None:
        """E2E: Non-slash decision rejected by executor."""
        interceptor = IntentInterceptor()
        decision = interceptor.should_intercept("review my code")

        assert decision.mode != InterceptionMode.SLASH_COMMAND

        executor = SlashCommandExecutor()
        with pytest.raises(ValueError, match="SLASH_COMMAND"):
            executor.execute(decision)


class TestCrossPlatformConsistency:
    """E2E: Consistency across platform adapters."""

    def test_all_adapters_have_mandatory_routing_instruction(self, tmp_path: Path) -> None:
        """E2E: All platform configs mention mandatory vibe route workflow."""
        from vibesop.core.models import SkillDefinition

        metadata = ManifestMetadata(platform="claude-code", version="1.0.0")
        skill = SkillDefinition(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            trigger_when="Testing",
        )

        # Claude Code
        claude_adapter = ClaudeCodeAdapter()
        claude_manifest = Manifest(metadata=metadata, skills=[skill])
        claude_result = claude_adapter.render_config(claude_manifest, tmp_path / "claude")
        assert claude_result.success is True

        claude_md = (tmp_path / "claude" / "CLAUDE.md").read_text()
        assert "vibe route" in claude_md
        assert "MANDATORY" in claude_md

        # Kimi CLI
        kimi_adapter = KimiCliAdapter()
        kimi_manifest = Manifest(
            metadata=ManifestMetadata(platform="kimi-cli", version="1.0.0"),
            skills=[skill],
        )
        kimi_result = kimi_adapter.render_config(kimi_manifest, tmp_path / "kimi")
        assert kimi_result.success is True

        readme = (tmp_path / "kimi" / "README.md").read_text()
        assert "vibe route" in readme
        assert "MANDATORY" in readme
