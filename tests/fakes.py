"""Reusable test doubles for the agent system.

These fakes implement the project interfaces with deterministic behaviour so
the multiagent graph can be exercised end-to-end without hitting real LLM,
embedding, or vector-store providers.
"""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

from app.shared.interfaces.database import QueryConfig, QueryResult
from app.shared.interfaces.llm import LLMConfig, LLMInterface, LLMResponse, Message
from app.src.ratelimit.interfaces import RateLimitServiceABC


class FakeLLM(LLMInterface):
    """LLM stub that always returns a fixed content string.

    Records the prompts it received in ``calls`` for assertions.
    """

    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[list[Message]] = []

    async def generate(
        self, messages: list[Message], config: LLMConfig | None = None
    ) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(content=self._content, model="fake-model")

    async def generate_stream(
        self, messages: list[Message], config: LLMConfig | None = None
    ) -> AsyncIterator[str]:
        self.calls.append(messages)
        yield self._content

    async def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(content=self._content, model="fake-model")

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def provider(self) -> str:
        return "fake"


class FakeEmbeddingClient:
    """Embedding stub returning a constant vector."""

    def __init__(self, dimension: int = 1024) -> None:
        self._vector = [0.1] * dimension

    async def embed_query(self, text: str) -> list[float]:
        return self._vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector for _ in texts]


class FakeVectorStore:
    """Vector-store stub returning a single high-confidence match."""

    def __init__(self, category: str = "restaurantes", score: float = 0.95) -> None:
        self._category = category
        self._score = score

    async def search(self, embedding: list[float], config: Any = None) -> list[Any]:
        return [SimpleNamespace(metadata={"category": self._category}, score=self._score)]


class FakeToolkit:
    """Minimal toolkit stand-in for graph/chat tests (no tool calls exercised)."""

    schemas: list[Any] = []

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: str) -> str:
        return "ok"


class FakeRateLimitService(RateLimitServiceABC):
    """Permissive rate-limit stub: records calls and never limits.

    Lets chat tests that aren't about rate limiting run without a live DB.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    async def check_chat(self, user_id: str, *, has_image: bool) -> None:
        self.calls.append((user_id, has_image))


class FakeDatabase:
    """In-memory stand-in for ``DatabaseInterface`` used by repository tests.

    Records inserts and serves ``rows`` for selects. Only the methods exercised
    by the transaction repository (``insert``, ``select``) are implemented.
    """

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows: list[dict[str, Any]] = rows or []
        self.inserted: list[dict[str, Any]] = []
        self.upserted: list[dict[str, Any]] = []
        self.upsert_calls: list[tuple[str, str]] = []
        self.updated: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.deleted: list[dict[str, Any]] = []
        self.select_configs: list[QueryConfig | None] = []
        self.count_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_result: list[dict[str, Any]] = []

    async def insert(self, table: str, data: Any) -> QueryResult:
        records = data if isinstance(data, list) else [data]
        out: list[dict[str, Any]] = []
        for item in records:
            record = dict(item)
            record.setdefault("id", "tx-generated-id")
            record.setdefault("created_at", "2024-12-20T10:00:00+00:00")
            self.inserted.append(record)
            out.append(record)
        return QueryResult(data=out, count=len(out))

    async def select(self, table: str, config: QueryConfig | None = None) -> QueryResult:
        self.select_configs.append(config)
        return QueryResult(data=list(self.rows), count=len(self.rows))

    async def count(self, table: str, filters: dict[str, Any]) -> int:
        self.count_calls.append((table, filters))
        return len(self.rows)

    async def update(
        self, table: str, data: dict[str, Any], filters: dict[str, Any]
    ) -> QueryResult:
        self.updated.append((data, filters))
        base = self.rows[0] if self.rows else {}
        return QueryResult(data=[{**base, **data}], count=1)

    async def delete(self, table: str, filters: dict[str, Any]) -> QueryResult:
        self.deleted.append(filters)
        return QueryResult(data=list(self.rows), count=len(self.rows))

    async def upsert(self, table: str, data: Any, on_conflict: str) -> QueryResult:
        records = data if isinstance(data, list) else [data]
        self.upsert_calls.append((table, on_conflict))
        self.upserted.extend(records)
        return QueryResult(data=list(records), count=len(records))

    async def execute_rpc(self, function_name: str, params: dict[str, Any]) -> QueryResult:
        self.rpc_calls.append((function_name, params))
        return QueryResult(data=list(self.rpc_result), count=len(self.rpc_result))


def make_transaction_row(**overrides: Any) -> dict[str, Any]:
    """Build a realistic transactions table row, overridable per field."""
    row = {
        "id": "tx-1",
        "user_id": "u1",
        "amount": 50000.0,
        "currency": "MXN",
        "type": "expense",
        "description": "Almuerzo con colegas",
        "category": "restaurantes",
        "transaction_date": "2024-12-20",
        "source": "manual",
        "created_at": "2024-12-20T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def make_goal_row(**overrides: Any) -> dict[str, Any]:
    """Build a realistic goals table row, overridable per field."""
    row = {
        "id": "goal-1",
        "user_id": "u1",
        "name": "Viaje a Japón",
        "description": "Ahorro para vacaciones",
        "type": "savings",
        "target_amount": 100000.0,
        "current_amount": 25000.0,
        "currency": "MXN",
        "target_date": "2025-12-31",
        "monthly_contribution": None,
        "status": "active",
        "priority": 1,
        "created_at": "2024-12-01T08:00:00+00:00",
    }
    row.update(overrides)
    return row


def make_budget_row(**overrides: Any) -> dict[str, Any]:
    """Build a realistic budgets table row, overridable per field."""
    row = {
        "id": "bud-1",
        "user_id": "u1",
        "name": "Comida mensual",
        "amount": 300000.0,
        "category": "restaurantes",
        "currency": "MXN",
        "period_type": "monthly",
        "start_date": "2024-12-01",
        "end_date": None,
        "alert_threshold": 80.0,
        "alert_enabled": True,
        "is_active": True,
        "created_at": "2024-12-01T08:00:00+00:00",
    }
    row.update(overrides)
    return row
