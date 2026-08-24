"""Per-model token pricing for cost estimation.

Pricing data sourced from official provider pricing pages. Tagged with
``LAST_UPDATED`` — refresh quarterly or when a major model launches. PRs
welcome when prices drift.

Usage::

    from vibesop.llm.pricing import get_pricing

    price = get_pricing("deepseek-v4-flash", provider="deepseek")
    if price is not None:
        cost = price.cost_usd(tokens_in=100, tokens_out=20)
        # cost ≈ $0.0000224 for deepseek-v4-flash at $0.14/$0.28 per Mtok

Design:

* Prices are USD per **million** tokens (industry convention).
* Lookup is exact-match first, then longest-prefix-match (handles
  ``gpt-4o-mini-2024-07-18`` → ``gpt-4o-mini``).
* ``provider`` is a hint. If the model isn't found in that provider's
  table, the lookup falls back to scanning all providers. This handles
  OpenAI-compatible proxies serving e.g. ``gpt-4o`` under a different
  provider key.
* Returns ``None`` for unknown models — never raises. Callers treat
  ``None`` as ``cost_usd=0`` with a ``cost_estimation="unavailable"``
  metadata marker.
"""

from __future__ import annotations

from typing import NamedTuple

LAST_UPDATED = "2026-07-23"


class ModelPrice(NamedTuple):
    """Per-token price for a single model.

    All rates are USD per 1 million tokens.
    """

    input_per_mtok: float
    output_per_mtok: float

    def cost_usd(self, tokens_in: int, tokens_out: int) -> float:
        """Cost in USD for the given token counts."""
        return (tokens_in * self.input_per_mtok + tokens_out * self.output_per_mtok) / 1_000_000


# Per-provider pricing tables.
# Keys are model ID prefixes (matched via longest-prefix).
# Values are (input_per_mtok, output_per_mtok) in USD per million tokens.
_PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {
        # https://www.anthropic.com/pricing
        "claude-opus-4": (15.0, 75.0),
        "claude-sonnet-4": (3.0, 15.0),
        "claude-haiku-4": (1.0, 5.0),
        # Legacy Claude 3.x (some still served)
        "claude-3-5-sonnet": (3.0, 15.0),
        "claude-3-5-haiku": (1.0, 5.0),
        "claude-3-opus": (15.0, 75.0),
        "claude-3-sonnet": (3.0, 15.0),
        "claude-3-haiku": (0.25, 1.25),
    },
    "openai": {
        # https://openai.com/api/pricing/
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.0),
        "gpt-4-turbo": (10.0, 30.0),
        "gpt-4": (30.0, 60.0),
        "gpt-3.5-turbo": (0.50, 1.50),
        "o4-mini": (1.10, 4.40),
        "o3-mini": (1.10, 4.40),
        "o3": (10.0, 40.0),
        "o1-mini": (3.0, 12.0),
        "o1": (15.0, 60.0),
    },
    "deepseek": {
        # https://api-docs.deepseek.com/quick_start/pricing
        # deepseek-v4-flash confirmed in catalog (see models.py). Price estimated
        # from deepseek-chat band; update when official v4 pricing published.
        "deepseek-v4-flash": (0.14, 0.28),
        "deepseek-v4-pro": (0.55, 2.19),
        "deepseek-v4": (0.27, 1.10),
        "deepseek-chat": (0.27, 1.10),
        "deepseek-reasoner": (0.55, 2.19),
    },
    "kimi": {
        # https://platform.moonshot.ai/docs/pricing
        # CNY converted to USD at ~7.2 CNY/USD; rounded to nearest cent.
        "moonshot-v1-8k": (1.68, 1.68),
        "moonshot-v1-32k": (3.36, 3.36),
        "moonshot-v1-128k": (8.58, 8.58),
        "kimi-k2": (1.20, 4.80),
    },
    "zhipu": {
        # https://open.bigmodel.cn/pricing
        # GLM-4-Flash is currently free; GLM-4 paid tier.
        "glm-4-flash": (0.0, 0.0),
        "glm-4-air": (0.10, 0.10),
        "glm-4-airx": (0.20, 0.20),
        "glm-4-plus": (5.0, 5.0),
        "glm-4v": (0.05, 0.05),
        "glm-4": (0.10, 0.10),
    },
    "ollama": {
        # Local, $0 — user provides compute.
    },
}


