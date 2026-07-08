"""Vertex AI LLM client (Google Gemini).

Implements ``LLMInterface`` using the ``google-genai`` SDK against Vertex AI,
billed to the GCP project (Vertex credits). Auth is via Application Default
Credentials (ADC) — no API key.

Gemini returns tool-call ``args`` already as a dict, so tool calling is cleaner
than the OpenAI/Groq path (no JSON-string parsing needed).
"""

from collections.abc import AsyncIterator
from typing import Any

from google.genai import types

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


class VertexLLMClient(LLMInterface):
    """LLM client backed by Vertex AI Gemini models."""

    def __init__(
        self,
        project: str,
        location: str,
        model: str,
        client: Any | None = None,
    ) -> None:
        self._project = project
        self._location = location
        self._model = model
        self._client = client or self._build_client(project, location)

    @staticmethod
    def _build_client(project: str, location: str) -> Any:
        from google import genai  # lazy import: only needed for real usage

        return genai.Client(vertexai=True, project=project, location=location)

    async def generate(
        self, messages: list[Message], config: LLMConfig | None = None
    ) -> LLMResponse:
        config = config or LLMConfig()
        system, contents = _to_gemini(messages)
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=_gen_config(system, config),
        )
        return _to_llm_response(response, self._model)

    async def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        config = config or LLMConfig()
        system, contents = _to_gemini(messages)
        gemini_tools = _to_gemini_tools(tools)
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=_gen_config(system, config, tools=gemini_tools),
        )
        return _to_llm_response(response, self._model)

    async def generate_stream(  # type: ignore[override,misc]  # async generator vs ABC coroutine
        self, messages: list[Message], config: LLMConfig | None = None
    ) -> AsyncIterator[str]:
        config = config or LLMConfig()
        system, contents = _to_gemini(messages)
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=_gen_config(system, config),
        )
        async for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield text

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "vertex"


# =============================================================================
# Conversion helpers (FinanceGPT Message <-> google-genai types)
# =============================================================================


def _to_gemini(messages: list[Message]) -> tuple[str | None, list[types.Content]]:
    """Split messages into a system instruction and Gemini contents.

    Tool results are flattened into user-visible text so the conversation works
    with our simple Message list without the strict function-response protocol.
    """
    system_parts = [m.content for m in messages if m.role == MessageRole.SYSTEM]
    contents: list[types.Content] = []
    for message in messages:
        if message.role == MessageRole.SYSTEM:
            continue
        if message.role == MessageRole.TOOL:
            text = f"[Resultado de la herramienta {message.name}]: {message.content}"
            role = "user"
        elif message.role == MessageRole.ASSISTANT:
            text = message.content
            role = "model"
        else:
            text = message.content
            role = "user"
        parts = [types.Part.from_text(text=text)]
        # Attach any images (vision) as inline byte parts alongside the text.
        for image in message.images or []:
            parts.append(
                types.Part.from_bytes(data=image.data, mime_type=image.mime_type)
            )
        contents.append(types.Content(role=role, parts=parts))
    system = "\n".join(system_parts) if system_parts else None
    return system, contents


def _to_gemini_tools(tools: list[dict[str, Any]]) -> list[Any] | None:
    """Convert OpenAI-style tool schemas to Gemini function declarations."""
    if not tools:
        return None
    declarations = [
        types.FunctionDeclaration(
            name=tool["function"]["name"],
            description=tool["function"].get("description", ""),
            parameters_json_schema=tool["function"].get("parameters", {}),
        )
        for tool in tools
    ]
    return [types.Tool(function_declarations=declarations)]


def _gen_config(
    system: str | None,
    config: LLMConfig,
    tools: list[Any] | None = None,
) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system,
        temperature=config.temperature,
        max_output_tokens=config.max_tokens,
        tools=tools,
        # Disable "thinking" for these structured tasks (classification, tools,
        # short generation): it would consume the small token budget. Supported
        # by gemini-2.5-flash / flash-lite.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )


def _to_llm_response(response: Any, model: str) -> LLMResponse:
    tool_calls = [
        ToolCall(id=f"call_{i}", name=fc.name, arguments=dict(fc.args or {}))
        for i, fc in enumerate(response.function_calls or [])
    ]

    content = _extract_text(response)

    usage = getattr(response, "usage_metadata", None)
    return LLMResponse(
        content=content,
        model=model,
        finish_reason=_finish_reason(response),
        tool_calls=tool_calls,
        prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
        completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        total_tokens=getattr(usage, "total_token_count", 0) or 0,
    )


def _extract_text(response: Any) -> str:
    """Concatenate the text parts of the response.

    Reading ``response.text`` warns when the response also has non-text parts
    (e.g. a function_call); iterating the candidate parts avoids that noise while
    yielding the same text (tool calls are read separately via function_calls).
    """
    chunks: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)
    return "".join(chunks)


def _finish_reason(response: Any) -> str | None:
    """Read the model's actual finish reason (e.g. STOP, MAX_TOKENS, SAFETY)."""
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return None
    return getattr(reason, "name", str(reason))
