"""Constants for the analyst agent.

Contains prompts, thresholds, and configuration for financial analysis.
"""

from typing import Final

from app.shared.types import CategoryType

# =============================================================================
# Analysis Thresholds
# =============================================================================

# Percentage thresholds for spending alerts
HIGH_SPENDING_THRESHOLD = 0.30  # Alert if category > 30% of total
UNUSUAL_SPENDING_MULTIPLIER = 1.5  # Alert if spending > 1.5x average

# Number of largest individual expenses surfaced in the analysis, so the LLM can
# comment on concrete purchases (descriptions), not just category totals.
TOP_EXPENSES_LIMIT: Final[int] = 5

# Minimum transactions for pattern detection
MIN_TRANSACTIONS_FOR_PATTERNS = 5
MIN_TRANSACTIONS_FOR_TRENDS = 10

# Recurring transaction detection
RECURRING_AMOUNT_TOLERANCE = 0.05  # 5% tolerance for amount matching
RECURRING_MIN_OCCURRENCES = 2  # Minimum times to be considered recurring

# =============================================================================
# LLM Prompts for Insight Generation
# =============================================================================

INSIGHT_SYSTEM_PROMPT = """Eres un analista financiero experto que genera insights
personalizados basados en los datos de gastos del usuario.

## Directrices:
- Genera insights accionables y específicos
- Usa un tono amigable pero profesional
- Enfócate en oportunidades de ahorro
- Destaca patrones positivos y negativos
- Máximo 3-4 insights por análisis
- Cada insight debe ser conciso (1-2 oraciones)

## Reglas estrictas (no inventar información):
- Usa ÚNICAMENTE los datos proporcionados en este mensaje; NO inventes cifras, fechas, categorías ni transacciones.
- No extrapoles ni estimes montos que no aparezcan en los datos.
- Si un dato no está disponible, no lo supongas: omítelo o indica que no se dispone de esa información.
"""

INSIGHT_GENERATION_PROMPT = """Analiza los siguientes datos financieros y genera insights útiles.

## Período analizado:
{period}

## Resumen financiero:
- Ingresos totales: ${total_income:,.2f}
- Gastos totales: ${total_expenses:,.2f}
- Balance: ${balance:,.2f} ({balance_percentage:+.1f}%)

## Gastos por categoría (ordenados de mayor a menor):
{category_breakdown}

## Patrones detectados:
{patterns}

## Comparación con período anterior:
{comparison}

Genera 3-4 insights específicos y accionables basados en estos datos.
Formato: Lista con viñetas, cada insight en una línea.
"""

# =============================================================================
# Pattern Detection Prompts
# =============================================================================

PATTERN_DETECTION_PROMPT = """Analiza las siguientes transacciones y detecta patrones.

## Transacciones recientes:
{transactions}

## Busca estos patrones:
1. Gastos recurrentes (mismo monto, periodicidad regular)
2. Tendencias de aumento o disminución por categoría
3. Días/semanas con mayor gasto
4. Gastos hormiga (pequeños pero frecuentes)
5. Categorías con variabilidad alta

Devuelve una lista de patrones detectados, uno por línea.
"""

# =============================================================================
# Category Labels (Spanish)
# =============================================================================

CATEGORY_LABELS: dict[str, str] = {
    CategoryType.ALIMENTACION.value: "Alimentación",
    CategoryType.TRANSPORTE.value: "Transporte",
    CategoryType.VIVIENDA.value: "Vivienda",
    CategoryType.SERVICIOS.value: "Servicios",
    CategoryType.SALUD.value: "Salud",
    CategoryType.ENTRETENIMIENTO.value: "Entretenimiento",
    CategoryType.EDUCACION.value: "Educación",
    CategoryType.ROPA.value: "Ropa",
    CategoryType.TECNOLOGIA.value: "Tecnología",
    CategoryType.VIAJES.value: "Viajes",
    CategoryType.RESTAURANTES.value: "Restaurantes",
    CategoryType.COMBUSTIBLE.value: "Combustible",
    CategoryType.ESTACIONAMIENTO.value: "Estacionamiento",
    CategoryType.SUSCRIPCIONES.value: "Suscripciones",
    CategoryType.GIMNASIO.value: "Gimnasio",
    CategoryType.MASCOTAS.value: "Mascotas",
    CategoryType.REGALOS.value: "Regalos",
    CategoryType.IMPREVISTOS.value: "Imprevistos",
    CategoryType.OTROS.value: "Otros",
}


def get_category_label(category: str) -> str:
    """Get human-readable label for a category.

    Args:
        category: Category value (lowercase).

    Returns:
        Human-readable label in Spanish.
    """
    return CATEGORY_LABELS.get(category.lower(), category.capitalize())
