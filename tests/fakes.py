"""Reusable test doubles for the agent system.

These fakes implement the project interfaces with deterministic behaviour so
the multiagent graph can be exercised end-to-end without hitting real LLM,
embedding, or vector-store providers.
"""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from app.shared.interfaces.database import QueryConfig, QueryResult
from app.shared.interfaces.llm import LLMConfig, LLMInterface, LLMResponse, Message
from app.shared.turn import TurnContext
from app.shared.types import CardId, UserId
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import (
    CardPayment,
    CardPaymentCreate,
    CardPaymentView,
    CreditCard,
    CreditCardCreate,
    CreditCardStatus,
)
from app.src.pending.interfaces import PendingActionRepositoryABC, PendingActionServiceABC
from app.src.pending.models import PendingAction
from app.src.pending.types import PendingActionKind
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


class FakePendingActionRepository(PendingActionRepositoryABC):
    """In-memory store mirroring the RPC semantics of migration 016.

    ``consume`` only matches a live row (``expires_at >= now``) of the same
    user/conversation/kind proposed in ANOTHER turn, and deletes it atomically.
    ``discard_stale`` drops the user's expired rows and this conversation's rows of
    other turns. ``now`` is settable so tests can expire proposals.
    """

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], PendingAction] = {}
        self.now: datetime = datetime.now(UTC)

    async def upsert(self, action: PendingAction) -> None:
        self.rows[(action.user_id, action.conversation_id)] = action

    async def get(self, user_id: UserId, conversation_id: str) -> PendingAction | None:
        return self.rows.get((user_id, conversation_id))

    async def consume(
        self, user_id: UserId, conversation_id: str, kind: PendingActionKind, turn_id: str
    ) -> dict[str, object] | None:
        self._drop_expired(user_id)
        row = self.rows.get((user_id, conversation_id))
        if row is None or row.kind != kind or row.turn_id == turn_id:
            return None
        del self.rows[(user_id, conversation_id)]
        return row.payload

    async def discard_stale(
        self, user_id: UserId, conversation_id: str, keep_turn_id: str
    ) -> None:
        self._drop_expired(user_id)
        row = self.rows.get((user_id, conversation_id))
        if row is not None and row.turn_id != keep_turn_id:
            del self.rows[(user_id, conversation_id)]

    def _drop_expired(self, user_id: UserId) -> None:
        for key in [k for k, r in self.rows.items() if k[0] == user_id and r.expires_at < self.now]:
            del self.rows[key]


class FakePendingActionService(PendingActionServiceABC):
    """Records sweeps (and optionally fails them) for route tests."""

    def __init__(self, error: Exception | None = None) -> None:
        self.discarded: list[tuple[str, TurnContext]] = []
        self.keep_current: list[bool] = []
        self._error = error

    async def propose(
        self,
        user_id: UserId,
        turn: TurnContext,
        kind: PendingActionKind,
        payload: dict[str, object],
    ) -> bool:
        return True

    async def consume(
        self, user_id: UserId, turn: TurnContext, kind: PendingActionKind
    ) -> dict[str, object] | None:
        return None

    async def discard_stale(
        self, user_id: UserId, turn: TurnContext, *, keep_current: bool = True
    ) -> None:
        self.discarded.append((user_id, turn))
        self.keep_current.append(keep_current)
        if self._error is not None:
            raise self._error


class InMemoryCardService(CreditCardServiceABC):
    """Card service stub that PERSISTS ``update_card`` (list_cards reflects it)."""

    def __init__(self, cards: list[CreditCard]) -> None:
        self.cards = cards
        self.update_calls = 0

    async def list_cards(self, user_id: UserId) -> list[CreditCard]:
        return [c for c in self.cards if c.user_id == user_id and c.is_active]

    async def resolve_by_name(self, name: str, user_id: UserId) -> CreditCard | None:
        return next(
            (c for c in await self.list_cards(user_id) if name.lower() in c.name.lower()), None
        )

    async def update_card(
        self,
        card_id: CardId,
        user_id: UserId,
        *,
        name: str | None = None,
        credit_limit: Decimal | None = None,
        cutoff_day: int | None = None,
        payment_day: int | None = None,
    ) -> CreditCard:
        from app.core.exceptions import CardNotFoundError

        self.update_calls += 1
        index = next(
            (i for i, c in enumerate(self.cards) if c.id == card_id and c.user_id == user_id), None
        )
        if index is None:
            raise CardNotFoundError(card_id)
        changes = {
            "name": name,
            "credit_limit": credit_limit,
            "cutoff_day": cutoff_day,
            "payment_day": payment_day,
        }
        self.cards[index] = self.cards[index].model_copy(
            update={k: v for k, v in changes.items() if v is not None}
        )
        return self.cards[index]

    async def create_card(self, card: CreditCardCreate, user_id: UserId) -> CreditCard:
        raise NotImplementedError

    async def get_all_status(
        self,
        user_id: UserId,
        as_of: date | None = None,
        *,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> list[CreditCardStatus]:
        raise NotImplementedError

    async def get_status(
        self, card_id: CardId, user_id: UserId, as_of: date | None = None
    ) -> CreditCardStatus:
        raise NotImplementedError

    async def total_paid_up_to(self, user_id: UserId, as_of: date) -> Decimal:
        raise NotImplementedError

    async def register_payment(
        self, card_id: CardId, user_id: UserId, payment: CardPaymentCreate
    ) -> CardPayment:
        raise NotImplementedError

    async def list_payments(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPaymentView]:
        raise NotImplementedError

    async def remove_payment(
        self,
        user_id: UserId,
        amount: Decimal,
        *,
        payment_date: date | None = None,
        card_id: CardId | None = None,
    ) -> CardPayment | None:
        raise NotImplementedError

    async def delete_card(self, card_id: CardId, user_id: UserId) -> CreditCard:
        raise NotImplementedError


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
        # Rows accepted by insert_ignore_duplicates, plus the conflict keys already
        # seen (so a duplicate (on_conflict-key) tuple is ignored, modeling the DB
        # unique index used for exactly-once materialization).
        self.ignore_inserted: list[dict[str, Any]] = []
        self._seen_conflict_keys: set[tuple[Any, ...]] = set()
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

    async def insert_ignore_duplicates(
        self, table: str, row: dict[str, Any], on_conflict: str
    ) -> QueryResult:
        # Model the DB unique index: a repeat of the same on_conflict-key tuple is
        # ignored (empty result); a new key inserts and returns the row.
        keys = tuple(row.get(column) for column in on_conflict.split(","))
        if keys in self._seen_conflict_keys:
            return QueryResult(data=[], count=0)
        self._seen_conflict_keys.add(keys)
        record = dict(row)
        record.setdefault("id", "tx-generated-id")
        record.setdefault("created_at", "2024-12-20T10:00:00+00:00")
        self.ignore_inserted.append(record)
        return QueryResult(data=[record], count=1)

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


def make_recurring_row(**overrides: Any) -> dict[str, Any]:
    """Build a realistic recurring_transactions table row, overridable per field."""
    row = {
        "id": "rec-1",
        "user_id": "u1",
        # Postgres numeric arrives as a string; keep it a Decimal-string so the
        # repository's parse_decimal path is exercised (not a lossy float).
        "amount": "50000.00",
        "description": "Netflix",
        "type": "expense",
        "category": "suscripciones",
        "payment_method": None,
        "card_id": None,
        "frequency": "monthly",
        "day_of_month": 5,
        "next_run_date": "2026-06-05",
        "last_run_date": None,
        "active": True,
        "created_at": "2026-01-01T08:00:00+00:00",
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
