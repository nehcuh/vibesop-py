"""OpenAI GPT LLM provider.

Supports GPT-4o, GPT-4o-mini, and other OpenAI models.
"""

import os

from openai import APIError as OpenAIAPIError
from openai import AsyncOpenAI, OpenAI

from vibesop.core.exceptions import LLMError
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
        model: str | None = None,
    ) -> None:
        """Initialize the OpenAI provider.

        Args:
            api_key: API key (defaults to OPENAI_API_KEY env var)
            base_url: Custom base URL (defaults to https://api.openai.com/v1)
            model: Default model name (defaults to gpt-4o-mini)
        """
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")

        if base_url is None:
            base_url = self.DEFAULT_BASE_URL

        if model:
            self.DEFAULT_MODEL = model

        self._is_deepseek = bool(base_url and "deepseek.com" in base_url)

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
            kwargs: dict[str, Any] = dict(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if self._is_deepseek:
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

            response = self._client.chat.completions.create(**kwargs)

            content = response.choices[0].message.content or ""
            if response.usage:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                tokens_used = response.usage.total_tokens
            else:
                input_tokens = None
                output_tokens = None
                tokens_used = None

            self._record_call(tokens_used)

            return LLMResponse(
                content=content,
                model=model,
                provider=self.provider_name,
                tokens_used=tokens_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except (OpenAIAPIError, OSError, ValueError) as e:
            msg = f"OpenAI API error: {e}"
            raise LLMError(self.provider_name, msg) from e

    def _is_configured(self) -> bool:
        """Check if API key is valid.

        OpenAI keys start with 'sk-' and are typically 40+ characters,
        but DeepSeek/Kimi/Zhipu keys may be shorter.
        """
        return bool(self.api_key and len(self.api_key) > 10)

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
                if response.usage:
                    input_tokens = response.usage.prompt_tokens
                    output_tokens = response.usage.completion_tokens
                    tokens_used = response.usage.total_tokens
                else:
                    input_tokens = None
                    output_tokens = None
                    tokens_used = None

                self._record_call(tokens_used)

                return LLMResponse(
                    content=content,
                    model=model,
                    provider=self.provider_name,
                    tokens_used=tokens_used,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

        except (OpenAIAPIError, OSError, ValueError) as e:
            msg = f"OpenAI API error: {e}"
            raise LLMError(self.provider_name, msg) from e
