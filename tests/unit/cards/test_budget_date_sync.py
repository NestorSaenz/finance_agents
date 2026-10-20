"""Unit tests for re-dating a card's pending charges after a schedule change."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from app.shared.interfaces.database import QueryConfig, QueryResult
from app.src.cards.constants import BUDGET_SYNC_CONCURRENCY
from app.src.cards.models import BudgetDateSync, CreditCard
from app.src.cards.services.budget_date_sync import TransactionBudgetDateSync
from tests.fakes import FakeDatabase, make_transaction_row

FROM = date(2026, 10, 1)

# Nu after the change: cutoff 27, payment 17.
NU = CreditCard(
    id="nu-1",
    user_id="u1",
    name="Nu",
    credit_limit=Decimal("5000000"),
    cutoff_day=27,
    payment_day=17,
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def _row(row_id: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "id": row_id,
        "card_id": "nu-1",
        "payment_method": "credito",
        "description": "Compra",
        "transaction_date": "2026-10-10",
        "budget_date": "2026-10-17",  # stale: the right one is 2026-11-17
    }
    return make_transaction_row(**{**base, **overrides})


class _ApplyingDatabase(FakeDatabase):
    """Applies updates to its rows (matching the filters) and tracks in-flight writes."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__(rows=rows)
        self.in_flight = 0
        self.max_in_flight = 0

    async def update(
        self, table: str, data: dict[str, Any], filters: dict[str, Any]
    ) -> QueryResult:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)
        self.in_flight -= 1
        for row in self.rows:
            if all(row.get(key) == value for key, value in filters.items()):
                row.update(data)
        return await super().update(table, data, filters)


class _FlakyDatabase(FakeDatabase):
    """Fails the update of the rows named in ``fail_ids``."""

    def __init__(self, rows: list[dict[str, Any]], fail_ids: set[str]) -> None:
        super().__init__(rows=rows)
        self.fail_ids = fail_ids

    async def update(
        self, table: str, data: dict[str, Any], filters: dict[str, Any]
    ) -> QueryResult:
        if filters["id"] in self.fail_ids:
            raise httpx.ConnectError("db down")
        return await super().update(table, data, filters)


class _BrokenSelectDatabase(FakeDatabase):
    async def select(self, table: str, config: QueryConfig | None = None) -> QueryResult:
        raise httpx.ConnectError("db down")


def _updated_ids(db: FakeDatabase) -> set[str]:
    return {filters["id"] for _, filters in db.updated}


@pytest.mark.asyncio
class TestResync:
    async def test_selects_the_card_expenses_once_with_the_needed_columns(self) -> None:
        db = FakeDatabase(rows=[_row("t1")])

        await TransactionBudgetDateSync(db).resync(NU, "u1", from_date=FROM)

        [config] = db.select_configs
        assert config is not None
        assert config.select == "id,description,payment_method,transaction_date,budget_date"
        assert config.filters == {"user_id": "u1", "type": "expense", "card_id": "nu-1"}

    async def test_updates_only_the_pending_credit_rows_that_changed(self) -> None:
        rows = [
            _row("stale"),  # pending, wrong -> updated
            _row("cuota", description="Nevera (cuota 2/6)"),  # installment -> excluded
            _row("cash", payment_method="efectivo"),  # cash -> excluded
            _row("history", budget_date="2026-09-17", transaction_date="2026-08-10"),  # past
            _row("correct", budget_date="2026-11-17"),  # already right
            # recurring occurrence -> included (right: 2026-11-17)
            _row("recurring", recurring_id="rec-1", transaction_date="2026-10-27"),
            # future-dated -> included (right: 2027-02-17)
            _row("future", transaction_date="2026-12-28", budget_date="2026-12-17"),
        ]
        db = FakeDatabase(rows=rows)

        result = await TransactionBudgetDateSync(db).resync(NU, "u1", from_date=FROM)

        assert result == BudgetDateSync(updated=3, failed=0)
        written = {f["id"]: d["budget_date"] for d, f in db.updated}
        assert written == {
            "stale": "2026-11-17",
            "recurring": "2026-11-17",
            "future": "2027-02-17",
        }

    async def test_update_is_scoped_by_id_user_and_card(self) -> None:
        db = FakeDatabase(rows=[_row("t1")])

        await TransactionBudgetDateSync(db).resync(NU, "u1", from_date=FROM)

        [(_, filters)] = db.updated
        assert filters == {"id": "t1", "user_id": "u1", "card_id": "nu-1"}

    async def test_is_idempotent(self) -> None:
        db = _ApplyingDatabase([_row("t1"), _row("t2")])
        sync = TransactionBudgetDateSync(db)

        first = await sync.resync(NU, "u1", from_date=FROM)
        second = await sync.resync(NU, "u1", from_date=FROM)

        assert first.updated == 2
        assert second == BudgetDateSync(updated=0, failed=0)

    async def test_one_failing_row_is_counted_and_the_others_still_apply(self) -> None:
        db = _FlakyDatabase([_row("ok1"), _row("bad"), _row("ok2")], fail_ids={"bad"})

        result = await TransactionBudgetDateSync(db).resync(NU, "u1", from_date=FROM)

        assert result == BudgetDateSync(updated=2, failed=1)
        assert _updated_ids(db) == {"ok1", "ok2"}

    async def test_select_is_newest_first_so_the_cap_drops_old_rows_only(self) -> None:
        db = FakeDatabase(rows=[_row("t1")])

        await TransactionBudgetDateSync(db).resync(NU, "u1", from_date=FROM)

        [config] = db.select_configs
        assert config is not None
        assert (config.order_by, config.order_ascending) == ("transaction_date", False)

    async def test_parallel_updates_are_bounded(self) -> None:
        db = _ApplyingDatabase([_row(f"t{i}") for i in range(30)])

        result = await TransactionBudgetDateSync(db).resync(NU, "u1", from_date=FROM)

        assert result == BudgetDateSync(updated=30, failed=0)
        assert 1 < db.max_in_flight <= BUDGET_SYNC_CONCURRENCY

    async def test_correcting_a_misconfigured_card_redates_the_open_cycle_charge(self) -> None:
        # BBVA cutoff was 10 (charge of Oct 10 -> Oct 26); corrected to cutoff 9 / pay 26,
        # the Oct 10 charge belongs to the NEXT statement -> Nov 26. Today is Oct 20.
        bbva = NU.model_copy(update={"id": "bbva-1", "cutoff_day": 9, "payment_day": 26})
        db = _ApplyingDatabase(
            [
                _row("open", transaction_date="2026-10-10", budget_date="2026-10-26"),
                # Already due by our records (budget_date before today): history, untouched.
                _row("paid", transaction_date="2026-09-20", budget_date="2026-10-02"),
            ]
        )

        result = await TransactionBudgetDateSync(db).resync(
            bbva, "u1", from_date=date(2026, 10, 20)
        )

        assert result == BudgetDateSync(updated=1, failed=0)
        assert {f["id"]: d["budget_date"] for d, f in db.updated} == {"open": "2026-11-26"}

    async def test_select_failure_propagates_for_the_service_to_handle(self) -> None:
        with pytest.raises(httpx.HTTPError):
            await TransactionBudgetDateSync(_BrokenSelectDatabase()).resync(
                NU, "u1", from_date=FROM
            )
