"""LLM client for unified access to different providers."""

from typing import AsyncGenerator, Optional

from ..config.loader import load_config
from ..config.models import ModelConfig
from ..logging.structured import get_logger
from .providers import get_provider

logger = get_logger(__name__)


class LLMClient:
    """Unified LLM client for accessing different providers."""

    def __init__(
        self, model_config: Optional[ModelConfig] = None, model_name: Optional[str] = None
    ):
        """Initialize LLM client.

        Args:
            model_config: Direct model configuration
            model_name: Name of model from configuration
        """
        if model_config:
            self.config = model_config
        elif model_name:
            # Load from configuration
            deployment_config = load_config("deployment")
            pipeline_config = deployment_config.pipeline

            if model_name not in pipeline_config.models:
                raise ValueError(f"Model {model_name} not found in configuration")

            self.config = pipeline_config.models[model_name]
        else:
            # Use default model for research stage
            deployment_config = load_config("deployment")
            pipeline_config = deployment_config.pipeline
            model_name = pipeline_config.default_models.get("research", "ollama-mixtral")
            self.config = pipeline_config.models[model_name]

        self.provider = get_provider(self.config)
        logger.info(
            "Initialized LLM client",
            provider=self.config.provider,
            model=self.config.model_name,
        )

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """Generate text from prompt.

        Args:
            prompt: User prompt
            system: System prompt
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text
        """
        generation_params = {}
        if system:
            generation_params["system"] = system
        if temperature is not None:
            generation_params["temperature"] = temperature
        if max_tokens is not None:
            generation_params["max_tokens"] = max_tokens

        generation_params.update(kwargs)

        return await self.provider.generate(prompt, **generation_params)

    async def stream_generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Stream generate text from prompt.

        Args:
            prompt: User prompt
            system: System prompt
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Yields:
            Generated text chunks
        """
        generation_params = {}
        if system:
            generation_params["system"] = system
        if temperature is not None:
            generation_params["temperature"] = temperature
        if max_tokens is not None:
            generation_params["max_tokens"] = max_tokens

        generation_params.update(kwargs)

        async for chunk in self.provider.stream_generate(prompt, **generation_params):
            yield chunk
