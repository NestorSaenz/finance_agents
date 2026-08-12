"""Profile tools for conversational data operations.

Thin wrapper over ``UserProfileService`` exposed to the LLM as a callable tool.
For now it exposes a single tool, ``set_currency``, so the user can set the
ISO-4217 code used to LABEL their amounts (display only — no conversion).

Security: ``user_id`` is supplied by the toolkit from the authenticated context
at dispatch time and is NEVER part of the tool schema nor read from the model's
arguments. The LLM only proposes a currency code; the service validates it
against the canonical ISO-4217 set before anything is persisted.
"""

from typing import Any

from app.core.exceptions import InvalidCurrencyError, InvalidTimezoneError
from app.core.logging import get_logger
from app.shared.types import UserId
from app.src.users.interfaces import UserProfileServiceABC

logger = get_logger(__name__)

SET_CURRENCY_TOOL = "set_currency"
SET_TIMEZONE_TOOL = "set_timezone"

# A wrong currency corrupts every displayed amount, so the prompt must CONFIRM
# the code with the user before calling this; the schema only carries the code.
_UNKNOWN_CURRENCY_REPLY = (
    "No reconozco esa moneda; dime el país o el código, p. ej. GTQ."
)

# A wrong timezone shifts every relative date, so the prompt infers the IANA zone
# from the user's city/country before calling this.
_UNKNOWN_TIMEZONE_REPLY = (
    "No reconozco esa zona; dime tu ciudad, p. ej. 'Bogotá'."
)

PROFILE_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": SET_CURRENCY_TOOL,
            "description": (
                "Fija la MONEDA en la que se muestran los montos del usuario "
                "(solo etiqueta, sin conversión). Úsala cuando el usuario indique "
                "su país o su moneda ('vivo en Guatemala', 'uso quetzales', "
                "'cámbiame la moneda a dólares') y TÚ ya CONFIRMASTE con él el "
                "código ISO-4217 correcto. Pasa ese código de 3 letras que "
                "infieres (COP, MXN, USD, EUR, GTQ, ...)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "currency": {
                        "type": "string",
                        "description": (
                            "Código ISO-4217 de 3 letras inferido y ya confirmado "
                            "con el usuario (p. ej. GTQ para quetzales, USD para "
                            "dólares, COP para pesos colombianos)"
                        ),
                    },
                },
                "required": ["currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": SET_TIMEZONE_TOOL,
            "description": (
                "Fija la ZONA HORARIA (IANA) del usuario para interpretar fechas "
                "relativas ('hoy', 'ayer') en SU día local. Úsala cuando el usuario "
                "indique su ciudad o país ('vivo en Bogotá', 'estoy en México') y TÚ "
                "ya infieras el identificador IANA correcto (America/Bogota, "
                "America/Mexico_City, ...). En países con varias zonas, confírmala "
                "antes. Pasa el identificador IANA que infieres."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": (
                            "Identificador IANA inferido de la ciudad/país del usuario "
                            "(p. ej. America/Bogota para Bogotá, America/Mexico_City "
                            "para Ciudad de México, Europe/Madrid para España)"
                        ),
                    },
                },
                "required": ["timezone"],
            },
        },
    },
]


class ProfileToolkit:
    """Exposes profile tools to the LLM and dispatches its tool calls."""

    def __init__(self, service: UserProfileServiceABC) -> None:
        self._service = service

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return PROFILE_TOOL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        if name == SET_CURRENCY_TOOL:
            return await self._set_currency(arguments, user_id)
        if name == SET_TIMEZONE_TOOL:
            return await self._set_timezone(arguments, user_id)
        raise ValueError(f"Unknown profile tool: {name}")

    async def _set_currency(self, args: dict[str, Any], user_id: UserId) -> str:
        code = str(args.get("currency", "")).strip()
        if not code:
            return _UNKNOWN_CURRENCY_REPLY
        try:
            profile = await self._service.set_currency(user_id, code)
        except InvalidCurrencyError:
            logger.info("Rejected unknown currency from tool", currency=code)
            return _UNKNOWN_CURRENCY_REPLY
        return f"✅ Listo, usaré {profile.currency} para tus montos."

    async def _set_timezone(self, args: dict[str, Any], user_id: UserId) -> str:
        tz = str(args.get("timezone", "")).strip()
        if not tz:
            return _UNKNOWN_TIMEZONE_REPLY
        try:
            profile = await self._service.set_timezone(user_id, tz)
        except InvalidTimezoneError:
            logger.info("Rejected unknown timezone from tool", timezone=tz)
            return _UNKNOWN_TIMEZONE_REPLY
        return f"✅ Listo, usaré tu zona {profile.timezone} para las fechas."
