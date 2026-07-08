"""Constants for the categorizer agent.

Contains category definitions, mappings, and prompts used by the categorizer.
Uses shared types from app.shared.types for consistency across the application.
"""

from app.shared.types import VALID_CATEGORIES, CategoryType

# Thresholds for hybrid categorization
EMBEDDING_CONFIDENCE_THRESHOLD = 0.85  # Use embedding result if score >= this
LLM_FALLBACK_THRESHOLD = 0.60  # Below this, definitely use LLM

# Default categories derived from shared CategoryType enum
DEFAULT_CATEGORIES: list[str] = VALID_CATEGORIES

# Default category when none matches
DEFAULT_CATEGORY = CategoryType.OTROS.value

# LLM prompt for categorization fallback
CATEGORIZATION_PROMPT = """Eres un categorizador de transacciones financieras.

Dada la siguiente descripcion de un gasto, determina la categoria mas apropiada.

## Categorias disponibles:
{categories}

## Descripcion del gasto:
"{description}"

## Responde SOLO con el nombre de la categoria (una palabra, en minusculas):
"""

# Mapping of common terms to categories (for LLM response normalization)
CATEGORY_MAPPINGS: dict[str, str] = {
    # Alimentacion (includes supermarkets)
    "comida": CategoryType.ALIMENTACION.value,
    "food": CategoryType.ALIMENTACION.value,
    "alimentos": CategoryType.ALIMENTACION.value,
    "super": CategoryType.ALIMENTACION.value,
    "despensa": CategoryType.ALIMENTACION.value,
    # Transporte
    "transport": CategoryType.TRANSPORTE.value,
    "taxi": CategoryType.TRANSPORTE.value,
    "uber": CategoryType.TRANSPORTE.value,
    "didi": CategoryType.TRANSPORTE.value,
    "metro": CategoryType.TRANSPORTE.value,
    # Vivienda
    "casa": CategoryType.VIVIENDA.value,
    "hogar": CategoryType.VIVIENDA.value,
    "alquiler": CategoryType.VIVIENDA.value,
    "renta": CategoryType.VIVIENDA.value,
    "hipoteca": CategoryType.VIVIENDA.value,
    # Servicios
    "luz": CategoryType.SERVICIOS.value,
    "agua": CategoryType.SERVICIOS.value,
    "gas": CategoryType.SERVICIOS.value,
    "internet": CategoryType.SERVICIOS.value,
    "telefono": CategoryType.SERVICIOS.value,
    # Salud
    "doctor": CategoryType.SALUD.value,
    "medicina": CategoryType.SALUD.value,
    "farmacia": CategoryType.SALUD.value,
    "medico": CategoryType.SALUD.value,
    "eps": CategoryType.SALUD.value,
    # Entretenimiento
    "cine": CategoryType.ENTRETENIMIENTO.value,
    "concierto": CategoryType.ENTRETENIMIENTO.value,
    "teatro": CategoryType.ENTRETENIMIENTO.value,
    # Suscripciones
    "netflix": CategoryType.SUSCRIPCIONES.value,
    "spotify": CategoryType.SUSCRIPCIONES.value,
    "streaming": CategoryType.SUSCRIPCIONES.value,
    "hbo": CategoryType.SUSCRIPCIONES.value,
    "youtube": CategoryType.SUSCRIPCIONES.value,
    "apple music": CategoryType.SUSCRIPCIONES.value,
    "xbox": CategoryType.SUSCRIPCIONES.value,
    "playstation": CategoryType.SUSCRIPCIONES.value,
    # Educacion
    "escuela": CategoryType.EDUCACION.value,
    "curso": CategoryType.EDUCACION.value,
    "universidad": CategoryType.EDUCACION.value,
    # Ropa
    "ropa": CategoryType.ROPA.value,
    "zapatos": CategoryType.ROPA.value,
    "vestir": CategoryType.ROPA.value,
    # Tecnologia
    "celular": CategoryType.TECNOLOGIA.value,
    "computadora": CategoryType.TECNOLOGIA.value,
    "laptop": CategoryType.TECNOLOGIA.value,
    # Viajes
    "vacaciones": CategoryType.VIAJES.value,
    "hotel": CategoryType.VIAJES.value,
    "avion": CategoryType.VIAJES.value,
    "vuelo": CategoryType.VIAJES.value,
    # Restaurantes
    "cafe": CategoryType.RESTAURANTES.value,
    "restaurant": CategoryType.RESTAURANTES.value,
    "comida rapida": CategoryType.RESTAURANTES.value,
    # Combustible
    "gasolina": CategoryType.COMBUSTIBLE.value,
    "diesel": CategoryType.COMBUSTIBLE.value,
    # Estacionamiento
    "parking": CategoryType.ESTACIONAMIENTO.value,
    "parqueo": CategoryType.ESTACIONAMIENTO.value,
    # Gimnasio
    "gym": CategoryType.GIMNASIO.value,
    "ejercicio": CategoryType.GIMNASIO.value,
    # Mascotas
    "perro": CategoryType.MASCOTAS.value,
    "gato": CategoryType.MASCOTAS.value,
    "veterinario": CategoryType.MASCOTAS.value,
    # Regalos
    "regalo": CategoryType.REGALOS.value,
    "obsequio": CategoryType.REGALOS.value,
    # Imprevistos
    "emergencia": CategoryType.IMPREVISTOS.value,
    "reparacion": CategoryType.IMPREVISTOS.value,
    "multa": CategoryType.IMPREVISTOS.value,
    "accidente": CategoryType.IMPREVISTOS.value,
    "urgente": CategoryType.IMPREVISTOS.value,
    "grua": CategoryType.IMPREVISTOS.value,
    "imprevisto": CategoryType.IMPREVISTOS.value,
    "inesperado": CategoryType.IMPREVISTOS.value,
    # Otros
    "otro": CategoryType.OTROS.value,
    "other": CategoryType.OTROS.value,
}

# Patterns to extract transaction descriptions from user messages
DESCRIPTION_PATTERNS: list[str] = [
    "gasté en ",
    "gaste en ",
    "compré ",
    "compre ",
    "pagué ",
    "pague ",
    "registra ",
    "agrega ",
    "añade ",
    "categoriza ",
]
