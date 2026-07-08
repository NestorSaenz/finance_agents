"""End-to-end smoke test of the transaction data layer against real Supabase.

Creates a transaction for DEMO_USER_ID and reads it back. Uses an explicit
category to keep this test focused on the DB path (no embedding/vector calls).

Run from project root:
    uv run python scripts/smoke_transaction.py
"""

import asyncio
from datetime import date
from decimal import Decimal

from app.core.config import settings
from app.shared.dependencies import close_database, get_database, init_database
from app.shared.types import CategoryType, TransactionType
from app.src.transactions.models import TransactionCreate
from app.src.transactions.repositories.transaction_repository import TransactionRepository


async def main() -> None:
    print("=" * 50)
    print("Transaction data-layer smoke test")
    print("=" * 50)
    print(f"DEMO_USER_ID: {settings.DEMO_USER_ID or '(not set!)'}")

    if not settings.DEMO_USER_ID:
        print("[ERROR] DEMO_USER_ID is empty. Set it in .env to a real users.id UUID.")
        return

    await init_database()
    repo = TransactionRepository(get_database())

    try:
        new_tx = TransactionCreate(
            amount=Decimal("50.00"),
            description="pizza de prueba (smoke test)",
            transaction_type=TransactionType.EXPENSE,
            transaction_date=date.today(),
            category=CategoryType.RESTAURANTES,
        )
        created = await repo.create(new_tx, settings.DEMO_USER_ID)
        print(f"\n[OK] Created transaction: id={created.id}")
        print(f"     {created.description} | ${created.amount} | {created.category.value}")

        items = await repo.list_page(settings.DEMO_USER_ID, limit=5, offset=0)
        print(f"\n[OK] Listed {len(items)} recent transaction(s):")
        for t in items:
            print(f"  - {t.transaction_date} | {t.description} | ${t.amount} | {t.category.value}")
    except Exception as e:  # noqa: BLE001
        print(f"\n[ERROR] {type(e).__name__}: {e}")
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
