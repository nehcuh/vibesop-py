"""OpenAI GPT LLM provider.

Supports GPT-4o, GPT-4o-mini, and other OpenAI models.
"""

import os

from openai import OpenAI, AsyncOpenAI

from vibesop.llm.base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    """OpenAI GPT LLM provider.

    Usage:
        provider = OpenAIProvider(api_key="sk-...")
        response = provider.call("Hello, GPT!")
        print(response.content)
    """

    # Default models
    DEFAULT_MODEL = "gpt-4o-mini"  # Fast and cost-effective
    FAST_MODEL = "gpt-4o-mini"
    SMART_MODEL = "gpt-4o"

    # API endpoint
    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the OpenAI provider.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            base_url: Custom base URL (defaults to https://api.openai.com/v1)
        """
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")

        if base_url is None:
            base_url = self.DEFAULT_BASE_URL

        super().__init__(api_key=api_key, base_url=base_url)

        # Initialize OpenAI client
        self._client: OpenAI | None = None
        if self.api_key:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "OpenAI"

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
        """Call GPT with a prompt.

        Args:
            prompt: The prompt to send
            model: Model to use (defaults to gpt-4o-mini for speed)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)

        Returns:
            LLMResponse with generated content

        Raises:
            ValueError: If provider is not configured
            openai.APIError: If API call fails
        """
        if not self._client:
            msg = "OpenAI provider not configured. Set OPENAI_API_KEY."
            raise ValueError(msg)

        if model is None:
            model = self.default_model()

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            content = response.choices[0].message.content or ""
            tokens_used = response.usage.total_tokens if response.usage else None

            self._record_call(tokens_used)

            return LLMResponse(
                content=content,
                model=model,
                provider=self.provider_name,
                tokens_used=tokens_used,
            )

        except Exception as e:
            msg = f"OpenAI API error: {e}"
            raise Exception(msg) from e

    def _is_configured(self) -> bool:
        """Check if OpenAI API key is valid.

        OpenAI keys start with 'sk-' and are typically 40+ characters.
        """
        return bool(self.api_key and self.api_key.startswith("sk-") and len(self.api_key) >= 40)

    async def acall(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Asynchronous call to GPT using AsyncOpenAI client.

        Args:
            prompt: The prompt to send
            model: Model to use (defaults to gpt-4o-mini for speed)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)

        Returns:
            LLMResponse with generated content

        Raises:
            ValueError: If provider is not configured
            Exception: If API call fails
        """
        if not self.api_key:
            msg = "OpenAI provider not configured. Set OPENAI_API_KEY."
            raise ValueError(msg)

        if model is None:
            model = self.default_model()

        try:
            async with AsyncOpenAI(api_key=self.api_key, base_url=self.base_url) as client:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                content = response.choices[0].message.content or ""
                tokens_used = response.usage.total_tokens if response.usage else None

                self._record_call(tokens_used)

                return LLMResponse(
                    content=content,
                    model=model,
                    provider=self.provider_name,
                    tokens_used=tokens_used,
                )

        except Exception as e:
            msg = f"OpenAI API error: {e}"
            raise Exception(msg) from e
