"""Gemini LLM Client - Implementation of LLMInterface for Google Gemini.

Uses Google's Gemini models via Vertex AI or Google AI Studio.
Recommended for production use with Google Cloud $300 credit.

Models available:
- gemini-1.5-pro: Best quality, ~$1.25/1M input, $5/1M output
- gemini-1.5-flash: Fast & cheap, ~$0.075/1M input, $0.30/1M output
- gemini-2.0-flash-exp: Latest experimental, free during preview
"""

import json
from typing import Any, AsyncIterator

import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse

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


class GeminiLLMClient(LLMInterface):
    """Google Gemini implementation of LLMInterface.

    Uses the google-generativeai SDK for accessing Gemini models.
    Supports both Google AI Studio (free tier) and Vertex AI (production).
    """

    # Role mapping from our enum to Gemini format
    ROLE_MAP = {
        MessageRole.SYSTEM: "user",  # Gemini handles system as first user message
        MessageRole.USER: "user",
        MessageRole.ASSISTANT: "model",
        MessageRole.TOOL: "function",
    }

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-pro",
    ) -> None:
        """Initialize the Gemini LLM client.

        Args:
            api_key: Google AI API key or Vertex AI credentials.
            model: Model name. Options:
                - gemini-1.5-pro (best quality)
                - gemini-1.5-flash (fast, cheap)
                - gemini-2.0-flash-exp (experimental)
        """
        genai.configure(api_key=api_key)
        self._model_name = model
        self._model = genai.GenerativeModel(model)
        logger.info("Gemini LLM client initialized", model=model)

    def _convert_messages(
        self, messages: list[Message]
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Convert messages to Gemini format.

        Gemini doesn't have a system role, so we extract it separately
        and pass it as system_instruction to the model.

        Args:
            messages: List of Message objects.

        Returns:
            Tuple of (history messages, system instruction).
        """
        system_instruction = None
        history = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Gemini uses system_instruction instead of system role
                system_instruction = msg.content
            else:
                history.append({
                    "role": self.ROLE_MAP.get(msg.role, "user"),
                    "parts": [msg.content],
                })

        return history, system_instruction

    def _create_model_with_system(self, system_instruction: str | None) -> genai.GenerativeModel:
        """Create a model instance with optional system instruction.

        Args:
            system_instruction: Optional system prompt.

        Returns:
            GenerativeModel instance.
        """
        if system_instruction:
            return genai.GenerativeModel(
                self._model_name,
                system_instruction=system_instruction,
            )
        return self._model

    async def generate(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Generate a response using Gemini.

        Args:
            messages: List of conversation messages.
            config: Optional configuration for this call.

        Returns:
            LLMResponse with the generated content.
        """
        config = config or LLMConfig()
        history, system_instruction = self._convert_messages(messages)

        logger.info(
            "Generating response",
            model=self._model_name,
            message_count=len(messages),
        )

        # Create model with system instruction if present
        model = self._create_model_with_system(system_instruction)

        # Configure generation settings
        generation_config = genai.GenerationConfig(
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
            top_p=config.top_p,
            stop_sequences=config.stop_sequences if config.stop_sequences else None,
        )

        # For single message, use generate_content directly
        # For multi-turn, create a chat
        if len(history) == 1:
            response = await model.generate_content_async(
                history[0]["parts"][0],
                generation_config=generation_config,
            )
        else:
            # Multi-turn conversation
            chat = model.start_chat(history=history[:-1] if len(history) > 1 else [])
            last_message = history[-1]["parts"][0] if history else ""
            response = await chat.send_message_async(
                last_message,
                generation_config=generation_config,
            )

        # Extract usage metadata
        usage_metadata = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0) if usage_metadata else 0
        completion_tokens = getattr(usage_metadata, "candidates_token_count", 0) if usage_metadata else 0

        logger.info(
            "Response generated",
            tokens_input=prompt_tokens,
            tokens_output=completion_tokens,
            finish_reason=response.candidates[0].finish_reason.name if response.candidates else "unknown",
        )

        return LLMResponse(
            content=response.text if response.text else "",
            model=self._model_name,
            finish_reason=response.candidates[0].finish_reason.name if response.candidates else None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            metadata={
                "safety_ratings": [
                    {"category": r.category.name, "probability": r.probability.name}
                    for r in response.candidates[0].safety_ratings
                ] if response.candidates else [],
            },
        )

    async def generate_stream(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response using Gemini.

        Args:
            messages: List of conversation messages.
            config: Optional configuration for this call.

        Yields:
            Chunks of the generated response.
        """
        config = config or LLMConfig()
        history, system_instruction = self._convert_messages(messages)

        logger.info("Starting streaming generation", model=self._model_name)

        model = self._create_model_with_system(system_instruction)

        generation_config = genai.GenerationConfig(
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
            top_p=config.top_p,
        )

        # For streaming, we need to handle it differently
        if len(history) == 1:
            response = await model.generate_content_async(
                history[0]["parts"][0],
                generation_config=generation_config,
                stream=True,
            )
        else:
            chat = model.start_chat(history=history[:-1] if len(history) > 1 else [])
            last_message = history[-1]["parts"][0] if history else ""
            response = await chat.send_message_async(
                last_message,
                generation_config=generation_config,
                stream=True,
            )

        async for chunk in response:
            if chunk.text:
                yield chunk.text

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
        history, system_instruction = self._convert_messages(messages)

        logger.info(
            "Generating with tools",
            model=self._model_name,
            tool_count=len(tools),
        )

        # Convert OpenAI-style tools to Gemini format
        gemini_tools = self._convert_tools_to_gemini(tools)

        # Create model with tools
        model = genai.GenerativeModel(
            self._model_name,
            system_instruction=system_instruction,
            tools=gemini_tools if gemini_tools else None,
        )

        generation_config = genai.GenerationConfig(
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
        )

        if len(history) == 1:
            response = await model.generate_content_async(
                history[0]["parts"][0],
                generation_config=generation_config,
            )
        else:
            chat = model.start_chat(history=history[:-1] if len(history) > 1 else [])
            last_message = history[-1]["parts"][0] if history else ""
            response = await chat.send_message_async(
                last_message,
                generation_config=generation_config,
            )

        # Extract tool calls if present
        tool_calls = []
        content = ""

        if response.candidates:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append(
                        ToolCall(
                            id=f"call_{fc.name}_{len(tool_calls)}",
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                        )
                    )
                elif hasattr(part, "text") and part.text:
                    content += part.text

        usage_metadata = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0) if usage_metadata else 0
        completion_tokens = getattr(usage_metadata, "candidates_token_count", 0) if usage_metadata else 0

        return LLMResponse(
            content=content,
            model=self._model_name,
            finish_reason=response.candidates[0].finish_reason.name if response.candidates else None,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    def _convert_tools_to_gemini(
        self, openai_tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        """Convert OpenAI-style tool definitions to Gemini format.

        Args:
            openai_tools: List of tools in OpenAI function calling format.

        Returns:
            List of tools in Gemini format, or None if empty.
        """
        if not openai_tools:
            return None

        gemini_functions = []
        for tool in openai_tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                gemini_functions.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {}),
                })

        return [{"function_declarations": gemini_functions}] if gemini_functions else None

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model_name

    @property
    def provider(self) -> str:
        """Return the provider name."""
        return "gemini"


# Convenience factory functions
def create_gemini_pro(api_key: str) -> GeminiLLMClient:
    """Create Gemini Pro client (best quality).

    Args:
        api_key: Google AI API key.

    Returns:
        GeminiLLMClient configured for Gemini 1.5 Pro.
    """
    return GeminiLLMClient(
        api_key=api_key,
        model="gemini-1.5-pro",
    )


def create_gemini_flash(api_key: str) -> GeminiLLMClient:
    """Create Gemini Flash client (fast, economical).

    Args:
        api_key: Google AI API key.

    Returns:
        GeminiLLMClient configured for Gemini 1.5 Flash.
    """
    return GeminiLLMClient(
        api_key=api_key,
        model="gemini-1.5-flash",
    )
