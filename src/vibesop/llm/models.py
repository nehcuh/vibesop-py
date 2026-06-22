"""Single source of truth for LLM provider default model IDs + validation.

Centralised so ``factory`` / ``llm_config`` / ``understander`` can't drift apart,
and so stale model IDs (which 404 at the provider) live in one place. The
codebase previously hard-coded stale snapshots — ``claude-3-5-sonnet-20241022``,
``claude-3-opus-20240229``, ``gpt-4`` — that the providers no longer serve.

``validate_provider_model`` checks a configured model against the provider's live
``/models`` endpoint when an API key is available. It is best-effort and
fail-safe: a missing key or a network error never blocks configuration (returns
``ok=True, "skipped …"``); only a confirmed "model not in catalog" returns
``ok=False``. (DeepSeek ``deepseek-v4-flash`` / ``deepseek-v4-pro`` were
confirmed valid via this path.)
"""

from __future__ import annotations

import os

# OpenAI-compatible provider -> (default model, /models base URL). Single source;
# was duplicated in factory.py + llm_config.py.
PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "deepseek": "deepseek-v4-flash",
    "kimi": "moonshot-v1-8k",
    "zhipu": "glm-4",
}

PROVIDER_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
}

# Canonical CURRENT Anthropic / OpenAI model IDs. The codebase had stale
# snapshots that 404 — reference these instead.
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-6"
ANTHROPIC_SMART_MODEL = "claude-opus-4-8"
ANTHROPIC_FAST_MODEL = "claude-haiku-4-5"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
OPENAI_SMART_MODEL = "gpt-4o"

_PROVIDER_KEYS: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "KIMI_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def validate_provider_model(
    provider: str, model: str, api_key: str | None = None
) -> tuple[bool, str]:
    """Best-effort check that ``model`` exists in ``provider``'s catalog.

    Returns ``(ok, message)``. Fail-safe: missing key / no endpoint / network or
    parse error -> ``(True, "skipped …")`` (never blocks configuration). Only a
    confirmed catalog lookup where the model is absent returns ``(False, ...)``.
    """
    base_url = PROVIDER_BASE_URLS.get(provider) or (
        "https://api.openai.com/v1" if provider == "openai" else ""
    )
    if not base_url:
        return True, "skipped (no /models endpoint for provider)"

    key = api_key or os.getenv(_PROVIDER_KEYS.get(provider, ""))
    if not key and provider != "openai":
        key = os.getenv("OPENAI_API_KEY")
    if not key:
        return True, "skipped (no api key)"

    try:
        import httpx

        resp = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=5,
        )
        if resp.status_code != 200:
            return True, f"skipped (provider returned HTTP {resp.status_code})"
        ids = {m.get("id", "") for m in resp.json().get("data", [])}
        if model in ids:
            return True, "ok"
        return False, f"model {model!r} not in provider catalog ({len(ids)} models)"
    except Exception as e:  # fail-safe — never block on validation
        return True, f"skipped (check error: {e})"
