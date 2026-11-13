# ДомДосье

MVP для вайботона: досье на дом из открытых данных.

Репозиторий: https://github.com/BuybackLFG/domdose
Работаем через PR в `main`. Локальная проверка `./scripts/check.sh` обязательна
до PR, CI повторяет её же. Деплой — на VPS через `docker-compose.prod.yml`,
см. [`deploy/README.md`](deploy/README.md).

## Структура

```
backend/            FastAPI + Python 3.12 (uv)
  schemas/          контракт API (Pydantic v2), меняет только техлид
  app/api/          эндпоинты (роутеры)
  app/core/         конфиг
  app/ingest/       загрузка данных и seed
  app/db/           доступ к БД
  tests/            pytest
frontend/           Vite + React 19 + TS + Tailwind 4
  src/types/api.ts  генерируется из OpenAPI, руками не править
data/seed/          JSON для наполнения локальной БД
scripts/            check.sh, gen_api_types.sh, check_api_types.sh
docs/api-contract.md  DOC-2: эндпоинты, модели, правило заморозки
.github/workflows/  ci.yml — лежит готовым, включится после первого пуша
AGENTS.md           правила работы агентов, владельцы, команды
```

## Быстрый старт

```bash
cd backend && uv sync
cd ../frontend && npm install
cd .. && ./scripts/check.sh
```

Разработка (два терминала):

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

- backend: http://localhost:8000, `GET /health` → `{"status":"ok"}`
- frontend: http://localhost:5173

## Проверки

`./scripts/check.sh` — ruff format --check, ruff check, pyright, pytest, сборка фронтенда
и проверка актуальности TS-типов. Exit code 0 = можно коммитить.

## Контракт API

```bash
./scripts/gen_api_types.sh   # frontend/src/types/api.ts из локального /openapi.json
```

Сгенерированный файл коммитим. Если он разошёлся с OpenAPI, `check.sh` падает.

## Seed

```bash
cd backend && uv run seeded
```

Читает `data/seed/*.json`. Пока каталог пуст — заглушки для задачи про модель данных.

## Стек и деплой

- backend: FastAPI + Python 3.12, frontend: React + Vite + TS + Tailwind.
- Прод: VPS, `docker-compose.prod.yml` (Caddy → nginx → uvicorn). См. `deploy/README.md`.
- CI проверяет код на каждый push/PR; выкатка на сервер — вручную (`git pull` + `compose up -d --build`).

## Правила

См. `AGENTS.md`: карта владельцев, порядок ревью, worktree на задачу, запрет на push.
