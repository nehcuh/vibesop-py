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

from vibesop.agent.runtime.agent_runtime import AgentRuntime
from vibesop.core.loop.models import LoopRunRecord, LoopSpec, LoopState
from vibesop.core.loop.store import LoopStore

logger = logging.getLogger(__name__)


def _build_query(spec: LoopSpec) -> str:
    """Construct the routing query for a loop tick.

    The query shape depends on which target field is set on the spec:
        - ``skill_id``    → ``/slash-route use {skill_id}``
        - ``query``       → passed through verbatim
        - ``workflow_id`` → ``run workflow {workflow_id}``

    LoopSpec validation guarantees exactly one of these is set, so the
    final ``else`` is a defensive guard against bypassed validation.
    """
    if spec.skill_id:
        return f"/slash-route use {spec.skill_id}"
    if spec.query:
        return spec.query
    if spec.workflow_id:
        return f"run workflow {spec.workflow_id}"
    raise ValueError(
        f"Loop {spec.name!r} has no skill_id / query / workflow_id set "
        f"(LoopSpec validation should have prevented this)"
    )


def execute_loop_tick(
    spec: LoopSpec,
    runtime: AgentRuntime | None = None,
    store: LoopStore | None = None,
) -> LoopRunRecord:
    """Execute one loop tick and persist the result.

    Args:
        spec: Loop definition. Caller is responsible for skipping
            ``PAUSED`` / ``DEAD`` loops — this function will execute
            whatever it's given.
        runtime: AgentRuntime instance. ``None`` creates a default
            instance with project_root=cwd (will attempt to read
            ``~/.vibe/config.toml`` for LLM credentials).
        store: LoopStore instance. ``None`` creates a default instance
            rooted at ``~/.vibe/loops/``.

    Returns:
        ``LoopRunRecord`` describing this tick. The record has already
        been appended to the loop's persisted ``LoopState``.
    """
    runtime = runtime or AgentRuntime()
    store = store or LoopStore()

    started_at = datetime.now(UTC)
    start_wall = time.monotonic()

    record = LoopRunRecord(loop_name=spec.name, started_at=started_at)

    try:
        query = _build_query(spec)
        # explain=True populates result.decision_message so output_summary
        # captures routing context for post-mortem debugging.
        result = runtime.handle_query(query, platform="generic", explain=True)

        if result.success and result.has_match:
            record.success = True
            record.matched_skill = result.skill_id or spec.skill_id
            record.output_summary = (result.decision_message or "")[:200]
        else:
            record.success = False
            if result.errors:
                record.error = "; ".join(result.errors)
            elif not result.has_match:
                record.error = "no matching skill found"
            else:
                record.error = "routing completed without success"

    except Exception as e:
        # AgentRuntime.handle_query already swallows its own exceptions
        # into result.errors. This outer guard is for _build_query
        # (defensive — LoopSpec validation should prevent) and for
        # catastrophic runtime failures (e.g. import errors).
        record.success = False
        record.error = f"executor exception: {e}"
        logger.exception("Loop tick raised unexpectedly [%s]", spec.name)

    record.duration_s = round(time.monotonic() - start_wall, 2)
    record.finished_at = datetime.now(UTC)

    # Persist state — even on failure, so the failure counter advances.
    state = store.load_state(spec.name) or LoopState(spec=spec)
    state.record_run(record)
    store.save_state(state)

    return record


__all__ = ["execute_loop_tick"]
