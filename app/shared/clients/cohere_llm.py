"""Cohere LLM Client - Implementation of LLMInterface for Cohere.

Uses Cohere's Command R+ model for text generation.
"""

from typing import Any, AsyncIterator

import cohere

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


class CohereLLMClient(LLMInterface):
    """Cohere implementation of LLMInterface.

    Uses Cohere's Command R+ for text generation with support
    for conversation, streaming, and tool calling.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "command-r-plus",
    ) -> None:
        """Initialize the Cohere LLM client.

        Args:
            api_key: Cohere API key.
            model: Model name (default: command-r-plus).
        """
        self._client = cohere.AsyncClient(api_key=api_key)
        self._model = model
        logger.info("Cohere LLM client initialized", model=model)

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict]]:
        """Convert messages to Cohere format.

        Args:
            messages: List of Message objects.

        Returns:
            Tuple of (system_prompt, chat_history).
        """
        system_prompt = None
        chat_history = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
            elif msg.role == MessageRole.USER:
                chat_history.append({"role": "USER", "message": msg.content})
            elif msg.role == MessageRole.ASSISTANT:
                chat_history.append({"role": "CHATBOT", "message": msg.content})

        return system_prompt, chat_history

    async def generate(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Generate a response using Cohere Command R+.

        Args:
            messages: List of conversation messages.
            config: Optional configuration for this call.

        Returns:
            LLMResponse with the generated content.
        """
        config = config or LLMConfig()
        system_prompt, chat_history = self._convert_messages(messages[:-1])

        # Last message is the current user input
        user_message = messages[-1].content if messages else ""

        logger.info(
            "Generating response",
            model=self._model,
            message_length=len(user_message),
        )

        response = await self._client.chat(
            model=self._model,
            message=user_message,
            chat_history=chat_history if chat_history else None,
            preamble=system_prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

        logger.info(
            "Response generated",
            tokens_input=response.meta.tokens.input_tokens if response.meta else 0,
            tokens_output=response.meta.tokens.output_tokens if response.meta else 0,
        )

        return LLMResponse(
            content=response.text,
            model=self._model,
            finish_reason=response.finish_reason,
            prompt_tokens=response.meta.tokens.input_tokens if response.meta else 0,
            completion_tokens=response.meta.tokens.output_tokens if response.meta else 0,
            total_tokens=(
                (response.meta.tokens.input_tokens + response.meta.tokens.output_tokens)
                if response.meta
                else 0
            ),
            metadata={"generation_id": response.generation_id},
        )

    async def generate_stream(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response using Cohere.

        Args:
            messages: List of conversation messages.
            config: Optional configuration for this call.

        Yields:
            Chunks of the generated response.
        """
        config = config or LLMConfig()
        system_prompt, chat_history = self._convert_messages(messages[:-1])
        user_message = messages[-1].content if messages else ""

        logger.info("Starting streaming generation", model=self._model)

        async for event in self._client.chat_stream(
            model=self._model,
            message=user_message,
            chat_history=chat_history if chat_history else None,
            preamble=system_prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        ):
            if event.event_type == "text-generation":
                yield event.text

    async def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Generate a response with tool calling support.

        Args:
            messages: List of conversation messages.
            tools: List of tool definitions.
            config: Optional configuration for this call.

        Returns:
            LLMResponse with content or tool_calls.
        """
        config = config or LLMConfig()
        system_prompt, chat_history = self._convert_messages(messages[:-1])
        user_message = messages[-1].content if messages else ""

        # Convert tools to Cohere format
        cohere_tools = self._convert_tools_to_cohere_format(tools)

        logger.info(
            "Generating with tools",
            model=self._model,
            tool_count=len(tools),
        )

        response = await self._client.chat(
            model=self._model,
            message=user_message,
            chat_history=chat_history if chat_history else None,
            preamble=system_prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            tools=cohere_tools if cohere_tools else None,
        )

        # Convert tool calls if present
        tool_calls = []
        if response.tool_calls:
            for tc in response.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.name,  # Cohere doesn't provide IDs
                        name=tc.name,
                        arguments=tc.parameters,
                    )
                )

        return LLMResponse(
            content=response.text or "",
            model=self._model,
            finish_reason=response.finish_reason,
            tool_calls=tool_calls,
            prompt_tokens=response.meta.tokens.input_tokens if response.meta else 0,
            completion_tokens=response.meta.tokens.output_tokens if response.meta else 0,
            total_tokens=(
                (response.meta.tokens.input_tokens + response.meta.tokens.output_tokens)
                if response.meta
                else 0
            ),
        )

    def _convert_tools_to_cohere_format(
        self,
        tools: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert OpenAI-style tools to Cohere format.

        Args:
            tools: List of tools in OpenAI format.

        Returns:
            List of tools in Cohere format.
        """
        cohere_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                cohere_tools.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "parameter_definitions": self._convert_parameters(
                            func.get("parameters", {})
                        ),
                    }
                )
        return cohere_tools

    def _convert_parameters(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert JSON Schema parameters to Cohere format."""
        if not params.get("properties"):
            return {}

        definitions = {}
        required = params.get("required", [])

        for name, prop in params["properties"].items():
            definitions[name] = {
                "type": prop.get("type", "string"),
                "description": prop.get("description", ""),
                "required": name in required,
            }

        return definitions

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model

    @property
    def provider(self) -> str:
        """Return the provider name."""
        return "cohere"
