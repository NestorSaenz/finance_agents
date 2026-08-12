"""Unit tests for the recurring service (repository + collaborators mocked)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.exceptions import RecurringNotFoundError
from app.shared.types import Category, PaymentMethod, TransactionType, UserId
from app.src.recurring.interfaces import RecurringRepositoryABC
from app.src.recurring.models import (
    RecurringCreate,
    RecurringFrequency,
    RecurringTransaction,
    RecurringUpdate,
)
from app.src.recurring.services import recurring_service as service_module
from app.src.recurring.services.recurring_service import RecurringService
from app.src.transactions.interfaces import TransactionCategorizerABC
from app.src.transactions.models import TransactionCreate
from app.src.transactions.repositories.transaction_repository import (
    TransactionRepository,
)
from app.src.transactions.services.transaction_service import TransactionService
from tests.fakes import FakeDatabase
from tests.unit.agents.test_card_tools import FakeCardService, _card
from tests.unit.agents.test_transaction_tools import FakeTransactionService


class _StubCategorizer(TransactionCategorizerABC):
    """Deterministic categorizer so the real transaction service can run."""

    def __init__(self) -> None:
        self.calls = 0

    async def categorize(self, description: str) -> Category:
        self.calls += 1
        return "otros"


def _real_tx_service(db: FakeDatabase) -> TransactionService:
    """A real transaction service whose exactly-once insert is backed by ``db``."""
    return TransactionService(TransactionRepository(db), _StubCategorizer())


def _rec(
    *,
    rec_id: str = "rec-1",
    user_id: str = "u1",
    day_of_month: int = 15,
    next_run_date: date = date(2026, 6, 15),
    active: bool = True,
    card_id: str | None = None,
    payment_method: PaymentMethod | None = None,
    transaction_type: TransactionType = TransactionType.EXPENSE,
    amount: Decimal = Decimal("50000"),
    description: str = "Netflix",
) -> RecurringTransaction:
    return RecurringTransaction(
        id=rec_id,
        user_id=user_id,
        amount=amount,
        description=description,
        transaction_type=transaction_type,
        category="suscripciones",
        payment_method=payment_method,
        card_id=card_id,
        frequency=RecurringFrequency.MONTHLY,
        day_of_month=day_of_month,
        next_run_date=next_run_date,
        last_run_date=None,
        active=active,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _apply(rec: RecurringTransaction, data: dict[str, object]) -> RecurringTransaction:
    update: dict[str, object] = {}
    if "amount" in data:
        update["amount"] = Decimal(str(data["amount"]))
    if "description" in data:
        update["description"] = data["description"]
    if "category" in data:
        update["category"] = data["category"]
    if "payment_method" in data:
        update["payment_method"] = PaymentMethod(str(data["payment_method"]))
    if "card_id" in data:
        update["card_id"] = data["card_id"]
    if "day_of_month" in data:
        update["day_of_month"] = data["day_of_month"]
    if "next_run_date" in data:
        update["next_run_date"] = date.fromisoformat(str(data["next_run_date"]))
    if "last_run_date" in data:
        update["last_run_date"] = date.fromisoformat(str(data["last_run_date"]))
    if "active" in data:
        update["active"] = data["active"]
    return rec.model_copy(update=update)


class FakeRecurringRepository(RecurringRepositoryABC):
    def __init__(self, items: list[RecurringTransaction] | None = None) -> None:
        self._items = list(items or [])
        self.created: list[RecurringTransaction] = []
        self.updates: list[tuple[str, dict[str, object]]] = []
        self.deleted: list[str] = []
        self._counter = 0

    async def create(
        self, rec: RecurringCreate, user_id: UserId
    ) -> RecurringTransaction:
        self._counter += 1
        created = RecurringTransaction(
            id=f"rec-{self._counter}",
            user_id=user_id,
            amount=rec.amount,
            description=rec.description,
            transaction_type=rec.transaction_type,
            category=rec.category,
            payment_method=rec.payment_method,
            card_id=rec.card_id,
            frequency=rec.frequency,
            day_of_month=rec.day_of_month,
            next_run_date=rec.next_run_date,
            last_run_date=None,
            active=rec.active,
            created_at=datetime.now(UTC),
        )
        self._items.append(created)
        self.created.append(created)
        return created

    async def get_by_id(
        self, recurring_id: str, user_id: UserId
    ) -> RecurringTransaction | None:
        return next(
            (r for r in self._items if r.id == recurring_id and r.user_id == user_id),
            None,
        )

    async def list_for_user(self, user_id: UserId) -> list[RecurringTransaction]:
        return [r for r in self._items if r.user_id == user_id]

    async def list_due(self, as_of: date) -> list[RecurringTransaction]:
        return [r for r in self._items if r.active and r.next_run_date <= as_of]

    async def update(
        self, recurring_id: str, user_id: UserId, data: dict[str, object]
    ) -> RecurringTransaction:
        self.updates.append((recurring_id, data))
        rec = await self.get_by_id(recurring_id, user_id)
        if rec is None:
            raise RecurringNotFoundError(recurring_id)
        updated = _apply(rec, data)
        self._items = [updated if r.id == recurring_id else r for r in self._items]
        return updated

    async def delete(self, recurring_id: str, user_id: UserId) -> None:
        self.deleted.append(recurring_id)
        self._items = [r for r in self._items if r.id != recurring_id]


def _service(
    repo: FakeRecurringRepository,
    transactions: FakeTransactionService | None = None,
    cards: FakeCardService | None = None,
) -> RecurringService:
    return RecurringService(
        repo,
        transactions or FakeTransactionService(),
        cards or FakeCardService(cards=[]),
    )


def _create_input(day_of_month: int, **overrides: object) -> RecurringCreate:
    base: dict[str, object] = {
        "amount": Decimal("50000"),
        "description": "Netflix",
        "transaction_type": TransactionType.EXPENSE,
        "day_of_month": day_of_month,
    }
    base.update(overrides)
    return RecurringCreate(**base)  # type: ignore[arg-type]


class TestCreateNextRunDate:
    def _freeze(self, monkeypatch: pytest.MonkeyPatch, today: date) -> None:
        monkeypatch.setattr(service_module, "_today", lambda: today)

    async def test_day_later_this_month_uses_this_month(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._freeze(monkeypatch, date(2026, 6, 10))
        repo = FakeRecurringRepository()
        created = await _service(repo).create_recurring(_create_input(20), "u1")
        assert created.next_run_date == date(2026, 6, 20)

    async def test_day_equal_today_uses_today(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._freeze(monkeypatch, date(2026, 6, 15))
        repo = FakeRecurringRepository()
        created = await _service(repo).create_recurring(_create_input(15), "u1")
        assert created.next_run_date == date(2026, 6, 15)

    async def test_day_already_passed_rolls_to_next_month(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._freeze(monkeypatch, date(2026, 6, 25))
        repo = FakeRecurringRepository()
        created = await _service(repo).create_recurring(_create_input(10), "u1")
        assert created.next_run_date == date(2026, 7, 10)

    async def test_day_31_clamps_in_short_month(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # February 2026 has 28 days -> day 31 clamps to Feb 28.
        self._freeze(monkeypatch, date(2026, 2, 5))
        repo = FakeRecurringRepository()
        created = await _service(repo).create_recurring(_create_input(31), "u1")
        assert created.next_run_date == date(2026, 2, 28)


class TestRunDue:
    async def test_materializes_and_advances(self) -> None:
        repo = FakeRecurringRepository([_rec(next_run_date=date(2026, 6, 15))])
        txs = FakeTransactionService()
        service = _service(repo, txs)

        created = await service.run_due(date(2026, 6, 20))

        assert created == 1
        tx, uid = txs.created[0]
        assert uid == "u1"
        assert tx.transaction_date == date(2026, 6, 15)
        assert tx.budget_date == date(2026, 6, 15)  # cash -> budget = tx date
        # Schedule advanced to July and last_run recorded.
        _rid, data = repo.updates[-1]
        assert data["last_run_date"] == "2026-06-15"
        assert data["next_run_date"] == "2026-07-15"

    async def test_catch_up_is_bounded_by_max(self) -> None:
        # A next_run_date years in the past would produce > 24 occurrences.
        repo = FakeRecurringRepository([_rec(next_run_date=date(2020, 1, 15))])
        txs = FakeTransactionService()
        service = _service(repo, txs)

        created = await service.run_due(date(2026, 6, 20))

        assert created == 24  # MAX_CATCHUP_RUNS
        assert len(txs.created) == 24

    async def test_skips_paused_templates(self) -> None:
        repo = FakeRecurringRepository(
            [
                _rec(rec_id="active", next_run_date=date(2026, 6, 15)),
                _rec(rec_id="paused", next_run_date=date(2026, 6, 15), active=False),
            ]
        )
        txs = FakeTransactionService()
        service = _service(repo, txs)

        created = await service.run_due(date(2026, 6, 20))

        assert created == 1  # only the active one materialized

    async def test_credit_template_gets_budget_date_from_card_cycle(self) -> None:
        card = _card()  # cutoff 15, payment 5
        repo = FakeRecurringRepository(
            [
                _rec(
                    next_run_date=date(2026, 6, 20),
                    card_id=card.id,
                    payment_method=PaymentMethod.CREDITO,
                )
            ]
        )
        txs = FakeTransactionService()
        service = _service(repo, txs, FakeCardService(cards=[card]))

        created = await service.run_due(date(2026, 6, 20))

        assert created == 1
        tx, _uid = txs.created[0]
        # cutoff 15 on Jun 20 -> cycle ends Jul 15 -> pays Aug 5.
        assert tx.budget_date == date(2026, 8, 5)
        assert tx.card_id == card.id

    async def test_no_due_templates_creates_nothing(self) -> None:
        repo = FakeRecurringRepository([_rec(next_run_date=date(2026, 12, 1))])
        txs = FakeTransactionService()
        service = _service(repo, txs)

        created = await service.run_due(date(2026, 6, 20))

        assert created == 0
        assert txs.created == []


class TestMutations:
    async def test_update_amount(self) -> None:
        repo = FakeRecurringRepository([_rec()])
        service = _service(repo)

        updated = await service.update_recurring(
            "rec-1", "u1", RecurringUpdate(amount=Decimal("99999"))
        )

        assert updated.amount == Decimal("99999")

    async def test_update_day_reschedules_next_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(service_module, "_today", lambda: date(2026, 6, 10))
        repo = FakeRecurringRepository([_rec(day_of_month=15)])
        service = _service(repo)

        updated = await service.update_recurring(
            "rec-1", "u1", RecurringUpdate(day_of_month=20)
        )

        assert updated.day_of_month == 20
        assert updated.next_run_date == date(2026, 6, 20)

    async def test_update_missing_raises(self) -> None:
        service = _service(FakeRecurringRepository())
        with pytest.raises(RecurringNotFoundError):
            await service.update_recurring(
                "missing", "u1", RecurringUpdate(amount=Decimal("1"))
            )

    async def test_delete_returns_removed_and_deletes(self) -> None:
        repo = FakeRecurringRepository([_rec()])
        service = _service(repo)

        removed = await service.delete_recurring("rec-1", "u1")

        assert removed.id == "rec-1"
        assert repo.deleted == ["rec-1"]

    async def test_delete_missing_raises(self) -> None:
        service = _service(FakeRecurringRepository())
        with pytest.raises(RecurringNotFoundError):
            await service.delete_recurring("missing", "u1")

    async def test_set_active_pauses(self) -> None:
        repo = FakeRecurringRepository([_rec(active=True)])
        service = _service(repo)

        updated = await service.set_active("rec-1", "u1", False)

        assert updated.active is False

    async def test_set_active_resumes(self) -> None:
        repo = FakeRecurringRepository([_rec(active=False)])
        service = _service(repo)

        updated = await service.set_active("rec-1", "u1", True)

        assert updated.active is True


class TestResolveByName:
    async def test_accent_insensitive_match(self) -> None:
        repo = FakeRecurringRepository([_rec(description="Salario")])
        service = _service(repo)

        match = await service.resolve_by_name("salário", "u1")

        assert match is not None and match.description == "Salario"

    async def test_returns_none_when_no_match(self) -> None:
        repo = FakeRecurringRepository([_rec(description="Netflix")])
        service = _service(repo)

        assert await service.resolve_by_name("Spotify", "u1") is None


class TestFindMatches:
    async def test_returns_all_partial_matches(self) -> None:
        # Neither is an exact match for "netflix", so both partials are returned.
        repo = FakeRecurringRepository(
            [_rec(rec_id="a", description="Netflix Basico"),
             _rec(rec_id="b", description="Netflix Premium")]
        )
        service = _service(repo)

        matches = await service.find_matches("netflix", "u1")

        assert {m.id for m in matches} == {"a", "b"}

    async def test_exact_match_short_circuits(self) -> None:
        repo = FakeRecurringRepository(
            [_rec(rec_id="a", description="Netflix"),
             _rec(rec_id="b", description="Netflix Premium")]
        )
        service = _service(repo)

        matches = await service.find_matches("Netflix", "u1")

        assert [m.id for m in matches] == ["a"]  # exact wins, no ambiguity


class TestIdempotency:
    async def test_second_run_over_unadvanced_schedule_does_not_duplicate(self) -> None:
        # Exactly-once via the DB unique index (modeled by FakeDatabase dedup):
        # replaying the SAME (recurring_id, occurrence_date) creates no second row.
        db = FakeDatabase()
        txs = _real_tx_service(db)
        first_repo = FakeRecurringRepository([_rec(next_run_date=date(2026, 6, 15))])
        created = await RecurringService(
            first_repo, txs, FakeCardService(cards=[])
        ).run_due(date(2026, 6, 15))
        assert created == 1
        assert len(db.ignore_inserted) == 1

        # A fresh run whose schedule was NOT advanced (retry/duplicate delivery)
        # re-attempts the same occurrence -> ignored, no new transaction.
        replay_repo = FakeRecurringRepository([_rec(next_run_date=date(2026, 6, 15))])
        recreated = await RecurringService(
            replay_repo, txs, FakeCardService(cards=[])
        ).run_due(date(2026, 6, 15))
        assert recreated == 0
        assert len(db.ignore_inserted) == 1  # still exactly one

    async def test_duplicate_advances_schedule_anyway(self) -> None:
        # Even when the occurrence already existed (materialize returns None), the
        # schedule still advances so the run stays idempotent and progresses.
        db = FakeDatabase()
        txs = _real_tx_service(db)
        # Pre-seed the occurrence so the run's first materialize is a duplicate.
        await txs.materialize_occurrence(_occurrence_tx("rec-1", date(2026, 6, 15)), "u1")
        repo = FakeRecurringRepository([_rec(next_run_date=date(2026, 6, 15))])
        created = await RecurringService(
            repo, txs, FakeCardService(cards=[])
        ).run_due(date(2026, 6, 15))
        assert created == 0  # was a duplicate
        # But the schedule advanced to July regardless.
        _rid, data = repo.updates[-1]
        assert data["next_run_date"] == "2026-07-15"

    async def test_categorizes_once_per_template_run(self) -> None:
        # A category-less template that catches up many months categorizes ONCE.
        db = FakeDatabase()
        categorizer = _StubCategorizer()
        txs = TransactionService(TransactionRepository(db), categorizer)
        repo = FakeRecurringRepository([_rec(next_run_date=date(2026, 1, 15))])
        # _rec() sets category="suscripciones"; override to None for this test so
        # the service must categorize.
        repo._items[0] = repo._items[0].model_copy(update={"category": None})

        created = await RecurringService(
            repo, txs, FakeCardService(cards=[])
        ).run_due(date(2026, 6, 15))

        assert created >= 5  # several catch-up months
        assert categorizer.calls == 1  # categorized once, reused for all


class TestPartialFailureIsolation:
    async def test_one_failing_template_does_not_abort_others(self) -> None:
        class _FailingDB(FakeDatabase):
            async def insert_ignore_duplicates(
                self, table: str, row: dict[str, object], on_conflict: str
            ) -> object:
                if row.get("recurring_id") == "bad":
                    raise RuntimeError("insert boom")
                return await super().insert_ignore_duplicates(table, row, on_conflict)

        db = _FailingDB()
        txs = _real_tx_service(db)
        repo = FakeRecurringRepository(
            [
                _rec(rec_id="bad", description="Bad", next_run_date=date(2026, 6, 15)),
                _rec(rec_id="good", description="Good", next_run_date=date(2026, 6, 15)),
            ]
        )
        service = RecurringService(repo, txs, FakeCardService(cards=[]))

        created = await service.run_due(date(2026, 6, 15))

        assert created == 1  # the good one still materialized
        assert len(db.ignore_inserted) == 1

        # A re-run does not duplicate the one already done (bad still fails).
        recreated = await service.run_due(date(2026, 6, 15))
        assert len(db.ignore_inserted) == 1
        assert recreated == 0  # good already advanced; bad keeps failing, no dupes


class TestResumeReschedules:
    async def test_resume_skips_missed_months(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(service_module, "_today", lambda: date(2026, 6, 10))
        repo = FakeRecurringRepository(
            [_rec(day_of_month=15, next_run_date=date(2020, 1, 15), active=False)]
        )
        service = _service(repo)

        updated = await service.set_active("rec-1", "u1", True)

        assert updated.active is True
        # Rescheduled to the next FUTURE occurrence, not the stale 2020 date.
        assert updated.next_run_date == date(2026, 6, 15)

    async def test_pause_does_not_reschedule(self) -> None:
        repo = FakeRecurringRepository(
            [_rec(next_run_date=date(2026, 6, 15), active=True)]
        )
        service = _service(repo)

        updated = await service.set_active("rec-1", "u1", False)

        assert updated.active is False
        assert updated.next_run_date == date(2026, 6, 15)  # unchanged


class TestDeletedCardFallback:
    async def test_credit_template_with_missing_card_materializes_as_efectivo(
        self,
    ) -> None:
        # Card was deleted but the template still names it: must NOT create a
        # credito movement with a dangling card_id.
        repo = FakeRecurringRepository(
            [
                _rec(
                    next_run_date=date(2026, 6, 15),
                    card_id="gone",
                    payment_method=PaymentMethod.CREDITO,
                )
            ]
        )
        txs = FakeTransactionService()
        service = _service(repo, txs, FakeCardService(cards=[]))  # no cards on file

        created = await service.run_due(date(2026, 6, 15))

        assert created == 1
        tx, _uid = txs.created[0]
        assert tx.payment_method == PaymentMethod.EFECTIVO
        assert tx.card_id is None
        assert tx.budget_date == date(2026, 6, 15)  # cash -> budget = run date


class TestBadDataRejected:
    def test_create_day_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _create_input(40)

    def test_update_day_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RecurringUpdate(day_of_month=0)


def _occurrence_tx(recurring_id: str, occurrence: date) -> TransactionCreate:
    return TransactionCreate(
        amount=Decimal("50000"),
        description="Netflix",
        transaction_type=TransactionType.EXPENSE,
        transaction_date=occurrence,
        category="suscripciones",
        recurring_id=recurring_id,
        occurrence_date=occurrence,
    )
