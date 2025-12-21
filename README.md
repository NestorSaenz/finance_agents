# FinanceGPT

Asistente Inteligente Multiagente para Gestión de Finanzas Personales.

## Descripción

FinanceGPT es un asistente financiero personal inteligente basado en arquitectura multiagente con IA Generativa que permite gestionar finanzas personales de forma conversacional y automatizada.

### Características principales

- **Chat conversacional** para gestión de finanzas
- **Categorización automática** de transacciones usando IA
- **Análisis de patrones** de gasto
- **Planificación financiera** personalizada
- **Alertas proactivas** de presupuesto
- **Búsqueda semántica** sobre historial financiero

## Stack Tecnológico

| Componente | Tecnología |
|------------|------------|
| Backend | FastAPI + Python 3.11+ |
| LLM | Cohere Command R+ |
| Embeddings | Cohere Embed v3 Multilingual |
| Vector DB | Pinecone Serverless |
| Base de Datos | Supabase (PostgreSQL) |
| Auth | Supabase Auth |
| Orquestación | LangGraph |
| Observabilidad | Langfuse |
| Frontend | React + TypeScript |

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes)
- Docker (opcional, para desarrollo)
- Cuentas en: Supabase, Cohere, Pinecone, Langfuse

## Instalación

### 1. Clonar repositorio

```bash
git clone <repo-url>
cd financegpt
```

### 2. Instalar dependencias

```bash
uv sync
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales
```

### 4. Ejecutar en desarrollo

```bash
uv run fastapi dev app/main.py
```

La API estará disponible en `http://localhost:8000`.

## Estructura del Proyecto

```
financegpt/
├── app/
│   ├── api/              # Endpoints FastAPI
│   ├── core/             # Configuración, logging, clients
│   └── src/              # Módulos de dominio
│       ├── agents/       # Sistema multiagente (LangGraph)
│       ├── embeddings/   # Cohere + Pinecone
│       ├── transactions/ # Gestión de transacciones
│       ├── budgets/      # Presupuestos
│       ├── goals/        # Objetivos financieros
│       ├── chat/         # Servicio de chat
│       └── users/        # Gestión de usuarios
├── tests/                # Tests
├── docs/                 # Documentación
└── scripts/              # Scripts de utilidad
```

## Documentación

- [Guía de Estructura de Módulos](docs/MODULE_STRUCTURE_GUIDE.md)
- [Arquitectura del Sistema](docs/ARCHITECTURE.md)

## Desarrollo

### Ejecutar tests

```bash
uv run pytest
```

### Linting y formateo

```bash
uv run ruff check .
uv run ruff format .
```

### Type checking

```bash
uv run mypy app/
```

## API Endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/v1/chat` | Enviar mensaje al asistente |
| GET | `/api/v1/transactions` | Listar transacciones |
| POST | `/api/v1/transactions` | Crear transacción |
| GET | `/api/v1/budgets` | Listar presupuestos |
| POST | `/api/v1/budgets` | Crear presupuesto |
| GET | `/api/v1/goals` | Listar objetivos |
| POST | `/api/v1/goals` | Crear objetivo |
| GET | `/health` | Health check |

## Licencia

Este proyecto es parte del Trabajo Final de Máster en Ingeniería y Desarrollo de Soluciones de IA Generativa.

## Autor

Néstor Raúl Sáenz Chajín - 2024
