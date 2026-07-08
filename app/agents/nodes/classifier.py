"""Query classifier — LLM-based intent classification.

Classifies the user's message into an intent, which the orchestrator maps to a
single routing target: the categorizer (RAG), the tool-calling agent (all
data-driven work), the refusal node (off-topic), or the response generator
(greetings / general).
"""

import json

from app.agents.constants import CLASSIFIER_MAX_TOKENS, CLASSIFIER_TEMPERATURE
from app.agents.models import ClassificationResult
from app.agents.types import AgentName, Intent, IntentType
from app.core.logging import get_logger
from app.shared.interfaces.llm import (
    LLMConfig,
    LLMInterface,
    Message,
    MessageRole,
)

logger = get_logger(__name__)


# Classification prompt in Spanish (target users are Spanish speakers)
CLASSIFICATION_PROMPT = """Eres un clasificador de intenciones para un asistente financiero personal.

Tu tarea es determinar la INTENCIÓN del mensaje del usuario.

## INTENTS disponibles:
- categorize: Quiere saber a qué categoría pertenece un concepto que describe (ej: "¿qué categoría es Netflix?"). NO para gastos ya registrados.
- analyze: Quiere analizar sus gastos, ver patrones, resúmenes o estadísticas
- plan: Quiere crear un plan de ahorro, establecer metas financieras o estrategias
- recommend: Quiere recomendaciones o consejos financieros
- register: Quiere registrar un gasto o ingreso nuevo
- query: Consulta sobre sus finanzas, transacciones, presupuestos o metas YA registradas (ej: "¿cuánto gasté?", "¿cómo van mis presupuestos?", "muéstrame mis metas")
- off_topic: El mensaje NO trata sobre las finanzas personales del usuario (ej: "escríbeme un poema", "¿capital de Francia?", "código en Python", chismes, temas generales). Úsalo siempre que el tema quede fuera de las finanzas personales.
- unknown: No se puede determinar la intención (saludos, mensajes vagos)

Los mensajes anteriores (si los hay) son el contexto de la conversación; úsalos
para interpretar referencias como "eso", "ese gasto" o "el anterior".

CONTINUIDAD (importante): si el mensaje es una respuesta o confirmación a una
pregunta previa del asistente sobre una operación financiera (por ejemplo "sí",
"no", una fecha, un monto, "el de $500", "el primero de julio", "ese", "en
efectivo", "con tarjeta", "crédito"), clasifícalo como "query" para CONTINUAR esa
operación — nunca como "unknown".

## Mensaje del usuario:
"{message}"

## Responde EXACTAMENTE en este formato JSON (sin markdown):
{{"intent": "<intent>"}}
"""

# Agent routing based on intent.
# All data-driven intents (register/query/analyze/recommend/plan) go to the
# tool-calling agent, which fetches real data via tools and answers — a single
# ReAct loop replaces the old dedicated + Plan-Execute-Replan nodes.
INTENT_TO_AGENT: dict[str, AgentName] = {
    IntentType.CATEGORIZE.value: AgentName.CATEGORIZER,  # RAG classify a described concept
    IntentType.ANALYZE.value: AgentName.TOOL_AGENT,
    IntentType.PLAN.value: AgentName.TOOL_AGENT,
    IntentType.RECOMMEND.value: AgentName.TOOL_AGENT,
    IntentType.REGISTER.value: AgentName.TOOL_AGENT,
    IntentType.QUERY.value: AgentName.TOOL_AGENT,
    IntentType.OFF_TOPIC.value: AgentName.REFUSAL,  # Out of scope -> declined at the gate
    IntentType.UNKNOWN.value: AgentName.RESPONSE_GENERATOR,
}


async def classify_query(
    message: str,
    llm: LLMInterface,
    context: list[Message] | None = None,
) -> ClassificationResult:
    """Classify a user message using LLM.

    Args:
        message: The user's message to classify.
        llm: LLM client to use for classification.
        context: Recent prior conversation messages, to disambiguate references.

    Returns:
        ClassificationResult with intent, confidence, and next_agent.
    """
    logger.info("Classifying query", message_length=len(message))

    prompt = CLASSIFICATION_PROMPT.format(message=message)
    config = LLMConfig(temperature=CLASSIFIER_TEMPERATURE, max_tokens=CLASSIFIER_MAX_TOKENS)

    try:
        response = await llm.generate(
            messages=[*(context or []), Message(role=MessageRole.USER, content=prompt)],
            config=config,
        )
        result = _parse_classification_response(response.content)
        logger.info(
            "Query classified",
            intent=result.intent,
            next_agent=result.next_agent,
            tokens_used=response.total_tokens,
        )
        return result

    except Exception as e:  # noqa: BLE001 - LLM boundary: fall back to a safe route.
        logger.error("Classification failed", error=str(e))
        return ClassificationResult(
            intent="query", confidence=0.5, next_agent=AgentName.TOOL_AGENT
        )


def _parse_classification_response(response: str) -> ClassificationResult:
    """Parse the LLM's ``{"intent": ...}`` JSON into a ClassificationResult."""
    response = response.strip()
    if response.startswith("```"):
        lines = response.split("\n")
        response = "\n".join(lines[1:-1])

    try:
        data = json.loads(response)
        intent = data.get("intent", "unknown")
        if intent not in {e.value for e in IntentType}:
            logger.warning("Invalid intent from LLM", raw_intent=intent)
            intent = "query"
        return ClassificationResult(
            intent=intent, confidence=1.0, next_agent=get_next_agent(intent)
        )

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse classification response", response=response, error=str(e))
        return ClassificationResult(
            intent="query", confidence=0.5, next_agent=AgentName.TOOL_AGENT
        )


def get_next_agent(intent: Intent) -> AgentName:
    """Map a classified intent to its routing target."""
    return INTENT_TO_AGENT.get(intent, AgentName.RESPONSE_GENERATOR)
