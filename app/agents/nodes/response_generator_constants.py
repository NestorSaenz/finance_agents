"""Constants for the response generator agent.

Contains prompts and templates for generating user-friendly responses.
"""

# System prompt for the response generator
RESPONSE_SYSTEM_PROMPT = """Eres un asistente financiero amigable y profesional llamado FinanceGPT.

Tu rol es comunicar los resultados del análisis financiero de manera clara, concisa y útil.

## Directrices:
- Responde siempre en español
- Sé amigable pero profesional
- Usa emojis con moderación (máximo 2-3 por respuesta)
- Sé conciso pero informativo
- Si hay recomendaciones, preséntalas como consejos prácticos
- Si el usuario preguntó algo específico, responde directamente a eso primero
- Adapta el tono según el contexto (más empático si hay problemas financieros)

## Formato de respuesta:
- Usa saltos de línea para separar ideas
- Usa viñetas (•) para listas
- Destaca números importantes
- Máximo 3-4 párrafos cortos
"""

# Template for categorization responses
CATEGORIZATION_TEMPLATE = """El usuario quería categorizar una transacción.

## Resultado de categorización:
- Categoría sugerida: {category}
- Confianza: {confidence:.0%}
- Alternativas consideradas: {alternatives}

## Mensaje original del usuario:
"{user_message}"

Genera una respuesta confirmando la categorización de forma natural y amigable.
Si la confianza es baja (<70%), menciona que puede cambiarla si no es correcta.
"""

# Template for analysis responses
ANALYSIS_TEMPLATE = """El usuario solicitó un análisis de sus finanzas.

## Resultados del análisis:
- Ingresos totales: ${total_income:,.2f}
- Gastos totales: ${total_expenses:,.2f}
- Balance: ${balance:,.2f}

## Gastos por categoría:
{by_category}

## Patrones detectados:
{patterns}

## Insights generados:
{insights}

## Mensaje original del usuario:
"{user_message}"

Genera una respuesta que resuma los hallazgos más importantes y ofrezca 1-2 consejos prácticos.
"""

# Template for recommendation responses
RECOMMENDATION_TEMPLATE = """El usuario busca recomendaciones para mejorar sus finanzas.

## Recomendaciones generadas:
{recommendations}

## Contexto financiero:
- Ingreso mensual: ${monthly_income:,.2f}
- Gastos mensuales: ${monthly_expenses:,.2f}
- Metas activas: {active_goals}

## Mensaje original del usuario:
"{user_message}"

Genera una respuesta que presente las recomendaciones de forma motivadora y accionable.
Prioriza las más impactantes y explica brevemente el beneficio de cada una.
"""

# Template for planning responses
PLANNING_TEMPLATE = """El usuario quiere crear o revisar un plan de ahorro.

## Plan generado:
- Meta: {goal_name}
- Monto objetivo: ${target_amount:,.2f}
- Ahorro actual: ${current_amount:,.2f}
- Contribución mensual sugerida: ${monthly_contribution:,.2f}
- Fecha estimada de logro: {estimated_completion}

## Recomendaciones del plan:
{recommendations}

## Mensaje original del usuario:
"{user_message}"

Genera una respuesta que explique el plan de forma clara y motivadora.
Incluye el progreso actual y los próximos pasos concretos.
"""

# Template for complex query responses (multi-step)
COMPLEX_RESPONSE_TEMPLATE = """El usuario hizo una consulta compleja que requirió múltiples pasos.

## Pasos ejecutados:
{execution_history}

## Resultados obtenidos:
{results}

## Mensaje original del usuario:
"{user_message}"

Genera una respuesta que sintetice todos los hallazgos de forma coherente.
Presenta la información de manera estructurada y fácil de entender.
"""

# Template for error/fallback responses
ERROR_TEMPLATE = """No se pudo procesar completamente la solicitud del usuario.

## Error o limitación:
{error_message}

## Mensaje original del usuario:
"{user_message}"

Genera una respuesta empática que:
1. Reconozca que no pudiste completar la solicitud
2. Explique brevemente el problema (sin tecnicismos)
3. Sugiera una alternativa o pida más información
"""

# Template for general/unknown intent
GENERAL_TEMPLATE = """El usuario envió un mensaje general.

## Intent detectado: {intent}
## Mensaje del usuario: "{user_message}"

## Datos disponibles:
- Categorización: {category_suggestion}
- Análisis: {has_analysis}
- Recomendaciones: {recommendations_count}

Genera una respuesta apropiada basada en la información disponible.
Si no hay suficiente información, ofrece ayuda y sugiere qué puede hacer el asistente.
"""

# Mapping of intents to templates
INTENT_TEMPLATES = {
    "categorize": CATEGORIZATION_TEMPLATE,
    "analyze": ANALYSIS_TEMPLATE,
    "recommend": RECOMMENDATION_TEMPLATE,
    "plan": PLANNING_TEMPLATE,
    "query": GENERAL_TEMPLATE,
    "register": CATEGORIZATION_TEMPLATE,  # Similar to categorize
    "unknown": GENERAL_TEMPLATE,
}
