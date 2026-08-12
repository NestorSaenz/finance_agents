"""Recurring-template use cases (business logic), including materialization."""

import calendar
import unicodedata
from datetime import date, datetime, timedelta

from app.core.exceptions import RecurringNotFoundError
from app.core.logging import get_logger
from app.shared.clock import current_today, local_date
from app.shared.serialization import decimal_to_db
from app.shared.types import Category, PaymentMethod, UserId
from app.src.cards.cycle import compute_cycle, next_payment_date
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import CreditCard
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.transactions.models import TransactionCreate
from app.src.users.interfaces import UserProfileServiceABC

from ..constants import MAX_CATCHUP_RUNS
from ..interfaces import RecurringRepositoryABC, RecurringServiceABC
from ..models import (
    RecurringCreate,
    RecurringTransaction,
    RecurringUpdate,
)

logger = get_logger(__name__)


class RecurringService(RecurringServiceABC):
    """Schedules recurring templates and materializes due ones into transactions.

    Depends on ``TransactionServiceABC`` to create the real movements (reusing all
    its logic) and on ``CreditCardServiceABC`` to derive the budget/impact date of
    a credit charge from the card's billing cycle.
    """

    def __init__(
        self,
        repository: RecurringRepositoryABC,
        transactions: TransactionServiceABC,
        cards: CreditCardServiceABC,
        profiles: UserProfileServiceABC,
    ) -> None:
        self._repository = repository
        self._transactions = transactions
        self._cards = cards
        self._profiles = profiles

    async def create_recurring(
        self, rec: RecurringCreate, user_id: UserId
    ) -> RecurringTransaction:
        # Compute the first run: the next occurrence of day_of_month on or after
        # today (clamped to the month length), so a day-31 template lands on the
        # last day of short months.
        next_run = _next_occurrence(rec.day_of_month, _today())
        scheduled = rec.model_copy(update={"next_run_date": next_run})
        return await self._repository.create(scheduled, user_id)

    async def list_recurring(self, user_id: UserId) -> list[RecurringTransaction]:
        return await self._repository.list_for_user(user_id)

    async def update_recurring(
        self, recurring_id: str, user_id: UserId, data: RecurringUpdate
    ) -> RecurringTransaction:
        await self._get(recurring_id, user_id)  # existence/ownership check
        patch: dict[str, object] = {}
        if data.amount is not None:
            patch["amount"] = decimal_to_db(data.amount)
        if data.description is not None:
            patch["description"] = data.description
        if data.transaction_type is not None:
            # Column is named "type" (matches the transactions table).
            patch["type"] = data.transaction_type.value
        if data.category is not None:
            patch["category"] = data.category
        if data.payment_method is not None:
            patch["payment_method"] = data.payment_method.value
            # Switching to cash can't keep a card link: clear it so the template
            # never carries a card_id it no longer pays with.
            if data.payment_method == PaymentMethod.EFECTIVO:
                patch["card_id"] = None
        if data.card_id is not None:
            patch["card_id"] = data.card_id
        # Explicit unlink wins over any card_id above (clears the link outright).
        if data.clear_card:
            patch["card_id"] = None
        if data.day_of_month is not None:
            patch["day_of_month"] = data.day_of_month
            # Changing the day reschedules the next occurrence off the new day.
            patch["next_run_date"] = _next_occurrence(
                data.day_of_month, _today()
            ).isoformat()
        if data.active is not None:
            patch["active"] = data.active
        if not patch:
            return await self._get(recurring_id, user_id)
        return await self._repository.update(recurring_id, user_id, patch)

    async def delete_recurring(
        self, recurring_id: str, user_id: UserId
    ) -> RecurringTransaction:
        rec = await self._get(recurring_id, user_id)  # confirm existence/ownership
        await self._repository.delete(recurring_id, user_id)
        logger.info("Recurring deleted", recurring_id=recurring_id, user_id=user_id)
        return rec

    async def set_active(
        self, recurring_id: str, user_id: UserId, active: bool
    ) -> RecurringTransaction:
        rec = await self._get(recurring_id, user_id)  # existence/ownership check
        patch: dict[str, object] = {"active": active}
        if active:
            # Resume must not backfill: recompute the next occurrence from today so
            # a template paused across several months fires once going forward, not
            # a flood of missed months. (active=False just pauses, no reschedule.)
            patch["next_run_date"] = _next_occurrence(
                rec.day_of_month, _today()
            ).isoformat()
        return await self._repository.update(recurring_id, user_id, patch)

    async def resolve_by_name(
        self, name: str, user_id: UserId
    ) -> RecurringTransaction | None:
        matches = await self.find_matches(name, user_id)
        return matches[0] if matches else None

    async def find_matches(
        self, name: str, user_id: UserId
    ) -> list[RecurringTransaction]:
        needle = _norm(name)
        if not needle:
            return []
        items = await self._repository.list_for_user(user_id)
        exact = [r for r in items if _norm(r.description) == needle]
        if exact:
            return exact
        # Partial match: the needle inside a stored name, or (only for stored names
        # long enough not to over-match) a stored name inside the needle. Mirrors
        # transaction_tools._matches_term's length gate so a short stored name
        # can't swallow a longer, unrelated request.
        return [
            r
            for r in items
            if (stored := _norm(r.description))
            and (needle in stored or (len(stored) >= 4 and stored in needle))
        ]

    async def run_due(self, now: datetime) -> int:
        # Materialize each template against ITS OWNER's local "today" (day-of-month
        # schedules must fire on the user's calendar day, not a single global tz).
        # Any user's local today is within ±1 day of the UTC date, so widen the
        # candidate window to ``now + 1 day``: this covers every timezone without
        # missing a due template, and a template not yet due in its owner's tz
        # (next_run_date > owner_today) simply materializes 0.
        cutoff = now.date() + timedelta(days=1)
        due = await self._repository.list_due(cutoff)
        # Cache each user's cards once per run so materializing several credit
        # templates for the same user doesn't refetch the card list every time.
        card_cache: dict[str, list[CreditCard]] = {}
        # Cache each owner's local "today" so N users cost N profile lookups, not
        # one per template.
        today_by_user: dict[UserId, date] = {}
        created = 0
        for rec in due:
            # Per-template failure isolation (batch-job boundary): one flaky
            # template must never abort the whole multi-user run. A broad catch
            # with context logging is acceptable here per the review skill.
            try:
                owner_today = today_by_user.get(rec.user_id)
                if owner_today is None:
                    # ``get_profile`` always yields a valid IANA tz (DEFAULT_TIMEZONE
                    # when the user never set one), so this preserves the old global
                    # behavior for those users and honors the real tz for the rest.
                    profile = await self._profiles.get_profile(rec.user_id)
                    owner_today = local_date(now, profile.timezone)
                    today_by_user[rec.user_id] = owner_today
                created += await self._materialize(rec, owner_today, card_cache)
            except Exception as exc:  # noqa: BLE001 - batch boundary, logged + continue
                logger.error(
                    "Recurring template failed; skipping",
                    recurring_id=rec.id,
                    user_id=rec.user_id,
                    error=str(exc),
                )
        return created

    async def _materialize(
        self,
        rec: RecurringTransaction,
        as_of: date,
        card_cache: dict[str, list[CreditCard]],
    ) -> int:
        """Create every occurrence of ``rec`` due on or before ``as_of``.

        Catches up occurrence-by-occurrence (bounded by ``MAX_CATCHUP_RUNS``).
        Each occurrence is materialized idempotently (keyed on
        ``(recurring_id, occurrence_date)``) and the advanced schedule is persisted
        after each — so an interruption, retry or duplicate run can't create the
        same occurrence twice. The schedule advances whether the insert created a
        row or hit an existing one (both mean "this occurrence is done").
        """
        category = await self._resolve_category(rec)
        card, payment_method, card_id = await self._resolve_card(rec, card_cache)

        count = 0
        created = 0
        next_run = rec.next_run_date
        while rec.active and next_run <= as_of and count < MAX_CATCHUP_RUNS:
            budget_date = self._budget_date(card, next_run)
            transaction = TransactionCreate(
                amount=rec.amount,
                description=rec.description,
                transaction_type=rec.transaction_type,
                transaction_date=next_run,
                budget_date=budget_date,
                category=category,
                payment_method=payment_method,
                card_id=card_id,
                recurring_id=rec.id,
                occurrence_date=next_run,
            )
            result = await self._transactions.materialize_occurrence(
                transaction, rec.user_id
            )
            if result is not None:
                created += 1
            # Advance regardless: a duplicate (None) is already materialized, so the
            # schedule must still move forward to stay idempotent under retries.
            last_run = next_run
            next_run = _advance(next_run, rec.day_of_month)
            await self._repository.update(
                rec.id,
                rec.user_id,
                {
                    "last_run_date": last_run.isoformat(),
                    "next_run_date": next_run.isoformat(),
                },
            )
            count += 1
        if created:
            logger.info(
                "Recurring materialized",
                recurring_id=rec.id,
                user_id=rec.user_id,
                created=created,
            )
        return created

    async def _resolve_category(self, rec: RecurringTransaction) -> Category | None:
        """Category for every occurrence of this template, resolved ONCE per run.

        If the template has no category, categorize its description a single time
        and reuse it across all catch-up occurrences — never per occurrence.
        """
        if rec.category is not None:
            return rec.category
        return await self._transactions.categorize(rec.description)

    async def _resolve_card(
        self,
        rec: RecurringTransaction,
        card_cache: dict[str, list[CreditCard]],
    ) -> tuple[CreditCard | None, PaymentMethod | None, str | None]:
        """Resolve the linked card ONCE, returning ``(card, payment_method, card_id)``.

        When a credit template's card can't be resolved (it was deleted), fall back
        to cash so we never create a ``credito`` movement with a dangling card_id:
        payment_method becomes ``efectivo`` and card_id is dropped. The FK's
        ON DELETE SET NULL usually nulls card_id first, but this guards the window
        where it hasn't.
        """
        if rec.card_id is None:
            return None, rec.payment_method, None
        cards = card_cache.get(rec.user_id)
        if cards is None:
            cards = await self._cards.list_cards(rec.user_id)
            card_cache[rec.user_id] = cards
        card = next((c for c in cards if c.id == rec.card_id), None)
        if card is None:
            logger.warning(
                "Recurring card unresolved; materializing as efectivo",
                recurring_id=rec.id,
                user_id=rec.user_id,
                card_id=rec.card_id,
            )
            return None, PaymentMethod.EFECTIVO, None
        return card, rec.payment_method, rec.card_id

    def _budget_date(self, card: CreditCard | None, run_date: date) -> date:
        """Budget/impact date for an occurrence.

        For a credit charge (a resolved card), the payment date of the statement
        that contains it, derived from the card's cutoff/payment cycle — so it hits
        the month it is actually paid. For cash/debit (no card), the run date.
        """
        if card is None:
            return run_date
        _, cycle_end = compute_cycle(card.cutoff_day, run_date)
        return next_payment_date(card.payment_day, cycle_end)

    async def _get(
        self, recurring_id: str, user_id: UserId
    ) -> RecurringTransaction:
        rec = await self._repository.get_by_id(recurring_id, user_id)
        if rec is None:
            raise RecurringNotFoundError(recurring_id)
        return rec


