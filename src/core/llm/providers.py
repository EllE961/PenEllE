"""LLM provider implementations."""

from abc import ABC, abstractmethod
from typing import AsyncGenerator

from ollama import AsyncClient as OllamaAsyncClient

from ..config.models import ModelConfig, ProviderType
from ..logging.structured import get_logger

logger = get_logger(__name__)


class BaseLLMProvider(ABC):
    """Base class for LLM providers."""

    def __init__(self, config: ModelConfig):
        """Initialize provider with configuration."""
        self.config = config

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        pass

    @abstractmethod
    async def stream_generate(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream generate text from prompt."""
        pass


class OllamaProvider(BaseLLMProvider):
    """Ollama provider implementation."""

    def __init__(self, config: ModelConfig):
        """Initialize Ollama provider."""
        super().__init__(config)
        base_url = config.api_base or "http://localhost:11434"
        self.client = OllamaAsyncClient(host=base_url)
        logger.info(
            "Initialized Ollama provider",
            model=config.model_name,
            base_url=base_url,
        )

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using Ollama."""
        try:
            # Merge config parameters with kwargs
            params = {
                "model": self.config.model_name,
                "prompt": prompt,
                "options": {
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "top_p": kwargs.get("top_p", self.config.top_p),
                    "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
                },
            }

            # Add system prompt if provided
            if "system" in kwargs:
                params["system"] = kwargs["system"]

            logger.debug("Generating with Ollama", model=self.config.model_name)
            response = await self.client.generate(**params)

            return response["response"]
        except Exception as e:
            logger.error(
                "Ollama generation failed",
                model=self.config.model_name,
                error=str(e),
            )
            raise

    async def stream_generate(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream generate text using Ollama."""
        try:
            params = {
                "model": self.config.model_name,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "top_p": kwargs.get("top_p", self.config.top_p),
                    "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
                },
            }

            if "system" in kwargs:
                params["system"] = kwargs["system"]

            async for part in await self.client.generate(**params):
                if "response" in part:
                    yield part["response"]
        except Exception as e:
            logger.error(
                "Ollama stream generation failed",
                model=self.config.model_name,
                error=str(e),
            )
            raise


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider implementation (placeholder)."""

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using OpenAI."""
        raise NotImplementedError("OpenAI provider not implemented yet")

    async def stream_generate(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream generate text using OpenAI."""
        raise NotImplementedError("OpenAI provider not implemented yet")


class AnthropicProvider(BaseLLMProvider):
    """Anthropic provider implementation (placeholder)."""

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using Anthropic."""
        raise NotImplementedError("Anthropic provider not implemented yet")

    async def stream_generate(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream generate text using Anthropic."""
        raise NotImplementedError("Anthropic provider not implemented yet")


def get_provider(config: ModelConfig) -> BaseLLMProvider:
    """Get LLM provider instance based on configuration."""
    providers = {
        ProviderType.OLLAMA: OllamaProvider,
        ProviderType.OPENAI: OpenAIProvider,
        ProviderType.ANTHROPIC: AnthropicProvider,
        # Add other providers as needed
    }

    provider_class = providers.get(config.provider)
    if not provider_class:
        raise ValueError(f"Unsupported provider: {config.provider}")

    return provider_class(config)
