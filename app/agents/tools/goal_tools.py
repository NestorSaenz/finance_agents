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

from app.core.exceptions import GoalWithdrawalExceedsBalanceError
from app.core.logging import get_logger
from app.shared.clock import current_today
from app.shared.types import GoalType, UserId
from app.src.goals.interfaces import GoalServiceABC
from app.src.goals.models import Goal, GoalCreate, GoalProgress

logger = get_logger(__name__)

CREATE_GOAL_TOOL = "create_goal"
QUERY_GOALS_TOOL = "query_goals"
CONTRIBUTE_GOAL_TOOL = "contribute_to_goal"
WITHDRAW_GOAL_TOOL = "withdraw_from_goal"
SET_GOAL_AMOUNT_TOOL = "set_goal_amount"
REMOVE_CONTRIBUTION_TOOL = "remove_goal_contribution"
UPDATE_GOAL_TOOL = "update_goal"
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
                "porcentaje y si va en camino). Úsala para '¿cómo van mis metas?'. "
                "Si el usuario pregunta por los aportes/abonos de UNA meta concreta "
                "('¿cuánto he aportado a mi viaje?'), pasa 'goal_name'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {
                        "type": "string",
                        "description": (
                            "Nombre de la meta para ver los aportes de UNA meta específica"
                        ),
                    },
                    "goal_target_amount": {
                        "type": "number",
                        "description": (
                            "Monto objetivo de la meta; úsalo SOLO para desambiguar si "
                            "hay varias metas con el mismo nombre"
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": CONTRIBUTE_GOAL_TOOL,
            "description": (
                "Abona un monto a una meta existente (identificada por su nombre). "
                "Úsala cuando el usuario dice que aportó o ahorró para una meta "
                "(p. ej. 'en junio aporté 2000 a mi viaje')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {"type": "string", "description": "Nombre de la meta"},
                    "amount": {"type": "number", "description": "Monto a abonar, mayor a 0"},
                    "date": {
                        "type": "string",
                        "description": (
                            "Fecha del abono YYYY-MM-DD si el usuario la indica "
                            "(p. ej. 'en junio aporté X'); por defecto, hoy."
                        ),
                    },
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
            "name": WITHDRAW_GOAL_TOOL,
            "description": (
                "Retira/saca dinero de una meta existente (identificada por su "
                "nombre): reduce lo ahorrado y ese dinero VUELVE al disponible del "
                "usuario. Úsala cuando el usuario dice 'retira/saca $X del fondo Y'. "
                "NO es un ingreso: nunca registres un ingreso por un retiro. Distíntela "
                "de remove_goal_contribution, que solo borra un aporte mal registrado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {"type": "string", "description": "Nombre de la meta"},
                    "amount": {"type": "number", "description": "Monto a retirar, mayor a 0"},
                    "date": {
                        "type": "string",
                        "description": (
                            "Fecha del retiro YYYY-MM-DD si el usuario la indica; "
                            "por defecto, hoy."
                        ),
                    },
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
            "name": SET_GOAL_AMOUNT_TOOL,
            "description": (
                "Ajusta/corrige/FIJA el total ahorrado de una meta a un valor EXACTO "
                "(identificada por su nombre). Úsala cuando el usuario dice cuánto TIENE "
                "ahora la meta, no cuánto añadir: 'ajusta/corrige/deja el ahorro de X en "
                "$Y', 'la meta X tiene $Y', 'pon la meta X en 0'. Reconcilia el total con "
                "sus aportes. NO la uses para aportar (contribute_to_goal SUMA) ni para "
                "retirar (withdraw_from_goal RESTA); nunca borres aportes para cuadrar el total."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {"type": "string", "description": "Nombre de la meta"},
                    "amount": {
                        "type": "number",
                        "description": "Total ahorrado deseado (0 o mayor)",
                    },
                    "date": {
                        "type": "string",
                        "description": (
                            "Fecha YYYY-MM-DD del ajuste si el usuario la indica; "
                            "por defecto, hoy."
                        ),
                    },
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
            "name": REMOVE_CONTRIBUTION_TOOL,
            "description": (
                "Borra un aporte puntual de una meta (por su monto y, si hace falta, "
                "su fecha). NO borra la meta (eso es delete_goal). Úsala solo tras "
                "confirmar con el usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {"type": "string", "description": "Nombre de la meta"},
                    "amount": {
                        "type": "number",
                        "description": "Monto del aporte a borrar, mayor a 0",
                    },
                    "date": {
                        "type": "string",
                        "description": (
                            "Fecha del aporte YYYY-MM-DD; úsala SOLO para desambiguar "
                            "si hay varios aportes del mismo monto"
                        ),
                    },
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
            "name": UPDATE_GOAL_TOOL,
            "description": (
                "Cambia los DATOS de una meta existente: su nombre, su MONTO OBJETIVO "
                "o su fecha objetivo ('sube el objetivo del fondo de emergencia a 15M', "
                "'renombra la meta X'). La identificas por su nombre. NO la uses para "
                "abonar/aportar dinero (eso es contribute_to_goal)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {"type": "string", "description": "Nombre actual de la meta"},
                    "new_name": {"type": "string", "description": "Nuevo nombre (opcional)"},
                    "new_target_amount": {
                        "type": "number",
                        "description": "Nuevo monto objetivo, mayor a 0 (opcional)",
                    },
                    "new_target_date": {
                        "type": "string",
                        "description": "Nueva fecha objetivo YYYY-MM-DD (opcional)",
                    },
                    "goal_target_amount": {
                        "type": "number",
                        "description": (
                            "Monto objetivo ACTUAL; úsalo SOLO para desambiguar si hay "
                            "varias metas con el mismo nombre"
                        ),
                    },
                },
                "required": ["goal_name"],
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
            return await self._query(arguments, user_id)
        if name == CONTRIBUTE_GOAL_TOOL:
            return await self._contribute(arguments, user_id)
        if name == WITHDRAW_GOAL_TOOL:
            return await self._withdraw(arguments, user_id)
        if name == SET_GOAL_AMOUNT_TOOL:
            return await self._set_amount(arguments, user_id)
        if name == REMOVE_CONTRIBUTION_TOOL:
            return await self._remove_contribution(arguments, user_id)
        if name == UPDATE_GOAL_TOOL:
            return await self._update(arguments, user_id)
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

    async def _query(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("goal_name", "")).strip()
        if name:
            return await self._query_one(name, args, user_id)

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

    async def _query_one(self, name: str, args: dict[str, Any], user_id: UserId) -> str:
        """List a single goal's dated contributions, newest first."""
        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "consultar")

        contribs = await self._service.list_contributions(goal.id, user_id)
        header = (
            f"Meta '{goal.name}': llevas ${goal.current_amount} de ${goal.target_amount}."
        )
        if not contribs:
            return f"{header} Aún no tiene aportes registrados."
        lines = [f"  - ${c.amount} ({c.contribution_date})" for c in contribs]
        return f"{header}\n" + "\n".join(lines)

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

        # Honor the date the user stated ("en junio aporté X"); default to today.
        today = current_today()
        contribution_date = _opt_date(args.get("date")) or today
        updated = await self._service.contribute(
            goal.id, user_id, amount, contribution_date
        )
        done = " 🎉 ¡Meta completada!" if updated.current_amount >= updated.target_amount else ""
        when = "" if contribution_date == today else f" ({contribution_date})"
        return (
            f"✅ Aboné ${amount} a '{updated.name}'{when}. "
            f"Llevas ${updated.current_amount} de ${updated.target_amount}.{done}"
        )

    async def _withdraw(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("goal_name", "")).strip()
        try:
            amount = _to_decimal(args.get("amount"))
        except ValueError:
            return "No pude registrar el retiro: el monto no es válido."
        if amount <= 0:
            return "El monto a retirar debe ser mayor a 0."

        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "retirar")

        # Honor the date the user stated; default to today.
        today = current_today()
        withdrawal_date = _opt_date(args.get("date")) or today
        try:
            updated = await self._service.withdraw_from_goal(
                goal.id, user_id, amount, withdrawal_date
            )
        except GoalWithdrawalExceedsBalanceError as e:
            return (
                f"No puedes retirar ${amount} de '{goal.name}': solo tiene "
                f"${e.available} ahorrados. Indica un monto igual o menor."
            )
        logger.info("Tool withdrew from goal", goal_id=goal.id, user_id=user_id)
        return (
            f"🏦 Retiré ${amount} de tu meta «{updated.name}». Ese dinero vuelve a "
            f"tu disponible. Ahora llevas ${updated.current_amount} de "
            f"${updated.target_amount}."
        )

    async def _set_amount(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("goal_name", "")).strip()
        try:
            amount = _to_decimal(args.get("amount"))
        except ValueError:
            return "No pude ajustar la meta: el monto no es válido."
        if amount < 0:
            return "El total ahorrado de la meta no puede ser negativo."

        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "ajustar")

        # Honor the date the user stated; default to today (used only when the
        # adjustment moves real money, i.e. writes a contribution/withdrawal).
        on_date = _opt_date(args.get("date")) or current_today()
        updated = await self._service.set_goal_amount(
            goal.id, user_id, amount, on_date
        )
        logger.info("Tool set goal amount", goal_id=goal.id, user_id=user_id)
        return (
            f"✅ Ajusté tu meta «{updated.name}»: ahora tiene ${updated.current_amount} "
            f"ahorrados (de ${updated.target_amount})."
        )

    async def _remove_contribution(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("goal_name", "")).strip()
        try:
            amount = _to_decimal(args.get("amount"))
        except ValueError:
            return "No pude borrar el aporte: el monto no es válido."
        if amount <= 0:
            return "El monto del aporte a borrar debe ser mayor a 0."

        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "editar")

        contribution_date = _opt_date(args.get("date"))
        updated = await self._service.remove_contribution(
            goal.id, user_id, amount, contribution_date
        )
        if updated is None:
            when = f" del {contribution_date}" if contribution_date else ""
            return (
                f"No encontré un aporte de ${amount}{when} en esa meta. "
                "Revisa el monto (y la fecha) del aporte que quieres borrar."
            )
        logger.info("Tool removed goal contribution", goal_id=goal.id, user_id=user_id)
        return (
            f"🗑️ Borré el aporte de ${amount} de '{updated.name}'. "
            f"Ahora llevas ${updated.current_amount} de ${updated.target_amount}."
        )

    async def _update(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("goal_name", "")).strip()
        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "actualizar")

        new_name = str(args.get("new_name", "")).strip() or None
        new_target = _opt_decimal(args.get("new_target_amount"))
        new_date = _opt_date(args.get("new_target_date"))
        if new_name is None and new_target is None and new_date is None:
            return "¿Qué quieres cambiar de la meta? (nombre, monto objetivo o fecha)"
        if new_target is not None and new_target <= 0:
            return "El monto objetivo debe ser mayor a 0."

        updated = await self._service.update_goal(
            goal.id,
            user_id,
            name=new_name,
            target_amount=new_target,
            target_date=new_date,
        )
        return (
            f"✏️ Actualicé la meta '{updated.name}' — objetivo ${updated.target_amount} "
            f"(llevas ${updated.current_amount})."
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


def _opt_date(value: Any) -> date | None:
    """Parse a 'YYYY-MM-DD' string to a date, or None if absent/invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
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
