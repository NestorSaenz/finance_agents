"""Unit tests for the gross-monthly-contributions provider (RPC vs Python fallback)."""

from datetime import date
from decimal import Decimal

from app.src.goals.constants import GOAL_MONTHLY_CONTRIBUTIONS_RPC
from app.src.goals.models import GoalMonthContribution
from app.src.goals.services.contribution_months_provider import ContributionMonthsProvider
from tests.fakes import FakeDatabase, InMemoryContributionLedger, RpcFailingDatabase

D = Decimal
START, END = date(2026, 4, 1), date(2026, 6, 30)


def _ledger() -> InMemoryContributionLedger:
    ledger = InMemoryContributionLedger()
    ledger.add("g1", D("100.10"), date(2026, 4, 3))
    ledger.add("g1", D("200.20"), date(2026, 4, 30))
    ledger.add("g1", D("-50.05"), date(2026, 4, 12))
    ledger.add("g1", D("70"), date(2026, 6, 1))
    ledger.add("g2", D("-30"), date(2026, 5, 9))  # a month with only a retiro
    ledger.add("g2", D("999"), date(2026, 3, 31))  # outside the window
    ledger.add("g2", D("999"), date(2026, 7, 1))  # outside the window
    return ledger


# What the Postgres function returns for the ledger above (month_trunc, gross sums).
_RPC_ROWS = [
    {"goal_id": "g1", "month": "2026-04-01", "saved": "300.30", "withdrawn": "50.05"},
    {"goal_id": "g1", "month": "2026-06-01", "saved": "70", "withdrawn": "0"},
    {"goal_id": "g2", "month": "2026-05-01", "saved": "0", "withdrawn": "30"},
]


class TestPythonFallback:
    async def test_groups_gross_saved_and_withdrawn_by_goal_and_month(self) -> None:
        provider = ContributionMonthsProvider(RpcFailingDatabase(), _ledger())  # type: ignore[arg-type]

        result = await provider.monthly_totals("u1", START, END)

        assert result == [
            GoalMonthContribution(goal_id="g1", month=date(2026, 4, 1), saved=D("300.30"), withdrawn=D("50.05")),
            GoalMonthContribution(goal_id="g1", month=date(2026, 6, 1), saved=D("70"), withdrawn=D("0")),
            GoalMonthContribution(goal_id="g2", month=date(2026, 5, 1), saved=D("0"), withdrawn=D("30")),
        ]

    async def test_no_contributions_gives_no_entries(self) -> None:
        provider = ContributionMonthsProvider(RpcFailingDatabase(), InMemoryContributionLedger())  # type: ignore[arg-type]

        assert await provider.monthly_totals("u1", START, END) == []


class TestRpc:
    async def test_rpc_and_python_fallback_agree(self) -> None:
        db = FakeDatabase()
        db.rpc_result = list(_RPC_ROWS)
        via_rpc = await ContributionMonthsProvider(db, _ledger()).monthly_totals("u1", START, END)  # type: ignore[arg-type]
        via_python = await ContributionMonthsProvider(
            RpcFailingDatabase(),  # type: ignore[arg-type]
            _ledger(),
        ).monthly_totals("u1", START, END)

        assert via_rpc == via_python

    async def test_calls_the_function_with_iso_dates(self) -> None:
        db = FakeDatabase()
        db.rpc_result = list(_RPC_ROWS)

        await ContributionMonthsProvider(db, InMemoryContributionLedger()).monthly_totals(  # type: ignore[arg-type]
            "u1", START, END
        )

        assert db.rpc_calls == [
            (
                GOAL_MONTHLY_CONTRIBUTIONS_RPC,
                {"p_user_id": "u1", "p_start": "2026-04-01", "p_end": "2026-06-30"},
            )
        ]

    async def test_empty_rpc_answer_is_trusted_without_scanning(self) -> None:
        db = FakeDatabase()  # rpc_result == [] -> a user with no movement in the window

        # The ledger has data, but an empty RPC answer must NOT trigger the fallback.
        result = await ContributionMonthsProvider(db, _ledger()).monthly_totals("u1", START, END)  # type: ignore[arg-type]

        assert result == []

    async def test_malformed_rpc_row_falls_back_to_python(self) -> None:
        db = FakeDatabase()
        db.rpc_result = [{"goal_id": "g1", "month": "2026-04-01", "saved": None, "withdrawn": "0"}]

        result = await ContributionMonthsProvider(db, _ledger()).monthly_totals("u1", START, END)  # type: ignore[arg-type]

        assert len(result) == 3
        assert result[0].saved == D("300.30")

    async def test_malformed_month_falls_back_to_python_instead_of_guessing_today(self) -> None:
        db = FakeDatabase()
        db.rpc_result = [{"goal_id": "g1", "month": "no-es-fecha", "saved": "1", "withdrawn": "0"}]

        result = await ContributionMonthsProvider(db, _ledger()).monthly_totals("u1", START, END)  # type: ignore[arg-type]

        assert [r.month for r in result] == [date(2026, 4, 1), date(2026, 6, 1), date(2026, 5, 1)]

    async def test_rpc_rows_are_sorted_by_goal_then_month(self) -> None:
        db = FakeDatabase()
        db.rpc_result = list(reversed(_RPC_ROWS))

        result = await ContributionMonthsProvider(db, InMemoryContributionLedger()).monthly_totals(  # type: ignore[arg-type]
            "u1", START, END
        )

        assert [(r.goal_id, r.month) for r in result] == [
            ("g1", date(2026, 4, 1)),
            ("g1", date(2026, 6, 1)),
            ("g2", date(2026, 5, 1)),
        ]
