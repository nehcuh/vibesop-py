"""Ollama LLM provider — local models via OpenAI-compatible API.

Uses the OpenAI SDK to communicate with a locally running Ollama instance.
Ollama exposes an OpenAI-compatible API at http://localhost:11434/v1 by default.

Setup:
    brew install ollama
    ollama pull qwen3:35b-a3b-mlx  # or any model from ollama.com
    ollama serve
"""

import os

from openai import APIError, OpenAI

from vibesop.core.exceptions import LLMError
from vibesop.llm.base import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider using OpenAI-compatible API.

    Usage:
        provider = OllamaProvider(model="qwen3:35b")
        response = provider.call("Hello!")
        print(response.content)
    """

    DEFAULT_MODEL = "Qwen3.6-35B-A3B-mlx-mxfp8"
    DEFAULT_BASE_URL = "http://localhost:11434/v1"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.getenv("OLLAMA_API_KEY", "ollama")
        if base_url is None:
            base_url = os.getenv("OLLAMA_BASE_URL", self.DEFAULT_BASE_URL)
        if model is None:
            model = os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)

        super().__init__(api_key=api_key, base_url=base_url)

        self._model = model
        self._client: OpenAI | None = None
        if self.api_key:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    @property
    def provider_name(self) -> str:
        return "Ollama"

    def default_model(self) -> str:
        return self._model

    def call(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        if self._client is None:
            raise LLMError(
                "Ollama client not configured. Ensure ollama is running: ollama serve"
            )

        model = model or self._model

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except APIError as e:
            msg = getattr(e, "message", str(e))
            raise LLMError(f"Ollama API error: {msg}") from e

        choice = response.choices[0]
        content = choice.message.content or ""

        return LLMResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )

    def configured(self) -> bool:
        return self._client is not None
