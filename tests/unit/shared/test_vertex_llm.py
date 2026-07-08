"""Unit tests for the Vertex LLM client (google-genai client injected)."""

from types import SimpleNamespace
from typing import Any

from app.agents.tools.transaction_tools import TRANSACTION_TOOL_SCHEMAS
from app.shared.clients.vertex_llm import VertexLLMClient
from app.shared.interfaces.llm import Message, MessageRole


class _FakeModels:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self._response


class FakeGenaiClient:
    def __init__(self, response: Any) -> None:
        self.aio = SimpleNamespace(models=_FakeModels(response))


def _client(response: Any) -> tuple[VertexLLMClient, FakeGenaiClient]:
    fake = FakeGenaiClient(response)
    client = VertexLLMClient(
        project="p", location="us-central1", model="gemini-2.0-flash", client=fake
    )
    return client, fake


def _text_response(text: str, usage: Any = None) -> SimpleNamespace:
    """Build a Gemini-like response whose text lives in candidate parts."""
    part = SimpleNamespace(text=text, function_call=None)
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[part]),
        finish_reason=SimpleNamespace(name="STOP"),
    )
    return SimpleNamespace(candidates=[candidate], function_calls=None, usage_metadata=usage)


class TestGenerate:
    async def test_returns_text_and_uses_system_instruction(self) -> None:
        response = _text_response("Hola!")
        client, fake = _client(response)

        result = await client.generate(
            [Message(role=MessageRole.SYSTEM, content="eres util"),
             Message(role=MessageRole.USER, content="hola")]
        )

        assert result.content == "Hola!"
        # The system message became the system instruction (not a content turn).
        config = fake.aio.models.calls[-1]["config"]
        assert config.system_instruction == "eres util"
        assert len(fake.aio.models.calls[-1]["contents"]) == 1  # only the user turn


class TestGenerateWithTools:
    async def test_parses_function_calls_as_dict_args(self) -> None:
        fc = SimpleNamespace(
            name="register_transaction",
            args={"amount": 50, "description": "pizza", "transaction_type": "expense"},
        )
        response = SimpleNamespace(
            text="",
            function_calls=[fc],
            usage_metadata=SimpleNamespace(
                prompt_token_count=10, candidates_token_count=5, total_token_count=15
            ),
        )
        client, _ = _client(response)

        result = await client.generate_with_tools(
            [Message(role=MessageRole.USER, content="gasté 50 en pizza")],
            TRANSACTION_TOOL_SCHEMAS,
        )

        assert len(result.tool_calls) == 1
        call = result.tool_calls[0]
        assert call.name == "register_transaction"
        assert isinstance(call.arguments, dict)  # Gemini returns args as a dict
        assert call.arguments["amount"] == 50
        assert result.total_tokens == 15

    async def test_no_function_calls_returns_text(self) -> None:
        response = _text_response("¿Cuánto gastaste?")
        client, _ = _client(response)

        result = await client.generate_with_tools(
            [Message(role=MessageRole.USER, content="quiero registrar")], TRANSACTION_TOOL_SCHEMAS
        )

        assert result.tool_calls == []
        assert result.content == "¿Cuánto gastaste?"


class TestProperties:
    def test_properties(self) -> None:
        client, _ = _client(SimpleNamespace(text="", function_calls=None, usage_metadata=None))
        assert client.provider == "vertex"
        assert client.model_name == "gemini-2.0-flash"
