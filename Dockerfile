# Safi backend (FastAPI) — container for Cloud Run.
# Vertex AI auth uses the Cloud Run service account (ADC); no key files needed.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# uv for fast, reproducible installs from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install ONLY dependencies (the app runs from source, so we don't build the
# root package — avoids needing README.md and speeds up the build).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# App code.
COPY ./app ./app

ENV PATH="/app/.venv/bin:$PATH"

# Cloud Run injects $PORT (default 8080). Bind to it.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
