# ДомДосье · backend

FastAPI + Python 3.12 (uv).

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
curl -f http://localhost:8000/health   # {"status":"ok"}
```

Структура:

- `schemas/` — **контракт API** (Pydantic v2). Меняет только техлид, см. `docs/api-contract.md`
- `app/api/` — публичные эндпоинты (роутеры)
- `app/core/` — конфиг и общие настройки
- `app/ingest/` — загрузка и разбор исходных данных
- `app/db/` — доступ к БД
- `tests/` — pytest

Проверки: `../scripts/check.sh` (ruff, pyright, pytest).
