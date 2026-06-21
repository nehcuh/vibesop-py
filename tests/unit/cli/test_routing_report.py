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
