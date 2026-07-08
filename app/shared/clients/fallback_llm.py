"""Fallback LLM client.

Wraps an ordered list of LLM clients and tries them in turn: if one fails
(timeout, rate limit, overload, provider outage), the next one is used. This
gives both a same-provider rescue (e.g. another Gemini model when one is
overloaded) and cross-provider redundancy (e.g. Groq when Vertex is down).

It sits behind ``LLMInterface``, so agents are unaware of it. Each agent still
has its own deterministic fallback if the whole chain fails.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.core.logging import get_logger
from app.shared.interfaces.llm import LLMConfig, LLMInterface, LLMResponse, Message

logger = get_logger(__name__)


class FallbackLLMClient(LLMInterface):
    """Tries a chain of LLM clients in order until one succeeds."""

    def __init__(self, clients: list[LLMInterface]) -> None:
        if not clients:
            raise ValueError("FallbackLLMClient requires at least one client")
        self._clients = clients

    async def _run(self, call: Callable[[LLMInterface], Awaitable[LLMResponse]]) -> LLMResponse:
        last_error: Exception | None = None
        for index, client in enumerate(self._clients):
            try:
                return await call(client)
            except Exception as e:  # noqa: BLE001 - failover boundary: try the next client.
                last_error = e
                logger.warning(
                    "LLM client failed, trying fallback",
                    position=index,
                    provider=client.provider,
                    model=client.model_name,
                    error=str(e),
                )
        assert last_error is not None
        raise last_error

    async def generate(
        self, messages: list[Message], config: LLMConfig | None = None
    ) -> LLMResponse:
        return await self._run(lambda client: client.generate(messages, config))

    async def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        return await self._run(
            lambda client: client.generate_with_tools(messages, tools, config)
        )

    async def generate_stream(  # type: ignore[override,misc]  # async generator vs ABC coroutine
        self, messages: list[Message], config: LLMConfig | None = None
    ) -> AsyncIterator[str]:
        # Streaming can't fail over mid-stream; use the primary client.
        async for chunk in self._clients[0].generate_stream(messages, config):  # type: ignore[attr-defined]
            yield chunk

    @property
    def model_name(self) -> str:
        return self._clients[0].model_name

    @property
    def provider(self) -> str:
        return self._clients[0].provider
