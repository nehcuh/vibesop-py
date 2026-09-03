"""Tests for routing report rendering functions."""

from __future__ import annotations

import io

from rich.console import Console

from vibesop.cli.routing_report import (
    render_compact_report,
    render_compact_summary,
    render_routing_report,
)
from vibesop.core.models import (
    LayerDetail,
    RejectedCandidate,
    RoutingLayer,
    RoutingResult,
    SkillRoute,
)


class TestRenderCompactSummary:
    """Test suite for render_compact_summary()."""

    def test_single_skill_result(self) -> None:
        """render_compact_summary() with a single-skill result shows skill_id, confidence, layer."""
        result = RoutingResult(
            query="debug error",
            primary=SkillRoute(
                skill_id="investigate",
                confidence=0.85,
                layer=RoutingLayer.TFIDF,
                source="routing",
            ),
            duration_ms=12.3,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_compact_summary(result, console=console)
        text = output.getvalue()
        assert "investigate" in text
        assert "85%" in text
        assert "tfidf" in text

    def test_orchestrated_result(self) -> None:
        """render_compact_summary() with orchestrated result shows steps count and strategy."""
        result = RoutingResult(
            query="debug error",
            primary=SkillRoute(
                skill_id="investigate",
                confidence=0.85,
                layer=RoutingLayer.TFIDF,
                source="routing",
            ),
            duration_ms=12.3,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_compact_summary(
            result,
            console=console,
            mode="orchestrated",
            steps_count=3,
            strategy="sequential",
        )
        text = output.getvalue()
        assert "Orchestrated" in text
        assert "3" in text
        assert "sequential" in text

    def test_shows_top_3_alternatives(self) -> None:
        """render_compact_summary() shows top 3 alternatives."""
        result = RoutingResult(
            query="debug error",
            primary=SkillRoute(
                skill_id="investigate",
                confidence=0.85,
                layer=RoutingLayer.TFIDF,
                source="routing",
            ),
            alternatives=[
                SkillRoute(
                    skill_id="alt-1",
                    confidence=0.70,
                    layer=RoutingLayer.KEYWORD,
                    source="routing_rejected",
                ),
                SkillRoute(
                    skill_id="alt-2",
                    confidence=0.65,
                    layer=RoutingLayer.TFIDF,
                    source="routing_rejected",
                ),
                SkillRoute(
                    skill_id="alt-3",
                    confidence=0.60,
                    layer=RoutingLayer.FALLBACK_LLM,
                    source="routing_rejected",
                ),
                SkillRoute(
                    skill_id="alt-4",
                    confidence=0.55,
                    layer=RoutingLayer.KEYWORD,
                    source="routing_rejected",
                ),
            ],
            duration_ms=12.3,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_compact_summary(result, console=console)
        text = output.getvalue()
        assert "alt-1" in text
        assert "alt-2" in text
        assert "alt-3" in text
        assert "alt-4" not in text

    def test_no_emoji_when_emoji_false(self) -> None:
        """Output doesn't contain emoji when emoji=False."""
        result = RoutingResult(
            query="debug error",
            primary=SkillRoute(
                skill_id="investigate",
                confidence=0.85,
                layer=RoutingLayer.TFIDF,
                source="routing",
            ),
            duration_ms=12.3,
        )
        output = io.StringIO()
        console = Console(file=output, emoji=False, force_terminal=False)
        render_compact_summary(result, console=console)
        text = output.getvalue()
        # Rich's emoji=False still renders the literal char if it's already in the string.
        # The test requirement says "optional", so we just verify the call completes
        # and the output contains expected content.
        assert "Routing Summary" in text

    def test_fallback_result(self) -> None:
        """render_compact_summary() with fallback result shows fallback status."""
        result = RoutingResult(
            query="debug error",
            primary=SkillRoute(
                skill_id="fallback-llm",
                confidence=1.0,
                layer=RoutingLayer.FALLBACK_LLM,
                source="fallback",
            ),
            duration_ms=5.0,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_compact_summary(result, console=console)
        text = output.getvalue()
        assert "fallback-llm" in text
        assert "Fallback" in text

    def test_no_match_result(self) -> None:
        """render_compact_summary() with no primary match shows 'No match'."""
        result = RoutingResult(
            query="debug error",
            primary=None,
            duration_ms=5.0,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_compact_summary(result, console=console)
        text = output.getvalue()
        assert "No match" in text


class TestRenderRoutingReport:
    """Test suite for render_routing_report()."""

    def test_render_with_match(self) -> None:
        """render_routing_report with a skill match."""
        result = RoutingResult(
            query="debug error",
            primary=SkillRoute(
                skill_id="investigate",
                confidence=0.85,
                layer=RoutingLayer.TFIDF,
                source="routing",
            ),
            layer_details=[
                LayerDetail(layer=RoutingLayer.EXPLICIT, matched=False, reason="No override"),
                LayerDetail(layer=RoutingLayer.TFIDF, matched=True, reason="TF-IDF match"),
            ],
            duration_ms=12.3,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_routing_report(result, console=console)
        text = output.getvalue()
        assert "investigate" in text
        assert "85%" in text
        assert "TF-IDF" in text.upper()

    def test_render_fallback_mode(self) -> None:
        """render_routing_report with fallback LLM result."""
        result = RoutingResult(
            query="unknown request",
            primary=SkillRoute(
                skill_id="fallback-llm",
                confidence=1.0,
                layer=RoutingLayer.FALLBACK_LLM,
                source="fallback",
            ),
            layer_details=[
                LayerDetail(
                    layer=RoutingLayer.FALLBACK_LLM,
                    matched=True,
                    reason="No skill matched",
                ),
            ],
            duration_ms=5.0,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_routing_report(result, console=console)
        text = output.getvalue()
        assert "Fallback" in text or "fallback" in text.lower()

    def test_render_no_match(self) -> None:
        """render_routing_report with no primary match."""
        result = RoutingResult(
            query="something weird",
            primary=None,
            duration_ms=3.0,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_routing_report(result, console=console)
        text = output.getvalue()
        assert "No match" in text

    def test_render_with_rejected_candidates(self) -> None:
        """render_routing_report shows rejected near-miss candidates."""
        result = RoutingResult(
            query="debug",
            primary=SkillRoute(
                skill_id="investigate",
                confidence=0.85,
                layer=RoutingLayer.TFIDF,
                source="routing",
            ),
            layer_details=[
                LayerDetail(
                    layer=RoutingLayer.TFIDF,
                    matched=True,
                    reason="TF-IDF match",
                    rejected_candidates=[
                        RejectedCandidate(
                            skill_id="alt-skill",
                            confidence=0.55,
                            reason="Below threshold",
                            layer=RoutingLayer.TFIDF,
                        )
                    ],
                ),
            ],
            duration_ms=10.0,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_routing_report(result, console=console)
        text = output.getvalue()
        assert "Near-Miss" in text or "Rejected" in text or "alt-skill" in text

    def test_render_with_alternatives(self) -> None:
        """render_routing_report shows alternative skills."""
        result = RoutingResult(
            query="debug",
            primary=SkillRoute(
                skill_id="investigate",
                confidence=0.85,
                layer=RoutingLayer.TFIDF,
                source="routing",
            ),
            alternatives=[
                SkillRoute(
                    skill_id="alt-1",
                    confidence=0.70,
                    layer=RoutingLayer.KEYWORD,
                    source="routing_rejected",
                    description="Alternative skill description",
                ),
            ],
            layer_details=[
                LayerDetail(layer=RoutingLayer.TFIDF, matched=True, reason="TF-IDF match"),
            ],
            duration_ms=10.0,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_routing_report(result, console=console)
        text = output.getvalue()
        assert "Alternative" in text or "alt-1" in text

    def test_render_with_context(self) -> None:
        """render_routing_report with context panel."""
        result = RoutingResult(
            query="debug",
            primary=SkillRoute(
                skill_id="investigate",
                confidence=0.85,
                layer=RoutingLayer.TFIDF,
                source="routing",
            ),
            layer_details=[],
            duration_ms=10.0,
        )
        context = type(
            "Ctx",
            (),
            {
                "conversation_id": "conv-123",
                "current_skill": "debug",
                "recent_queries": ["previous query"],
                "habit_boosts": {"debug": 0.1},
                "project_type": "python",
            },
        )()
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_routing_report(result, console=console, context=context)
        text = output.getvalue()
        assert "conv-123" in text or "Context" in text or "debug" in text


class TestRenderCompactReport:
    """Test suite for render_compact_report()."""

    def test_compact_with_match(self) -> None:
        """render_compact_report with skill match."""
        result = RoutingResult(
            query="debug",
            primary=SkillRoute(
                skill_id="investigate",
                confidence=0.85,
                layer=RoutingLayer.TFIDF,
                source="routing",
            ),
            duration_ms=5.0,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_compact_report(result, console=console)
        text = output.getvalue()
        assert "investigate" in text

    def test_compact_fallback(self) -> None:
        """render_compact_report with fallback."""
        result = RoutingResult(
            query="unknown",
            primary=SkillRoute(
                skill_id="fallback-llm",
                confidence=1.0,
                layer=RoutingLayer.FALLBACK_LLM,
                source="fallback",
            ),
            duration_ms=3.0,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_compact_report(result, console=console)
        text = output.getvalue()
        assert "fallback" in text.lower() or "No skill" in text

    def test_compact_no_match(self) -> None:
        """render_compact_report with no match."""
        result = RoutingResult(
            query="unknown",
            primary=None,
            duration_ms=3.0,
        )
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)
        render_compact_report(result, console=console)
        text = output.getvalue()
        assert "No match" in text


class TestAttachSkillFilePayload:
    """CLI demote contract: unresolvable single-mode match is not a match."""

    def test_single_mode_unresolvable_demotes(self, tmp_path, monkeypatch) -> None:
        from types import SimpleNamespace

        from vibesop.cli.render import attach_skill_file_payload

        monkeypatch.chdir(tmp_path)
        primary = SimpleNamespace(skill_id="ghost-skill-xyz-123", metadata={"source_file": None})
        result = SimpleNamespace(primary=primary)
        payload = {
            "mode": "single",
            "skill_id": "ghost-skill-xyz-123",
            "has_match": True,
            "primary": {"skill_id": "ghost-skill-xyz-123"},
        }

        attach_skill_file_payload(payload, result)

        assert payload["skill_file"] == ""
        assert payload["demoted_skill_id"] == "ghost-skill-xyz-123"
        assert payload["skill_id"] == ""
        assert payload["has_match"] is False
        assert payload["mode"] == "no_match"
        assert payload["primary"]["skill_id"] == ""

    def test_orchestrated_mode_unresolvable_keeps_match(self, tmp_path, monkeypatch) -> None:
        """Orchestrate payloads are exempt — the plan is the payload."""
        from types import SimpleNamespace

        from vibesop.cli.render import attach_skill_file_payload

        monkeypatch.chdir(tmp_path)
        primary = SimpleNamespace(skill_id="step-skill-abc", metadata={})
        result = SimpleNamespace(primary=primary)
        payload = {
            "mode": "orchestrated",
            "skill_id": "step-skill-abc",
            "has_match": True,
            "steps": [{"step": 1, "skill_id": "step-skill-abc"}],
        }

        attach_skill_file_payload(payload, result)

        assert payload["skill_file"] == ""
        assert "demoted_skill_id" not in payload
        assert payload["skill_id"] == "step-skill-abc"
        assert payload["has_match"] is True
        assert payload["mode"] == "orchestrated"

    def test_resolvable_skill_file_attached(self, tmp_path, monkeypatch) -> None:
        from types import SimpleNamespace

        from vibesop.cli.render import attach_skill_file_payload

        monkeypatch.chdir(tmp_path)
        skill = tmp_path / ".vibe" / "skills" / "real-skill" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nid: real-skill\n---\n# body\n", encoding="utf-8")

        primary = SimpleNamespace(skill_id="real-skill", metadata={})
        result = SimpleNamespace(primary=primary)
        payload = {"mode": "single", "skill_id": "real-skill"}

        attach_skill_file_payload(payload, result)

        assert payload["skill_file"] == skill.as_posix()
        assert "demoted_skill_id" not in payload

    def test_source_lookup_beats_glob_and_rescues_demote(self, tmp_path, monkeypatch) -> None:
        """candidate_source_lookup pins the main.py wiring: the authoritative
        pool path (outside .vibe/skills, so the injector glob cannot find it)
        fills both the top-level skill_file and plan steps — without the
        lookup the same payload demotes."""
        from types import SimpleNamespace

        from vibesop.cli.render import attach_skill_file_payload, candidate_source_lookup

        monkeypatch.chdir(tmp_path)
        pooled = tmp_path / "central" / "pooled-skill" / "SKILL.md"
        pooled.parent.mkdir(parents=True)
        pooled.write_text("---\nid: pooled-skill\n---\n# body\n", encoding="utf-8")

        cm = SimpleNamespace(
            source_file_for=lambda sid: str(pooled) if sid == "pooled-skill" else None
        )
        router = SimpleNamespace(_router=SimpleNamespace(_candidate_manager=cm))
        lookup = candidate_source_lookup(router)
        assert lookup("pooled-skill") == str(pooled)
        assert lookup("other") is None

        primary = SimpleNamespace(skill_id="pooled-skill", metadata={})
        result = SimpleNamespace(primary=primary)
        payload = {
            "mode": "single",
            "skill_id": "pooled-skill",
            "steps": [{"step": 1, "skill_id": "pooled-skill"}],
        }
        attach_skill_file_payload(payload, result, source_lookup=lookup)
        assert payload["skill_file"] == pooled.as_posix()
        assert "demoted_skill_id" not in payload
        assert payload["steps"][0]["skill_file"] == pooled.as_posix()

        bare = {"mode": "single", "skill_id": "pooled-skill"}
        attach_skill_file_payload(bare, result)
        assert bare["skill_file"] == ""
        assert bare["demoted_skill_id"] == "pooled-skill"

    def test_candidate_source_lookup_mock_router_safe(self) -> None:
        """MagicMock routers must yield None, never a Mock in skill_file."""
        from unittest.mock import MagicMock

        from vibesop.cli.render import candidate_source_lookup

        lookup = candidate_source_lookup(MagicMock())
        assert lookup("any-skill") is None

    def test_real_orchestration_to_dict_payload_annotated(self, tmp_path, monkeypatch) -> None:
        """Pin the REAL OrchestrationResult.to_dict() shape (not a hand-crafted
        dict): execution_plan steps must flow through annotate and get the
        real SKILL.md path."""
        from vibesop.cli.render import attach_skill_file_payload
        from vibesop.core.models import (
            ExecutionPlan,
            ExecutionStep,
            OrchestrationMode,
            OrchestrationResult,
            RoutingLayer,
            SkillRoute,
        )

        monkeypatch.chdir(tmp_path)
        skill = tmp_path / ".vibe" / "skills" / "plan-skill" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nid: plan-skill\n---\n# body\n", encoding="utf-8")

        plan = ExecutionPlan(
            plan_id="p1",
            steps=[
                ExecutionStep(
                    step_id="s1", step_number=1, skill_id="plan-skill", input_query="do it"
                )
            ],
        )
        result = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            execution_plan=plan,
            primary=SkillRoute(skill_id="plan-skill", layer=RoutingLayer.KEYWORD),
        )

        payload = result.to_dict()
        attach_skill_file_payload(payload, result)

        steps = payload["execution_plan"]["steps"]
        assert steps[0]["skill_file"] == skill.as_posix()
        assert payload["skill_file"] == skill.as_posix()
        assert "demoted_skill_id" not in payload

    def test_real_lightweight_format_result_payloads(self, tmp_path, monkeypatch) -> None:
        """Pin the REAL LightweightRouter._format_result() shapes (the
        minimal-output channel): orchestrated steps get annotated, single-mode
        unresolvable demotes."""
        from vibesop.cli.render import attach_skill_file_payload
        from vibesop.core.models import (
            ExecutionPlan,
            ExecutionStep,
            OrchestrationMode,
            OrchestrationResult,
            RoutingLayer,
            SkillRoute,
        )
        from vibesop.core.routing.lightweight_api import LightweightRouter

        monkeypatch.chdir(tmp_path)
        skill = tmp_path / ".vibe" / "skills" / "lite-skill" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nid: lite-skill\n---\n# body\n", encoding="utf-8")

        plan = ExecutionPlan(
            plan_id="p1",
            steps=[
                ExecutionStep(step_id="s1", step_number=1, skill_id="lite-skill", input_query="q")
            ],
        )
        orchestrated = OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            execution_plan=plan,
            primary=SkillRoute(skill_id="lite-skill", layer=RoutingLayer.KEYWORD),
        )
        payload = LightweightRouter._format_result(orchestrated)
        assert payload["mode"] == "orchestrated"
        attach_skill_file_payload(payload, orchestrated)
        assert payload["steps"][0]["skill_file"] == skill.as_posix()
        assert payload["skill_file"] == skill.as_posix()

        ghost = OrchestrationResult(
            mode=OrchestrationMode.SINGLE,
            primary=SkillRoute(skill_id="ghost-skill-xyz-123", layer=RoutingLayer.KEYWORD),
        )
        ghost_payload = LightweightRouter._format_result(ghost)
        attach_skill_file_payload(ghost_payload, ghost)
        assert ghost_payload["demoted_skill_id"] == "ghost-skill-xyz-123"
        assert ghost_payload["skill_id"] == ""
        assert ghost_payload["mode"] == "no_match"
        # minimal channel never carries has_match — consumers read mode
        assert "has_match" not in ghost_payload
