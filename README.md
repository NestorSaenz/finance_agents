# Safi
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-multiagente-1C3C3C)
![Vertex AI](https://img.shields.io/badge/Vertex%20AI-Gemini-4285F4?logo=googlecloud&logoColor=white)
![Cloud Run](https://img.shields.io/badge/Deploy-Cloud%20Run-4285F4?logo=googlecloud&logoColor=white)
![mypy](https://img.shields.io/badge/mypy-strict-2A6DB2)

**Asistente conversacional multiagente para la gestión de finanzas personales, basado en IA Generativa.**

Safi permite registrar, consultar, corregir y analizar movimientos económicos escribiendo en lenguaje
natural, en lugar de rellenar formularios o mantener una hoja de cálculo. Además, admite la carga de
una imagen o un PDF (una factura, una captura de una hoja de cálculo) para extraer de ellos los
movimientos de forma asistida.

> Trabajo Final de Máster — Máster en Ingeniería y Desarrollo de Soluciones de IA Generativa.
> Autor: Néstor Raúl Sáenz Chajín.

## Características

- **Gestión conversacional** de transacciones, presupuestos, metas de ahorro y tarjetas de crédito
  (crear, consultar, corregir y eliminar en lenguaje natural).
- **Categorización automática** mediante RAG, con soporte de **categorías propias** definidas por el
  usuario.
- **Ingesta multimodal**: extracción de movimientos a partir de una imagen o un PDF, con
  confirmación previa (pregunta lo ambiguo antes de registrar).
- **Memoria** conversacional (corto plazo) y conocimiento persistente del usuario (largo plazo).
- **Autenticación** con aislamiento estricto de datos por usuario.
- **Observabilidad** de coste y comportamiento, y **panel de resumen** (dashboard).

## Arquitectura

La aplicación se compone de un backend (FastAPI) y un frontend (Next.js). El backend orquesta con
**LangGraph** un clasificador de intención económico (enrutador) y un **agente ReAct** con
*tool-calling* que ejecuta acciones sobre datos reales a través de herramientas por dominio. La
categorización se apoya en RAG (embeddings + pgvector) y la lógica sigue una arquitectura limpia por
capas (rutas → servicios → repositorios).

## Stack tecnológico

| Componente | Tecnología |
|------------|------------|
| Backend | Python 3.12, FastAPI |
| Orquestación de agentes | LangGraph, LangChain |
| Modelo de lenguaje | Vertex AI (Gemini 2.5) con respaldo en Groq (Llama 3.3) |
| Embeddings | Vertex AI (gemini-embedding-001, 768) |
| Base de datos y vectores | Supabase (PostgreSQL + pgvector) |
| Autenticación | Supabase Auth (JWT) |
| Observabilidad | Langfuse, Sentry, Grafana |
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Despliegue | Docker, Google Cloud Run, Secret Manager |

## Puesta en marcha (local)

```bash
# Backend (desde la raíz)
uv sync
cp .env.example .env   # completa las credenciales (Supabase, Vertex, …)
uv run uvicorn app.main:app --port 8000 --reload

# Frontend (en otra terminal)
cd frontend
npm install
cp .env.local.example .env.local
npm run dev            # http://localhost:3000
```

Las credenciales se externalizan en un archivo `.env` (a partir de `.env.example`). El despliegue en
Google Cloud Run está documentado en [`DEPLOY.md`](DEPLOY.md).

> **Para revisar sin credenciales:** no hacen falta claves ni servicios externos para verificar el
> código. Las pruebas usan dobles (mocks/fakes), así que basta con `uv sync` y ejecutar los comandos
> de la sección [Calidad](#calidad).

## Estructura del proyecto

```
app/          Backend: api/ (rutas), agents/ (LangGraph), src/ (módulos de dominio),
              shared/ (clientes e interfaces), core/ (configuración, logging, observabilidad)
frontend/     Aplicación web (Next.js)
database/     Esquema y migraciones SQL
tests/        Pruebas unitarias e integración
docs/         Documentación técnica: ARCHITECTURE.md y MODULE_STRUCTURE_GUIDE.md
```

> La memoria del TFM se entrega por separado (no forma parte del repositorio).

## Calidad

El proyecto se valida con análisis de tipos estricto (mypy), *linting* (ruff) y una batería de
pruebas automatizadas (backend y frontend). Los comandos (no requieren credenciales):

```bash
# Backend (desde la raíz)
uv run ruff check .          # linting
uv run mypy app/             # tipos estrictos
uv run pytest -q             # pruebas (unitarias + integración con dobles)

# Frontend (desde frontend/)
npm run lint
npm run typecheck            # tsc --noEmit (strict)
npm run test
npm run build                # build de producción
```

## Autor

Néstor Raúl Sáenz Chajín — 2026
