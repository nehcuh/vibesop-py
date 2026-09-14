"""DeepSeek client: no SDK retries, thinking disabled, secrets never logged."""
from __future__ import annotations

from openai import OpenAI
from vibesop.core.llm_config import VibeSOPConfigManager

MODEL = "deepseek-v4-flash"
THINKING = {"type": "disabled"}
TEMPERATURE = 0


def make_client():
    config = VibeSOPConfigManager.get_llm_config()
    if not config.api_key:
        raise RuntimeError("missing_api_key")
    return OpenAI(
        api_key=config.api_key,
        base_url=config.api_base or "https://api.deepseek.com",
        max_retries=0,
        timeout=120,
    )


def complete(client, messages, *, max_tokens: int, tools: list | None):
    """HTTP call only. Caller must persist the request before invoking this."""
    kwargs = {
        "model": MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
        "extra_body": {"thinking": THINKING},
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)


def usage_dict(response) -> dict:
    usage = response.usage
    if usage is None:
        raise RuntimeError("missing_usage")
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return dict(usage)
