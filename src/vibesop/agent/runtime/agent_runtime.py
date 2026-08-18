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

# Module-level observability tracer (lazy-initialised).
_obs_tracer: ObservabilityTracer | None = None


def _get_obs_tracer() -> ObservabilityTracer:
    """Return the module-level observability tracer.

    Creates it lazily so the observability module is only imported
    when tracing is actually needed (avoids import overhead on cold starts).
    """
    global _obs_tracer
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

        # Hint path must match real on-disk layout. For builtin skills the
        # file is bundled as data (force-include per commit 185dfe4) — it may
        # live in site-packages next to the installed package, OR in the dev
        # repo's core/skills/ directory. Scan both and emit an absolute path
        # so Claude can Read it regardless of the user's CWD.
        user_root = self.project_root or Path.cwd()
        if "/" in self.skill_id:
            namespace, bare_name = self.skill_id.split("/", 1)
            if namespace == "builtin":
                import sys

                builtin_candidates = [user_root / "core" / "skills" / bare_name / "SKILL.md"]
                for path_entry in sys.path:
                    if not path_entry:
                        continue
                    bundled = (
                        Path(path_entry) / "vibesop" / "builtin_skills" / bare_name / "SKILL.md"
                    )
                    if bundled not in builtin_candidates:
                        builtin_candidates.append(bundled)
                hint_path = next(
                    (p.as_posix() for p in builtin_candidates if p.exists()),
                    f"core/skills/{bare_name}/SKILL.md",
                )
            else:
                hint_path = f"skills/{skill_flat}/SKILL.md"
        else:
            hint_path = f"skills/{self.skill_id}/SKILL.md"

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
                result.mode = decision.mode.value if hasattr(decision.mode, "value") else str(decision.mode)

                # 3. Route the query
                try:
                    if decision.mode in (InterceptionMode.ORCHESTRATE, InterceptionMode.MULTI_AGENT_SQUAD):
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

                        orch_result = self.router.orchestrate(query, callbacks=callbacks, context=squad_ctx)
                        if orch_result.get("is_multi_intent"):
                            result.mode = "orchestrate"
                            plan = orch_result.get("plan", {})
                            result.plan = plan
                            steps = plan.get("steps", [])
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
                    else:
                        routing_result = self.router.route(query, enable_ai_triage=True)

                        # 4. Present the decision
                        try:
                            present = self.presenter.present_single_result(routing_result, platform)
                            result.decision_message = present.message if explain else ""
                        except Exception as e:
                            logger.debug(f"Decision presentation failed: {e}")

                        # 5. Extract match details
                        if hasattr(routing_result, "has_match") and routing_result.has_match:
                            primary = routing_result.primary if hasattr(routing_result, "primary") else None
                            if primary:
                                result.skill_id = getattr(primary, "skill_id", "")
                                result.skill_name = getattr(primary, "skill_name", "")
                                result.confidence = getattr(primary, "confidence", 0.0)

                            if hasattr(routing_result, "alternatives"):
                                for alt in routing_result.alternatives[:5]:
                                    result.alternatives.append(
                                        {"skill_id": getattr(alt, "skill_id", ""), "confidence": getattr(alt, "confidence", 0.0)}
                                    )

                            if hasattr(routing_result, "plan") and routing_result.plan:
                                try:
                                    from vibesop.agent.execution_protocol import ExecutionProtocol
                                    result.plan = ExecutionProtocol.plan_to_json(routing_result.plan)
                                except Exception as e:
                                    logger.debug(f"Plan serialization failed: {e}")
                except Exception as e:
                    result.errors.append(f"Routing failed: {e}")
                    _task_span.set_error(f"Routing failed: {e}")
                    return result

                # 6. Inject skill content
                if result.skill_id:
                    try:
                        injection = self.injector.inject_single_skill(result.skill_id, platform)
                        if isinstance(injection.payload, str):
                            result.skill_content = injection.payload
                        elif isinstance(injection.payload, dict):
                            result.skill_content = (
                                injection.payload.get("additionalContext")
                                or injection.payload.get("content")
                                or ""
                            )
                    except Exception as e:
                        logger.debug(f"Skill injection failed: {e}")

                # Enrich the task span with routing metadata
                _task_span.metadata["skill_id"] = result.skill_id or ""
                _task_span.metadata["mode"] = result.mode
                _task_span.metadata["confidence"] = result.confidence
                _task_span.metadata["has_match"] = result.has_match

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
