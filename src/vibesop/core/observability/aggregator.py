"""Span aggregator — transforms raw spans into structured metrics.

Consumed by the metric-driven loop system and the instinct learner
to bridge the gap between observability data and optimization actions.

Reads spans from ``.vibe/observability/spans.jsonl`` (written by SpanWriter).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SkillMetrics:
    """Aggregated metrics for a single skill over a time window.

    Source field indicates data quality:
    - "spans": most accurate (agent-internal spans)
    - "analytics": routing history (analytics.jsonl, coarser)
    - "loop_records": loop execution records (minimal data)
    - "none": no data available
    """

    skill_id: str
    total_executions: int = 0
    success_count: int = 0
    avg_duration_ms: float = 0.0
    avg_tokens: int = 0
    avg_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    top_errors: list[str] = field(default_factory=list)
    llm_success_rate: float = 0.0
    llm_call_count: int = 0
    tool_call_distribution: dict[str, int] = field(default_factory=dict)
    source: str = "none"
    window_hours: int = 24

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.success_count / self.total_executions

    @property
    def cost_usd_per_execution(self) -> float:
        """Average cost in USD per execution (total / executions)."""
        if self.total_executions == 0:
            return 0.0
        return self.total_cost_usd / self.total_executions


@dataclass
class PatternSeq:
    """A detected repeatable sequence of tool calls from span data."""

    steps: list[str]
    occurrence_count: int = 0
    avg_duration_ms: float = 0.0


@dataclass
class AnomalyEvent:
    """A detected anomaly from span data."""

    skill_id: str
    event_type: str  # "success_rate_drop", "duration_spike", "new_error_type"
    description: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SpanAggregator:
    """Aggregates raw span data into structured metrics for downstream consumers."""

    def __init__(self, spans_path: Path | str | None = None) -> None:
        self._spans_path = (
            Path(spans_path) if spans_path else Path(".vibe/observability/spans.jsonl")
        )
        self._all_skills: set[str] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_skill_metrics(
        self,
        skill_id: str,
        window_hours: int = 24,
        use_analytics_fallback: bool = True,
        project_id: str | None = None,
    ) -> SkillMetrics:
        """Get aggregated metrics for a skill over a time window.

        Attribution: a span is considered to belong to ``skill_id`` if EITHER:
        * its own ``metadata.skill_id`` matches, OR
        * it shares a ``trace_id`` with a task-span whose ``metadata.skill_id``
          matches (covers llm-spans emitted by SpanWrappedProvider — they
          carry ``task_id`` but not ``skill_id``).

        If ``project_id`` is provided, spans whose ``project_id`` differs are
        excluded — prevents cross-project contamination when multiple projects
        share a span file (rare today; becomes important when storage path
        is anchored to a shared cache).

        If no spans data is available and ``use_analytics_fallback`` is True,
        falls back to analytics.jsonl data (coarser, but available sooner).
        """
        metrics = SkillMetrics(skill_id=skill_id, window_hours=window_hours, source="none")

        # Primary: spans from agent-internal observability
        spans = self._read_spans_in_window(window_hours)
        if project_id is not None:
            spans = [s for s in spans if s.get("project_id", "default") == project_id]
        attribution = self._build_attribution_map(spans)
        skill_spans = [s for s in spans if self._span_belongs_to_skill(s, skill_id, attribution)]
        tasks = [s for s in skill_spans if s.get("span_kind") == "task"]

        if tasks:
            metrics.source = "spans"
            metrics.total_executions = len(tasks)
            metrics.success_count = sum(1 for t in tasks if t.get("status") == "ok")
            durations = [t.get("duration_ms", 0) or 0 for t in tasks if t.get("duration_ms")]
            metrics.avg_duration_ms = round(sum(durations) / len(durations)) if durations else 0.0

            # LLM child spans (now attributable via trace_id propagation)
            llm_spans = [s for s in skill_spans if s.get("span_kind") == "llm"]
            metrics.llm_call_count = len(llm_spans)
            if llm_spans:
                llm_ok = sum(1 for s in llm_spans if s.get("status") == "ok")
                metrics.llm_success_rate = llm_ok / len(llm_spans)
                # Token + cost aggregation prefers LLM child spans when present
                # (they carry real token counts; task-spans have tokens_input=0
                # pre-M2). Filter out estimated tokens to avoid polluting the mean.
                measured = [
                    s
                    for s in llm_spans
                    if (s.get("metadata", {}) or {}).get("token_accounting") == "measured"
                ]
                token_source = measured or llm_spans
                metrics.avg_tokens = round(
                    sum(s.get("tokens_input", 0) + s.get("tokens_output", 0) for s in token_source)
                    / len(token_source)
                )
                metrics.total_cost_usd = round(sum(s.get("cost_usd", 0) or 0 for s in llm_spans), 6)
                metrics.avg_cost_usd = (
                    round(metrics.total_cost_usd / len(tasks), 6) if tasks else 0.0
                )
            else:
                # No LLM spans — fall back to task-span token field (often 0)
                metrics.avg_tokens = round(
                    sum(t.get("tokens_input", 0) + t.get("tokens_output", 0) for t in tasks)
                    / len(tasks)
                )
                metrics.total_cost_usd = round(sum(t.get("cost_usd", 0) or 0 for t in tasks), 6)
                metrics.avg_cost_usd = (
                    round(metrics.total_cost_usd / len(tasks), 6) if tasks else 0.0
                )

            # Tool call child spans
            tool_spans = [s for s in skill_spans if s.get("span_kind") == "tool_call"]
            for t in tool_spans:
                tool_name = t.get("name", "unknown").split(":", 1)[-1].strip()
                metrics.tool_call_distribution[tool_name] = (
                    metrics.tool_call_distribution.get(tool_name, 0) + 1
                )

            # Error collection
            error_tasks = [t for t in tasks if t.get("status") == "error"]
            error_counts: dict[str, int] = {}
            for t in error_tasks:
                err = t.get("error_message", "unknown")[:80]
                error_counts[err] = error_counts.get(err, 0) + 1
            metrics.top_errors = [
                e for e, _ in sorted(error_counts.items(), key=lambda x: -x[1])[:5]
            ]

            return metrics

        # Fallback: analytics.jsonl (if no spans data yet)
        if use_analytics_fallback:
            analytics_metrics = self._get_analytics_fallback(skill_id, window_hours)
            if analytics_metrics:
                return analytics_metrics

        return metrics

    def get_pattern_sequences(self, min_occurrences: int = 5) -> list[PatternSeq]:
        """Extract repeatable tool call sequences from span data.

        Groups consecutive tool_call spans within the same trace and
        identifies sequences that appear frequently.
        """
        spans = self._read_spans_in_window(window_hours=168)  # 7 days
        # Group by trace_id
        traces: dict[str, list[dict]] = {}
        for s in spans:
            tid = s.get("trace_id", "")
            if tid:
                traces.setdefault(tid, []).append(s)

        # Extract tool call sequences per trace
        sequence_counts: dict[str, PatternSeq] = {}
        for _tid, trace_spans in traces.items():
            tools = [s for s in trace_spans if s.get("span_kind") == "tool_call"]
            if len(tools) < 2:
                continue
            # Sort by started_at
            tools.sort(key=lambda t: t.get("started_at", ""))
            steps = [t.get("name", "?").split(":", 1)[-1].strip() for t in tools]
            key = "→".join(steps)
            if key in sequence_counts:
                sequence_counts[key].occurrence_count += 1
            else:
                sequence_counts[key] = PatternSeq(steps=steps, occurrence_count=1)

        return [s for s in sequence_counts.values() if s.occurrence_count >= min_occurrences]

    def get_anomaly_events(self, skill_id: str) -> list[AnomalyEvent]:
        """Detect anomalies for a skill by comparing recent vs baseline metrics.

        Uses a simple heuristic: recent window (1h) vs baseline (24h).
        """
        recent = self.get_skill_metrics(skill_id, window_hours=1, use_analytics_fallback=False)
        baseline = self.get_skill_metrics(skill_id, window_hours=24, use_analytics_fallback=False)

        anomalies: list[AnomalyEvent] = []

        # Success rate drop
        if (
            baseline.success_rate > 0.5
            and recent.success_rate < baseline.success_rate * 0.5
            and recent.total_executions >= 3
        ):
            anomalies.append(
                AnomalyEvent(
                    skill_id=skill_id,
                    event_type="success_rate_drop",
                    description=(
                        f"Success rate dropped from {baseline.success_rate:.0%} to "
                        f"{recent.success_rate:.0%} (n={recent.total_executions})"
                    ),
                )
            )

        # Duration spike
        if (
            baseline.avg_duration_ms > 0
            and recent.avg_duration_ms > baseline.avg_duration_ms * 3
            and recent.total_executions >= 3
        ):
            anomalies.append(
                AnomalyEvent(
                    skill_id=skill_id,
                    event_type="duration_spike",
                    description=(
                        f"Avg duration spiked from {baseline.avg_duration_ms:.0f}ms to "
                        f"{recent.avg_duration_ms:.0f}ms"
                    ),
                )
            )

        if not anomalies and recent.source == "none":
            anomalies.append(
                AnomalyEvent(
                    skill_id=skill_id,
                    event_type="no_data",
                    description=f"No span data available for skill '{skill_id}'",
                )
            )

        return anomalies

    def get_all_skill_ids(self) -> set[str]:
        """Return all skill IDs observed in span data (last 30 days).

        Includes skills attributed via trace_id propagation (i.e. skills
        that only show up on task-spans but whose llm-spans also belong
        to them by attribution).
        """
        spans = self._read_spans_in_window(window_hours=720)  # 30 days
        attribution = self._build_attribution_map(spans)
        skill_ids: set[str] = set()
        for s in spans:
            sid = self._skill_of(s, attribution)
            if sid:
                skill_ids.add(sid)
        return skill_ids

    def has_data(self) -> bool:
        """Quick check: is there any span data available?"""
        if not self._spans_path.exists():
            return False
        return self._spans_path.stat().st_size > 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_attribution_map(spans: list[dict[str, Any]]) -> dict[str, str]:
        """Build a ``trace_id → skill_id`` map from task-spans.

        ``agent_runtime`` writes ``metadata.skill_id`` to the root task-span
        after routing completes (agent_runtime.py:551). Descendant llm-spans
        share the same ``trace_id`` but don't carry ``skill_id`` themselves
        — consumers use this map to attribute them.

        Note: assumes one root task-span per trace_id (true today — only
        ``agent_runtime.handle_query`` calls ``tracer.trace()``, once per
        query). If nested task-spans are introduced (e.g. a workflow_node
        that itself opens a sub-trace), the last-writer-wins here will
        silently overwrite the root skill_id. Tagged as P2 cleanup when
        tracer gains proper parent-child task_id inheritance.
        """
        mapping: dict[str, str] = {}
        for s in spans:
            if s.get("span_kind") != "task":
                continue
            tid = s.get("trace_id", "")
            if not tid:
                continue
            meta = s.get("metadata") or {}
            sid = meta.get("skill_id") if isinstance(meta, dict) else None
            if sid:
                mapping[tid] = sid
        return mapping

    @staticmethod
    def _skill_of(span: dict[str, Any], attribution: dict[str, str]) -> str | None:
        """Resolve the skill_id for a span: own metadata first, then trace_id map."""
        meta = span.get("metadata") or {}
        own = meta.get("skill_id") if isinstance(meta, dict) else None
        if own:
            return own
        tid = span.get("trace_id", "")
        return attribution.get(tid) if tid else None

    @staticmethod
    def _span_belongs_to_skill(
        span: dict[str, Any],
        skill_id: str,
        attribution: dict[str, str],
    ) -> bool:
        return SpanAggregator._skill_of(span, attribution) == skill_id

    def _read_spans_in_window(self, window_hours: int) -> list[dict[str, Any]]:
        """Read spans within the given time window from JSONL."""
        if not self._spans_path.exists():
            return []
        cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
        spans: list[dict[str, Any]] = []
        with self._spans_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Normalise metadata: SpanWriter serialises metadata as
                # a JSON string (after redaction), so deserialise it back
                # to a dict for consumers.
                meta = record.get("metadata")
                if isinstance(meta, str):
                    try:
                        record["metadata"] = json.loads(meta)
                    except (json.JSONDecodeError, TypeError):
                        record["metadata"] = {}
                elif not isinstance(meta, dict):
                    record["metadata"] = {}
                started = record.get("started_at", "")
                if started:
                    try:
                        dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                        # Span writers should always emit tz-aware ISO strings,
                        # but a tz-naive value (e.g. "2026-07-24T10:00:00")
                        # would raise TypeError against the tz-aware cutoff and
                        # be silently included via the except branch — masking
                        # real out-of-window data. Treat naive as UTC (matches
                        # the rest of the observability stack).
                        # (deep-diagnosis-2026-07-24 P1-2.)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=UTC)
                        if dt >= cutoff:
                            spans.append(record)
                    except (ValueError, TypeError):
                        spans.append(record)  # include if can't parse date
        return spans

    def _get_analytics_fallback(self, skill_id: str, window_hours: int) -> SkillMetrics | None:
        """Fallback to analytics.jsonl when no span data exists."""
        analytics_path = self._spans_path.parent.parent / "analytics.jsonl"
        if not analytics_path.exists():
            return None
        cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
        total = 0
        durations: list[float] = []
        with analytics_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("primary_skill") == skill_id:
                    ts = record.get("timestamp", "")
                    if ts:
                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            # Same tz-naive guard as _read_spans_in_window
                            # (deep-diagnosis-2026-07-24 P1-2 — naive dt would
                            # TypeError on the cutoff compare and fall through,
                            # including out-of-window analytics rows).
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=UTC)
                            if dt < cutoff:
                                continue
                        except (ValueError, TypeError):
                            pass
                    total += 1
                    d = record.get("duration_ms")
                    if isinstance(d, (int, float)):
                        durations.append(float(d))
        if total == 0:
            return None
        return SkillMetrics(
            skill_id=skill_id,
            total_executions=total,
            success_count=total,  # analytics doesn't track per-execution success
            avg_duration_ms=round(sum(durations) / len(durations)) if durations else 0.0,
            source="analytics",
            window_hours=window_hours,
        )
