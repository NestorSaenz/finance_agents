"""Integration tests for the /chat endpoint wired to the multiagent graph."""

import asyncio
import base64
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.agents.graph import create_financegpt_graph, get_compiled_graph
from app.api.routes.chat import get_ingestion_service
from app.main import app
from app.src.chat.dependencies import get_chat_memory_service
from app.src.chat.interfaces import ChatMemoryServiceABC
from app.src.chat.models import ChatMessage
from app.src.memory.dependencies import get_memory_agent_service
from app.src.memory.interfaces import MemoryAgentServiceABC
from app.src.ratelimit.dependencies import get_rate_limit_service
from app.src.ratelimit.interfaces import RateLimitRepositoryABC, RateLimitServiceABC
from app.src.ratelimit.models import RateLimitBucket
from app.src.ratelimit.services.rate_limit_service import RateLimitService
from app.src.users.dependencies import get_user_profile_service
from app.src.users.interfaces import UserProfileServiceABC
from app.src.users.models import UserProfile, UserProfileUpdate
from tests.fakes import (
    FakeEmbeddingClient,
    FakeLLM,
    FakeRateLimitService,
    FakeToolkit,
    FakeVectorStore,
)

CHAT_URL = "/api/v1/chat"
FINAL_TEXT = "Tu gasto fue categorizado como restaurantes."


class FakeChatMemory(ChatMemoryServiceABC):
    """In-memory chat memory stub (no DB)."""

    def __init__(self) -> None:
        self.saved: list[tuple[str, str]] = []

    async def resolve_conversation(self, user_id: str, session_id: str | None) -> str:
        return session_id or "conv-generated"

    async def load_history(self, conversation_id: str, user_id: str) -> list[ChatMessage]:
        return []

    async def save_turn(
        self, conversation_id: str, user_id: str, user_message: str, assistant_message: str
    ) -> None:
        self.saved.append((user_message, assistant_message))


class FakeMemoryAgent(MemoryAgentServiceABC):
    """Long-term memory stub: no context, no extraction."""

    async def process(
        self, user_id: str, user_message: str, assistant_message: str
    ) -> None:
        return None

    async def get_context(self, user_id: str) -> str:
        return ""


class FakeProfileService(UserProfileServiceABC):
    """Profile stub: no name, no persistence."""

    async def get_profile(self, user_id: str) -> UserProfile:
        return UserProfile(user_id=user_id)

    async def update_profile(
        self, user_id: str, data: UserProfileUpdate
    ) -> UserProfile:
        return UserProfile(user_id=user_id)


INGESTION_REPLY = "Leí esto de tu imagen:\n- Supermercado: $200,000 (gasto)\n\n¿Los registro tal cual?"


class StubIngestion:
    """Stub ingestion service: returns a fixed proposal without a real vision LLM."""

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str]] = []
        self.notes: list[str] = []

    async def propose(
        self, image: bytes, mime_type: str, user_context: str = "", user_note: str = ""
    ) -> str:
        self.calls.append((image, mime_type))
        self.notes.append(user_note)
        return INGESTION_REPLY


def _override_memory() -> None:
    app.dependency_overrides[get_chat_memory_service] = lambda: FakeChatMemory()
    app.dependency_overrides[get_memory_agent_service] = lambda: FakeMemoryAgent()
    app.dependency_overrides[get_user_profile_service] = lambda: FakeProfileService()
    app.dependency_overrides[get_ingestion_service] = lambda: StubIngestion()
    # Permissive limiter so unrelated chat tests don't need a live rate-limit DB.
    app.dependency_overrides[get_rate_limit_service] = lambda: FakeRateLimitService()


@pytest.fixture
def client_with_fake_graph() -> Iterator[TestClient]:
    """TestClient where the compiled graph is built from deterministic fakes."""
    graph = create_financegpt_graph(
        llm_simple=FakeLLM(json.dumps({"intent": "categorize", "complexity": "simple"})),
        llm_complex=FakeLLM(FINAL_TEXT),
        embedding_client=FakeEmbeddingClient(),
        vector_store=FakeVectorStore(category="restaurantes"),
        toolkit=FakeToolkit(),
    )
    app.dependency_overrides[get_compiled_graph] = lambda: graph
    _override_memory()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


