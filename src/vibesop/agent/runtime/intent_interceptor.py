"""Intent interceptor — decides whether to trigger VibeSOP routing for a message.

This module provides platform-agnostic logic to determine when a user
message should be routed through VibeSOP's skill matching pipeline.

Platform integrations call `should_intercept()` at message boundaries:
- Claude Code: UserPromptSubmit hook
- OpenCode: chat.message plugin hook
- Kimi CLI: System prompt self-instruction (AI decides)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from vibesop.core.models import IntentAnalysis
from vibesop.core.orchestration.patterns import (
    EXPLICIT_SKILL_PATTERNS,
    MULTI_INTENT_REGEX_PATTERNS,
)
from vibesop.core.orchestration.semantic_intent_analyzer import SemanticIntentAnalyzer


class InterceptionMode(StrEnum):
    """How to handle the intercepted message."""

    NONE = "none"  # Don't route, let agent handle normally
    SINGLE = "single"  # Route to single best skill
    SINGLE_AGENT = "single_agent"  # Single agent with a role and per-agent skills
    MULTI_AGENT_SQUAD = "multi_agent_squad"  # Multiple agents collaborating as a squad
    ORCHESTRATE = "orchestrate"  # Detect multi-intent and build execution plan
    SLASH_COMMAND = "slash_command"  # Execute built-in slash command directly


@dataclass
class InterceptionContext:
    """Context for interception decisions.

    Attributes:
        session_id: Unique session identifier
        current_skill: Skill currently active (if known)
        message_history: Recent messages in conversation
        platform: Platform type (claude-code, opencode, kimi-cli)
    """

    session_id: str = "default"
    current_skill: str | None = None
    message_history: list[dict[str, Any]] = field(default_factory=list)
    platform: str = "unknown"


@dataclass
class InterceptionDecision:
    """Result of interception analysis.

    Attributes:
        should_route: Whether to trigger VibeSOP routing
        mode: Routing mode (none/single/single_agent/multi_agent_squad/orchestrate)
        reason: Human-readable explanation
        query: Normalized query to route (may differ from original)
        analysis: Optional semantic analysis (populated for agent modes)
    """

    should_route: bool
    mode: InterceptionMode = InterceptionMode.NONE
    reason: str = ""
    query: str = ""
    analysis: IntentAnalysis | None = None


class IntentInterceptor:
    """Intercepts user messages and decides whether to trigger skill routing.

    Uses a tiered decision strategy:
    - Slash commands and meta-queries are handled first.
    - Explicit skill overrides fast-path to single-skill routing.
    - Short, focused queries use a fast heuristic and remain SINGLE for
      backward compatibility.
    - Longer or ambiguous queries are analyzed by SemanticIntentAnalyzer,
      which may select SINGLE_AGENT or MULTI_AGENT_SQUAD modes.

    Example:
        >>> interceptor = IntentInterceptor()
        >>> decision = interceptor.should_intercept("review my code")
        >>> decision.should_route
        True
        >>> decision.mode
        <InterceptionMode.SINGLE: 'single'>
    """

    # Minimum query length to consider routing
    MIN_QUERY_LENGTH: int = 10

    # Maximum query length for fast-path single routing
    MAX_SHORT_QUERY: int = 50

    # Patterns that indicate meta-queries about VibeSOP itself
    META_PATTERNS: tuple[str, ...] = (
        r"vibe\s+(route|skill|config|build|install)",
        r"为什么.*(?:路由|技能|skill|route)",
        r"(?:技能|skill).*(?:怎么|如何|为什么|工作)",
        r"routing.*(?:work|how|why)",
        r"what\s+(?:is|does)\s+vibesop",
        r"explain\s+(?:the\s+)?routing",
    )

    EXPLICIT_SKILL_PATTERNS: tuple[str, ...] = EXPLICIT_SKILL_PATTERNS

    MULTI_INTENT_PATTERNS: tuple[str, ...] = MULTI_INTENT_REGEX_PATTERNS

    # Roles that, when detected alone in a short query, should promote to
    # SINGLE_AGENT so downstream can attach per-agent skills and role prompts.
    _SINGLE_AGENT_ROLES: frozenset[str] = frozenset({"architect", "red_team"})

    # Role keyword dictionary for the fast multi-role detection path.
    # When ≥ SQUAD_ROLE_THRESHOLD distinct roles are matched in a query, the
    # interceptor short-circuits to MULTI_AGENT_SQUAD without calling an LLM.
    ROLE_KEYWORDS: ClassVar[dict[str, tuple[str, ...]]] = {
        "architect": (
            "架构",
            "架构设计",
            "设计架构",
            "系统设计",
            "技术选型",
            "模块划分",
            "architecture",
            "system design",
            "tech selection",
        ),
        "implementer": (
            "实现",
            "编码",
            "编程",
            "写代码",
            "开发",
            "用python实现",
            "用go实现",
            "implement",
            "develop",
        ),
        "reviewer": (
            "审查",
            "评审",
            "代码审查",
            "质量检查",
            "review",
            "code review",
        ),
        "tester": (
            "测试",
            "单元测试",
            "集成测试",
            "覆盖率",
            "test",
            "testing",
            "coverage",
        ),
        "red_team": (
            "安全",
            "安全审查",
            "安全审计",
            "渗透",
            "漏洞",
            "威胁建模",
            "security",
            "audit",
            "vulnerability",
            "penetration",
        ),
        "debater": (
            "对比",
            "方案对比",
            "选型对比",
            "trade-off",
            "pros and cons",
            "方案选择",
        ),
    }

    SQUAD_ROLE_THRESHOLD: int = 2

    def __init__(
        self,
        semantic_analyzer: SemanticIntentAnalyzer | None = None,
    ) -> None:
        """Initialize the interceptor.

        Args:
            semantic_analyzer: Optional analyzer for deep intent analysis.
                If None, a default analyzer with no LLM client is created,
                which uses only the fast heuristic path.
        """
        self._semantic_analyzer = semantic_analyzer or SemanticIntentAnalyzer()

    def should_intercept(
        self,
        query: str,
        _context: InterceptionContext | None = None,
    ) -> InterceptionDecision:
        """Decide whether to intercept and route this message.

        Args:
            query: The user's message/query
            context: Optional session context

        Returns:
            InterceptionDecision with routing recommendation
        """
        original_query = query.strip()

        # 0. Check for VibeSOP slash commands → direct execution
        if original_query.startswith("/vibe-"):
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.SLASH_COMMAND,
                reason=f"VibeSOP slash command detected: {original_query.split()[0]}",
                query=original_query,
            )

        # 1. Empty or too short → skip
        if len(original_query) < self.MIN_QUERY_LENGTH:
            return InterceptionDecision(
                should_route=False,
                reason=f"Query too short ({len(original_query)} < {self.MIN_QUERY_LENGTH})",
            )

        # 2. Meta-query about VibeSOP itself → skip
        if self._is_meta_query(original_query):
            return InterceptionDecision(
                should_route=False,
                reason="Meta-query about VibeSOP system",
            )

        # 3. Check for explicit skill override → fast-path single routing.
        #    Skip this check when multi-role detection would yield a richer
        #    squad decision (e.g. "用Python实现" alone shouldn't pin the query
        #    to a single skill when other roles are also mentioned).
        explicit_skill = self._extract_explicit_skill(original_query)
        detected_roles_for_skill = self._detect_roles(original_query)
        if explicit_skill and len(detected_roles_for_skill) < self.SQUAD_ROLE_THRESHOLD:
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.SINGLE,
                reason=f"Explicit skill override: {explicit_skill}",
                query=original_query,
            )

        # 4. Fast multi-role detection: ≥ threshold distinct professional roles
        #    → MULTI_AGENT_SQUAD (no LLM needed). Checked before multi-intent
        #    markers so that "design + implement + audit" yields a squad even
        #    when sequential markers ("然后"/"最后") are present.
        if len(detected_roles_for_skill) >= self.SQUAD_ROLE_THRESHOLD:
            analysis = self._build_quick_squad_analysis(original_query, detected_roles_for_skill)
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.MULTI_AGENT_SQUAD,
                reason=f"Multi-role detected: {', '.join(detected_roles_for_skill)}",
                query=original_query,
                analysis=analysis,
            )

        # 5. Explicit multi-intent markers without multi-role → orchestrate.
        if self._has_multi_intent_markers(original_query):
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.ORCHESTRATE,
                reason="Multi-intent markers detected",
                query=original_query,
            )

        # 6. Short, focused query → fast path.
        if len(original_query) <= self.MAX_SHORT_QUERY:
            return self._analyze_short_query(original_query)

        # 6. Longer queries without explicit markers → deep semantic analysis.
        analysis = self._semantic_analyzer.analyze(original_query)
        return self._decision_from_analysis(original_query, analysis)

    def _analyze_short_query(self, query: str) -> InterceptionDecision:
        """Fast path for short queries; uses heuristic analyzer (no LLM)."""
        analysis = self._semantic_analyzer.analyze(query)

        # Preserve legacy behavior: multi-intent short queries go to ORCHESTRATE.
        if len(analysis.suggested_roles) >= 2 or analysis.complexity in (
            "composite",
            "multi_agent",
        ):
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.ORCHESTRATE,
                reason=f"Short query with composite intent: {analysis.facets}",
                query=query,
                analysis=analysis,
            )

        # Promote complex single-role short queries to SINGLE_AGENT.
        if analysis.suggested_roles and analysis.suggested_roles[0] in self._SINGLE_AGENT_ROLES:
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.SINGLE_AGENT,
                reason=f"Short query with complex role: {analysis.suggested_roles[0]}",
                query=query,
                analysis=analysis,
            )

        # Default legacy behavior: short focused query → SINGLE.
        return InterceptionDecision(
            should_route=True,
            mode=InterceptionMode.SINGLE,
            reason="Short focused query, likely single intent",
            query=query,
            analysis=analysis,
        )

    def _decision_from_analysis(
        self,
        query: str,
        analysis: IntentAnalysis,
    ) -> InterceptionDecision:
        """Map a semantic IntentAnalysis to an InterceptionDecision."""
        if analysis.squad_needed or analysis.complexity == "multi_agent":
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.MULTI_AGENT_SQUAD,
                reason=f"Multi-agent squad needed: {analysis.suggested_roles}",
                query=query,
                analysis=analysis,
            )

        if analysis.complexity == "composite":
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.ORCHESTRATE,
                reason=f"Composite task: {analysis.facets}",
                query=query,
                analysis=analysis,
            )

        # Simple but specific role → give it per-agent skills and role context.
        if analysis.suggested_roles:
            return InterceptionDecision(
                should_route=True,
                mode=InterceptionMode.SINGLE_AGENT,
                reason=f"Single agent with role: {analysis.suggested_roles[0]}",
                query=query,
                analysis=analysis,
            )

        # Default backward-compatible fallback.
        return InterceptionDecision(
            should_route=True,
            mode=InterceptionMode.ORCHESTRATE,
            reason="Default: check for multi-intent via orchestration",
            query=query,
            analysis=analysis,
        )

    def _is_meta_query(self, query: str) -> bool:
        """Check if query is about VibeSOP itself."""
        query_lower = query.lower()
        return any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in self.META_PATTERNS)

    def _extract_explicit_skill(self, query: str) -> str | None:
        """Extract explicitly mentioned skill ID from query."""
        for pattern in self.EXPLICIT_SKILL_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                # Return the captured group (skill identifier)
                skill = match.group(1).lower().strip()
                # Reject false positives like "高可用 的微服务架构" — the "用"
                # in "高可用" matches the "用 X" pattern but captures Chinese
                # text that cannot be a real skill ID. Real skill IDs are
                # ASCII (slashes, dashes, underscores, alphanumerics).
                if not skill.isascii():
                    continue
                return skill
        return None

    def _has_multi_intent_markers(self, query: str) -> bool:
        """Check if query contains multi-intent conjunctions."""
        query_lower = query.lower()
        for pattern in self.MULTI_INTENT_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False

    def _detect_roles(self, query: str) -> list[str]:
        """Detect which professional roles a query mentions.

        Each role is counted at most once even if multiple of its keywords
        appear.  Matching is case-insensitive on the lowercased query.

        Args:
            query: User query string.

        Returns:
            Deduplicated list of role IDs in first-seen order.
        """
        query_lower = query.lower()
        detected: list[str] = []
        for role_id, keywords in self.ROLE_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in query_lower:
                    detected.append(role_id)
                    break
        return detected

    def _build_quick_squad_analysis(
        self,
        query: str,  # noqa: ARG002  # accepted by caller for signature clarity
        roles: list[str],
    ) -> IntentAnalysis:
        """Build an IntentAnalysis for the fast multi-role path (no LLM).

        Args:
            query: Original user query.
            roles: Detected role IDs (≥ SQUAD_ROLE_THRESHOLD).

        Returns:
            IntentAnalysis with squad_needed=True, per-role skill hints, and
            a collaboration protocol inferred from the role combination.
        """
        from vibesop.core.orchestration.skill_composer import infer_skills_for_role

        per_agent_skills = {role: infer_skills_for_role(role) for role in roles}

        if "red_team" in roles:
            protocol = "red_team"
        elif "reviewer" in roles and "implementer" in roles:
            protocol = "review_gate"
        elif "debater" in roles:
            protocol = "debate"
        elif len(roles) >= 3:
            protocol = "parallel"
        else:
            protocol = "sequential"

        return IntentAnalysis(
            complexity="multi_agent",
            facets=roles,
            squad_needed=True,
            suggested_roles=roles,
            collaboration_protocol=protocol,
            per_agent_skills=per_agent_skills,
            handoff_points=list(range(1, len(roles))),
            confidence=0.8,
            reasoning=f"Fast role-keyword detection: {', '.join(roles)}",
        )


__all__ = [
    "IntentInterceptor",
    "InterceptionContext",
    "InterceptionDecision",
    "InterceptionMode",
]
