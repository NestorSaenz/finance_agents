"""Goal tools for conversational data operations.

Thin wrappers over ``GoalService`` exposed to the LLM as callable tools.

Security: ``user_id`` is supplied by the toolkit from the authenticated context
at dispatch time and is NEVER part of the tool schema nor read from the model's
arguments. Contributions reference a goal by NAME (resolved to an id server-side)
so the model never handles internal ids.
"""

import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Final, TypeVar

from pydantic import ValidationError

from app.agents.tools.names import (
    CLEAR_GOAL_PLAN_TOOL,
    CONTRIBUTE_GOAL_TOOL,
    CREATE_GOAL_TOOL,
    DELETE_GOAL_TOOL,
    PAUSE_GOAL_TOOL,
    QUERY_GOALS_TOOL,
    REMOVE_CONTRIBUTION_TOOL,
    RESUME_GOAL_TOOL,
    SET_GOAL_AMOUNT_TOOL,
    SET_GOAL_PLAN_TOOL,
    UPDATE_GOAL_TOOL,
    WITHDRAW_GOAL_TOOL,
)
from app.core.config import settings
from app.core.exceptions import (
    FinanceGPTError,
    GoalNotFoundError,
    GoalWithdrawalExceedsBalanceError,
    InvalidAmountError,
    InvalidPlanPeriodError,
)
from app.core.logging import get_logger
from app.shared.clock import current_today
from app.shared.periods import ESTE_MES, MES_PASADO, period_label
from app.shared.text_match import names_match, normalize
from app.shared.turn import confirmation_asked_this_turn, mark_confirmation_asked
from app.shared.types import (
    CurrencyType,
    GoalPlanClearMode,
    GoalPlanScope,
    GoalStatus,
    GoalType,
    UserId,
)
from app.src.goals.interfaces import GoalServiceABC
from app.src.goals.models import Goal, GoalCreate, GoalMonthLine, GoalPlanStatus, GoalProgress
from app.src.goals.planning import (
    add_months,
    first_of_month,
    goal_created_month,
    last_of_month,
    month_key,
)

logger = get_logger(__name__)

