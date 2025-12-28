"""Query Classifier - LLM-based intent and complexity classification.

This module uses an LLM to classify user queries into:
1. Intent: What the user wants to do (categorize, analyze, plan, etc.)
2. Complexity: Whether the task is simple or complex

Simple tasks go directly to specialized agents.
Complex tasks go through the Plan-Execute-Replan cycle.
"""

import json

from app.agents.constants import CLASSIFIER_MAX_TOKENS, CLASSIFIER_TEMPERATURE
from app.agents.models import ClassificationResult
from app.agents.types import AgentName, Complexity, Intent, IntentType
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

Tu tarea es analizar el mensaje del usuario y determinar:
1. INTENT: Qué quiere hacer el usuario
2. COMPLEXITY: Si es una tarea simple o compleja

## INTENTS disponibles:
- categorize: Quiere categorizar o saber la categoría de un gasto/ingreso
- analyze: Quiere analizar sus gastos, ver patrones, resúmenes o estadísticas
- plan: Quiere crear un plan de ahorro, establecer metas financieras o estrategias
- recommend: Quiere recomendaciones o consejos financieros
- register: Quiere registrar un gasto o ingreso nuevo
- query: Consulta general sobre sus finanzas o el sistema
- unknown: No se puede determinar la intención

## COMPLEXITY:
- simple: Tareas directas de un solo paso
  * Registrar un gasto ("gasté 50 pesos en comida")
  * Categorizar una transacción ("¿qué categoría es Netflix?")
  * Consultas simples ("¿cuánto gasté hoy?")

- complex: Tareas que requieren análisis o múltiples pasos
  * Analizar patrones ("¿en qué estoy gastando más?")
  * Crear planes ("ayúdame a ahorrar para un viaje")
  * Comparar períodos ("¿gasté más este mes que el anterior?")
  * Estrategias ("¿cómo puedo reducir mis gastos?")

## Mensaje del usuario:
"{message}"

## Responde EXACTAMENTE en este formato JSON (sin markdown):
{{"intent": "<intent>", "complexity": "<simple|complex>"}}
"""

# Agent routing based on intent
INTENT_TO_AGENT: dict[str, AgentName] = {
    IntentType.CATEGORIZE.value: AgentName.CATEGORIZER,
    IntentType.ANALYZE.value: AgentName.ANALYST,
    IntentType.PLAN.value: AgentName.PLANNER,
    IntentType.RECOMMEND.value: AgentName.RECOMMENDER,
    IntentType.REGISTER.value: AgentName.CATEGORIZER,  # First categorize, then register
    IntentType.QUERY.value: AgentName.ANALYST,  # Default to analyst for general queries
    IntentType.UNKNOWN.value: AgentName.RESPONSE_GENERATOR,
}


async def classify_query(
    message: str,
    llm: LLMInterface,
) -> ClassificationResult:
    """Classify a user message using LLM.

    Args:
        message: The user's message to classify.
        llm: LLM client to use for classification.

    Returns:
        ClassificationResult with intent, complexity, confidence, and next_agent.
    """
    logger.info("Classifying query", message_length=len(message))

    # Build the prompt
    prompt = CLASSIFICATION_PROMPT.format(message=message)

    # Use low temperature for consistent classification
    config = LLMConfig(
        temperature=CLASSIFIER_TEMPERATURE,
        max_tokens=CLASSIFIER_MAX_TOKENS,
    )

    try:
        response = await llm.generate(
            messages=[
                Message(role=MessageRole.USER, content=prompt),
            ],
            config=config,
        )

        # Parse the response
        result = _parse_classification_response(response.content)

        logger.info(
            "Query classified",
            intent=result.intent,
            complexity=result.complexity,
            next_agent=result.next_agent,
            tokens_used=response.total_tokens,
        )

        return result

    except Exception as e:
        logger.error("Classification failed", error=str(e))
        # Default to safe fallback
        return ClassificationResult(
            intent="query",
            complexity="simple",
            confidence=0.5,
            next_agent=AgentName.ANALYST,
        )


def _parse_classification_response(response: str) -> ClassificationResult:
    """Parse the LLM classification response.

    Args:
        response: Raw LLM response string.

    Returns:
        ClassificationResult with parsed values.
    """
    # Clean up the response
    response = response.strip()

    # Remove markdown code blocks if present
    if response.startswith("```"):
        lines = response.split("\n")
        response = "\n".join(lines[1:-1])

    try:
        data = json.loads(response)
        intent = data.get("intent", "unknown")
        complexity = data.get("complexity", "simple")

        # Validate intent
        valid_intents = {e.value for e in IntentType}
        if intent not in valid_intents:
            logger.warning("Invalid intent from LLM", raw_intent=intent)
            intent = "query"

        # Validate complexity
        if complexity not in ("simple", "complex"):
            logger.warning("Invalid complexity from LLM", raw_complexity=complexity)
            complexity = "simple"

        # Determine next agent
        next_agent = get_next_agent(intent, complexity)

        return ClassificationResult(
            intent=intent,
            complexity=complexity,
            confidence=1.0,  # LLM doesn't provide confidence, assume high
            next_agent=next_agent,
        )

    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse classification response",
            response=response,
            error=str(e),
        )
        return ClassificationResult(
            intent="query",
            complexity="simple",
            confidence=0.5,
            next_agent=AgentName.ANALYST,
        )


def get_next_agent(intent: Intent, complexity: Complexity) -> AgentName:
    """Determine the next agent based on classification.

    Args:
        intent: The classified intent.
        complexity: The classified complexity.

    Returns:
        AgentName of the next agent to route to.
    """
    if complexity == "complex":
        # Complex tasks go to the task_planner for Plan-Execute-Replan
        return AgentName.TASK_PLANNER

    # Simple tasks go directly to the specialized agent
    return INTENT_TO_AGENT.get(intent, AgentName.RESPONSE_GENERATOR)