class TestChatEndpoint:
    def test_returns_assistant_response(self, client_with_fake_graph: TestClient) -> None:
        response = client_with_fake_graph.post(CHAT_URL, json={"message": "gasté 50 en pizza"})

        assert response.status_code == 200
        body = response.json()
        assert body["response"] == FINAL_TEXT
        assert body["agent_used"] == "categorize"
        assert body["session_id"]  # a session id was generated

    def test_reuses_provided_session_id(self, client_with_fake_graph: TestClient) -> None:
        response = client_with_fake_graph.post(
            CHAT_URL,
            json={"message": "gasté 50 en pizza", "session_id": "sess-123"},
        )

        assert response.status_code == 200
        assert response.json()["session_id"] == "sess-123"

    def test_rejects_empty_message(self, client_with_fake_graph: TestClient) -> None:
        response = client_with_fake_graph.post(CHAT_URL, json={"message": ""})

        assert response.status_code == 422

    def test_image_triggers_ingestion_flow(self, client_with_fake_graph: TestClient) -> None:
        image_b64 = base64.b64encode(b"fake-image-bytes").decode()
        response = client_with_fake_graph.post(
            CHAT_URL,
            json={"message": "", "image": image_b64, "image_mime_type": "image/png"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["response"] == INGESTION_REPLY  # from ingestion, not the graph
        assert body["agent_used"] == "ingestion"

    def test_image_forwards_user_note_to_ingestion(
        self, client_with_fake_graph: TestClient
    ) -> None:
        # The accompanying note ("son de mi Nu") must reach the extractor so it can
        # apply the card/payment method and not re-ask at registration.
        stub = StubIngestion()
        app.dependency_overrides[get_ingestion_service] = lambda: stub
        image_b64 = base64.b64encode(b"fake-image-bytes").decode()

        client_with_fake_graph.post(
            CHAT_URL,
            json={
                "message": "estos son de mi tarjeta Nu",
                "image": image_b64,
                "image_mime_type": "image/png",
            },
        )

        assert stub.notes[-1] == "estos son de mi tarjeta Nu"

    def test_pdf_triggers_ingestion_flow(self, client_with_fake_graph: TestClient) -> None:
        pdf_b64 = base64.b64encode(b"%PDF-1.4 fake").decode()
        response = client_with_fake_graph.post(
            CHAT_URL,
            json={"message": "", "image": pdf_b64, "image_mime_type": "application/pdf"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["response"] == INGESTION_REPLY  # PDF is a valid attachment
        assert body["agent_used"] == "ingestion"

    def test_image_with_invalid_mime_is_rejected_gracefully(
        self, client_with_fake_graph: TestClient
    ) -> None:
        image_b64 = base64.b64encode(b"x").decode()
        response = client_with_fake_graph.post(
            CHAT_URL,
            json={"message": "", "image": image_b64, "image_mime_type": "image/gif"},
        )

        assert response.status_code == 200
        assert "no es válido" in response.json()["response"].lower()

    def test_rejects_request_with_neither_message_nor_image(
        self, client_with_fake_graph: TestClient
    ) -> None:
        response = client_with_fake_graph.post(CHAT_URL, json={"message": ""})

        assert response.status_code == 422

    def test_graph_failure_degrades_gracefully(self) -> None:
        class BrokenGraph:
            async def ainvoke(self, state: dict, config: dict) -> dict:
                raise RuntimeError("llm down")

        app.dependency_overrides[get_compiled_graph] = lambda: BrokenGraph()
        _override_memory()
        try:
            client = TestClient(app)
            response = client.post(CHAT_URL, json={"message": "hola"})
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json()["agent_used"] == "error"

    def test_timeout_degrades_gracefully(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.api.routes.chat as chat_module

        class SlowGraph:
            async def ainvoke(self, state: dict, config: dict) -> dict:
                await asyncio.sleep(1)  # exceeds the (patched) timeout
                return {"messages": []}

        monkeypatch.setattr(chat_module, "GRAPH_TIMEOUT_SECONDS", 0.01)
        app.dependency_overrides[get_compiled_graph] = lambda: SlowGraph()
        _override_memory()
        try:
            client = TestClient(app)
            response = client.post(CHAT_URL, json={"message": "hola"})
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json()["agent_used"] == "timeout"

    def test_memory_failure_proceeds_without_history(
        self, client_with_fake_graph: TestClient
    ) -> None:
        # The chat route must survive a memory backend that raises: no history,
        # but the turn still completes and returns the assistant's reply.
        class BrokenMemory(ChatMemoryServiceABC):
            async def resolve_conversation(self, user_id: str, session_id: str | None) -> str:
                raise RuntimeError("db down")

            async def load_history(self, conversation_id: str, user_id: str) -> list[ChatMessage]:
                return []

            async def save_turn(self, *args: object) -> None:
                return None

        app.dependency_overrides[get_chat_memory_service] = lambda: BrokenMemory()

        response = client_with_fake_graph.post(CHAT_URL, json={"message": "gasté 50 en pizza"})

        assert response.status_code == 200
        assert response.json()["response"] == FINAL_TEXT  # replied despite memory being down


class _OverLimitRepo(RateLimitRepositoryABC):
    """Rate-limit repo stub that reports every window as already over the limit."""

    async def increment(
        self, user_id: str, bucket: RateLimitBucket, window_start: object
    ) -> int:
        return 999


class TestChatRateLimiting:
    def test_over_limit_returns_429_with_friendly_message(
        self, client_with_fake_graph: TestClient
    ) -> None:
        # A real service with a zero per-minute allowance -> the first turn is over.
        service: RateLimitServiceABC = RateLimitService(
            _OverLimitRepo(),
            per_minute=0,
            per_day=0,
            images_per_day=0,
            enabled=True,
        )
        app.dependency_overrides[get_rate_limit_service] = lambda: service

        response = client_with_fake_graph.post(CHAT_URL, json={"message": "hola"})

        assert response.status_code == 429
        body = response.json()
        assert body["error"] == "RATE_LIMIT_EXCEEDED"
        assert "demasiados mensajes" in body["message"]
        assert response.headers["Retry-After"]  # tells the client when to retry

    def test_within_limit_still_returns_200(
        self, client_with_fake_graph: TestClient
    ) -> None:
        # A permissive service (high thresholds) lets a normal turn through.
        service: RateLimitServiceABC = RateLimitService(
            _OverLimitRepo(),
            per_minute=10_000,
            per_day=10_000,
            images_per_day=10_000,
            enabled=True,
        )
        app.dependency_overrides[get_rate_limit_service] = lambda: service

        response = client_with_fake_graph.post(CHAT_URL, json={"message": "hola"})

        assert response.status_code == 200
        assert response.json()["response"] == FINAL_TEXT
