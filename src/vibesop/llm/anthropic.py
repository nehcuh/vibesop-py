"""Anthropic Claude LLM provider.

Supports Claude 3.5 Haiku, Sonnet, and Opus models.
"""

import os
from typing import cast

import anthropic
from anthropic import Anthropic, AsyncAnthropic

from vibesop.llm.base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider.

    Usage:
        provider = AnthropicProvider(api_key="sk-ant-...")
        response = provider.call("Hello, Claude!")
        print(response.content)
    """

    # Default models
    DEFAULT_MODEL = "claude-3-5-haiku-20241022"  # Fast and cost-effective
    FAST_MODEL = "claude-3-5-haiku-20241022"
    SMART_MODEL = "claude-3-5-sonnet-20241022"

    # API endpoint
    DEFAULT_BASE_URL = "https://api.anthropic.com"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            base_url: Custom base URL (defaults to https://api.anthropic.com)
        """
        if api_key is None:
            api_key = os.getenv("ANTHROPIC_API_KEY")

        if base_url is None:
            base_url = self.DEFAULT_BASE_URL

        super().__init__(api_key=api_key, base_url=base_url)

        # Initialize Anthropic client
        self._client: Anthropic | None = None
        if self.api_key:
            self._client = Anthropic(api_key=self.api_key, base_url=self.base_url)

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "Anthropic"

    def default_model(self) -> str:
        """Get default model."""
        return self.DEFAULT_MODEL

    def call(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Call Claude with a prompt.

        Args:
            prompt: The prompt to send
            model: Model to use (defaults to haiku for speed)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)

        Returns:
            LLMResponse with generated content

        Raises:
            ValueError: If provider is not configured
            anthropic.APIError: If API call fails
        """
        if not self._client:
            msg = "Anthropic provider not configured. Set ANTHROPIC_API_KEY."
            raise ValueError(msg)

        if model is None:
            model = self.default_model()

        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )

            content = cast("str", response.content[0].text)  # type: ignore[reportAttributeAccessIssue]
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            tokens_used = input_tokens + output_tokens

            self._record_call(tokens_used)

            return LLMResponse(
                content=content,
                model=model,
                provider=self.provider_name,
                tokens_used=tokens_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except anthropic.APIError:
            raise

    def _is_configured(self) -> bool:
        """Check if Anthropic API key is valid.

        Anthropic keys start with 'sk-ant-' and are typically 40+ characters.
        """
        return bool(self.api_key and self.api_key.startswith("sk-ant-") and len(self.api_key) >= 40)

    async def acall(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Asynchronous call to Claude using AsyncAnthropic client.

        Args:
            prompt: The prompt to send
            model: Model to use (defaults to haiku for speed)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)

        Returns:
            LLMResponse with generated content

        Raises:
            ValueError: If provider is not configured
            anthropic.APIError: If API call fails
        """
        if not self.api_key:
            msg = "Anthropic provider not configured. Set ANTHROPIC_API_KEY."
            raise ValueError(msg)

        if model is None:
            model = self.default_model()

        try:
            async with AsyncAnthropic(api_key=self.api_key, base_url=self.base_url) as client:
                response = await client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}],
                )

                content = cast("str", response.content[0].text)  # type: ignore[reportAttributeAccessIssue]
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                tokens_used = input_tokens + output_tokens

                self._record_call(tokens_used)

                return LLMResponse(
                    content=content,
                    model=model,
                    provider=self.provider_name,
                    tokens_used=tokens_used,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

        except anthropic.APIError:
            raise
