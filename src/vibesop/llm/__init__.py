"""LLM provider support for VibeSOP.

Supports multiple LLM providers:
- Anthropic (Claude 3.5 Haiku, Sonnet, Opus)
- OpenAI (GPT-4o, GPT-4o-mini)
- Ollama (local models via OpenAI-compatible API)
"""

from vibesop.llm.anthropic import AnthropicProvider
from vibesop.llm.base import LLMProvider, LLMResponse, ProviderStats
from vibesop.llm.factory import (
    create_from_env,
    create_provider,
    detect_provider_from_env,
)
from vibesop.llm.ollama import OllamaProvider
from vibesop.llm.openai import OpenAIProvider

__all__ = [
    "AnthropicProvider",
    "LLMProvider",
    "LLMResponse",
    "OllamaProvider",
    "OpenAIProvider",
    "ProviderStats",
    "create_from_env",
    "create_provider",
    "detect_provider_from_env",
]
