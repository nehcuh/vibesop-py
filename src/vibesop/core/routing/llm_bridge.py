"""Bridge between core routing and LLM providers.

Core routing should not import from vibesop.llm directly.
Instead, LLM-dependent operations (provider creation, prompt templates)
are registered here at startup time by the application layer.

This breaks the core → llm dependency inversion.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)



@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers used by AI triage.

    Any object with ``configured()`` and ``call()`` methods satisfies this.
    """

    def configured(self) -> bool: ...
    def call(self, prompt: str, max_tokens: int = 300, temperature: float = 0.1) -> Any: ...


class _LLMFactory:
    """Pluggable factory for creating LLM providers.

    The ``vibesop.llm`` package registers its ``create_provider`` function
    during import. If not registered, falls back to lazy import.
    """

    def __init__(self) -> None:
        self._factory: Any | None = None

    def register(self, factory: Any) -> None:
        self._factory = factory

    def create_provider(self, **kwargs: Any) -> LLMProvider | None:
        if self._factory is not None:
            try:
                return self._factory(**kwargs)
            except Exception as e:
                logger.debug(f"Registered LLM factory failed: {e}")
                return None

        try:
            from vibesop.llm.factory import create_provider

            return create_provider(**kwargs)  # type: ignore[no-any-return]
        except Exception as e:
            logger.debug(f"LLM provider creation failed: {e}")
            return None


llm_factory = _LLMFactory()


def init_llm_from_config() -> LLMProvider | None:
    """Create an LLM provider from VibeSOP configuration.

    Uses the registered factory if available, falls back to direct import.
    Returns None if no LLM is configured.
    """
    if _is_disabled():
        return None

    try:
        from vibesop.core.llm_config import VibeSOPConfigManager

        llm_config = VibeSOPConfigManager.get_llm_config()
        if llm_config and llm_config.api_key:
            return llm_factory.create_provider(
                provider=llm_config.provider,
                api_key=llm_config.api_key,
                base_url=llm_config.api_base,
            )
    except Exception as e:
        logger.debug(f"LLM config lookup failed: {e}")

    return llm_factory.create_provider()


def build_triage_prompt(query: str, skills_summary: str, **kwargs: Any) -> str:
    """Build the AI triage prompt using the prompt registry.

    Falls back to a basic prompt if the registry is unavailable.
    Extra kwargs (e.g. version) are forwarded to the registry.
    """
    try:
        from vibesop.llm.triage_prompts import TriagePromptRegistry

        return TriagePromptRegistry.render(
            query=query,
            skills_summary=skills_summary,
            **kwargs,
        )
    except ImportError:
        return _fallback_prompt(query, skills_summary)


def _is_disabled() -> bool:
    return os.getenv("VIBE_AI_TRIAGE_ENABLED", "").lower() in ("0", "false", "no")


def _fallback_prompt(query: str, skills_summary: str) -> str:
    return (
        f"Given these skills:\n{skills_summary}\n\n"
        f"Which skill best matches this query: \"{query}\"\n\n"
        f'Respond with JSON: {{"skill_id": "...", "confidence": 0.0-1.0}}'
    )
