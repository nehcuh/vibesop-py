"""Decorator that wraps any LLMProvider to emit llm-spans around call()/acall().

This is the single emission point required by v8.2 GAP-1: every LLM call that
flows through ``vibesop.llm.factory.create_provider`` becomes an llm-span
automatically. No call-site changes are required — the wrapper is installed
in the factory and transparent to callers.

Design notes:

* Tracer is queried via ``get_tracer()`` lazily. If tracing is disabled
  (``enabled=False``) the wrapper is a thin pass-through — no span overhead.
* The wrapper **does not** own ``api_key`` / ``base_url``; those live on the
  inner provider. Non-call methods (``provider_name``, ``default_model``,
  ``configured``, ``stats``) delegate to inner.
* Token accounting falls back to ``tokens_used // 2`` if the underlying
  response lacks ``input_tokens`` / ``output_tokens`` (legacy path).
* ``cost_usd`` is left at ``0.0`` in P1 — pricing table is M3 scope. Metadata
  carries ``cost_estimation="p1_not_available"`` so downstream aggregators
  know not to sum the field.
"""

from __future__ import annotations

import logging
from typing import Any

from vibesop.core.observability.tracer import get_tracer
from vibesop.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

_PROMPT_PREVIEW_LIMIT = 500


class SpanWrappedProvider(LLMProvider):
    """Wraps an inner LLMProvider, emitting llm-spans around every call.

    Implements the LLMProvider ABC by delegating non-call surface to the
    inner instance. Both sync ``call()`` and async ``acall()`` emit spans.
    """

    def __init__(self, inner: LLMProvider) -> None:
        # Intentionally do NOT call super().__init__ — we don't own api_key
        # or base_url, and we proxy ``_stats`` via the inner provider.
        self._inner = inner
        self.api_key = getattr(inner, "api_key", None)
        self.base_url = getattr(inner, "base_url", None)

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    def default_model(self) -> str:
        return self._inner.default_model()

    def configured(self) -> bool:
        return self._inner.configured()

    def stats(self) -> Any:
        return self._inner.stats()

    def _build_metadata(
        self,
        model: str | None,
        max_tokens: int,
        temperature: float,
        prompt_len: int,
        token_accounting: str = "measured",
    ) -> dict[str, Any]:
        resolved_model = model or self.default_model()
        return {
            "provider": self.provider_name,
            "model": resolved_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "prompt_chars": prompt_len,
            "cost_estimation": "p1_not_available",
            "token_accounting": token_accounting,
        }

    @staticmethod
    def _extract_tokens(response: LLMResponse) -> tuple[int, int, bool]:
        """Returns (tokens_in, tokens_out, was_estimated).

        ``was_estimated=True`` when input/output tokens were missing and we
        split ``tokens_used`` 50/50 as a fallback. Callers should record
        this in metadata so downstream aggregators can distinguish measured
        vs estimated token counts.
        """
        tokens_in = response.input_tokens or 0
        tokens_out = response.output_tokens or 0
        if tokens_in == 0 and tokens_out == 0 and response.tokens_used:
            tokens_in = response.tokens_used // 2
            tokens_out = response.tokens_used - tokens_in
            return tokens_in, tokens_out, True
        return tokens_in, tokens_out, False

    def call(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        tracer = get_tracer()
        if not tracer.enabled:
            return self._inner.call(
                prompt, model=model, max_tokens=max_tokens, temperature=temperature
            )

        span_name = f"llm:{self.provider_name}:{model or self.default_model()}"
        metadata = self._build_metadata(
            model, max_tokens, temperature, len(prompt)
        )
        # Use start_span/finish_span rather than the ``with tracer.span(...)``
        # context manager because the latter only catches ``Exception``. We
        # need to also handle BaseException (KeyboardInterrupt /
        # asyncio.CancelledError) so spans don't leak in 'running' state.
        span = tracer.start_span(span_name, kind="llm", metadata=metadata)
        span.set_input({"prompt_preview": prompt[:_PROMPT_PREVIEW_LIMIT]})
        try:
            response = self._inner.call(
                prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except BaseException as e:
            tracer.fail_span(span, str(e))
            raise

        tokens_in, tokens_out, was_estimated = self._extract_tokens(response)
        if was_estimated:
            metadata["token_accounting"] = "estimated_50_50_from_tokens_used"
        span.with_tokens(tokens_in, tokens_out)
        span.set_output(
            {
                "content_preview": response.content[:_PROMPT_PREVIEW_LIMIT],
                "model": response.model,
                "provider": response.provider,
            }
        )
        tracer.finish_span(span)
        return response

    async def acall(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        tracer = get_tracer()
        if not tracer.enabled:
            return await self._inner.acall(
                prompt, model=model, max_tokens=max_tokens, temperature=temperature
            )

        span_name = f"llm:{self.provider_name}:{model or self.default_model()}"
        metadata = self._build_metadata(
            model, max_tokens, temperature, len(prompt)
        )
        # Same rationale as sync path: ``except BaseException`` covers
        # asyncio.CancelledError (a BaseException subclass since 3.8) so
        # cancellation doesn't leak the span in 'running' state.
        span = tracer.start_span(span_name, kind="llm", metadata=metadata)
        span.set_input({"prompt_preview": prompt[:_PROMPT_PREVIEW_LIMIT]})
        try:
            response = await self._inner.acall(
                prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except BaseException as e:
            tracer.fail_span(span, str(e))
            raise

        tokens_in, tokens_out, was_estimated = self._extract_tokens(response)
        if was_estimated:
            metadata["token_accounting"] = "estimated_50_50_from_tokens_used"
        span.with_tokens(tokens_in, tokens_out)
        span.set_output(
            {
                "content_preview": response.content[:_PROMPT_PREVIEW_LIMIT],
                "model": response.model,
                "provider": response.provider,
            }
        )
        tracer.finish_span(span)
        return response
