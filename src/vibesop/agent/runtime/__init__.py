"""Agent Runtime — bridges VibeSOP routing to AI Agent platforms.

Provides platform-agnostic components for:
- Intent interception (when to trigger routing)
- Skill injection (how to load matched skills into agent context)
- Decision presentation (transparent routing results to users)
- Plan execution (guide agents through multi-step orchestration)

Platform adapters (Claude Code / OpenCode / Kimi CLI) consume these
components via their respective hook/plugin/prompt mechanisms.
"""

from __future__ import annotations

from vibesop.agent.runtime.decision_presenter import (
    DecisionPresenter,
    PresentResult,
)
from vibesop.agent.runtime.intent_interceptor import (
    InterceptionContext,
    InterceptionDecision,
    InterceptionMode,
    IntentInterceptor,
)
from vibesop.agent.runtime.plan_executor import (
    ExecutionGuide,
    PlanExecutor,
)
from vibesop.agent.runtime.skill_injector import (
    InjectionMethod,
    InjectionResult,
    PlatformType,
    SkillInjector,
)

__all__ = [
    "DecisionPresenter",
    "ExecutionGuide",
    "InjectionMethod",
    "InjectionResult",
    "InterceptionContext",
    "InterceptionDecision",
    "InterceptionMode",
    "IntentInterceptor",
    "PlatformType",
    "PlanExecutor",
    "PresentResult",
    "SkillInjector",
]
