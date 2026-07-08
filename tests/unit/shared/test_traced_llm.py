"""Unit tests for the Langfuse-tracing LLM decorator."""

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.shared.clients.traced_llm import TracedLLMClient
from app.shared.interfaces.llm import (
    LLMConfig,
    LLMInterface,
    LLMResponse,
    Message,
    MessageRole,
    ToolCall,
)


class InnerLLM(LLMInterface):
    """Configurable inner client: returns a fixed response or raises."""

    def __init__(
        self, response: LLMResponse | None = None, error: Exception | None = None
    ) -> None:
        self._response = response or LLMResponse(
            content="hola", model="gemini-2.5-flash-lite",
            prompt_tokens=100, completion_tokens=20, total_tokens=120,
        )
        self._error = error

    async def generate(
        self, messages: list[Message], config: LLMConfig | None = None
    ) -> LLMResponse:
        if self._error:
            raise self._error
        return self._response

    async def generate_with_tools(
        self, messages: list[Message], tools: list[dict[str, Any]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        if self._error:
            raise self._error
        return self._response

    async def generate_stream(
        self, messages: list[Message], config: LLMConfig | None = None
    ) -> AsyncIterator[str]:
        yield self._response.content

    @property
    def model_name(self) -> str:
        return "gemini-2.5-flash-lite"

    @property
    def provider(self) -> str:
        return "vertex"


class FakeGeneration:
    def __init__(self) -> None:
        self.update_kwargs: dict[str, Any] = {}

    def update(self, **kwargs: Any) -> None:
        self.update_kwargs = kwargs


class FakeGenerationCtx:
    def __init__(self, gen: FakeGeneration, spy: dict[str, Any], kwargs: dict[str, Any]) -> None:
        self._gen, self._spy, self._kwargs = gen, spy, kwargs

    def __enter__(self) -> FakeGeneration:
        self._spy["start_kwargs"] = self._kwargs
        return self._gen

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        self._spy["exit_exc_type"] = exc_type
        return False  # never suppress: exceptions must reach the fallback chain


class FakeLangfuseClient:
    def __init__(self) -> None:
        self.spy: dict[str, Any] = {}
        self.generation = FakeGeneration()

    def start_as_current_generation(self, **kwargs: Any) -> FakeGenerationCtx:
        return FakeGenerationCtx(self.generation, self.spy, kwargs)


MESSAGES = [Message(role=MessageRole.USER, content="hola")]


class TestDisabled:
    async def test_delegates_without_span(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.shared.clients.traced_llm.get_langfuse_client", lambda: None
        )
        client = TracedLLMClient(InnerLLM())

        result = await client.generate(MESSAGES)

        assert result.content == "hola"


class TestEnabled:
    def _use_fake(self, monkeypatch: pytest.MonkeyPatch) -> FakeLangfuseClient:
        fake = FakeLangfuseClient()
        monkeypatch.setattr(
            "app.shared.clients.traced_llm.get_langfuse_client", lambda: fake
        )
        return fake

    async def test_records_model_input_and_usage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = self._use_fake(monkeypatch)
        client = TracedLLMClient(InnerLLM())

        result = await client.generate(MESSAGES, LLMConfig(temperature=0.3, max_tokens=200))

        assert result.content == "hola"
        assert fake.spy["start_kwargs"]["name"] == "vertex:gemini-2.5-flash-lite"
        assert fake.spy["start_kwargs"]["model"] == "gemini-2.5-flash-lite"
        assert fake.spy["start_kwargs"]["input"] == [{"role": "user", "content": "hola"}]
        assert fake.spy["start_kwargs"]["model_parameters"] == {
            "temperature": 0.3, "max_tokens": 200,
        }
        assert fake.generation.update_kwargs["output"] == "hola"
        assert fake.generation.update_kwargs["usage_details"] == {
            "input": 100, "output": 20, "total": 120,
        }

    async def test_tool_output_includes_tool_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = self._use_fake(monkeypatch)
        response = LLMResponse(
            content="", model="gemini-2.5-flash-lite",
            tool_calls=[ToolCall(id="c1", name="register_transaction", arguments={"amount": 50})],
        )
        client = TracedLLMClient(InnerLLM(response=response))

        await client.generate_with_tools(MESSAGES, tools=[{"function": {"name": "x"}}])

        output = fake.generation.update_kwargs["output"]
        assert output["tool_calls"] == [
            {"name": "register_transaction", "arguments": {"amount": 50}}
        ]

    async def test_error_propagates_and_span_closes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = self._use_fake(monkeypatch)
        client = TracedLLMClient(InnerLLM(error=RuntimeError("vertex down")))

        with pytest.raises(RuntimeError, match="vertex down"):
            await client.generate(MESSAGES)

        assert fake.spy["exit_exc_type"] is RuntimeError  # span saw the failure
