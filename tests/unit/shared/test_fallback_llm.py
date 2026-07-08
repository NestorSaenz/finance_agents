"""Unit tests for the fallback LLM client (chain failover)."""

import pytest

from app.shared.clients.fallback_llm import FallbackLLMClient
from app.shared.interfaces.llm import Message, MessageRole
from tests.fakes import FakeLLM


class FailingLLM(FakeLLM):
    """An LLM whose calls always raise, to trigger failover."""

    def __init__(self, label: str = "boom") -> None:
        super().__init__("")
        self.label = label
        self.calls = 0

    async def generate(self, messages, config=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise RuntimeError(self.label)

    async def generate_with_tools(self, messages, tools, config=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise RuntimeError(self.label)


def _msgs() -> list[Message]:
    return [Message(role=MessageRole.USER, content="hola")]


class TestFallbackChain:
    async def test_uses_primary_when_it_succeeds(self) -> None:
        primary = FakeLLM("primary-response")
        secondary = FailingLLM("should-not-run")
        client = FallbackLLMClient([primary, secondary])

        result = await client.generate(_msgs())

        assert result.content == "primary-response"
        assert secondary.calls == 0  # never reached

    async def test_falls_back_when_primary_fails(self) -> None:
        primary = FailingLLM("primary-down")
        secondary = FakeLLM("rescued")
        client = FallbackLLMClient([primary, secondary])

        result = await client.generate(_msgs())

        assert result.content == "rescued"
        assert primary.calls == 1  # tried first

    async def test_falls_through_multiple_failures(self) -> None:
        first = FailingLLM("a")
        second = FailingLLM("b")
        third = FakeLLM("third-ok")
        client = FallbackLLMClient([first, second, third])

        result = await client.generate(_msgs())

        assert result.content == "third-ok"
        assert first.calls == 1
        assert second.calls == 1

    async def test_raises_last_error_when_all_fail(self) -> None:
        client = FallbackLLMClient([FailingLLM("x"), FailingLLM("last-error")])
        with pytest.raises(RuntimeError, match="last-error"):
            await client.generate(_msgs())

    async def test_failover_applies_to_tools(self) -> None:
        primary = FailingLLM("tools-down")
        secondary = FakeLLM("tool-rescue")
        client = FallbackLLMClient([primary, secondary])

        result = await client.generate_with_tools(_msgs(), tools=[])

        assert result.content == "tool-rescue"

    def test_requires_at_least_one_client(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            FallbackLLMClient([])

    def test_properties_reflect_primary(self) -> None:
        client = FallbackLLMClient([FakeLLM("x"), FakeLLM("y")])
        assert client.provider == "fake"
        assert client.model_name == "fake-model"