def get_pricing(model: str, provider: str | None = None) -> ModelPrice | None:
    """Look up per-token pricing for a model.

    Args:
        model: Model ID (e.g. ``"gpt-4o-mini"``, ``"deepseek-v4-flash"``).
        provider: Optional provider hint (``"anthropic"``, ``"openai"``,
            ``"deepseek"``, ``"kimi"``, ``"zhipu"``, ``"ollama"``).

    Returns:
        ``ModelPrice`` if found, ``None`` if unknown. Never raises.

    Notes:
        Provider hint is a *hint*, not a constraint. If the model isn't in
        the hinted provider's table, we fall back to scanning all providers.
        This handles OpenAI-compatible proxies (e.g. DeepSeek served via the
        ``openai`` library with a custom ``base_url``): the wrapper reports
        ``provider="OpenAI"`` but the model name ``deepseek-v4-flash`` is
        only in the ``deepseek`` table.
    """
    if not model:
        return None

    # Provider-specific lookup first (cheap path)
    if provider and provider in _PRICING:
        price = _lookup_in_table(model, _PRICING[provider])
        if price is not None:
            return ModelPrice(*price)

    # Cross-provider fallback. ALWAYS scan if provider-keyed lookup failed.
    # This is necessary because OpenAI-compatible providers serve foreign
    # models (DeepSeek, Kimi, Zhipu) under the "openai" provider key.
    for table in _PRICING.values():
        price = _lookup_in_table(model, table)
        if price is not None:
            return ModelPrice(*price)

    return None


def _lookup_in_table(
    model: str, table: dict[str, tuple[float, float]]
) -> tuple[float, float] | None:
    """Exact match first, then longest *boundary-aware* prefix match.

    Boundary rule: a prefix matches only if it ends at a model-name boundary
    in the input. A boundary is the end-of-string or a ``-`` / ``.`` / ``_``
    character immediately after the prefix. This prevents ``gpt-4`` from
    matching ``gpt-4.1`` (which is ~15x cheaper) or ``o1`` from matching
    ``o1-pro`` (~10x different), while still allowing ``gpt-4o-mini`` to
    match ``gpt-4o-mini-2024-07-18`` and ``claude-sonnet-4`` to match
    ``claude-sonnet-4-6-20250818``.
    """
    if model in table:
        return table[model]
    best_prefix: str | None = None
    best_price: tuple[float, float] | None = None
    for prefix, price in table.items():
        if not _prefix_matches(model, prefix):
            continue
        if best_prefix is None or len(prefix) > len(best_prefix):
            best_prefix = prefix
            best_price = price
    return best_price


# A prefix is a valid match only if the character following it in ``model``
# is one of these (or EOL). ``-`` and ``_`` are segment continuations
# (e.g. ``-2024-07-18``, ``_preview``). ``.`` is deliberately NOT included:
# it separates distinct model generations with different pricing
# (``gpt-4`` is legacy $30/$60, ``gpt-4.1`` is modern ~$2/$8 — 15x apart).
# Treating ``.`` as a continuation would silently mis-price 4.1, 4.5, etc.
_BOUNDARY_CHARS = frozenset("-_")


def _prefix_matches(model: str, prefix: str) -> bool:
    """Return True if ``model`` starts with ``prefix`` at a name boundary.

    Boundary = EOL or a ``-`` / ``_`` char immediately after the prefix.
    See ``_BOUNDARY_CHARS`` for the rationale on why ``.`` is excluded.
    """
    if not model.startswith(prefix):
        return False
    if len(model) == len(prefix):
        return True
    return model[len(prefix)] in _BOUNDARY_CHARS


def last_updated() -> str:
    """Return the LAST_UPDATED date stamp (for diagnostic output)."""
    return LAST_UPDATED
