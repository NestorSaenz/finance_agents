"""Quick connectivity + schema check for Supabase.

Verifies that the configured credentials work and that the schema has been
applied (queries the seeded `categories` table).

Run from project root:
    uv run python -m scripts.check_supabase
"""

import asyncio

from app.core.config import settings
from app.shared.clients.supabase_client import SupabaseClient
from app.shared.interfaces.database import QueryConfig


async def main() -> None:
    print("=" * 50)
    print("Supabase connectivity check")
    print("=" * 50)
    print(f"URL: {settings.SUPABASE_URL}")
    print(f"Key configured: {bool(settings.SUPABASE_KEY)}")

    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        print("[ERROR] SUPABASE_URL / SUPABASE_KEY not set in .env")
        return

    try:
        client = await SupabaseClient.create(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Could not create client: {e}")
        return

    try:
        result = await client.select("categories", QueryConfig(limit=10))
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] Query failed (schema not applied yet?): {e}")
        return

    print(f"\n[OK] Connected. 'categories' rows returned: {len(result.data)}")
    for row in result.data[:10]:
        print(f"  - {row.get('name')} ({row.get('type')})")

    if not result.data:
        print("\n[WARN] categories is empty -> apply database/schema.sql in the SQL Editor.")


if __name__ == "__main__":
    asyncio.run(main())
