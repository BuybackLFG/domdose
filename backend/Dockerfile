# Сборка: docker build -f backend/Dockerfile -t domdose-backend .
# Запуск (локальная проверка образа): docker run --rm -p 8001:8000 domdose-backend
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

WORKDIR /app/backend

# Локальный пакет устанавливается из корня репозитория.
COPY pyproject.toml /app/pyproject.toml
COPY core /app/core
COPY contract /app/contract
COPY rating /app/rating
COPY data/datasets/communal-outages-2026.json /app/data/datasets/communal-outages-2026.json
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/app ./app
COPY backend/schemas ./schemas
RUN uv sync --locked --no-dev

ENV PATH="/app/backend/.venv/bin:$PATH"

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=30s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/ready').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