def _today() -> date:
    # The request-scoped local day of the user in the current chat turn (UTC
    # outside a bound turn, e.g. the REST create path), so day-of-month schedules
    # fire on the user's local calendar day.
    return current_today()


def _clamp_day(year: int, month: int, day: int) -> date:
    """Return ``day`` of the month, clamped to the month's last day."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _add_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _next_occurrence(day_of_month: int, today: date) -> date:
    """Next occurrence of ``day_of_month`` on or after ``today`` (clamped).

    If this month's clamped day is still on or after today, use it; otherwise
    roll to next month.
    """
    this_month = _clamp_day(today.year, today.month, day_of_month)
    if this_month >= today:
        return this_month
    ny, nm = _add_month(today.year, today.month)
    return _clamp_day(ny, nm, day_of_month)


def _advance(current: date, day_of_month: int) -> date:
    """The next month's clamped ``day_of_month`` after ``current``.

    Uses ``day_of_month`` (not ``current.day``) so a day-31 template that clamped
    to Feb 28 goes back to Mar 31, not Mar 28.
    """
    ny, nm = _add_month(current.year, current.month)
    return _clamp_day(ny, nm, day_of_month)


def _norm(text: str) -> str:
    """Lowercase and strip accents so 'Salário'/'salario' compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))
