"""LLM provider factory.

Creates LLM providers based on configuration and environment.
"""

import os
from typing import Literal, cast

from vibesop.llm.anthropic import AnthropicProvider
from vibesop.llm.base import LLMProvider
from vibesop.llm.models import OPENAI_DEFAULT_MODEL, PROVIDER_DEFAULT_MODELS
from vibesop.llm.ollama import OllamaProvider
from vibesop.llm.openai import OpenAIProvider

ProviderType = Literal["anthropic", "openai", "ollama", "deepseek", "kimi", "zhipu"]

# Valid providers for input validation
_VALID_PROVIDERS: frozenset[str] = frozenset(
    ["anthropic", "openai", "ollama", "deepseek", "kimi", "zhipu"]
)

# OpenAI-compatible providers — all routed through OpenAIProvider
# with the appropriate base_url.
_OPENAI_COMPATIBLE: dict[str, str] = {
    "deepseek": "https://api.deepseek.com",
    "kimi": "https://api.moonshot.cn/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
}

# Default models live in vibesop.llm.models (single source of truth).


def create_provider(
    provider: ProviderType | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Create an LLM provider.

    Args:
        provider: Provider type ('anthropic', 'openai', 'ollama',
                  'deepseek', 'kimi', 'zhipu'). None = auto-detect.
        api_key: Optional API key (defaults to env var)
        base_url: Optional custom base URL (overrides provider default)

    Returns:
        Configured LLM provider instance

    Raises:
        ValueError: If provider type is invalid
    """
    if provider is None:
        provider = detect_provider_from_env()

    if provider not in _VALID_PROVIDERS:
        raise ValueError(f"Invalid provider: {provider}")

    if provider == "anthropic":
        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        return AnthropicProvider(api_key=resolved_key, base_url=base_url)
    if provider == "ollama":
        resolved_key = api_key
        resolved_base = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return OllamaProvider(api_key=resolved_key, base_url=resolved_base)

    # OpenAI and all OpenAI-compatible providers
    resolved_key = api_key
    if not resolved_key:
        env_map = {"deepseek": "DEEPSEEK_API_KEY", "kimi": "KIMI_API_KEY", "zhipu": "ZHIPU_API_KEY"}
        resolved_key = os.getenv(env_map.get(provider, "")) or os.getenv("OPENAI_API_KEY")
    resolved_base_url = base_url or _OPENAI_COMPATIBLE.get(provider)
    resolved_model = PROVIDER_DEFAULT_MODELS.get(provider, OPENAI_DEFAULT_MODEL)
    return OpenAIProvider(api_key=resolved_key, base_url=resolved_base_url, model=resolved_model)


def detect_provider_from_env() -> ProviderType:
    """Detect which provider to use from environment variables.

    Priority:
        1. VIBE_LLM_PROVIDER env var (explicit override)
        2. ANTHROPIC_API_KEY env var (first-class)
        3. OPENAI_API_KEY env var (first-class)
        4. DEEPSEEK_API_KEY (third-party, highest priority)
        5. KIMI_API_KEY (third-party)
        6. ZHIPU_API_KEY (third-party)
        7. OLLAMA_BASE_URL or OLLAMA_MODEL env var (local fallback)
        8. Default to 'ollama' (local, no API key required)

    Third-party providers are ordered: deepseek → kimi → zhipu → ollama.
    This matches the team's preferred provider ranking for VibeSOP routing.
    """
    explicit_provider = os.getenv("VIBE_LLM_PROVIDER")
    if explicit_provider and explicit_provider in _VALID_PROVIDERS:
        return cast("ProviderType", explicit_provider)

    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek"

    for provider_name in ["kimi", "zhipu"]:
        env_key = f"{provider_name.upper()}_API_KEY"
        if os.getenv(env_key):
            return cast("ProviderType", provider_name)

    if os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_MODEL"):
        return "deepseek"

    return "ollama"


def create_from_env(
    preferred_provider: ProviderType | None = None,
) -> LLMProvider:
    """Create provider from environment configuration.

    This is the recommended way to create providers for production use.
    It will automatically detect API keys and configuration.

    Args:
        preferred_provider: Preferred provider if multiple are available

    Returns:
        Configured provider (may be unconfigured if no API keys found)
    """
    provider = create_provider(preferred_provider)
    if provider.configured():
        return provider

    # Try alternatives in order
    alternatives: list[ProviderType] = ["openai", "deepseek", "kimi", "zhipu", "ollama"]
    for alt in alternatives:
        if alt == preferred_provider:
            continue
        try:
            p = create_provider(alt)
            if p.configured():
                return p
        except (ValueError, TypeError):
            pass

    return create_provider(preferred_provider)
