"""Supabase Client - Implementation of DatabaseInterface for Supabase.

Uses Supabase's PostgreSQL database with Row Level Security.
"""

from typing import Any, cast

from postgrest.types import CountMethod
from supabase import AsyncClient, create_async_client

from app.core.logging import get_logger
from app.shared.interfaces.database import (
    DatabaseInterface,
    QueryConfig,
    QueryResult,
)

logger = get_logger(__name__)


def _rows(data: object) -> list[dict[str, Any]]:
    """Narrow the Supabase SDK's loosely-typed response rows to dict rows."""
    return cast("list[dict[str, Any]]", data)


class SupabaseClient(DatabaseInterface):
    """Supabase implementation of DatabaseInterface.

    Uses Supabase's AsyncClient for database operations.
    Supports Row Level Security (RLS) through JWT tokens.
    """

    def __init__(self, client: AsyncClient) -> None:
        """Initialize with an existing Supabase client.

        Args:
            client: Supabase AsyncClient instance.
        """
        self._client = client
        logger.info("Supabase client initialized")

    @classmethod
    async def create(cls, url: str, key: str) -> "SupabaseClient":
        """Factory method to create a SupabaseClient.

        Args:
            url: Supabase project URL.
            key: Supabase API key (anon or service role).

        Returns:
            Initialized SupabaseClient.
        """
        client = await create_async_client(url, key)
        return cls(client)

    async def select(
        self,
        table: str,
        config: QueryConfig | None = None,
    ) -> QueryResult:
        """Select records from a table.

        Args:
            table: Table name.
            config: Optional query configuration.

        Returns:
            QueryResult with the selected data.
        """
        config = config or QueryConfig()

        logger.info(
            "Selecting from table",
            table=table,
            limit=config.limit,
            has_filters=bool(config.filters),
        )

        query = self._client.table(table).select(config.select)

        # Apply filters
        for key, value in config.filters.items():
            query = query.eq(key, value)

        # Apply ordering
        if config.order_by:
            query = query.order(
                config.order_by,
                desc=not config.order_ascending,
            )

        # Apply pagination
        if config.limit:
            query = query.limit(config.limit)
        if config.offset:
            query = query.offset(config.offset)

        response = await query.execute()

        return QueryResult(
            data=_rows(response.data),
            count=len(response.data),
        )

    async def count(self, table: str, filters: dict[str, Any]) -> int:
        """Return the number of matching rows using a server-side exact count."""
        query = self._client.table(table).select("id", count=CountMethod.exact, head=True)
        for key, value in filters.items():
            query = query.eq(key, value)
        response = await query.execute()
        return response.count or 0

    async def insert(
        self,
        table: str,
        data: dict[str, Any] | list[dict[str, Any]],
    ) -> QueryResult:
        """Insert record(s) into a table.

        Args:
            table: Table name.
            data: Single record or list of records to insert.

        Returns:
            QueryResult with the inserted data.
        """
        logger.info(
            "Inserting into table",
            table=table,
            is_batch=isinstance(data, list),
        )

        response = await self._client.table(table).insert(data).execute()

        return QueryResult(
            data=_rows(response.data),
            count=len(response.data),
        )

    async def upsert(
        self,
        table: str,
        data: dict[str, Any] | list[dict[str, Any]],
        on_conflict: str,
    ) -> QueryResult:
        """Insert or update record(s) on conflict.

        Args:
            table: Table name.
            data: Single record or list of records.
            on_conflict: Comma-separated unique-constraint columns.

        Returns:
            QueryResult with the upserted data.
        """
        logger.info("Upserting into table", table=table, on_conflict=on_conflict)

        response = await self._client.table(table).upsert(
            data, on_conflict=on_conflict
        ).execute()

        return QueryResult(data=_rows(response.data), count=len(response.data))

    async def insert_ignore_duplicates(
        self,
        table: str,
        row: dict[str, Any],
        on_conflict: str,
    ) -> QueryResult:
        """Insert a row, ignoring it on conflict (``ON CONFLICT DO NOTHING``).

        Uses supabase-py's ``ignore_duplicates=True`` so a conflicting row is a
        no-op: the returned ``data`` is empty when the row already existed.
        """
        logger.info(
            "Inserting (ignore duplicates)", table=table, on_conflict=on_conflict
        )

        response = await self._client.table(table).upsert(
            row, on_conflict=on_conflict, ignore_duplicates=True
        ).execute()

        return QueryResult(data=_rows(response.data), count=len(response.data))

    async def update(
        self,
        table: str,
        data: dict[str, Any],
        filters: dict[str, Any],
    ) -> QueryResult:
        """Update records in a table.

        Args:
            table: Table name.
            data: Fields to update.
            filters: Filters to match records.

        Returns:
            QueryResult with the updated data.
        """
        logger.info(
            "Updating table",
            table=table,
            filters=filters,
        )

        query = self._client.table(table).update(data)

        for key, value in filters.items():
            query = query.eq(key, value)

        response = await query.execute()

        return QueryResult(
            data=_rows(response.data),
            count=len(response.data),
        )

    async def delete(
        self,
        table: str,
        filters: dict[str, Any],
    ) -> QueryResult:
        """Delete records from a table.

        Args:
            table: Table name.
            filters: Filters to match records.

        Returns:
            QueryResult with the deleted data.
        """
        logger.info(
            "Deleting from table",
            table=table,
            filters=filters,
        )

        query = self._client.table(table).delete()

        for key, value in filters.items():
            query = query.eq(key, value)

        response = await query.execute()

        return QueryResult(
            data=_rows(response.data),
            count=len(response.data),
        )

    async def execute_rpc(
        self,
        function_name: str,
        params: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Execute a stored procedure/function.

        Args:
            function_name: Name of the function to call.
            params: Optional parameters for the function.

        Returns:
            QueryResult with the function result.
        """
        logger.info(
            "Executing RPC",
            function=function_name,
            has_params=params is not None,
        )

        response = await self._client.rpc(
            function_name,
            params or {},
        ).execute()

        return QueryResult(
            data=_rows(response.data if isinstance(response.data, list) else [response.data]),
            count=1,
        )

    async def health_check(self) -> bool:
        """Check if the database connection is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            # Cheap round-trip that proves the DB answers (users exists per migration 001).
            await self._client.table("users").select("id").limit(1).execute()
            return True
        except Exception as e:  # noqa: BLE001 - readiness probe: report down, don't raise.
            logger.warning("Database health check failed", error=str(e))
            return False

    @property
    def provider(self) -> str:
        """Return the provider name."""
        return "supabase"

    @property
    def client(self) -> AsyncClient:
        """Return the underlying Supabase client for advanced operations."""
        return self._client
