"""LLM provider factory.

Creates LLM providers based on configuration and environment.
"""

import os
from typing import Literal

from vibesop.llm.anthropic import AnthropicProvider
from vibesop.llm.base import LLMProvider
from vibesop.llm.openai import OpenAIProvider

ProviderType = Literal["anthropic", "openai"]


def create_provider(
    provider: ProviderType | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Create an LLM provider.

    Args:
        provider: Provider type ('anthropic' or 'openai')
                 If None, auto-detects from environment
        api_key: Optional API key (defaults to env var)
        base_url: Optional custom base URL

    Returns:
        Configured LLM provider instance

    Raises:
        ValueError: If provider type is invalid

    Examples:
        >>> provider = create_provider('anthropic')
        >>> response = provider.call('Hello!')

        >>> # Auto-detect from environment
        >>> provider = create_provider()
    """
    if provider is None:
        provider = detect_provider_from_env()

    if provider == "anthropic":
        return AnthropicProvider(api_key=api_key, base_url=base_url)
    if provider == "openai":
        return OpenAIProvider(api_key=api_key, base_url=base_url)

    msg = f"Invalid provider: {provider}. Must be 'anthropic' or 'openai'."
    raise ValueError(msg)


def detect_provider_from_env() -> ProviderType:
    """Detect which provider to use from environment variables.

    Priority:
        1. VIBE_LLM_PROVIDER env var
        2. ANTHROPIC_API_KEY env var
        3. OPENAI_API_KEY env var
        4. Default to 'anthropic'

    Returns:
        Provider type to use
    """
    # Explicit provider selection
    explicit_provider = os.getenv("VIBE_LLM_PROVIDER")
    if explicit_provider and explicit_provider in ("anthropic", "openai"):
        return explicit_provider
    # If invalid value, default to anthropic

    # Auto-detect from API keys
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"

    # Default to Anthropic (Claude is better for routing)
    return "anthropic"


def create_from_env(
    preferred_provider: ProviderType = "anthropic",
) -> LLMProvider:
    """Create provider from environment configuration.

    This is the recommended way to create providers for production use.
    It will automatically detect API keys and configuration.

    Args:
        preferred_provider: Preferred provider if both are available

    Returns:
        Configured provider (may be unconfigured if no API keys found)

    Examples:
        >>> provider = create_from_env('anthropic')
        >>> if provider.configured():
        ...     response = provider.call('Hello!')
    """
    # Try preferred provider first
    provider = create_provider(preferred_provider)
    if provider.configured():
        return provider

    # Try other provider
    other_provider = "openai" if preferred_provider == "anthropic" else "anthropic"
    provider = create_provider(other_provider)
    if provider.configured():
        return provider

    # Return unconfigured preferred provider
    return create_provider(preferred_provider)
