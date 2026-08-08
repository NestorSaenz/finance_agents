"""Category management tools for conversational data operations.

A single ``manage_category`` tool (rename/merge or delete) so the LLM's schema
payload stays small. Categories are free-text on transactions and budgets (no
dedicated table), so a rename/delete is a bulk operation across BOTH: this
toolkit orchestrates the transaction and budget services.

Security: ``user_id`` comes from the authenticated context at dispatch time and
is never part of the schema nor read from the model's arguments.
"""

from typing import Any

from app.core.logging import get_logger
from app.shared.types import UserId, normalize_category
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.transactions.interfaces import TransactionServiceABC

logger = get_logger(__name__)

MANAGE_CATEGORY_TOOL = "manage_category"

CATEGORY_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": MANAGE_CATEGORY_TOOL,
            "description": (
                "Renombra/fusiona o elimina una categoría COMPLETA (afecta todos sus "
                "movimientos y su tope). action='rename' requiere new_name. "
                "action='delete': si la categoría tiene movimientos y no indicas qué "
                "hacer con ellos, el sistema te preguntará; muévelos con move_to o "
                "bórralos con delete_movements=true."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["rename", "delete"],
                        "description": "Renombrar/fusionar o eliminar",
                    },
                    "category": {
                        "type": "string",
                        "description": "Categoría a renombrar o eliminar",
                    },
                    "new_name": {
                        "type": "string",
                        "description": "Nuevo nombre (solo action='rename')",
                    },
                    "move_to": {
                        "type": "string",
                        "description": "Al eliminar: categoría destino para sus movimientos",
                    },
                    "delete_movements": {
                        "type": "boolean",
                        "description": "Al eliminar: true para borrar también los movimientos",
                    },
                },
                "required": ["action", "category"],
            },
        },
    }
]


class CategoryToolkit:
    """Exposes bulk category management (rename/delete) across transactions + topes."""

    def __init__(
        self, transactions: TransactionServiceABC, budgets: BudgetServiceABC
    ) -> None:
        self._transactions = transactions
        self._budgets = budgets

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return CATEGORY_TOOL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        if name != MANAGE_CATEGORY_TOOL:
            raise ValueError(f"Unknown category tool: {name}")
        action = str(arguments.get("action", "")).strip().lower()
        # normalize_category("") -> "otros", so guard the raw value first; otherwise a
        # missing category would silently operate on the user's "otros" category.
        category_raw = str(arguments.get("category", "")).strip()
        category = normalize_category(category_raw) if category_raw else ""
        if not category:
            return "¿Qué categoría quieres gestionar?"
        if action == "rename":
            return await self._rename(category, arguments, user_id)
        if action == "delete":
            return await self._delete(category, arguments, user_id)
        return "Acción no reconocida. Usa 'rename' (renombrar) o 'delete' (eliminar)."

    async def _rename(
        self, category: str, args: dict[str, Any], user_id: UserId
    ) -> str:
        # normalize_category maps empty -> "otros", so only normalize a real value;
        # otherwise new_name/move_to would never be falsy and the guards below break.
        new_name_raw = str(args.get("new_name", "")).strip()
        new_name = normalize_category(new_name_raw) if new_name_raw else ""
        if not new_name:
            return f"¿A qué nombre quieres renombrar la categoría '{category}'?"
        if new_name == category:
            return "El nombre nuevo es igual al actual; no hay nada que cambiar."
        moved = await self._transactions.recategorize(user_id, category, new_name)
        topes = await self._budgets.recategorize(user_id, category, new_name)
        logger.info(
            "Category renamed",
            old=category, new=new_name, movements=moved, topes=topes, user_id=user_id,
        )
        tope_note = " y su tope" if topes else ""
        return (
            f"✅ Renombré '{category}' a '{new_name}': {moved} movimiento(s){tope_note} "
            f"ahora están en '{new_name}'."
        )

    async def _delete(
        self, category: str, args: dict[str, Any], user_id: UserId
    ) -> str:
        move_to_raw = str(args.get("move_to", "")).strip()
        move_to = normalize_category(move_to_raw) if move_to_raw else ""
        # Moving to the same category is a no-op; drop it so we don't fall through
        # to deleting the very movements the user meant to keep.
        if move_to == category:
            move_to = ""
        delete_movements = bool(args.get("delete_movements", False))
        count = await self._transactions.count_by_category(user_id, category)

        # Movements exist but no decision yet: ask instead of guessing.
        if count > 0 and not move_to and not delete_movements:
            return (
                f"La categoría '{category}' tiene {count} movimiento(s). ¿Qué hago con "
                f"ellos: los muevo a otra categoría (dime cuál), los dejo en 'otros', o "
                f"los elimino también? El tope de '{category}' se borrará."
            )

        topes = await self._budgets.delete_by_category(user_id, category)
        logger.info(
            "Category delete", category=category, count=count, move_to=move_to or None,
            delete_movements=delete_movements, topes=topes, user_id=user_id,
        )
        tope_note = " y su tope" if topes else ""

        if move_to and move_to != category:
            moved = await self._transactions.recategorize(user_id, category, move_to)
            return (
                f"✅ Eliminé la categoría '{category}'{tope_note}: moví {moved} "
                f"movimiento(s) a '{move_to}'."
            )

        deleted = await self._transactions.delete_by_category(user_id, category)
        if deleted or count:
            return (
                f"✅ Eliminé la categoría '{category}'{tope_note} y sus {deleted} "
                f"movimiento(s)."
            )
        return f"✅ Eliminé la categoría '{category}'{tope_note}."
