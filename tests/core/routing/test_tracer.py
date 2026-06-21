"""Tests for the RoutingTracer."""

from pathlib import Path

from vibesop.core.models import LayerDetail, RoutingLayer
from vibesop.core.routing.tracer import LayerTrace, RouteTrace, RoutingTracer


class TestLayerTrace:
    def test_creation(self):
        lt = LayerTrace(layer="keyword", layer_number=3, matched=True, reason="test")
        assert lt.layer == "keyword"
        assert lt.matched

    def test_defaults(self):
        lt = LayerTrace(layer="explicit", layer_number=0, matched=False)
        assert lt.confidence == 0.0
        assert lt.matched_skill is None
        assert lt.rejected == []


class TestRouteTrace:
    def test_to_dict(self):
        trace = RouteTrace(
            trace_id="abc123",
            timestamp="2026-01-01T00:00:00",
            query="test query",
            total_duration_ms=10.5,
        )
        d = trace.to_dict()
        assert d["trace_id"] == "abc123"
        assert d["query"] == "test query"
        assert d["final"]["skill_id"] is None

    def test_with_layers(self):
        trace = RouteTrace(
            trace_id="abc123",
            timestamp="2026-01-01T00:00:00",
            query="test query",
            layers=[
                LayerTrace(
                    layer="keyword",
                    layer_number=3,
                    matched=True,
                    matched_skill="test-skill",
                    confidence=0.85,
                    reason="matched",
                    duration_ms=2.1,
                    candidates_considered=50,
                ),
            ],
            final_skill="test-skill",
            final_confidence=0.85,
            final_layer="keyword",
        )
        d = trace.to_dict()
        assert len(d["layers"]) == 1
        assert d["final"]["skill_id"] == "test-skill"
        assert d["layers"][0]["matched"]
        assert d["layers"][0]["confidence"] == 0.85


class TestRoutingTracer:
    def test_disabled_by_default(self):
        t = RoutingTracer()
        assert not t.enabled
        tid = t.start_trace("query")
        assert tid == ""

    def test_enabled_trace_lifecycle(self, tmp_path: Path):
        traces_dir = tmp_path / "traces"
        t = RoutingTracer(enabled=True, traces_dir=traces_dir)
        assert t.enabled

        tid = t.start_trace("debug this error")
        assert len(tid) == 12

        # Record a few layers
        for layer, matched, conf in [
            (RoutingLayer.EXPLICIT, False, 0.0),
            (RoutingLayer.AI_TRIAGE, True, 0.85),
        ]:
            detail = LayerDetail(
                layer=layer,
                matched=matched,
                reason="test reason" if not matched else "matched via LLM",
                duration_ms=1.5,
                diagnostics={"skill_id": "gstack/investigate"} if matched else {},
            )
            t.record_layer(layer, detail, 50)

        trace = t.finish_trace(
            final_skill="gstack/investigate",
            final_confidence=0.85,
            final_layer="ai_triage",
        )
        assert trace is not None
        assert trace.final_skill == "gstack/investigate"
        assert trace.final_confidence == 0.85
        assert len(trace.layers) == 2
        assert trace.layers[1].matched

        # Save and verify
        path = t.save(trace)
        assert path is not None
        assert traces_dir.exists()
        files = list(traces_dir.glob("*.json"))
        assert len(files) == 1

    def test_list_traces(self, tmp_path: Path):
        traces_dir = tmp_path / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        (traces_dir / "trace1.json").write_text(
            '{"trace_id":"trace1","timestamp":"","query":"q1","layers":[],'
            '"final":{"skill_id":"a","confidence":0.8,"layer":"x"},"total_duration_ms":1}'
        )
        (traces_dir / "trace2.json").write_text(
            '{"trace_id":"trace2","timestamp":"","query":"q2","layers":[],'
            '"final":{"skill_id":null,"confidence":0,"layer":"no_match"},"total_duration_ms":1}'
        )

        t = RoutingTracer(enabled=True, traces_dir=traces_dir)
        traces = t.list_traces(limit=5)
        assert len(traces) == 2
        assert traces[0]["trace_id"] in ("trace1", "trace2")

    def test_save_disabled(self):
        t = RoutingTracer(enabled=False)
        path = t.save(None)
        assert path is None
