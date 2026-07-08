"""Langfuse-tracing decorator for any ``LLMInterface`` client.

Wraps an inner LLM client so each ``generate`` / ``generate_with_tools`` call
emits a Langfuse *generation* (model, prompt/response, token usage) nested under
the current trace span. Because each link of the fallback chain is wrapped
individually, the trace shows exactly which provider/model answered — and a
failed link appears as an errored span before the next one succeeds.

Tracing is fully optional: when Langfuse is not configured the wrapper simply
delegates to the inner client with zero overhead (the wrapper isn't even built).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.core.logging import get_logger
from app.core.observability import get_langfuse_client
from app.shared.interfaces.llm import LLMConfig, LLMInterface, LLMResponse, Message

logger = get_logger(__name__)


class TracedLLMClient(LLMInterface):
    """Decorator that records each LLM call as a Langfuse generation."""

    def __init__(self, inner: LLMInterface) -> None:
        self._inner = inner

    async def generate(
        self, messages: list[Message], config: LLMConfig | None = None
    ) -> LLMResponse:
        return await self._traced(messages, config, lambda: self._inner.generate(messages, config))

    async def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        return await self._traced(
            messages, config, lambda: self._inner.generate_with_tools(messages, tools, config)
        )

    async def generate_stream(  # type: ignore[override,misc]  # async generator vs ABC coroutine
        self, messages: list[Message], config: LLMConfig | None = None
    ) -> AsyncIterator[str]:
        # Streaming is passed through untraced (spans can't wrap a live stream cleanly).
        async for chunk in self._inner.generate_stream(messages, config):  # type: ignore[attr-defined]
            yield chunk

    async def _traced(
        self,
        messages: list[Message],
        config: LLMConfig | None,
        call: Callable[[], Awaitable[LLMResponse]],
    ) -> LLMResponse:
        client = get_langfuse_client()
        if client is None:
            return await call()

        with client.start_as_current_generation(
            name=f"{self._inner.provider}:{self._inner.model_name}",
            model=self._inner.model_name,
            input=_to_input(messages),
            model_parameters=_to_params(config),
        ) as generation:
            response = await call()  # may raise -> the context records the error and re-raises
            generation.update(
                output=_to_output(response),
                usage_details={
                    "input": response.prompt_tokens,
                    "output": response.completion_tokens,
                    "total": response.total_tokens,
                },
            )
            return response

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    @property
    def provider(self) -> str:
        return self._inner.provider


def _to_input(messages: list[Message]) -> list[dict[str, str]]:
    return [{"role": m.role.value, "content": m.content} for m in messages]


def _to_output(response: LLMResponse) -> Any:
    if response.tool_calls:
        return {
            "content": response.content,
            "tool_calls": [
                {"name": tc.name, "arguments": tc.arguments} for tc in response.tool_calls
            ],
        }
    return response.content


def _to_params(config: LLMConfig | None) -> dict[str, Any]:
    if config is None:
        return {}
    return {"temperature": config.temperature, "max_tokens": config.max_tokens}
