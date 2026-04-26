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

from vibesop.agent.runtime.context_injector import (
    DEFAULT_MARKER_TEMPLATE,
    StepContextInjector,
    StepOutput,
)
from vibesop.agent.runtime.decision_presenter import (
    DecisionPresenter,
    PresentResult,
)
from vibesop.agent.runtime.intent_interceptor import (
    IntentInterceptor,
    InterceptionContext,
    InterceptionDecision,
    InterceptionMode,
)
from vibesop.agent.runtime.plan_executor import (
    COMPLETION_MARKER_PREFIX,
    ExecutionGuide,
    PlanExecutor,
)
from vibesop.agent.runtime.skill_injector import (
    InjectionMethod,
    InjectionResult,
    PlatformType,
    SkillInjector,
)
from vibesop.agent.runtime.slash_command_executor import (
    SlashCommandExecutor,
    SlashCommandResult,
)

__all__ = [
    "COMPLETION_MARKER_PREFIX",
    "DEFAULT_MARKER_TEMPLATE",
    "DecisionPresenter",
    "ExecutionGuide",
    "InjectionMethod",
    "InjectionResult",
    "IntentInterceptor",
    "InterceptionContext",
    "InterceptionDecision",
    "InterceptionMode",
    "PlanExecutor",
    "PlatformType",
    "PresentResult",
    "SkillInjector",
    "SlashCommandExecutor",
    "SlashCommandResult",
    "StepContextInjector",
    "StepOutput",
]
