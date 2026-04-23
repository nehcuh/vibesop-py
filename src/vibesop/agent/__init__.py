"""VibeSOP Agent Integration.

This module provides direct Python API for AI Agents (like Claude Code)
to use VibeSOP routing with their internal LLM, without requiring
external API key configuration.

Usage:
    >>> from vibesop.agent import AgentRouter
    >>>
    >>> # Create a simple LLM wrapper
    >>> class AgentLLM:
    ...     def call(self, prompt, max_tokens=100, temperature=0.1):
    ...         # Use Agent's internal LLM here
    ...         response = agent_internal_llm(prompt)
    ...         return SimpleResponse(content=response)
    >>>
    >>> # Route with Agent's LLM
    >>> router = AgentRouter()
    >>> router.set_llm(AgentLLM())
    >>> result = router.route("帮我审查代码质量")
    >>> print(result.primary.skill_id)  # gstack/review
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SimpleResponse:
    """Simple response wrapper for LLM output.

    Matches the interface expected by TriageService.
    """

    def __init__(self, content: str, model: str = "agent-internal", input_tokens: int = 0, output_tokens: int = 0):
        self.content = content
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.tokens_used = input_tokens + output_tokens


class SimpleLLM:
    """Simple LLM wrapper interface for Agent integration.

    Subclasses should implement the `call` method.

    Example:
        >>> class MyLLM(SimpleLLM):
        ...     def call(self, prompt, max_tokens=100, temperature=0.1):
        ...         response = my_llm_generate(prompt)
        ...         return SimpleResponse(content=response)
    """

    def configured(self) -> bool:
        """Check if the LLM is configured and ready to use.

        Returns:
            True if the LLM can generate responses
        """
        return True

    def call(self, prompt: str, max_tokens: int = 100, temperature: float = 0.1) -> SimpleResponse:
        """Call the LLM with the given prompt.

        Args:
            prompt: The prompt to send to the LLM
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            SimpleResponse with the LLM output
        """
        raise NotImplementedError("Subclasses must implement call()")


class AgentRouter:
    """Router wrapper for AI Agent integration.

    This class provides a simplified API for Agents to use VibeSOP routing
    with their internal LLM.

    Example:
        >>> from vibesop.agent import AgentRouter, SimpleResponse
        >>>
        >>> # Define LLM wrapper
        >>> class MyLLM:
        ...     def call(self, prompt, max_tokens=100, temperature=0.1):
        ...         response = self._agent.generate(prompt)
        ...         return SimpleResponse(content=response)
        >>>
        >>> # Route with Agent's LLM
        >>> router = AgentRouter()
        >>> router.set_llm(MyLLM())
        >>> result = router.route("debug the failing test")
        >>> if result.has_match:
        ...     skill_id = result.primary.skill_id
        ...     confidence = result.primary.confidence
    """

    def __init__(self, project_root: str | Path = "."):
        """Initialize the Agent router.

        Args:
            project_root: Path to project root directory
        """
        from vibesop.core.routing import UnifiedRouter

        self._router = UnifiedRouter(project_root=project_root)

    def set_llm(self, llm_provider: Any) -> None:
        """Inject the Agent's LLM for AI triage.

        The LLM provider must have a `call` method with signature:
            call(prompt: str, max_tokens: int, temperature: float) -> Response

        The Response object must have a `content` attribute with the LLM output.

        Args:
            llm_provider: Agent's LLM wrapper

        Example:
            >>> class AgentLLM:
            ...     def call(self, prompt, max_tokens=100, temperature=0.1):
            ...         return SimpleResponse(content=self._generate(prompt))
            >>> router.set_llm(AgentLLM())
        """
        self._router.set_llm(llm_provider)

    def route(self, query: str, enable_ai_triage: bool = True) -> Any:
        """Route a query to the best matching skill.

        Args:
            query: User query or intent
            enable_ai_triage: Whether to use AI triage (requires LLM to be set)

        Returns:
            RoutingResult object with primary match, alternatives, and metadata

        Note:
            When enable_ai_triage=True and an LLM is set via set_llm(),
            AI triage will be used for this call regardless of global config.
        """
        # If AI triage is requested and LLM is available, temporarily enable it
        if enable_ai_triage and self._router._llm is not None:
            # Store original configs
            original_router_config = self._router._config
            original_triage_config = self._router._triage_service._config
            try:
                # Create modified configs with AI triage enabled
                modified_config = original_router_config.model_copy(update={"enable_ai_triage": True})
                self._router._config = modified_config
                self._router._triage_service._config = modified_config
                result = self._router.route(query)
            finally:
                # Restore original configs
                self._router._config = original_router_config
                self._router._triage_service._config = original_triage_config
        else:
            result = self._router.route(query)

        return result

    def check_reroute(
        self,
        new_message: str,
        current_skill: str,
        enable_ai_triage: bool = True,
    ) -> dict[str, Any]:
        """Check if re-routing is suggested for a new message.

        This is useful for multi-turn conversations to detect when the
        user's intent has shifted.

        Args:
            new_message: The latest user message
            current_skill: The skill currently being used
            enable_ai_triage: Whether to use AI triage (requires LLM to be set)

        Returns:
            Dictionary with:
                - should_reroute: bool
                - recommended_skill: str | None
                - confidence: float
                - reason: str
                - current_skill: str
        """
        from vibesop.core.sessions import SessionContext

        # Enable AI triage temporarily if requested and LLM is available
        if enable_ai_triage and self._router._llm is not None:
            original_router_config = self._router._config
            original_triage_config = self._router._triage_service._config
            try:
                modified_config = original_router_config.model_copy(update={"enable_ai_triage": True})
                self._router._config = modified_config
                self._router._triage_service._config = modified_config
                ctx = SessionContext(project_root=self._router.project_root, router=self._router)
                ctx.set_current_skill(current_skill)
                suggestion = ctx.check_reroute_needed(new_message)
            finally:
                self._router._config = original_router_config
                self._router._triage_service._config = original_triage_config
        else:
            ctx = SessionContext(project_root=self._router.project_root, router=self._router)
            ctx.set_current_skill(current_skill)
            suggestion = ctx.check_reroute_needed(new_message)

        return {
            "should_reroute": suggestion.should_reroute,
            "recommended_skill": suggestion.recommended_skill,
            "confidence": suggestion.confidence,
            "reason": suggestion.reason,
            "current_skill": suggestion.current_skill,
        }

    def get_session_summary(self) -> dict[str, Any]:
        """Get summary of current routing session.

        Returns:
            Dictionary with session statistics
        """
        from vibesop.core.sessions import SessionContext

        ctx = SessionContext.load(project_root=self._router.project_root)
        return ctx.get_session_summary()


__all__ = [
    "AgentRouter",
    "SimpleResponse",
    "SimpleLLM",
]
