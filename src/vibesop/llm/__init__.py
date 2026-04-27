"""LLM provider support for VibeSOP.

Supports multiple LLM providers:
- Anthropic (Claude 3.5 Haiku, Sonnet, Opus)
- OpenAI (GPT-4o, GPT-4o-mini)
- Ollama (local models via OpenAI-compatible API)

Heavy module imports (anthropic, openai, ollama) are lazy-loaded via
__getattr__ to avoid adding ~0.3s to cold-start without reducing
compatibility for callers that import from vibesop.llm directly.

When imported from cost_tracker or triage_prompts (lightweight modules),
the heavy third-party dependencies are not loaded until actually needed.
"""

from vibesop.llm.base import LLMProvider, LLMResponse, ProviderStats

_LAZY_MAP: dict[str, str] = {
    "AnthropicProvider": "vibesop.llm.anthropic",
    "OpenAIProvider": "vibesop.llm.openai",
    "OllamaProvider": "vibesop.llm.ollama",
    "create_from_env": "vibesop.llm.factory",
    "create_provider": "vibesop.llm.factory",
    "detect_provider_from_env": "vibesop.llm.factory",
}


def __getattr__(name: str):
    if name in _LAZY_MAP:
        import importlib

        module = importlib.import_module(_LAZY_MAP[name])
        attr = getattr(module, name)
        globals()[name] = attr
        return attr
    raise AttributeError(f"module 'vibesop.llm' has no attribute '{name}'")


__all__ = [  # pyright: ignore[reportUnsupportedDunderAll]
    "AnthropicProvider",  # pyright: ignore[reportUnsupportedDunderAll]
    "LLMProvider",
    "LLMResponse",
    "OllamaProvider",  # pyright: ignore[reportUnsupportedDunderAll]
    "OpenAIProvider",  # pyright: ignore[reportUnsupportedDunderAll]
    "ProviderStats",
    "create_from_env",  # pyright: ignore[reportUnsupportedDunderAll]
    "create_provider",  # pyright: ignore[reportUnsupportedDunderAll]
    "detect_provider_from_env",  # pyright: ignore[reportUnsupportedDunderAll]
]
