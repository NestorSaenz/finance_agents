"""Database Interface - Abstract contract for database providers.

Implementations:
- SupabaseClient: Supabase (PostgreSQL + Auth + Realtime)
- PostgreSQLClient: Direct PostgreSQL connection
- MongoDBClient: MongoDB (if needed)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass
class QueryResult:
    """Result of a database query."""

    data: list[dict[str, Any]]
    count: int | None = None  # Total count (for pagination)
    error: str | None = None


@dataclass
class QueryConfig:
    """Configuration for database queries."""

    select: str = "*"
    limit: int | None = None
    offset: int | None = None
    order_by: str | None = None
    order_ascending: bool = True
    filters: dict[str, Any] = field(default_factory=dict)


class DatabaseInterface(ABC):
    """Abstract interface for database providers.

    This interface allows swapping database providers without changing
    the business logic. All database clients must implement this contract.

    Note: This is a simplified interface. For complex queries,
    you may need to extend it or use the underlying client directly.

    Example usage:
        ```python
        # In dependencies.py
        def get_database() -> DatabaseInterface:
            return SupabaseClient(
                url=settings.SUPABASE_URL,
                key=settings.SUPABASE_KEY,
            )

        # In repository
        class TransactionRepository:
            def __init__(self, db: DatabaseInterface):
                self.db = db

            async def get_by_user(self, user_id: str) -> list[dict]:
                result = await self.db.select(
                    table="transactions",
                    config=QueryConfig(
                        filters={"user_id": user_id},
                        order_by="created_at",
                        order_ascending=False,
                    )
                )
                return result.data
        ```
    """

    @abstractmethod
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

        Raises:
            DatabaseError: If the query fails.
        """
        pass

    @abstractmethod
    async def count(self, table: str, filters: dict[str, Any]) -> int:
        """Return the number of rows matching ``filters`` (server-side count).

        Uses the database's native count so no rows are transferred, avoiding a
        full-table fetch just to compute a length.

        Args:
            table: Table name.
            filters: Equality filters to match rows.

        Returns:
            The number of matching rows.
        """
        pass

    @abstractmethod
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

        Raises:
            DatabaseError: If the insertion fails.
        """
        pass

    @abstractmethod
    async def upsert(
        self,
        table: str,
        data: dict[str, Any] | list[dict[str, Any]],
        on_conflict: str,
    ) -> QueryResult:
        """Insert record(s), updating on conflict with ``on_conflict`` columns.

        Args:
            table: Table name.
            data: Single record or list of records.
            on_conflict: Comma-separated columns defining the unique constraint.

        Returns:
            QueryResult with the upserted data.
        """
        pass

    @abstractmethod
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

        Raises:
            DatabaseError: If the update fails.
        """
        pass

    @abstractmethod
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

        Raises:
            DatabaseError: If the deletion fails.
        """
        pass

    @abstractmethod
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

        Raises:
            DatabaseError: If the execution fails.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the database connection is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        pass

    @property
    @abstractmethod
    def provider(self) -> str:
        """Return the provider name (e.g., 'supabase', 'postgresql')."""
        pass
