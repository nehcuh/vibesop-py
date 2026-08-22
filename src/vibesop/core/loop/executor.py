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
import os
import shlex
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
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

# Subprocess (command_args) failure classification. Inverted default relative to
# routing: unknown command failures default to TRANSIENT — environment issues
# (uv not on PATH, locked .venv, transient file locks) are far more common than
# permanent ones, and we don't want a single broken tick to burn the DEAD budget.
# Only clear-cut permanent markers (wrong subcommand, permission denied) skip retry.
# Note: "no such file or directory" is INTENTIONALLY omitted — file races (e.g.
# locked .venv, target file mid-write by an interactive session) surface as this
# exact stderr and should be retryable, not burn the DEAD budget. Prefix-binary
# missing (uv not installed) is handled separately via the OSError branch which
# IS PERMANENT (PATH won't change mid-tick).
_COMMAND_PERMANENT_KEYWORDS: tuple[str, ...] = (
    "no such command",
    "no such option",
    "permission denied",
    "errno 13",
    "usage: ",
    "invalid value",
    "missing argument",
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


def _classify_command_failure(stderr_tail: str, return_code: int | None) -> FailureInfo:
    """Classify a subprocess (command_args) failure.

    Inverted default vs routing: unknown command failures default to TRANSIENT.
    Reason: command-target failures are usually environmental (uv not on PATH,
    locked .venv, file races with interactive sessions) and worth a retry. Only
    explicit usage/permission/file-not-found errors are PERMANENT.
    """
    lowered = stderr_tail.lower()
    if any(k in lowered for k in _COMMAND_PERMANENT_KEYWORDS):
        return FailureInfo(
            category=FailureCategory.PERMANENT,
            reason=f"command exited {return_code}: {stderr_tail}",
            suggestion="Not retryable — check command spelling, file path, and permissions.",
        )
    return FailureInfo(
        category=FailureCategory.TRANSIENT,
        reason=f"command exited {return_code}: {stderr_tail}",
        suggestion="Retryable — likely environmental; executor backs off if spec.max_retries > 0.",
    )


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

    # Injection is opt-in: it mutates the query text fed to the matchers, which
    # can alter routing outcomes (esp. for CJK queries polluted by the English
    # template below). Default off preserves existing matching behaviour.
    if not spec.inject_history or not history or not history.recent_runs:
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


def _missing_exec_root_failure(spec: LoopSpec, exec_root: Path) -> FailureInfo:
    """PERMANENT failure for a spec whose pinned ``project_root`` no longer exists.

    Deliberately PERMANENT (consumes DEAD budget): a missing ownership root is a
    loud, observable signal that the loop needs re-pinning — silently running in
    the ambient cwd would execute the loop against the WRONG project. The
    suggestion is fixed by design (gate26): adopt re-pins the root, reset clears
    the failure budget burned by the loud signal.
    """
    return FailureInfo(
        category=FailureCategory.PERMANENT,
        reason=(
            f"loop {spec.name!r} is pinned to project_root {exec_root} "
            f"which does not exist (deleted/moved project?)"
        ),
        suggestion=(
            f"Re-pin ownership with `vibe loop adopt {spec.name}` (from the new "
            f"project root), then clear the failure budget with "
            f"`vibe loop reset {spec.name}`."
        ),
    )


def _run_command_target(
    spec: LoopSpec,
    record: LoopRunRecord,
    project_root: str | None = None,
) -> None:
    """Execute ``spec.command_args`` as a subprocess and mutate ``record`` in place.

    Called from inside ``execute_loop_tick``'s retry loop, sharing the same
    persistence path (caller still runs ``state.record_run(record)`` +
    ``store.save_state(state)``). Raises no exceptions — failures are written
    into ``record`` so the existing DEAD/FAILING state machine applies.

    Args:
        spec: Loop definition with ``command_args`` set.
        record: Pre-constructed ``LoopRunRecord`` (loop_name + started_at) to fill.
        project_root: Working directory (subprocess ``cwd``). ``None`` inherits
            the ambient cwd (unscoped legacy/--global loops). Production callers
            pass the spec's resolved pinned ``project_root``; tests may point at
            a tmp_path.
    """
    # shlex.split handles quoted paths with spaces (e.g.
    # VIBESOP_RUN_PREFIX='"/path/with space/uv" run vibe'). Plain .split()
    # would break that into 4 args and FileNotFoundError on the binary.
    prefix_env = os.environ.get("VIBESOP_RUN_PREFIX", "uv run vibe")
    try:
        prefix = shlex.split(prefix_env, posix=True)
    except ValueError as e:
        # Mismatched quotes — fall back to whitespace split rather than crash.
        logger.warning("VIBESOP_RUN_PREFIX has unbalanced quotes (%r): %s", prefix_env, e)
        prefix = prefix_env.split()
    argv = [*prefix, *spec.command_args]
    env = {**os.environ, **spec.env_overrides}

    try:
        result = subprocess.run(
            argv,
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=spec.timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        record.success = False
        # Use shlex.join so multi-line argv / unicode args survive in logs
        # readable and round-trippable (deep-diagnosis-2026-07-24 P1-9 —
        # plain ' '.join corrupts on whitespace/newlines inside an arg).
        record.error = f"command timeout after {spec.timeout_s}s: {shlex.join(spec.command_args)}"
        record.failure_info = FailureInfo(
            category=FailureCategory.TRANSIENT,
            reason=record.error,
            suggestion="Retryable — command took too long; consider raising spec.timeout_s.",
        )
        return
    except OSError as e:
        # Two distinct spawn-failure shapes used to share one misleading message:
        #   1. missing cwd — project_root was deleted between the executor's
        #      pre-flight check and this spawn (or pre-flight was bypassed);
        #      the fix is re-pinning ownership, not checking uv.
        #   2. missing prefix binary — uv not on PATH (the original meaning).
        # Known mis-classification (gate27 pi#2/claude#3): EACCES (permission
        # denied on the cwd or the binary) also lands here and may get the
        # "wrong" suggestion text depending on which branch fires. Accepted:
        # both branches are PERMANENT, so the failure budget is unaffected —
        # only the suggestion wording can mislead, never the state machine.
        record.success = False
        record.error = f"command spawn failed: {e}"
        if project_root is not None and not Path(project_root).is_dir():
            record.failure_info = FailureInfo(
                category=FailureCategory.PERMANENT,
                reason=record.error,
                suggestion=(
                    f"working directory {project_root} is missing — re-pin with "
                    f"`vibe loop adopt {spec.name}`, then `vibe loop reset {spec.name}`."
                ),
            )
        else:
            record.failure_info = FailureInfo(
                category=FailureCategory.PERMANENT,
                reason=record.error,
                suggestion="Check VIBESOP_RUN_PREFIX / uv installation.",
            )
        return

    stdout_tail = (result.stdout or "")[-2000:]
    stderr_tail = (result.stderr or "")[-2000:]

    if result.returncode == 0:
        record.success = True
        record.matched_skill = ""  # command targets have no skill
        record.output_summary = (stdout_tail or stderr_tail)[:200]
        record.error = ""
        record.failure_info = None
        return

    record.success = False
    record.error = f"command exited {result.returncode}: {stderr_tail}"
    record.failure_info = _classify_command_failure(stderr_tail, result.returncode)


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
    # state.json embeds a spec copy that may be stale (e.g. adopt re-pinned
    # project_root after the last run). Re-bind the live spec so record_run's
    # status machine (max_failures) and the re-saved state both see current
    # values (gate26 review: stale-copy fix).
    state.spec = spec

    # Ownership execution root: a pinned spec executes against ITS project,
    # never the ambient cwd. None = unscoped (legacy/--global) — unchanged
    # behaviour (subprocess inherits cwd; routing runtime is caller-built).
    exec_root: Path | None = Path(spec.project_root).resolve() if spec.project_root else None

    if exec_root is not None and not exec_root.is_dir():
        # Pre-flight: refuse to run in the wrong cwd. PERMANENT by design —
        # burns DEAD budget as a loud re-pin signal (gate26 review pi#5).
        record.success = False
        record.failure_info = _missing_exec_root_failure(spec, exec_root)
        record.error = record.failure_info.reason
        record.duration_s = round(time.monotonic() - start_wall, 2)
        record.finished_at = datetime.now(UTC)
        state.record_run(record)
        try:
            store.save_state(state)
        except Exception:
            logger.exception(
                "Failed to persist loop state for [%s] — failure counter may not advance",
                spec.name,
            )
        return record

    history = RunHistory(
        recent_runs=list(state.recent_runs),
        progress_notes=list(state.progress_notes),
    )

    attempt = 0
    attempt_errors: list[str] = []  # accumulated across retries for debugging
    failure: FailureInfo | None = None  # initialised defensively (kimi latent-risk)
    while True:
        err = ""
        try:
            if spec.command_args:
                # Command-target path: no routing query, no AgentRuntime —
                # direct subprocess invocation. Reuses the same record/state
                # machine as routing so DEAD/FAILING transitions still fire.
                # exec_root (the spec's pinned project_root, resolved) is the
                # subprocess cwd — pre-fix this call never passed project_root,
                # so pinned loops silently ran in the ambient cwd (gate26).
                _run_command_target(
                    spec, record, project_root=str(exec_root) if exec_root else None
                )
                if record.success:
                    break
                err = record.error or "command failed"
                failure = record.failure_info or _classify_command_failure(err, return_code=None)
            else:
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
                failure = _classify_failure(err)
        except Exception as e:
            # AgentRuntime.handle_query already swallows its own exceptions
            # into result.errors. This outer guard is for _build_query
            # (defensive — LoopSpec validation should prevent) and for
            # catastrophic runtime failures (e.g. import errors).
            err = f"executor exception: {e}"
            logger.exception("Loop tick raised unexpectedly [%s]", spec.name)
            failure = _classify_failure(err)

        assert failure is not None  # defensive: every path above assigns it

        # Retry only TRANSIENT failures, up to spec.max_retries (default 0 = off).
        # The retry stays inside the persistence boundary so a transient blip
        # does NOT advance the DEAD failure counter — only the final outcome
        # of the tick is recorded once.
        if failure.category == FailureCategory.TRANSIENT and attempt < spec.max_retries:
            attempt += 1
            attempt_errors.append(f"attempt {attempt}: {err}")
            delay = min(2 ** (attempt - 1) * spec.retry_delay_base, 300)
            time.sleep(delay)
            continue

        # Final failure — commit to record. If retries happened, prepend
        # earlier attempts' errors so post-mortem debugging isn't blind to
        # the first failure (adversarial review §2).
        record.success = False
        if attempt_errors:
            record.error = " | ".join([*attempt_errors, f"final: {err}"])
        else:
            record.error = err
        record.failure_info = failure
        break

    record.duration_s = round(time.monotonic() - start_wall, 2)
    record.finished_at = datetime.now(UTC)

    # Persist state — even on failure, so the failure counter advances.
    # Resilient: a save failure (disk full / IO) must not crash the tick or
    # mask the outcome — log loudly and still return the record. (kimi HIGH:
    # save_state was outside any try/except, so a failed save lost the
    # failure-counter advance AND propagated.)
    state.record_run(record)
    try:
        store.save_state(state)
    except Exception:
        logger.exception(
            "Failed to persist loop state for [%s] — failure counter may not advance",
            spec.name,
        )

    return record


__all__ = ["execute_loop_tick"]
