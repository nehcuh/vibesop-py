"""Base LLM provider interface.

All LLM providers must implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Response from LLM provider.

    Attributes:
        content: Response text content
        model: Model used for generation
        provider: Provider name
        tokens_used: Total number of tokens used (if available)
        input_tokens: Number of input/prompt tokens (if available)
        output_tokens: Number of output/completion tokens (if available)
    """

    content: str
    model: str
    provider: str
    tokens_used: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class ProviderStats:
    """Statistics about LLM provider usage.

    Attributes:
        provider_name: Name of the provider
        configured: Whether the provider is configured with API key
        base_url: Base URL for API requests
        total_calls: Total number of API calls made
        total_tokens: Total tokens used
    """

    provider_name: str
    configured: bool
    base_url: str | None = None
    total_calls: int = 0
    total_tokens: int = 0


class LLMProvider(ABC):
    """Base class for LLM providers.

    All LLM providers (Anthropic, OpenAI, etc.) must inherit from this class
    and implement the required methods.
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the LLM provider.

        Args:
            api_key: API key for authentication
            base_url: Optional custom base URL
        """
        self.api_key = api_key
        self.base_url = base_url
        self._stats = ProviderStats(
            provider_name=self.provider_name,
            configured=self._is_configured(),
            base_url=base_url,
        )

    @abstractmethod
    def call(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Call the LLM with a prompt.

        Args:
            prompt: The prompt to send
            model: Model to use (defaults to provider default)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)

        Returns:
            LLMResponse with generated content

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider name.

        Returns:
            Provider name as string
        """
        raise NotImplementedError

    @abstractmethod
    def default_model(self) -> str:
        """Get the default model for this provider.

        Returns:
            Default model identifier
        """
        raise NotImplementedError

    def configured(self) -> bool:
        """Check if the provider is configured with valid credentials.

        Returns:
            True if configured, False otherwise
        """
        return self._stats.configured

    def stats(self) -> ProviderStats:
        """Get provider statistics.

        Returns:
            ProviderStats copy
        """
        return ProviderStats(
            provider_name=self._stats.provider_name,
            configured=self._stats.configured,
            base_url=self._stats.base_url,
            total_calls=self._stats.total_calls,
            total_tokens=self._stats.total_tokens,
        )

    def _is_configured(self) -> bool:
        """Check if provider has valid configuration.

        Returns:
            True if API key is set and valid
        """
        return bool(self.api_key and len(self.api_key) > 10)

    def _record_call(self, tokens_used: int | None = None) -> None:
        """Record an API call for statistics.

        Args:
            tokens_used: Number of tokens used (if available)
        """
        self._stats.total_calls += 1
        if tokens_used:
            self._stats.total_tokens += tokens_used

    async def acall(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Asynchronous call to the LLM.

        Default implementation runs the synchronous call in a thread pool.
        Subclasses should override for native async support.

        Args:
            prompt: The prompt to send
            model: Model to use (defaults to provider default)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)

        Returns:
            LLMResponse with generated content
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.call(prompt, model=model, max_tokens=max_tokens, temperature=temperature),
        )
