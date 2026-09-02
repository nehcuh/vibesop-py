"""AgentRuntime — unified entry point for the VibeSOP agent runtime.

Wires together all runtime components (interception, routing, injection,
presentation, execution) that were previously isolated or used only
piecemeal by the CLI. Platform adapters can call ``AgentRuntime.handle_query()``
instead of shelling out to ``vibe route`` via a subprocess.

Refactored in v5.5.0 as part of Phase 3 — see the plan for details.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vibesop.agent.runtime.intent_interceptor import InterceptionMode
from vibesop.core.observability import ObservabilityTracer, get_tracer

logger = logging.getLogger(__name__)


def _source_file_from_route(primary: Any) -> str | None:
    """Pull the discovered SKILL.md path off a SkillRoute-like object."""
    meta = getattr(primary, "metadata", None) or {}
    if isinstance(meta, dict):
        sf = meta.get("source_file")
        if sf:
            return str(sf)
    sf = getattr(primary, "source_file", None)
    return str(sf) if sf else None


# Module-level observability tracer (lazy-initialised).
_obs_tracer: ObservabilityTracer | None = None


def _get_obs_tracer() -> ObservabilityTracer:
    """Return the module-level observability tracer.

    Creates it lazily so the observability module is only imported
    when tracing is actually needed (avoids import overhead on cold starts).
    """
    global _obs_tracer  # noqa: PLW0603
    if _obs_tracer is None:
        _obs_tracer = get_tracer(enabled=True)
    return _obs_tracer


@dataclass
class AgentRuntimeResult:
    """Structured result from AgentRuntime.handle_query().

    Attributes:
        intercepted: Whether the query was intercepted for routing.
        mode: Interception mode (none, single, orchestrate, slash_command).
        skill_id: Matched skill ID (if single match).
        skill_name: Matched skill name (if available).
        confidence: Routing confidence score (0.0-1.0).
        alternatives: Alternative skill candidates.
        plan: Orchestration plan (if multi-intent).
        decision_message: Human-readable decision explanation.
        skill_content: Injected skill content (if any).
        slash_result: Slash command execution result (if applicable).
        errors: Any errors encountered during processing.
    """

    intercepted: bool = False
    mode: str = "none"
    skill_id: str = ""
    skill_name: str = ""
    confidence: float = 0.0
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    plan: dict[str, Any] | None = None
    decision_message: str = ""
    skill_content: str = ""
    slash_result: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    project_root: Path | None = None
    # The ROUTER's real match verdict, distinct from the mode-derived
    # ``has_match`` property below (which is ``intercepted and mode in
    # (...)`` and stays True on a real miss once the interceptor chose a
    # routing mode — the M12 hook-path miss blind spot). Span metadata
    # ``has_match`` is written from THIS field so
    # ``gold_detection.is_route_miss_span`` can see hook-path misses.
    # Existing consumers of the property (instinct bridge, hook JSON)
    # are untouched.
    router_matched: bool = False
    # True when skill_content is a VibeSOP empty/unsafe notice, not a
    # skill body. Hook JSON must not wrap it as [ACTIVE SKILL] / MUST follow.
    notice_only: bool = False
    # Absolute/posix SKILL.md path actually loaded. Hook NEXT STEP uses this
    # instead of guessing core/skills/<id>/SKILL.md.
    skill_path: str = ""

    @property
    def has_match(self) -> bool:
        return self.intercepted and self.mode in (
            "single",
            "orchestrate",
            "multi_agent_squad",
        )

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def to_hook_json(self) -> str:
        """Serialize to JSON for consumption by shell hook wrappers.

        Returns a compact JSON string suitable for parsing by a thin
        shell wrapper (vibesop-route.sh). The shell hook reads this
        output and translates it into the platform-specific hook
        response format.
        """
        return json.dumps(
            {
                "intercepted": self.intercepted,
                "mode": self.mode,
                "skillId": self.skill_id,
                "skillName": self.skill_name,
                "confidence": self.confidence,
                "alternatives": self.alternatives,
                "plan": self.plan,
                "decisionMessage": self.decision_message,
                "skillContent": self.skill_content[:3000] if self.skill_content else "",
                "slashResult": self.slash_result,
                "errors": self.errors,
            },
            ensure_ascii=False,
        )

    def to_hook_response(
        self,
        platform: str = "generic",  # noqa: ARG002  # interface-conforming param
        hook_event_name: str = "",
        include_additional_context: bool = True,
        no_match_message: bool = True,
    ) -> str:
        """Serialize to a platform-specific hook response format.

        Produces the JSON structure expected by Claude Code, OpenCode,
        and Kimi CLI hook interfaces with systemMessage and optional
        hookSpecificOutput.additionalContext.

        Args:
            platform: Platform identifier (claude-code, opencode, kimi-cli).
            hook_event_name: Hook event name for hookSpecificOutput.
            include_additional_context: When True, attach skill content/plan
                as additionalContext in hookSpecificOutput.
            no_match_message: When True, produce a fallback message when
                no skill matches.

        Returns:
            JSON string in the platform hook response format.
        """
        # Not intercepted — empty response
        if not self.intercepted:
            return "{}"

        # Slash command result
        if self.mode == "slash_command" and self.slash_result:
            msg = self.slash_result.get("message", "")
            return json.dumps(
                {"systemMessage": f"📎 VibeSOP: {msg}"},
                ensure_ascii=False,
            )

        # Orchestration mode
        if self.mode == "orchestrate" and self.plan:
            plan_text = json.dumps(self.plan, indent=2, ensure_ascii=False)
            response: dict[str, Any] = {
                "systemMessage": ("🔀 VibeSOP detected multiple intents. Execution plan injected."),
            }
            if include_additional_context:
                ctx = f"[VibeSOP Execution Plan]\n{plan_text}"
                ho: dict[str, Any] = {"additionalContext": ctx}
                if hook_event_name:
                    ho["hookEventName"] = hook_event_name
                response["hookSpecificOutput"] = ho
            return json.dumps(response, ensure_ascii=False)

        # Notice-only (unsafe refusal, or a leftover empty notice): tell the
        # host the body was not injected. Do NOT wrap [ACTIVE SKILL] / MUST
        # follow, and do NOT emit NEXT STEP pointing at the refused file.
        if self.notice_only:
            notice = (self.skill_content or f"[VibeSOP] Skill '{self.skill_id}' was not injected.")[
                :3000
            ]
            notice_resp: dict[str, Any] = {"systemMessage": notice}
            if include_additional_context:
                notice_ho: dict[str, Any] = {"additionalContext": notice}
                if hook_event_name:
                    notice_ho["hookEventName"] = hook_event_name
                notice_resp["hookSpecificOutput"] = notice_ho
            return json.dumps(notice_resp, ensure_ascii=False)

        # No match — fallback
        if not self.skill_id or self.skill_id == "fallback-llm":
            if no_match_message:
                return json.dumps(
                    {
                        "systemMessage": (
                            "🤖 VibeSOP: No matching skill found. Proceeding in normal mode."
                        )
                    },
                    ensure_ascii=False,
                )
            return "{}"

        # Single skill match — build full response
        skill_flat = self.skill_id.replace("/", "-")
        conf_pct = int(self.confidence * 100)

        # Hint path must match real on-disk layout. Prefer the path inject
        # actually loaded (discovered source_file). Fall back to the guess
        # ladder for results constructed without going through inject.
        user_root = self.project_root or Path.cwd()
        if self.skill_path:
            hint_path = self.skill_path.replace("\\", "/")
        elif "/" in self.skill_id:
            namespace, bare_name = self.skill_id.split("/", 1)
            if namespace == "builtin":
                from vibesop.utils.bundled import resolve_builtin_skills_dir

                hint_file = resolve_builtin_skills_dir(user_root) / bare_name / "SKILL.md"
                hint_path = (
                    hint_file.as_posix()
                    if hint_file.exists()
                    else f"core/skills/{bare_name}/SKILL.md"
                )
            else:
                hint_path = f"skills/{skill_flat}/SKILL.md"
                # W4/W5 promote materializes custom skills under
                # <project>/.vibe/skills/ or ~/.vibe/skills/ (nested by
                # skill_id) — never the platform skills dir. Point the agent
                # at the real file so the "read SKILL.md" step succeeds.
                for p in (
                    user_root / ".vibe" / "skills" / self.skill_id / "SKILL.md",
                    Path.home() / ".vibe" / "skills" / self.skill_id / "SKILL.md",
                ):
                    if p.exists():
                        hint_path = p.resolve().as_posix()
                        break
        else:
            hint_path = f"skills/{self.skill_id}/SKILL.md"
            vibe_skills = user_root / ".vibe" / "skills"
            if vibe_skills.is_dir():
                dotted = list(vibe_skills.glob(f"**/{self.skill_id}.skill/SKILL.md"))
                if dotted:
                    hint_path = dotted[0].resolve().as_posix()
                else:
                    direct = vibe_skills / self.skill_id / "SKILL.md"
                    if direct.exists():
                        hint_path = direct.resolve().as_posix()

        # Build alternatives message
        alt_msg = ""
        if self.alternatives:
            alt_lines = [
                f"  {i + 1}. {a['skill_id']} ({int(a.get('confidence', 0) * 100)}%)"
                for i, a in enumerate(self.alternatives[:5])
            ]
            alt_msg = (
                "\nALTERNATIVE SKILLS "
                f"(if '{self.skill_id}' doesn't fit, load one of these):\n"
                + "\n".join(alt_lines)
                + "\n"
            )

        system_message = (
            f"🎯 VibeSOP routed: {self.skill_id} ({conf_pct}% confidence)"
            f"{alt_msg}"
            f"\n\nNEXT STEP (MANDATORY): read {hint_path}\n"
            "Do NOT proceed without reading this file.\n"
            "If the skill doesn't match, load an alternative skill above."
        )

        resp: dict[str, Any] = {"systemMessage": system_message}

        if include_additional_context and self.skill_content:
            # The claude-code/grok-build injectors already open with the
            # [ACTIVE SKILL] banner — wrapping again duplicated it (gate46
            # dual-review P1: double banner ate the preview's line budget).
            # VibeSOP notices must never be wrapped as an active skill.
            stripped_content = self.skill_content.lstrip()
            if stripped_content.startswith("[VibeSOP") or "[ACTIVE SKILL:" in self.skill_content:
                additional_context = self.skill_content[:3000]
            else:
                additional_context = (
                    f"[ACTIVE SKILL: {self.skill_id}]\n"
                    "You MUST follow this skill's workflow. Do not skip steps.\n\n"
                    f"{self.skill_content[:3000]}"
                )
            hook_output: dict[str, Any] = {
                "additionalContext": additional_context,
            }
            if hook_event_name:
                hook_output["hookEventName"] = hook_event_name
            resp["hookSpecificOutput"] = hook_output

        return json.dumps(resp, ensure_ascii=False)


class AgentRuntime:
    """Wired runtime connecting all VibeSOP agent components.

    Platform adapters use this as their primary integration point instead
    of shelling out to ``vibe route``. The runtime handles the full
    pipeline: interception → routing → presentation → injection.

    Example:
        >>> runtime = AgentRuntime()
        >>> result = runtime.handle_query("review my code", platform="claude-code")
        >>> if result.has_match:
        ...     print(runtime.injector.inject_single_skill(result.skill_id, "claude-code"))
    """

    # Patterns for route-like slash commands that strip prefix and route
    _ROUTE_LIKE_RE = re.compile(
        r'^/(?:vibe-route|slash-route|vibe-orchestrate|orchestrate)\s+["\']?(.+?)["\']?\s*$',
        re.DOTALL,
    )

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()

        # Lazy-initialized components (created on first use)
        self._interceptor: Any = None
        self._router: Any = None
        self._injector: Any = None
        self._presenter: Any = None
        self._slash_executor: Any = None
        self._plan_executor: Any = None
        self._context_injector: Any = None

    def _lookup_routed_source_file(self, skill_id: str) -> str | None:
        """The SKILL.md the candidate pool indexed for this id, if any."""
        inner = getattr(self.router, "_router", self.router)
        cm = getattr(inner, "_candidate_manager", None)
        lookup = getattr(cm, "source_file_for", None)
        if not callable(lookup):
            return None
        try:
            found = lookup(skill_id)
        except Exception:
            logger.debug("candidate source_file lookup failed for %s", skill_id, exc_info=True)
            return None
        return found if isinstance(found, str) and found else None

    # ---- Lazy component accessors ----

    @property
    def interceptor(self):
        if self._interceptor is None:
            from vibesop.agent.runtime.intent_interceptor import IntentInterceptor

            self._interceptor = IntentInterceptor()
        return self._interceptor

    @property
    def router(self):
        if self._router is None:
            from vibesop.agent import AgentRouter

            self._router = AgentRouter(project_root=self.project_root)
            # v7.3.4 fix (Round 3 P0, part 2): auto-inject LLM factory so
            # AI triage works for hook callers (which don't go through the
            # CLI's explicit runtime.router.set_llm_factory() call).
            # Without this, _single_skill_route sees _llm=None and falls
            # back to keyword-only routing → "No matching skill found"
            # even when CLI 'vibe route' on the same query succeeds.
            try:
                factory = self._build_llm_factory()
                if factory is not None:
                    self._router.set_llm_factory(factory)
            except Exception as e:
                logger.debug(f"LLM factory auto-inject failed (degraded mode): {e}")
        return self._router

    @staticmethod
    def _build_llm_factory() -> Any:
        """Build an LLM factory that honors ~/.vibe/config.toml.

        Mirrors cli/main.py:_build_llm_factory() — uses LLMConfigResolver
        so hook callers get the same provider/model as `vibe route` CLI.
        Returns None if no provider can be resolved (degraded mode).
        """
        try:
            from vibesop.core.llm_config import LLMConfigResolver
            from vibesop.llm.factory import create_provider

            resolver = LLMConfigResolver()
            cfg = resolver.get_llm_for_understanding()
            if not cfg or not cfg.provider:
                return None
            if not cfg.api_key:
                # Same warning as cli/main.py:_build_llm_factory() — an
                # empty api_key means the configured provider/api_base fall
                # back to environment variable detection.
                logger.warning(
                    "Config [llm] found but api_key is empty; configured "
                    "provider/api_base (%s/%s) are ignored, falling back to "
                    "environment variable detection. Set api_key in the config "
                    "or export the provider's API key env var.",
                    cfg.provider,
                    cfg.api_base,
                )

            def _factory():
                return create_provider(
                    provider=cfg.provider,
                    api_key=cfg.api_key,
                    base_url=cfg.api_base,
                )

            return _factory
        except Exception:
            return None

    @property
    def injector(self):
        if self._injector is None:
            from vibesop.agent.runtime.skill_injector import SkillInjector

            self._injector = SkillInjector(project_root=self.project_root)
        return self._injector

    @property
    def presenter(self):
        if self._presenter is None:
            from vibesop.agent.runtime.decision_presenter import DecisionPresenter

            self._presenter = DecisionPresenter()
        return self._presenter

    @property
    def slash_executor(self):
        if self._slash_executor is None:
            from vibesop.agent.runtime.slash_command_executor import SlashCommandExecutor

            self._slash_executor = SlashCommandExecutor(project_root=self.project_root)
        return self._slash_executor

    @property
    def plan_executor(self):
        if self._plan_executor is None:
            from vibesop.agent.runtime.plan_executor import PlanExecutor

            self._plan_executor = PlanExecutor(project_root=self.project_root)
        return self._plan_executor

    @property
    def context_injector(self):
        if self._context_injector is None:
            from vibesop.agent.runtime.context_injector import StepContextInjector

            self._context_injector = StepContextInjector(project_root=self.project_root)
        return self._context_injector

    # ---- Main entry point ----

    def handle_query(
        self,
        query: str,
        *,
        platform: str = "generic",
        session_id: str | None = None,
        conversation_id: str = "",
        explain: bool = False,
        callbacks: Any | None = None,
    ) -> AgentRuntimeResult:
        """Handle a user query through the full routing pipeline.

        Args:
            query: The user's natural language query.
            platform: Platform identifier (claude-code, opencode, kimi-cli, pi).
            session_id: Session identifier for context-aware routing. When
                None (default), a UUID is minted for this process and seeded
                into ``process_identity`` so descendant spans via TraceContext
                inherit it. Explicit non-None values win and are also seeded.
            conversation_id: Conversation ID for multi-turn continuity.
                Auto-generated from project path if empty.
            explain: When True, include full decision transparency output.
            callbacks: Optional orchestration callbacks (e.g. LiveOrchestrationCallbacks).

        Returns:
            AgentRuntimeResult with routing decision, skill content, and metadata.
        """
        # W5.1 Task 1.2: seed process_identity so descendant spans inherit the
        # session_id via TraceContext. Mirrors CLI pattern at cli/main.py:734.
        # Idempotent: only mint + seed if no explicit session_id was passed AND
        # the process identity is still unset. Per-call re-seeding would race
        # with concurrent handle_query invocations and orphan async spans onto
        # whichever UUID was last written (architect review BLOCK).
        from vibesop.core.observability.process_identity import (
            get_process_session_id,
            set_process_session_id,
        )

        if session_id is None:
            existing = get_process_session_id()
            if existing is None:
                session_id = str(uuid.uuid4())
                set_process_session_id(session_id)
            else:
                session_id = existing
        else:
            set_process_session_id(session_id)

        result = AgentRuntimeResult(project_root=self.project_root)

        # --- Observability: start a trace span for this query ---
        tracer = _get_obs_tracer()
        trace_name = query[:80] if len(query) <= 80 else query[:77] + "..."
        # Pure-query task_id: same query → same task_id across the parent
        # process and any sub-agent CLIs it spawns (contextvars cannot cross
        # process boundaries; pure derivation can). None for empty queries.
        from vibesop.core.observability.task_id import derive_task_id

        _task_id = derive_task_id(query)
        try:
            with tracer.trace(
                f"route:{trace_name}",
                task_id=_task_id,
                session_id=session_id,
                agent_id=platform,
                metadata={"query": query[:200], "platform": platform},
            ) as _task_span:
                # Generate conversation ID if not provided
                if not conversation_id:
                    project_hash = hashlib.sha256(str(self.project_root).encode()).hexdigest()[:16]
                    conversation_id = project_hash

                # 1. Check for slash commands
                if self.slash_executor.is_slash_command(query):
                    try:
                        route_match = self._ROUTE_LIKE_RE.match(query.strip())
                        if route_match:
                            query = route_match.group(1).strip()
                        else:
                            slash_result = self.slash_executor.execute_query(query)
                            result.intercepted = True
                            result.mode = "slash_command"
                            result.slash_result = {
                                "success": slash_result.success,
                                "message": slash_result.message,
                                "command": slash_result.command,
                            }
                            _task_span.metadata["mode"] = "slash_command"
                            return result
                    except Exception as e:
                        logger.debug(f"Slash command execution failed: {e}")

                # 2. Check if interception is needed
                from vibesop.agent.runtime.intent_interceptor import InterceptionContext

                context = InterceptionContext(
                    session_id=session_id,
                    platform=platform,
                )
                try:
                    decision = self.interceptor.should_intercept(query, _context=context)
                except Exception as e:
                    result.errors.append(f"Interception failed: {e}")
                    _task_span.set_error(f"Interception failed: {e}")
                    return result

                if not decision.should_route:
                    _task_span.metadata["mode"] = "not_intercepted"
                    return result

                result.intercepted = True
                result.mode = (
                    decision.mode.value if hasattr(decision.mode, "value") else str(decision.mode)
                )

                # Discovered SKILL.md for the eventual inject (match ⇔ that file).
                _inject_source: str | None = None

                # 3. Route the query
                # gate18 pi NIT-4: routing layer for the task span (set in
                # the branches below; written to span metadata at step 6).
                _route_layer: str | None = None
                try:
                    if decision.mode in (
                        InterceptionMode.ORCHESTRATE,
                        InterceptionMode.MULTI_AGENT_SQUAD,
                    ):
                        squad_ctx: Any = None
                        if decision.analysis is not None:
                            from vibesop.core.matching import RoutingContext

                            mode_tag = (
                                "multi_agent_squad"
                                if decision.mode == InterceptionMode.MULTI_AGENT_SQUAD
                                else "orchestrate"
                            )
                            squad_ctx = RoutingContext()
                            squad_ctx.interception_mode = mode_tag
                            squad_ctx.intent_analysis = decision.analysis.to_dict()
                            squad_ctx.metadata["intent_analysis"] = squad_ctx.intent_analysis
                            squad_ctx.metadata["_interception_mode"] = mode_tag

                        orch_result = self.router.orchestrate(
                            query, callbacks=callbacks, context=squad_ctx
                        )
                        if orch_result.get("is_multi_intent"):
                            result.mode = "orchestrate"
                            plan = orch_result.get("plan", {})
                            result.plan = plan
                            steps = plan.get("steps", [])
                            # Multi-intent verdict (gate20 claude NIT-1):
                            # PlanBuilder steps CAN carry
                            # skill_id="fallback-llm" (plan_builder.py
                            # :321-339, squad branch :626), so non-empty
                            # steps is NOT sufficient — a plan counts as a
                            # match only when at least one step routed to a
                            # REAL skill. All-fallback/empty → miss, the
                            # same verdict the single-intent branch gives
                            # fallback-llm (skill_id None there).
                            result.router_matched = any(
                                s.get("skill_id") not in ("", "fallback-llm", None) for s in steps
                            )
                            if steps:
                                result.skill_id = steps[0].get("skill_id", "")
                                result.confidence = 0.8
                                result.skill_name = steps[0].get("intent", "")
                            for step in steps[1:5]:
                                result.alternatives.append(
                                    {"skill_id": step.get("skill_id", ""), "confidence": 0.7}
                                )
                        else:
                            single = orch_result.get("single_result", {})
                            result.skill_id = single.get("skill_id", "") or ""
                            result.confidence = single.get("confidence", 0.0)
                            result.mode = "single"
                            # single_result carries no explicit has_match
                            # key; agent/__init__.py builds skill_id as
                            # ``primary.skill_id if has_match else None``,
                            # so a truthy skill_id IS the router's verdict
                            # (most truthful signal available on this path).
                            # INVARIANT (gate20 pi NIT-3): this relies on
                            # agent/__init__.py:347-351 ALWAYS building
                            # single_result WITH the skill_id key (None on
                            # miss) — a missing key also yields False via
                            # .get, which would mislabel a real match as a
                            # miss. If that construction changes, re-review
                            # this line.
                            result.router_matched = bool(single.get("skill_id"))
                            # single_result["layer"] is the winning layer's
                            # value on match, None on miss (agent __init__).
                            _route_layer = single.get("layer") or None
                    else:
                        routing_result = self.router.route(query, enable_ai_triage=True)
                        # The router's real match verdict — persisted
                        # separately from the mode-derived has_match
                        # property (see AgentRuntimeResult.router_matched).
                        result.router_matched = bool(getattr(routing_result, "has_match", False))

                        # 4. Present the decision
                        try:
                            present = self.presenter.present_single_result(routing_result, platform)
                            result.decision_message = present.message if explain else ""
                        except Exception as e:
                            logger.debug(f"Decision presentation failed: {e}")

                        # 5. Extract match details
                        if hasattr(routing_result, "has_match") and routing_result.has_match:
                            primary = (
                                routing_result.primary
                                if hasattr(routing_result, "primary")
                                else None
                            )
                            if primary:
                                result.skill_id = getattr(primary, "skill_id", "")
                                result.skill_name = getattr(primary, "skill_name", "")
                                result.confidence = getattr(primary, "confidence", 0.0)
                                _inject_source = _source_file_from_route(primary)
                                # gate18 pi NIT-4: winning layer.
                                _win_layer = getattr(primary, "layer", None)
                                if _win_layer is not None:
                                    _route_layer = getattr(_win_layer, "value", str(_win_layer))

                            if hasattr(routing_result, "alternatives"):
                                for alt in routing_result.alternatives[:5]:
                                    result.alternatives.append(
                                        {
                                            "skill_id": getattr(alt, "skill_id", ""),
                                            "confidence": getattr(alt, "confidence", 0.0),
                                        }
                                    )

                            if hasattr(routing_result, "plan") and routing_result.plan:
                                try:
                                    from vibesop.agent.execution_protocol import ExecutionProtocol

                                    result.plan = ExecutionProtocol.plan_to_json(
                                        routing_result.plan
                                    )
                                except Exception as e:
                                    logger.debug(f"Plan serialization failed: {e}")
                        else:
                            # gate18 pi NIT-4: miss → attribute the deepest
                            # layer the cascade reached (layer_details[-1]);
                            # absent details → field omitted (consumer buckets
                            # missing as "unknown").
                            _details = getattr(routing_result, "layer_details", None) or []
                            if _details:
                                _last_layer = getattr(_details[-1], "layer", None)
                                if _last_layer is not None:
                                    _route_layer = getattr(_last_layer, "value", str(_last_layer))
                except Exception as e:
                    result.errors.append(f"Routing failed: {e}")
                    _task_span.set_error(f"Routing failed: {e}")
                    return result

                # 6. Inject skill content. A routed id with no SKILL.md body
                # is not a match — demote to no-match rather than hand the
                # host a "matched" id plus an empty-content notice.
                # Skip the sentinel (result contract keeps skill_id=
                # fallback-llm) and orchestrate mode (the plan is the
                # payload; steps[0] may be fallback while a later step is
                # real — demoting would clobber router_matched).
                if (
                    result.skill_id
                    and result.skill_id != "fallback-llm"
                    and result.mode != "orchestrate"
                ):
                    try:
                        source_file = _inject_source or self._lookup_routed_source_file(
                            result.skill_id
                        )
                        injection = self.injector.inject_single_skill(
                            result.skill_id, platform, source_file=source_file
                        )
                        if not injection.has_content:
                            logger.warning(
                                "Routed skill '%s' has no injectable content; "
                                "demoting to no-match.",
                                result.skill_id,
                            )
                            result.skill_id = ""
                            result.skill_name = ""
                            result.skill_content = ""
                            result.router_matched = False
                            result.notice_only = False
                        elif injection.refused_unsafe:
                            logger.warning(
                                "Routed skill '%s' failed the runtime security "
                                "scan; injecting notice without activation.",
                                result.skill_id,
                            )
                            result.skill_content = (
                                injection.payload
                                if isinstance(injection.payload, str)
                                else str(injection.payload)
                            )
                            result.router_matched = False
                            result.notice_only = True
                        elif isinstance(injection.payload, str):
                            result.skill_content = injection.payload
                            result.skill_path = injection.resolved_path
                        elif isinstance(injection.payload, dict):
                            result.skill_content = (
                                injection.payload.get("additionalContext")
                                or injection.payload.get("content")
                                or ""
                            )
                            result.skill_path = injection.resolved_path
                    except Exception as e:
                        logger.warning(
                            "Skill injection failed for '%s': %s; demoting to no-match.",
                            result.skill_id,
                            e,
                        )
                        result.errors.append(f"Skill injection failed: {e}")
                        result.skill_id = ""
                        result.skill_name = ""
                        result.skill_content = ""
                        result.router_matched = False
                        result.notice_only = False

                # Enrich the task span with routing metadata.
                # gate40 项4: the SPAN's skill_id / top_skills are built
                # from the first REAL-skill step — the ``fallback-llm``
                # sentinel (plan_builder all-fallback / steps[0]-fallback
                # plans) is filtered out, so all-fallback orchestrated
                # runs write skill_id="" and omit top_skills instead of
                # leaking the sentinel. The RESULT object (skill_id /
                # skill_name / alternatives — consumed by the :653
                # injection gate and the :780 instinct bridge) is
                # deliberately UNTOUCHED (result contract).
                _full_steps = (
                    result.plan.get("steps", []) if isinstance(result.plan, dict) else None
                )
                if _full_steps is not None:
                    # gate40 follow-up: scan ALL plan steps, not just the
                    # steps[0] + steps[1:5] window that result.skill_id /
                    # result.alternatives cover — a >5-step plan whose first
                    # five steps are all fallback would otherwise leak the
                    # same has_match=true ∧ skill_id="" hole.
                    _span_candidates = [
                        step.get("skill_id", "") for step in _full_steps if isinstance(step, dict)
                    ]
                else:
                    _span_candidates = [
                        result.skill_id,
                        *(
                            alt.get("skill_id", "")
                            for alt in result.alternatives
                            if isinstance(  # pyright: ignore[reportUnnecessaryIsInstance] MagicMock guard
                                alt, dict
                            )
                        ),
                    ]
                _span_skill_ids = [
                    s for s in _span_candidates if isinstance(s, str) and s and s != "fallback-llm"
                ]
                # gate41 项3: ONE unified match predicate, shared by
                # metadata["has_match"] and metadata["confidence"] below.
                # router_matched alone is not a sufficient SPAN verdict —
                # it keeps the router's raw verdict (the :557/:585/:594
                # assignments are deliberately UNTOUCHED), while the span
                # must also require a REAL skill to attribute: an
                # all-fallback orchestrated plan stamps confidence=0.8 on
                # the result (:562) under router_matched=False, and the
                # sentinel/empty steps are filtered out of _span_skill_ids
                # above, so has_match=False rows must not carry that
                # high-confidence noise. This is the SAME expression as
                # the top_skills gate below and isomorphic to the CLI-path
                # span verdict cli/main.py:934 (``bool(_span_skill_id)`` —
                # the CLI path has no router_matched signal, so the
                # filtered skill ids ARE the verdict there). On current
                # main the AND is a no-op for router_matched=True (a true
                # match always yields non-empty _span_skill_ids across all
                # three assignment branches); it exists as a defensive
                # invariant should a future branch break that coupling.
                matched = result.router_matched and bool(_span_skill_ids)
                _task_span.metadata["skill_id"] = _span_skill_ids[0] if _span_skill_ids else ""
                _task_span.metadata["mode"] = result.mode
                # gate41 项3: miss rows write confidence=0.0 — the only
                # behavior change vs. gate40 (was result.confidence, which
                # leaked the fixed 0.8 from the :562 all-fallback branch).
                _task_span.metadata["confidence"] = result.confidence if matched else 0.0
                # Deliberate asymmetry (M12 miss blind-spot fix): the span
                # carries the ROUTER's real verdict (router_matched, ANDed
                # with the sentinel-filtered _span_skill_ids per gate41
                # 项3), NOT the mode-derived has_match property — the
                # property stays True on intercepted single-mode misses,
                # which kept hook-path misses invisible to
                # is_route_miss_span.
                # mode on a genuine miss is "single" (set from the
                # interception decision before routing), which the miss
                # predicate accepts (only "not_intercepted" is excluded).
                #
                # Consumers of this key (gate20): BOTH
                # ``gold_detection.is_route_miss_span`` (discovery pool)
                # AND ``tool_call_bridge._is_miss`` (outcome-signal
                # derivation) read metadata has_match — hook-path misses
                # now enter the bridge's miss set for the first time.
                # Direction verified correct: hook spans carry the real
                # platform session_id (route-hook forwarding), so
                # session_moved_on / re-ask evidence is meaningful — NOT
                # the hollow-weak_positive case the bridge's CLI exclusion
                # guards (one-shot CLI sessions). The gate17
                # cross-reference convention ("change one, re-read the
                # other") was honored — both predicates re-checked.
                _task_span.metadata["has_match"] = matched
                # gate18 pi NIT-4: layer semantics — match → winning layer;
                # miss → deepest cascade layer; omitted when unknown
                # (ScanSummary.miss_share_by_layer buckets missing as
                # "unknown"; pre-change spans simply lack the field).
                # isinstance guard: a mocked router's .value can be a
                # non-str MagicMock — never write that into span metadata.
                if isinstance(_route_layer, str) and _route_layer:
                    _task_span.metadata["layer"] = _route_layer

                # gate38 L2a: ordered routing snapshot ("top_skills", ≤3,
                # primary first) for future L2b analysis. Written ONLY on
                # a real router hit — gated on ``result.router_matched and
                # _span_skill_ids``, the SAME ``matched`` predicate as
                # metadata["has_match"] above (gate41 项3), NOT the
                # mode-derived ``has_match`` property (which stays
                # True on intercepted misses, :671-675). On miss the key
                # is omitted entirely. Duplication with
                # metadata["skill_id"] is deliberate: this is the full
                # at-write-time ranking snapshot — router state drifts
                # and cannot be replayed later. Data source: the same
                # sentinel-filtered ``_span_skill_ids`` list built above
                # (gate40 项4: fallback-llm steps never enter the
                # snapshot; all-fallback plans omit the key).
                if result.router_matched and _span_skill_ids:
                    _task_span.metadata["top_skills"] = _span_skill_ids[:3]

                # --- Instinct feedback bridge (neutral signal) ---
                if result.has_match and result.skill_id:
                    try:
                        # Dynamic import to avoid circular dependency at module load
                        from vibesop.core.routing.context_mixin import RouterContextMixin

                        mixin = RouterContextMixin.__new__(RouterContextMixin)
                        mixin._project_root = str(self.project_root)
                        mixin.record_instinct_matched(query, result.skill_id)
                    except Exception:
                        pass  # instinct recording is best-effort

        except Exception:
            # Trace context-manager handles span.error() automatically.
            # Catch here only to prevent trace failures from crashing the route.
            pass

        return result

    def route_step(
        self,
        step_query: str,
        step_number: int = 0,
        phase: int = 0,
    ) -> dict[str, Any]:
        """Lightweight step-level routing for Prompt Chain execution.

        Called by sub-agents or step runners to dynamically select skills
        for individual steps within a prompt chain.

        Args:
            step_query: The step's task description.
            step_number: Current step number (for context).
            phase: Current phase number (for context).

        Returns:
            Minimal routing dict with skill_id, confidence, etc.
        """
        from vibesop.core.routing.lightweight_api import LightweightRouter

        lw = LightweightRouter(project_root=self.project_root)
        return lw.route(
            step_query,
            context={"step": step_number, "phase": phase},
        )

    def handle_query_for_hook(
        self,
        query: str,
        *,
        platform: str = "generic",
        hook_event_name: str = "",
        include_additional_context: bool = True,
        no_match_message: bool = True,
        session_id: str | None = None,
        conversation_id: str = "",
    ) -> str:
        """Handle a query and return a platform hook response JSON string.

        This is the primary entry point for shell hook wrappers. It runs
        the full handle_query pipeline and formats the result as a hook
        response suitable for direct output to the platform.

        Args:
            query: The user's natural language query.
            platform: Platform identifier (claude-code, opencode, kimi-cli).
            hook_event_name: Hook event name for hookSpecificOutput.
            include_additional_context: Attach skill content as additionalContext.
            no_match_message: Produce fallback message when no skill matches.
            session_id: Session identifier; None mints a process UUID (see
                ``handle_query`` for seeding semantics).
            conversation_id: Conversation ID for multi-turn continuity.

        Returns:
            JSON string in the platform hook response format.
        """
        result = self.handle_query(
            query,
            platform=platform,
            session_id=session_id,
            conversation_id=conversation_id,
        )
        return result.to_hook_response(
            platform=platform,
            hook_event_name=hook_event_name,
            include_additional_context=include_additional_context,
            no_match_message=no_match_message,
        )

    # ── Async query dispatch (Phase 4) ───────────────────────────────────────

    async def process_query(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process a user query asynchronously based on the interception mode.

        Args:
            query: The user's natural language query.
            context: Optional context passed through to handlers.

        Returns:
            Dict with interception decision, routing result, and payload.
        """
        context = context or {}
        decision = self.interceptor.should_intercept(query)

        if not decision.should_route:
            return await self._default_handler(query, context)

        if decision.mode == InterceptionMode.SINGLE:
            return await self._single_route(query, context)

        if decision.mode == InterceptionMode.SINGLE_AGENT:
            analysis = decision.analysis
            if analysis is None or not analysis.suggested_roles:
                return await self._single_route(query, context)
            role = analysis.suggested_roles[0]
            skills = analysis.per_agent_skills.get(role, [])
            return await self._single_agent_with_skills(query, role, skills, context)

        if decision.mode == InterceptionMode.MULTI_AGENT_SQUAD:
            return await self._orchestrate(query, decision.analysis, context, mode=decision.mode)

        if decision.mode == InterceptionMode.ORCHESTRATE:
            return await self._orchestrate(query, None, context, mode=decision.mode)

        # Fallback for unhandled modes (e.g. slash commands)
        return {
            "intercepted": decision.should_route,
            "mode": decision.mode.value,
            "query": query,
            "reason": decision.reason,
        }

    async def _default_handler(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        """Default handler when the query is not intercepted."""
        _ = context
        return {"intercepted": False, "query": query}

    async def _single_route(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        """Route a query to a single skill asynchronously."""
        loop = asyncio.get_event_loop()
        route_result = await loop.run_in_executor(None, self.router.route, query)

        primary: dict[str, Any] = {}
        if route_result.primary is not None:
            primary = {
                "skill_id": route_result.primary.skill_id,
                "confidence": route_result.primary.confidence,
                "layer": route_result.primary.layer.value,
            }

        return {
            "intercepted": True,
            "mode": InterceptionMode.SINGLE.value,
            "query": query,
            "context": context,
            "primary": primary,
            "alternatives": [
                {"skill_id": alt.skill_id, "confidence": alt.confidence}
                for alt in getattr(route_result, "alternatives", [])[:5]
            ],
        }

    async def _single_agent_with_skills(
        self,
        query: str,
        role: str,
        skills: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Route a query for a single agent with an assigned role and skills."""
        result = await self._single_route(query, context)
        result["mode"] = InterceptionMode.SINGLE_AGENT.value
        result["role"] = role
        result["skills"] = skills
        return result

    async def _orchestrate(
        self,
        query: str,
        analysis: Any | None,
        context: dict[str, Any],
        mode: InterceptionMode = InterceptionMode.ORCHESTRATE,
    ) -> dict[str, Any]:
        """Orchestrate a query into a multi-step plan asynchronously."""
        loop = asyncio.get_event_loop()
        orch_result = await loop.run_in_executor(None, self.router.orchestrate, query)

        plan = getattr(orch_result, "execution_plan", None)
        plan_dict = plan.to_dict() if plan is not None else None

        return {
            "intercepted": True,
            "mode": mode.value,
            "query": query,
            "context": context,
            "analysis": analysis.to_dict() if analysis is not None else None,
            "plan": plan_dict,
            "is_multi_intent": getattr(orch_result, "is_multi_intent", plan is not None),
        }