# A month as the model passes it: "YYYY-MM" (a full "YYYY-MM-DD" date is tolerated).
_MONTH_ARG: re.Pattern[str] = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])(?:-\d{2})?$")
_MIN_PLAN_YEAR: Final = 1900
_GOALS_PAGE_SIZE: Final = 20
_E = TypeVar("_E", GoalPlanScope, GoalPlanClearMode)


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
                    "monthly_plan": {
                        "type": "number",
                        "description": (
                            "Monto que el usuario PLANEA abonar cada mes a esta meta "
                            "(opcional, mayor a 0): se guarda como plan mensual desde "
                            "este mes. NO es un aporte."
                        ),
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
                "porcentaje y si va en camino) y, por cada meta, su PLAN del mes (planeado vs "
                "aportado vs faltan) con un TOTAL PLAN METAS. Úsala para '¿cómo van mis "
                "metas?'. Si el usuario pregunta por los aportes/abonos de UNA meta concreta "
                "('¿cuánto he aportado a mi viaje?'), pasa 'goal_name'; con 'months' además "
                "ve el mes a mes de esa meta (plan vs aportado)."
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
                    "period": {
                        "type": "string",
                        "description": (
                            "Mes del plan a mostrar: 'este_mes' (por defecto), 'mes_pasado' "
                            "o 'YYYY-MM'."
                        ),
                    },
                    "months": {
                        "type": "integer",
                        "description": (
                            "Con goal_name: cuántos meses ANTERIORES al período incluir en "
                            "el mes a mes de esa meta (p. ej. 6). Sin goal_name se ignora."
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
    {
        "type": "function",
        "function": {
            "name": PAUSE_GOAL_TOOL,
            "description": (
                "Pausa una meta existente (la 'aparca'): deja de estar activa pero NO "
                "se borra ni se pierde lo ahorrado. Úsala cuando el usuario quiere "
                "pausar/suspender/congelar una meta ('pausa mi meta X', 'dejo de "
                "ahorrar para X por ahora'). Reactívala luego con resume_goal. NO la "
                "elimina (eso es delete_goal)."
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
    {
        "type": "function",
        "function": {
            "name": RESUME_GOAL_TOOL,
            "description": (
                "Reactiva/reanuda una meta que estaba pausada ('reactiva mi meta X', "
                "'vuelvo a ahorrar para X'). Vuelve a estar activa (o completada si ya "
                "alcanzó su objetivo)."
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
    {
        "type": "function",
        "function": {
            "name": SET_GOAL_PLAN_TOOL,
            "description": (
                "PLANEA cuánto abonar a una meta de ahorro en un mes ('para noviembre aparta "
                "500.000 a vacaciones', 'de ahora en adelante abona 300.000 al mes al fondo', "
                "'cada mes 200 mil a X'). Es un PLAN a futuro: NO mueve dinero, NO es un aporte "
                "(eso es contribute_to_goal), NO es un gasto ni un tope de presupuesto. "
                "scope 'solo_mes' = solo ese mes; 'desde_mes' = ese mes y los siguientes. "
                "'de ahora en adelante'/'cada mes' = desde_mes con el mes actual. Para un mes "
                "que ya pasó, pregunta primero al usuario y repite la llamada con "
                "confirm_past=true SOLO después de que confirme."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {"type": "string", "description": "Nombre de la meta"},
                    "amount": {"type": "number", "description": "Monto planeado, mayor a 0"},
                    "scope": {
                        "type": "string",
                        "enum": ["solo_mes", "desde_mes"],
                        "description": "solo_mes = solo ese mes; desde_mes = desde ese mes en adelante",
                    },
                    "month": {
                        "type": "string",
                        "description": (
                            "Mes del plan: 'YYYY-MM' o 'este_mes' (por defecto, el mes actual)"
                        ),
                    },
                    "goal_target_amount": {
                        "type": "number",
                        "description": (
                            "Monto objetivo de la meta; úsalo SOLO para desambiguar si "
                            "hay varias metas con el mismo nombre"
                        ),
                    },
                    "confirm_past": {
                        "type": "boolean",
                        "description": (
                            "true SOLO si el mes ya pasó Y el usuario confirmó explícitamente "
                            "en el turno anterior que quiere ese plan"
                        ),
                    },
                },
                "required": ["goal_name", "amount", "scope"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": CLEAR_GOAL_PLAN_TOOL,
            "description": (
                "Quita o cambia el PLAN mensual de una meta (no toca lo ya aportado). "
                "mode 'sin_plan' = ese mes no planea abonar ('quita el plan de diciembre'); "
                "'volver_al_general' = ese mes vuelve al plan normal ('en diciembre vuelve al "
                "plan normal'); 'terminar' = deja de planear desde ese mes en adelante ('ya "
                "no quiero planear más para X'). Para un mes que ya pasó, pregunta primero y "
                "repite con confirm_past=true SOLO tras la confirmación del usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_name": {"type": "string", "description": "Nombre de la meta"},
                    "mode": {
                        "type": "string",
                        "enum": ["sin_plan", "volver_al_general", "terminar"],
                        "description": "Qué quitar (ver descripción)",
                    },
                    "month": {
                        "type": "string",
                        "description": "Mes: 'YYYY-MM' o 'este_mes' (por defecto, el mes actual)",
                    },
                    "goal_target_amount": {
                        "type": "number",
                        "description": (
                            "Monto objetivo de la meta; úsalo SOLO para desambiguar si "
                            "hay varias metas con el mismo nombre"
                        ),
                    },
                    "confirm_past": {
                        "type": "boolean",
                        "description": (
                            "true SOLO si el mes ya pasó Y el usuario lo confirmó explícitamente"
                        ),
                    },
                },
                "required": ["goal_name", "mode"],
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
        if name == PAUSE_GOAL_TOOL:
            return await self._set_paused(arguments, user_id, paused=True)
        if name == RESUME_GOAL_TOOL:
            return await self._set_paused(arguments, user_id, paused=False)
        if name == SET_GOAL_PLAN_TOOL:
            return await self._set_plan(arguments, user_id)
        if name == CLEAR_GOAL_PLAN_TOOL:
            return await self._clear_plan(arguments, user_id)
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

        monthly_plan = _opt_decimal(args.get("monthly_plan"))
        if args.get("monthly_plan") is not None and (monthly_plan is None or monthly_plan <= 0):
            # Validate BEFORE creating, so a bad plan never leaves a half-done request.
            return "No pude crear la meta: el plan mensual debe ser un monto mayor a 0."

        created = await self._service.create_goal(goal, user_id)
        target = f" para {created.target_date}" if created.target_date else ""
        message = f"✅ Meta creada: {created.name} — objetivo ${created.target_amount}{target}."
        if monthly_plan is None:
            return message

        # Never before the goal's own creation month (a month-edge clock skew would make
        # the service refuse the plan).
        month = max(
            first_of_month(current_today()),
            goal_created_month(created.created_at, settings.DEFAULT_TIMEZONE),
        )
        try:
            planned = await self._service.set_plan(
                user_id, created.id, monthly_plan, month, GoalPlanScope.DESDE_MES
            )
        except (InvalidPlanPeriodError, InvalidAmountError, GoalNotFoundError) as e:
            logger.warning("Plan for a new goal failed", error=str(e))
            return f"{message} No pude guardar el plan mensual: {_plan_error_text(e)}"
        return (
            f"{message} Plan: ${planned if planned is not None else monthly_plan} al mes "
            f"desde {_month_label(month)} (es un plan, no un aporte)."
        )

    async def _query(self, args: dict[str, Any], user_id: UserId) -> str:
        today = current_today()
        try:
            month = _parse_month(args.get("period"), today)
        except ValueError:
            return (
                f"No entendí el período '{args.get('period')}'. "
                "Usa 'este_mes', 'mes_pasado' o AAAA-MM (por ejemplo 2026-11)."
            )
        name = str(args.get("goal_name", "")).strip()
        if name:
            return await self._query_one(name, args, user_id, month, today)

        goals, total = await self._list_all_goals(user_id)
        if not goals:
            return "No tienes metas configuradas."

        statuses = await self._plan_statuses(user_id, month, today)
        lines: list[str] = []
        for goal in goals:
            suggested: Decimal | None = None
            try:
                progress = await self._service.get_progress(goal.id, user_id)
                lines.append(_format_progress(progress))
                suggested = progress.required_monthly_contribution
            except Exception as e:  # noqa: BLE001 - one goal failing shouldn't drop the rest.
                logger.warning("Goal progress failed", goal_id=goal.id, error=str(e))
                lines.append(f"- {goal.name}: ${goal.current_amount} de ${goal.target_amount}")
            lines.append(_plan_line(goal, statuses.get(goal.id), suggested))
        totals = _plan_totals_lines(list(statuses.values()), month)
        return f"{total} meta(s):\n" + "\n".join([*lines, *totals])

    async def _list_all_goals(self, user_id: UserId) -> tuple[list[Goal], int]:
        """Every goal of the user (paging through), so the plan total never covers more
        goals than the ones listed."""
        goals: list[Goal] = []
        page = 1
        while True:
            batch, total = await self._service.list_goals(
                user_id, page=page, page_size=_GOALS_PAGE_SIZE
            )
            goals.extend(batch)
            if not batch or len(goals) >= total:
                return goals, total
            page += 1

    async def _plan_statuses(
        self, user_id: UserId, month: date, today: date
    ) -> dict[str, GoalPlanStatus]:
        """The month's plan status by goal id; empty when the plan can't be read."""
        try:
            statuses = await self._service.get_plan_status(
                user_id, month, last_of_month(month), today
            )
        except FinanceGPTError as e:
            logger.warning("Goal plan status failed", user_id=user_id, error=str(e))
            return {}
        return {s.goal_id: s for s in statuses}

    async def _query_one(
        self, name: str, args: dict[str, Any], user_id: UserId, month: date, today: date
    ) -> str:
        """List a single goal's contributions (newest first) and its plan; or month by month."""
        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "consultar")

        months = _opt_int(args.get("months"))
        if months is not None and months > 0:
            return await self._monthly_history(goal, user_id, months, month, today)

        contribs = await self._service.list_contributions(goal.id, user_id)
        header = (
            f"Meta '{goal.name}': llevas ${goal.current_amount} de ${goal.target_amount}."
        )
        statuses = await self._plan_statuses(user_id, month, today)
        plan = _plan_line(goal, statuses.get(goal.id), None)
        if not contribs:
            return f"{header}\n{plan}\nAún no tiene aportes registrados."
        lines = [f"  - ${c.amount} ({c.contribution_date})" for c in contribs]
        return f"{header}\n{plan}\n" + "\n".join(lines)

    async def _monthly_history(
        self, goal: Goal, user_id: UserId, months: int, month: date, today: date
    ) -> str:
        """Plan vs contributed for one goal, month by month (code-computed lines)."""
        try:
            history = await self._service.get_monthly_history(user_id, months, month, today)
        except InvalidPlanPeriodError as e:
            return f"No pude armar el mes a mes: {_plan_error_text(e)}"
        lines = [_history_line(line) for line in history if line.goal_id == goal.id]
        header = f"Mes a mes de '{goal.name}' (plan vs aportado):"
        if not lines:
            return f"{header}\n  Sin movimientos ni plan en esos meses."
        return header + "\n" + "\n".join(lines)

    async def _set_plan(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("goal_name", "")).strip()
        today = current_today()
        amount = _opt_decimal(args.get("amount"))
        if amount is None:
            return "No pude guardar el plan: el monto no es válido."
        if amount <= 0:
            return (
                "No puedo guardar un plan de 0 o negativo: el monto debe ser mayor a 0. "
                "Para quitar el plan de una meta usa clear_goal_plan."
            )
        try:
            month = _parse_month(args.get("month"), today)
        except ValueError:
            return _invalid_month_text(args.get("month"))
        scope = _opt_enum(GoalPlanScope, args.get("scope"))
        if scope is None:
            label = _month_label(month)
            return f"¿El plan de {label} es solo para ese mes o desde {label} en adelante?"

        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "planear")
        if blocked := _past_gate(goal.id, month, today, args.get("confirm_past")):
            return blocked

        try:
            planned = await self._service.set_plan(user_id, goal.id, amount, month, scope)
        except (InvalidPlanPeriodError, InvalidAmountError, GoalNotFoundError) as e:
            return f"No pude guardar el plan: {_plan_error_text(e)}"
        logger.info("Tool set goal plan", goal_id=goal.id, user_id=user_id, scope=scope.value)

        shown = planned if planned is not None else amount
        label = _month_label(month)
        reach = f"solo {label}" if scope is GoalPlanScope.SOLO_MES else f"desde {label} en adelante"
        return f"✅ Plan de {goal.name}: ${shown} ({reach}).{_plan_notes(goal, shown)}"

    async def _clear_plan(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("goal_name", "")).strip()
        today = current_today()
        try:
            month = _parse_month(args.get("month"), today)
        except ValueError:
            return _invalid_month_text(args.get("month"))
        mode = _opt_enum(GoalPlanClearMode, args.get("mode"))
        if mode is None:
            label = _month_label(month)
            return (
                f"¿Qué quieres hacer con el plan de {label}: dejar ese mes sin plan, volver "
                f"al plan normal o dejar de planear desde {label} en adelante?"
            )

        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "cambiar el plan de")
        if blocked := _past_gate(goal.id, month, today, args.get("confirm_past")):
            return blocked

        try:
            planned = await self._service.clear_plan(user_id, goal.id, month, mode)
        except (InvalidPlanPeriodError, GoalNotFoundError) as e:
            return f"No pude cambiar el plan: {_plan_error_text(e)}"
        logger.info("Tool cleared goal plan", goal_id=goal.id, user_id=user_id, mode=mode.value)

        label = _month_label(month)
        if mode is GoalPlanClearMode.SIN_PLAN:
            return f"✅ Quité el plan de {goal.name} para {label}: ese mes no planeas abonar."
        if mode is GoalPlanClearMode.TERMINAR:
            return (
                f"✅ Dejé de planear {goal.name} desde {label}; también quité los planes "
                "de los meses siguientes."
            )
        general = f"${planned} al mes" if planned is not None else "sin plan"
        return f"✅ {goal.name}: en {label} vuelve al plan normal ({general})."

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

    async def _set_paused(
        self, args: dict[str, Any], user_id: UserId, *, paused: bool
    ) -> str:
        name = str(args.get("goal_name", "")).strip()
        matches = await self._resolve_goals(name, user_id)
        if not matches:
            return f"No encontré una meta llamada '{name}'. ¿Puedes indicar el nombre exacto?"
        goal = self._pick_goal(matches, _opt_decimal(args.get("goal_target_amount")))
        if goal is None:
            return _ambiguous_message(name, matches, "pausar" if paused else "reactivar")

        updated = await self._service.set_paused(goal.id, user_id, paused)
        if paused:
            return (
                f"⏸️ Pausé tu meta «{updated.name}». Lo ahorrado (${updated.current_amount}) "
                "sigue ahí; reactívala cuando quieras."
            )
        done = updated.status == GoalStatus.COMPLETED
        tail = " Ya está completada 🎉." if done else ""
        return (
            f"▶️ Reactivé tu meta «{updated.name}». Llevas ${updated.current_amount} "
            f"de ${updated.target_amount}.{tail}"
        )

    async def _resolve_goals(self, name: str, user_id: UserId) -> list[Goal]:
        """Return ALL goals matching ``name`` at the best tier, or [].

        Tries exact match, then substring, then accent- and inflection-tolerant
        word matching (shared ``names_match``) so "vacaciones de la playa" still
        resolves to "vacaciones playa" and, crucially, "emergencias" resolves to
        "Fondo de emergencia" (singular/plural). All tiers are accent-insensitive.
        Returning every match (not just the first) lets the caller disambiguate
        when several share a name.
        """
        if not name:
            return []
        goals, _ = await self._service.list_goals(user_id, page=1, page_size=50)
        target = normalize(name)

        exact = [g for g in goals if normalize(g.name) == target]
        if exact:
            return exact
        substr = [
            g
            for g in goals
            if target in (gn := normalize(g.name)) or (len(gn) >= 4 and gn in target)
        ]
        if substr:
            return substr
        return [g for g in goals if names_match(name, g.name)]

    def _pick_goal(
        self, matches: list[Goal], target_amount: Decimal | None
    ) -> Goal | None:
        """Disambiguate by target amount; return the single goal or None."""
        if target_amount is not None:
            filtered = [g for g in matches if g.target_amount == target_amount]
            if filtered:
                matches = filtered
        return matches[0] if len(matches) == 1 else None


def _format_progress(progress: GoalProgress) -> str:
    """Format a goal's progress for the LLM."""
    goal = progress.goal
    track = "✅ en camino" if progress.on_track else "⚠️ atrasada"
    status = " (completada)" if progress.is_completed else f", {track}"
    return (
        f"- {goal.name}: ${goal.current_amount} de ${goal.target_amount} "
        f"({progress.percentage:.0f}%){status}"
    )


def _month_label(month: date) -> str:
    """'noviembre 2026' for a month's first day."""
    return period_label(month_key(month)).replace(" de ", " ")


def _parse_month(value: Any, today: date) -> date:
    """First day of the month named by ``value`` ('YYYY-MM', 'este_mes', 'mes_pasado').

    An absent value means the current month. Raises ``ValueError`` when unreadable.
    """
    text = str(value or "").strip().lower()
    if text in ("", ESTE_MES):
        return first_of_month(today)
    if text == MES_PASADO:
        return add_months(first_of_month(today), -1)
    match = _MONTH_ARG.match(text)
    if match is None or int(match.group(1)) < _MIN_PLAN_YEAR:
        raise ValueError(f"Invalid month: {value!r}")
    return date(int(match.group(1)), int(match.group(2)), 1)


def _invalid_month_text(value: Any) -> str:
    return f"No entendí el mes '{value}'. Usa el formato AAAA-MM (por ejemplo 2026-11) o 'este_mes'."


def _past_gate(goal_key: str, month: date, today: date, confirm: Any) -> str | None:
    """Guard for planning a month that already passed; ``None`` lets the write go on.

    Without ``confirm_past`` it asks the confirmation question (and remembers, for THIS
    turn only, that it asked). A ``confirm_past=true`` arriving in the SAME turn as that
    question can only be the model confirming on its own, so it is refused: the user has
    to answer in their next message. Outside a bound turn nothing is remembered.
    """
    if month >= first_of_month(today):
        return None
    key = (goal_key, month_key(month))
    if not _is_true(confirm):
        mark_confirmation_asked(key)
        return _past_confirmation_question(month)
    if confirmation_asked_this_turn(key):
        return (
            "No puedo aplicarlo todavía: pídele al usuario que confirme primero y espera "
            "su respuesta en su siguiente mensaje."
        )
    return None


def _past_confirmation_question(month: date) -> str:
    return (
        f"¿Confirmas que quieres poner el plan de {_month_label(month)} que ya pasó? "
        "No he cambiado nada todavía."
    )


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() in ("true", "sí", "si", "yes")


def _opt_enum(enum_cls: type[_E], value: Any) -> _E | None:
    if value is None:
        return None
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        return None


def _opt_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _plan_error_text(error: FinanceGPTError) -> str:
    """A domain error as a short Spanish sentence (no codes, ids or traces)."""
    if isinstance(error, InvalidPlanPeriodError):
        return str(error.details.get("reason", "el mes no es válido")) + "."
    if isinstance(error, InvalidAmountError):
        return "el monto no es válido (debe ser mayor a 0 y no demasiado grande)."
    return "no encontré esa meta."


def _plan_notes(goal: Goal, planned: Decimal) -> str:
    """Heads-ups after saving a plan: it exceeds what's missing, or the goal is paused."""
    notes: list[str] = []
    missing = max(goal.target_amount - goal.current_amount, Decimal("0"))
    if missing == 0:
        notes.append("la meta ya está completa")
    elif planned > missing:
        notes.append(f"con ${missing} ya la completas")
    if goal.status is GoalStatus.PAUSED:
        notes.append("la meta está pausada: el plan no cuenta hasta que la reactives")
    return "" if not notes else " Ojo: " + "; ".join(notes) + "."


def _plan_line(goal: Goal, status: GoalPlanStatus | None, suggested: Decimal | None) -> str:
    """The goal's plan-vs-contributed line, computed here (Decimal), never by the LLM."""
    if status is None:
        if goal.status is GoalStatus.PAUSED:
            return "  · pausada: su plan no cuenta mientras esté pausada"
        if goal.status is GoalStatus.COMPLETED:
            return "  · meta completada"
        hint = (
            f" · sugerido ${suggested}/mes (no guardado)"
            if suggested is not None and suggested > 0
            else ""
        )
        return f"  · sin plan{hint}"
    parts = [
        f"plan ${status.planned}",
        f"aportado ${status.contributed_gross} ({status.percentage:.0f}%)",
    ]
    if status.effective_planned < status.planned:
        parts.append(f"solo te faltaban ${status.effective_planned} para completarla")
    parts.append("✓ cumplido" if status.is_met else f"faltan ${status.remaining}")
    if status.withdrawn > 0:
        parts.append(f"retiraste ${status.withdrawn}")
    return "  · " + " · ".join(parts)


def _plan_totals_lines(statuses: list[GoalPlanStatus], month: date) -> list[str]:
    """One TOTAL line per currency (never mixing currencies), as Decimal sums.

    The total uses the same effective plan as each goal's line; when a plan was bigger
    than what the goals still lacked, the planned figure is shown next to it.
    """
    if not statuses:
        return []
    planned: dict[CurrencyType, Decimal] = defaultdict(lambda: Decimal("0"))
    effective: dict[CurrencyType, Decimal] = defaultdict(lambda: Decimal("0"))
    saved: dict[CurrencyType, Decimal] = defaultdict(lambda: Decimal("0"))
    for s in statuses:
        planned[s.currency] += s.planned
        effective[s.currency] += s.effective_planned
        saved[s.currency] += s.contributed_gross
    several = len(planned) > 1
    return [
        "TOTAL PLAN METAS (no es gasto ni tope)"
        + (f" [{currency.value}]" if several else "")
        + f": planificado ${planned[currency]}"
        + (f" (necesitabas ${effective[currency]})" if effective[currency] != planned[currency] else "")
        + f" · aportado ${saved[currency]}"
        for currency in planned
    ]


def _history_line(line: GoalMonthLine) -> str:
    plan = f"plan ${line.planned}" if line.planned is not None else "sin plan"
    text = f"  - {_month_label(line.month)}: {plan} · aportado ${line.saved}"
    if line.withdrawn > 0:
        text += f" · retiraste ${line.withdrawn}"
    return f"{text} · acumulado ${line.cumulative}"


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
