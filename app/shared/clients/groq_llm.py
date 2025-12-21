"""Groq LLM Client - Implementation of LLMInterface for Groq.

Uses Groq's ultra-fast inference for Llama models.
Free tier limits (as of 2024):
- llama-3.3-70b-versatile: 1K req/day, 100K tokens/day
- llama-3.1-8b-instant: 14.4K req/day, 500K tokens/day
"""

from typing import Any, AsyncIterator

from groq import AsyncGroq

from app.core.logging import get_logger
from app.shared.interfaces.llm import (
    LLMConfig,
    LLMInterface,
    LLMResponse,
    Message,
    MessageRole,
    ToolCall,
)

logger = get_logger(__name__)


class GroqLLMClient(LLMInterface):
    """Groq implementation of LLMInterface.

    Uses Groq's inference API for ultra-fast Llama model responses.
    Supports both simple and complex models for the hybrid architecture.
    """

    # Role mapping from our enum to Groq format
    ROLE_MAP = {
        MessageRole.SYSTEM: "system",
        MessageRole.USER: "user",
        MessageRole.ASSISTANT: "assistant",
        MessageRole.TOOL: "tool",
    }

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
    ) -> None:
        """Initialize the Groq LLM client.

        Args:
            api_key: Groq API key.
            model: Model name. Options:
                - llama-3.3-70b-versatile (complex tasks)
                - llama-3.1-8b-instant (simple tasks, higher limits)
                - llama-3.1-70b-versatile (alternative)
        """
        self._client = AsyncGroq(api_key=api_key)
        self._model = model
        logger.info("Groq LLM client initialized", model=model)

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, str]]:
        """Convert messages to Groq/OpenAI format.

        Args:
            messages: List of Message objects.

        Returns:
            List of message dicts in Groq format.
        """
        return [
            {
                "role": self.ROLE_MAP.get(msg.role, "user"),
                "content": msg.content,
            }
            for msg in messages
        ]

    async def generate(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Generate a response using Groq.

        Args:
            messages: List of conversation messages.
            config: Optional configuration for this call.

        Returns:
            LLMResponse with the generated content.
        """
        config = config or LLMConfig()
        groq_messages = self._convert_messages(messages)

        logger.info(
            "Generating response",
            model=self._model,
            message_count=len(messages),
        )

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=groq_messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
            stop=config.stop_sequences if config.stop_sequences else None,
        )

        choice = response.choices[0]
        usage = response.usage

        logger.info(
            "Response generated",
            tokens_input=usage.prompt_tokens if usage else 0,
            tokens_output=usage.completion_tokens if usage else 0,
            finish_reason=choice.finish_reason,
        )

        return LLMResponse(
            content=choice.message.content or "",
            model=self._model,
            finish_reason=choice.finish_reason,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            metadata={
                "id": response.id,
                "created": response.created,
            },
        )

    async def generate_stream(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response using Groq.

        Args:
            messages: List of conversation messages.
            config: Optional configuration for this call.

        Yields:
            Chunks of the generated response.
        """
        config = config or LLMConfig()
        groq_messages = self._convert_messages(messages)

        logger.info("Starting streaming generation", model=self._model)

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=groq_messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Generate a response with tool calling support.

        Args:
            messages: List of conversation messages.
            tools: List of tool definitions (OpenAI function format).
            config: Optional configuration for this call.

        Returns:
            LLMResponse with content or tool_calls.
        """
        config = config or LLMConfig()
        groq_messages = self._convert_messages(messages)

        logger.info(
            "Generating with tools",
            model=self._model,
            tool_count=len(tools),
        )

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=groq_messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
        )

        choice = response.choices[0]
        usage = response.usage

        # Extract tool calls if present
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,  # JSON string
                    )
                )

        return LLMResponse(
            content=choice.message.content or "",
            model=self._model,
            finish_reason=choice.finish_reason,
            tool_calls=tool_calls,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model

    @property
    def provider(self) -> str:
        """Return the provider name."""
        return "groq"


# Convenience factory functions for the hybrid architecture
def create_simple_llm(api_key: str) -> GroqLLMClient:
    """Create LLM client for Simple Path (high limits, fast).

    Args:
        api_key: Groq API key.

    Returns:
        GroqLLMClient configured for simple tasks.
    """
    return GroqLLMClient(
        api_key=api_key,
        model="llama-3.1-8b-instant",  # 14.4K req/day
    )


def create_complex_llm(api_key: str) -> GroqLLMClient:
    """Create LLM client for Complex Path (powerful model).

    Args:
        api_key: Groq API key.

    Returns:
        GroqLLMClient configured for complex tasks.
    """
    return GroqLLMClient(
        api_key=api_key,
        model="llama-3.3-70b-versatile",  # 1K req/day, pero más capaz
    )
