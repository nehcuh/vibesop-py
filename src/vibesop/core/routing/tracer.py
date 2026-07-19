"""Routing tracer — per-layer diagnostic trace for routing transparency.

Inspired by SkillTree's routing trace mode (triggered by "路由调试" keyword),
this module captures a full decision tree for each route() call when enabled.

Outputs structured JSON traces to .vibe/traces/ for post-hoc analysis.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vibesop.utils.redaction import redact_sensitive

if TYPE_CHECKING:
    from vibesop.core.models import LayerDetail, RoutingLayer

logger = logging.getLogger(__name__)


@dataclass
class LayerTrace:
    """Trace record for a single routing layer attempt."""

    layer: str
    layer_number: int
    matched: bool
    matched_skill: str | None = None
    confidence: float = 0.0
    reason: str = ""
    duration_ms: float = 0.0
    candidates_considered: int = 0
    rejected: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RouteTrace:
    """Complete trace of a single routing request."""

    trace_id: str
    timestamp: str
    query: str
    layers: list[LayerTrace] = field(default_factory=list)
    final_skill: str | None = None
    final_confidence: float = 0.0
    final_layer: str | None = None
    total_duration_ms: float = 0.0
    mode: str = "single"  # "single" | "orchestrated"
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    degradation_level: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "query": self.query,
            "mode": self.mode,
            "total_duration_ms": self.total_duration_ms,
            "final": {
                "skill_id": self.final_skill,
                "confidence": self.final_confidence,
                "layer": self.final_layer,
                "degradation_level": self.degradation_level,
            },
            "alternatives": self.alternatives,
            "layers": [
                {
                    "layer": lt.layer,
                    "layer_number": lt.layer_number,
                    "matched": lt.matched,
                    "matched_skill": lt.matched_skill,
                    "confidence": lt.confidence,
                    "reason": lt.reason,
                    "duration_ms": lt.duration_ms,
                    "candidates_considered": lt.candidates_considered,
                    "rejected": lt.rejected,
                }
                for lt in self.layers
            ],
        }


class RoutingTracer:
    """Captures per-layer routing decisions for diagnostic trace output.

    When enabled, records every layer attempt during a route() call.
    Use `start_trace()` / `finish_trace()` around routing, then call
    `save()` to persist the trace to .vibe/traces/.

    Usage:
        tracer = RoutingTracer(enabled=True)
        tracer.start_trace("debug this error")
        # ... routing happens, calling record_layer() ...
        trace = tracer.finish_trace()
        tracer.save(trace)
    """

    def __init__(
        self,
        enabled: bool = False,
        traces_dir: Path | None = None,
    ) -> None:
        self.enabled = enabled
        self._traces_dir = traces_dir or Path(".vibe/traces")
        self._current: RouteTrace | None = None
        self._start_time: float = 0.0

    def start_trace(self, query: str, mode: str = "single") -> str:
        """Begin a new trace. Returns trace_id."""
        if not self.enabled:
            return ""
        import uuid

        tid = uuid.uuid4().hex[:12]
        self._current = RouteTrace(
            trace_id=tid,
            timestamp=datetime.now(UTC).isoformat(),
            query=query,
            mode=mode,
        )
        self._start_time = time.perf_counter()
        return tid

    def record_layer(
        self,
        layer: RoutingLayer,
        detail: LayerDetail,
        candidates_count: int = 0,
    ) -> None:
        """Record a single layer attempt."""
        if not self.enabled or self._current is None:
            return

        rejected = [
            {
                "skill_id": r.skill_id,
                "confidence": r.confidence,
                "reason": r.reason,
            }
            for r in detail.rejected_candidates
        ]

        lt = LayerTrace(
            layer=layer.value,
            layer_number=layer.layer_number,
            matched=detail.matched,
            matched_skill=detail.diagnostics.get("skill_id") if detail.matched else None,
            confidence=detail.diagnostics.get("confidence", 0.0),
            reason=detail.reason,
            duration_ms=detail.duration_ms,
            candidates_considered=candidates_count,
            rejected=rejected,
        )
        self._current.layers.append(lt)

    def finish_trace(
        self,
        final_skill: str | None = None,
        final_confidence: float = 0.0,
        final_layer: str | None = None,
        alternatives: list[dict[str, Any]] | None = None,
        degradation_level: str | None = None,
    ) -> RouteTrace | None:
        """Complete the trace and return it."""
        if not self.enabled or self._current is None:
            return None

        self._current.total_duration_ms = (time.perf_counter() - self._start_time) * 1000
        self._current.final_skill = final_skill
        self._current.final_confidence = final_confidence
        self._current.final_layer = final_layer
        self._current.alternatives = alternatives or []
        self._current.degradation_level = degradation_level

        trace = self._current
        self._current = None
        return trace

    def save(self, trace: RouteTrace | None) -> str | None:
        """Persist trace to .vibe/traces/<trace_id>.json. Returns file path.

        The query is redacted (F-07) — traces are a debugging surface and the
        raw query is the most PII-dense field.
        """
        if trace is None:
            return None
        self._traces_dir.mkdir(parents=True, exist_ok=True)
        data = trace.to_dict()
        data["query"] = redact_sensitive(data["query"])
        filepath = self._traces_dir / f"{trace.trace_id}.json"
        filepath.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        logger.debug("Routing trace saved: %s", filepath)
        return str(filepath)

    def clear(self) -> int:
        """Delete all saved traces (F-08). Returns files removed."""
        if not self._traces_dir.exists():
            return 0
        files = list(self._traces_dir.glob("*.json"))
        for f in files:
            f.unlink()
        logger.info("Cleared %d routing traces", len(files))
        return len(files)

    def list_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent traces from .vibe/traces/."""
        if not self._traces_dir.exists():
            return []

        files = sorted(
            self._traces_dir.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:limit]

        traces = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                traces.append(
                    {
                        "trace_id": data.get("trace_id", f.stem),
                        "timestamp": data.get("timestamp", ""),
                        "query": data.get("query", "")[:80],
                        "final_skill": data.get("final", {}).get("skill_id"),
                        "confidence": data.get("final", {}).get("confidence", 0),
                        "layer_count": len(data.get("layers", [])),
                    }
                )
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
                continue
        return traces
