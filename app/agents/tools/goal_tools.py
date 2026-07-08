"""Goal tools for conversational data operations.

Thin wrappers over ``GoalService`` exposed to the LLM as callable tools.

Security: ``user_id`` is supplied by the toolkit from the authenticated context
at dispatch time and is NEVER part of the tool schema nor read from the model's
arguments. Contributions reference a goal by NAME (resolved to an id server-side)
so the model never handles internal ids.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.core.logging import get_logger
from app.shared.types import GoalType, UserId
from app.src.goals.interfaces import GoalServiceABC
from app.src.goals.models import Goal, GoalCreate, GoalProgress

logger = get_logger(__name__)

CREATE_GOAL_TOOL = "create_goal"
QUERY_GOALS_TOOL = "query_goals"
CONTRIBUTE_GOAL_TOOL = "contribute_to_goal"
DELETE_GOAL_TOOL = "delete_goal"

GOAL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": CREATE_GOAL_TOOL,
            "description": (
                "Crea una meta financiera de ahorro para el usuario. Úsala cuando el "
                "usuario quiere ahorrar para algo (un viaje, un fondo, una compra)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre de la meta"},
                    "target_amount": {"type": "number", "description": "Monto objetivo, mayor a 0"},
                    "goal_type": {
                        "type": "string",
                        "enum": [
                            "savings",
                            "debt_payoff",
                            "investment",
                            "purchase",
                            "emergency_fund",
                            "other",
                        ],
                        "description": "Tipo de meta (por defecto ahorro)",
                    },
                    "target_date": {
                        "type": "string",
                        "description": "Fecha límite ISO YYYY-MM-DD (opcional)",
                    },
                },
                "required": ["name", "target_amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": QUERY_GOALS_TOOL,
            "description": (
                "Consulta las metas del usuario y su progreso (ahorrado, objetivo, "
                "porcentaje y si va en camino). Úsala para '¿cómo van mis metas?'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": CONTRIBUTE_GOAL_TOOL,
            "description": (
                "Abona un monto a una meta existente (identificada por su nombre). "
                "Úsala cuando el usuario dice que aportó o ahorró para una meta."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {"type": "string", "description": "Nombre de la meta"},
                    "amount": {"type": "number", "description": "Monto a abonar, mayor a 0"},
                    "goal_target_amount": {
                        "type": "number",
                        "description": (
                            "Monto objetivo de la meta; úsalo SOLO para desambiguar si "
                            "hay varias metas con el mismo nombre"
                        ),
                    },
                },
                "required": ["goal_name", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": DELETE_GOAL_TOOL,
            "description": (
                "Elimina una meta existente (identificada por su nombre). Úsala SOLO "
                "tras identificar la meta correcta y que el usuario confirme "
                "explícitamente que quiere eliminarla. NO la uses para abonar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {"type": "string", "description": "Nombre de la meta"},
                    "goal_target_amount": {
                        "type": "number",
                        "description": (
                            "Monto objetivo de la meta; úsalo SOLO para desambiguar si "
                            "hay varias metas con el mismo nombre"
                        ),
                    },
                },
                "required": ["goal_name"],
            },
        },
    },
]


class GoalToolkit:
    """Exposes goal tools to the LLM and dispatches its tool calls."""

    def __init__(self, service: GoalServiceABC) -> None:
        self._service = service

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return GOAL_TOOL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        if name == CREATE_GOAL_TOOL:
            return await self._create(arguments, user_id)
        if name == QUERY_GOALS_TOOL:
            return await self._query(user_id)
        if name == CONTRIBUTE_GOAL_TOOL:
            return await self._contribute(arguments, user_id)
        if name == DELETE_GOAL_TOOL:
            return await self._delete(arguments, user_id)
        raise ValueError(f"Unknown goal tool: {name}")

    async def _create(self, args: dict[str, Any], user_id: UserId) -> str:
        try:
            goal = GoalCreate(
                name=str(args.get("name", "")).strip(),
                target_amount=_to_decimal(args.get("target_amount")),
                goal_type=_to_goal_type(args.get("goal_type")),
                target_date=_to_date(args.get("target_date")),
            )
        except (ValidationError, ValueError) as e:
            logger.warning("Invalid goal args from tool", error=str(e))
            return "No pude crear la meta: revisa el nombre y el monto objetivo (mayor a 0)."

        created = await self._service.create_goal(goal, user_id)
        target = f" para {created.target_date}" if created.target_date else ""
        return f"✅ Meta creada: {created.name} — objetivo ${created.target_amount}{target}."

    async def _query(self, user_id: UserId) -> str:
        goals, total = await self._service.list_goals(user_id, page=1, page_size=20)
        if not goals:
            return "No tienes metas configuradas."

        lines: list[str] = []
        for goal in goals:
            try:
                progress = await self._service.get_progress(goal.id, user_id)
                lines.append(_format_progress(progress))
            except Exception as e:  # noqa: BLE001 - one goal failing shouldn't drop the rest.
                logger.warning("Goal progress failed", goal_id=goal.id, error=str(e))
                lines.append(f"- {goal.name}: ${goal.current_amount} de ${goal.target_amount}")
        return f"{total} meta(s):\n" + "\n".join(lines)

    async def _contribute(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("goal_name", "")).strip()
        try:
            amount = _to_decimal(args.get("amount"))
        except ValueError:
            return "No pude registrar el abono: el monto no es válido."
        if amount <= 0:
            return "El monto a abonar debe ser mayor a 0."

        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "abonar")

        updated = await self._service.contribute(goal.id, user_id, amount)
        done = " 🎉 ¡Meta completada!" if updated.current_amount >= updated.target_amount else ""
        return (
            f"✅ Aboné ${amount} a '{updated.name}'. "
            f"Llevas ${updated.current_amount} de ${updated.target_amount}.{done}"
        )

    async def _delete(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("goal_name", "")).strip()
        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "eliminar")

        await self._service.delete_goal(goal.id, user_id)
        logger.info("Tool deleted goal", goal_id=goal.id, user_id=user_id)
        return f"🗑️ Eliminé la meta '{goal.name}'."

    async def _resolve_goals(self, name: str, user_id: UserId) -> list[Goal]:
        """Return ALL goals matching ``name`` at the best tier, or [].

        Tries exact match, then substring, then significant-word overlap so
        "vacaciones de la playa" still resolves to "vacaciones playa" (filler
        words like de/la/para are ignored). Returning every match (not just the
        first) lets the caller disambiguate when several share a name.
        """
        if not name:
            return []
        goals, _ = await self._service.list_goals(user_id, page=1, page_size=50)
        target = name.lower().strip()

        exact = [g for g in goals if g.name.lower() == target]
        if exact:
            return exact
        substr = [
            g for g in goals if target in g.name.lower() or g.name.lower() in target
        ]
        if substr:
            return substr

        target_words = _significant_words(target)
        if not target_words:
            return []
        return [
            g
            for g in goals
            if (gw := _significant_words(g.name.lower()))
            and (target_words <= gw or gw <= target_words)
        ]

    def _pick_goal(
        self, matches: list[Goal], target_amount: Decimal | None
    ) -> Goal | None:
        """Disambiguate by target amount; return the single goal or None."""
        if target_amount is not None:
            filtered = [g for g in matches if g.target_amount == target_amount]
            if filtered:
                matches = filtered
        return matches[0] if len(matches) == 1 else None


_FILLER_WORDS = frozenset(
    {"de", "la", "el", "los", "las", "para", "un", "una", "del", "al", "mi", "mis"}
)


def _significant_words(text: str) -> frozenset[str]:
    """Return the meaningful words of ``text`` (filler words removed)."""
    return frozenset(w for w in text.split() if w and w not in _FILLER_WORDS)


def _format_progress(progress: GoalProgress) -> str:
    """Format a goal's progress for the LLM."""
    goal = progress.goal
    track = "✅ en camino" if progress.on_track else "⚠️ atrasada"
    status = " (completada)" if progress.is_completed else f", {track}"
    return (
        f"- {goal.name}: ${goal.current_amount} de ${goal.target_amount} "
        f"({progress.percentage:.0f}%){status}"
    )


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"Invalid amount: {value!r}") from e


def _opt_decimal(value: Any) -> Decimal | None:
    """Parse an optional decimal; None/invalid yields None."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _ambiguous_message(name: str, matches: list[Goal], action: str) -> str:
    """Ask which goal when several share a name (distinguished by target)."""
    options = "; ".join(
        f"objetivo ${g.target_amount} (llevas ${g.current_amount})" for g in matches
    )
    return (
        f"Tienes {len(matches)} metas llamadas '{name}': {options}. "
        f"¿Cuál quieres {action}? Dime el monto objetivo para identificarla."
    )


def _to_goal_type(value: Any) -> GoalType:
    if not value:
        return GoalType.SAVINGS
    try:
        return GoalType(str(value).lower())
    except ValueError:
        return GoalType.SAVINGS


def _to_date(value: Any) -> date | None:
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None
