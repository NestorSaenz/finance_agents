"""LLM Interface - Abstract contract for Language Model providers.

Implementations:
- CohereLLMClient: Cohere Command R+
- OpenAILLMClient: GPT-4, GPT-3.5
- AnthropicLLMClient: Claude
- OllamaLLMClient: Local models (Llama, Mistral)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


class MessageRole(str, Enum):
    """Role of a message in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """A message in a conversation."""

    role: MessageRole
    content: str
    name: str | None = None  # For tool messages
    tool_call_id: str | None = None  # For tool responses


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from an LLM."""

    content: str
    model: str
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    # Usage statistics
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Provider-specific metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMConfig:
    """Configuration for LLM calls."""

    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 1.0
    stop_sequences: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)


class LLMInterface(ABC):
    """Abstract interface for Language Model providers.

    This interface allows swapping LLM providers without changing
    the business logic. All LLM clients must implement this contract.

    Example usage:
        ```python
        # In dependencies.py
        def get_llm_client() -> LLMInterface:
            return CohereLLMClient(api_key=settings.COHERE_API_KEY)

        # In service
        class ChatService:
            def __init__(self, llm: LLMInterface):
                self.llm = llm

            async def chat(self, message: str) -> str:
                response = await self.llm.generate([
                    Message(role=MessageRole.USER, content=message)
                ])
                return response.content
        ```
    """

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            messages: List of conversation messages.
            config: Optional configuration for this call.

        Returns:
            LLMResponse with the generated content.

        Raises:
            LLMError: If the LLM call fails.
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the LLM.

        Args:
            messages: List of conversation messages.
            config: Optional configuration for this call.

        Yields:
            Chunks of the generated response.

        Raises:
            LLMError: If the LLM call fails.
        """
        pass

    @abstractmethod
    async def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Generate a response with tool/function calling support.

        Args:
            messages: List of conversation messages.
            tools: List of tool definitions (OpenAI function format).
            config: Optional configuration for this call.

        Returns:
            LLMResponse with content or tool_calls.

        Raises:
            LLMError: If the LLM call fails.
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the name of the model being used."""
        pass

    @property
    @abstractmethod
    def provider(self) -> str:
        """Return the provider name (e.g., 'cohere', 'openai')."""
        pass
