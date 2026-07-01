"""Loop executor — runs a single loop tick: dispatch, record, persist.

Single tick flow:
    1. Build routing query from spec (skill_id / query / workflow_id).
    2. Call ``AgentRuntime.handle_query`` — non-interactive, exception-safe.
    3. Build ``LoopRunRecord`` with success/error/summary.
    4. ``LoopState.record_run(record)`` — updates failure counter + status.
    5. ``LoopStore.save_state(state)`` — atomic persistence.
    6. Return record.

Design decisions (Phase 0 + Phase 1-1/1-2/1-3 landed):
    - ``skill_id`` → ``/slash-route use {skill_id}`` query.
    - ``query``    → passed through verbatim.
    - ``workflow_id`` → ``run workflow {workflow_id}`` query.
    - ``AgentRuntime.handle_query`` is non-interactive ✅.
    - Persistence via ``LoopStore`` atomic writes ✅.

Known v1 limitations (documented for future phases):
    - **/slash-route semantics**: the prefix is *not* a true EXPLICIT-layer
      invocation. ``_ROUTE_LIKE_RE`` (agent_runtime.py) strips the prefix
      and routes the remainder through the normal 10-layer pipeline. So
      ``/slash-route use foo`` is equivalent to routing the string
      ``"use foo"``. The ``foo`` skill matches when keyword/scenario
      layers pick up the skill_id as a token. v8.1 should add a real
      explicit-invocation path (e.g. ``--skill-id`` flag on
      ``handle_query``).
    - **No status filter**: executor runs whatever spec it's given. The
      caller (``CronDaemon``, CLI) is responsible for skipping
      ``PAUSED`` / ``DEAD`` loops. Phase 1-5 will add daemon-level
      filtering.

Concurrency:
    v1 callers must serialise ticks per loop (CronDaemon.run_once is a
    synchronous function; CLI invokes it once per cron tick). Concurrent
    ticks on the same loop would TOCTOU on ``load_state``.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any, Protocol

from vibesop.core.loop.models import (
    FailureCategory,
    FailureInfo,
    LoopRunRecord,
    LoopSpec,
    LoopState,
    RunHistory,
)
from vibesop.core.loop.store import LoopStore

logger = logging.getLogger(__name__)

# Keyword heuristics for failure classification. Conservative: unknown failures
# default to PERMANENT (no retry) rather than the plan's optimistic TRANSIENT —
# retrying an unrecognised failure wastes ticks and risks DEAD-by-retry.
_TRANSIENT_KEYWORDS: tuple[str, ...] = (
    "timeout",
    "timed out",
    "rate limit",
    "429",
    "503",
    "connection",
    "temporarily",
    "unavailable",
    "reset by peer",
    "temporary",
)
_PERMANENT_KEYWORDS: tuple[str, ...] = (
    "not found",
    "no skill",
    "no matching",
    "config",
    "auth",
    "api key",
    "import",
    "module",
    "syntax",
)


class LoopRunner(Protocol):
    """Structural type for a runtime that executes a routed query.

    ``AgentRuntime`` (agent layer) satisfies this. core/loop depends on the
    Protocol, not the concrete class, so core no longer imports the agent
    layer — fixing the Core->Agent layer inversion. The concrete runtime is
    injected by the CLI caller (which is allowed to import agent).
    """

    def handle_query(self, query: str, *, platform: str = ..., explain: bool = ...) -> Any: ...


def _classify_failure(error: str) -> FailureInfo:
    """Classify an execution/routing failure into a structured FailureInfo.

    Conservative default: unknown failures are PERMANENT (no retry).
    """
    lowered = error.lower()
    if any(k in lowered for k in _TRANSIENT_KEYWORDS):
        return FailureInfo(
            category=FailureCategory.TRANSIENT,
            reason=error,
            suggestion="Retryable — executor backs off and retries if spec.max_retries > 0.",
        )
    if any(k in lowered for k in _PERMANENT_KEYWORDS):
        return FailureInfo(
            category=FailureCategory.PERMANENT,
            reason=error,
            suggestion="Not retryable — check skill/config with 'vibe doctor'.",
        )
    return FailureInfo(category=FailureCategory.PERMANENT, reason=error)


def _build_query(spec: LoopSpec, history: RunHistory | None = None) -> str:
    """Construct the routing query for a loop tick.

    The query shape depends on which target field is set on the spec:
        - ``skill_id``    → ``/slash-route use {skill_id}``
        - ``query``       → passed through verbatim
        - ``workflow_id`` → ``run workflow {workflow_id}``

    When ``history`` is provided (with recent runs), cross-run context
    (recent success rate, failure categories, progress notes) is appended so
    each tick's routing query is aware of prior outcomes.

    LoopSpec validation guarantees exactly one target is set, so the final
    ``else`` is a defensive guard against bypassed validation.
    """
    if spec.skill_id:
        base = f"/slash-route use {spec.skill_id}"
    elif spec.query:
        base = spec.query
    elif spec.workflow_id:
        base = f"run workflow {spec.workflow_id}"
    else:
        raise ValueError(
            f"Loop {spec.name!r} has no skill_id / query / workflow_id set "
            f"(LoopSpec validation should have prevented this)"
        )

    if not history or not history.recent_runs:
        return base

    recent = history.recent_runs[-10:]
    successes = sum(1 for r in recent if r.success)
    total = len(recent)
    rate = successes / total if total else 0.0
    parts = [
        base,
        "",
        "## Cross-run context",
        f"- Recent success rate: {rate:.0%} ({successes}/{total})",
    ]

    failed = [r for r in recent if not r.success and r.failure_info]
    if failed:
        cats: dict[str, int] = {}
        for r in failed:
            cat = r.failure_info.category.value if r.failure_info else "unknown"
            cats[cat] = cats.get(cat, 0) + 1
        parts.append(f"- Recent failure categories: {cats}")

    if history.progress_notes:
        parts.append("- Notes: " + "; ".join(history.progress_notes[-3:]))

    return "\n".join(parts)


def execute_loop_tick(
    spec: LoopSpec,
    runtime: LoopRunner,
    store: LoopStore | None = None,
) -> LoopRunRecord:
    """Execute one loop tick and persist the result.

    Args:
        spec: Loop definition. Caller is responsible for skipping
            ``PAUSED`` / ``DEAD`` loops — this function will execute
            whatever it's given.
        runtime: A ``LoopRunner`` (e.g. ``AgentRuntime``) that executes the
            routed query. Injected by the caller (CLI) so core/loop does not
            import the agent layer (Core->Agent inversion fix).
        store: LoopStore instance. ``None`` creates a default instance
            rooted at ``~/.vibe/loops/``.

    Returns:
        ``LoopRunRecord`` describing this tick. The record has already
        been appended to the loop's persisted ``LoopState``.
    """
    store = store or LoopStore()

    started_at = datetime.now(UTC)
    start_wall = time.monotonic()
    record = LoopRunRecord(loop_name=spec.name, started_at=started_at)

    # Load state up-front so cross-run history can be injected into the query.
    state = store.load_state(spec.name) or LoopState(spec=spec)
    history = RunHistory(
        recent_runs=list(state.recent_runs),
        progress_notes=list(state.progress_notes),
    )

    attempt = 0
    while True:
        err = ""
        try:
            query = _build_query(spec, history=history)
            # explain=True populates result.decision_message so output_summary
            # captures routing context for post-mortem debugging.
            result = runtime.handle_query(query, platform="generic", explain=True)

            if result.success and result.has_match:
                record.success = True
                record.matched_skill = result.skill_id or spec.skill_id
                record.output_summary = (result.decision_message or "")[:200]
                record.error = ""
                record.failure_info = None
                break

            if result.errors:
                err = "; ".join(result.errors)
            elif not result.has_match:
                err = "no matching skill found"
            else:
                err = "routing completed without success"
        except Exception as e:
            # AgentRuntime.handle_query already swallows its own exceptions
            # into result.errors. This outer guard is for _build_query
            # (defensive — LoopSpec validation should prevent) and for
            # catastrophic runtime failures (e.g. import errors).
            err = f"executor exception: {e}"
            logger.exception("Loop tick raised unexpectedly [%s]", spec.name)

        failure = _classify_failure(err)
        # Retry only TRANSIENT failures, up to spec.max_retries (default 0 = off).
        # The retry stays inside the persistence boundary so a transient blip
        # does NOT advance the DEAD failure counter — only the final outcome
        # of the tick is recorded once.
        if failure.category == FailureCategory.TRANSIENT and attempt < spec.max_retries:
            attempt += 1
            delay = min(2 ** (attempt - 1) * spec.retry_delay_base, 300)
            time.sleep(delay)
            continue

        # Final failure — commit to record.
        record.success = False
        record.error = err
        record.failure_info = failure
        break

    record.duration_s = round(time.monotonic() - start_wall, 2)
    record.finished_at = datetime.now(UTC)

    # Persist state — even on failure, so the failure counter advances.
    state.record_run(record)
    store.save_state(state)

    return record


__all__ = ["execute_loop_tick"]
