# AGENTS.md — правила работы в репозитории «ДомДосье»

Репозиторий: https://github.com/BuybackLFG/domdose (public).
Ветка `main` защищена от прямых пушей силами команды: изменения идут через PR.
Локальная проверка `./scripts/check.sh` обязательна до PR — CI её дублирует.
Деплой (Fly/Railway/Render/Vercel) пока не настроен и требует отдельного решения тимлида.

## Быстрый старт

```bash
cd backend && uv sync                 # зависимости backend (Python 3.12)
cd frontend && npm install            # зависимости frontend
./scripts/check.sh                    # все проверки, exit 0 = зелёно
```

Запуск для разработки (два терминала):

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev            # http://localhost:5173
curl -f http://localhost:8000/health  # {"status":"ok"}
```

## Порты

| Сервис | Порт | Почему нельзя менять |
| --- | --- | --- |
| backend (uvicorn) | 8000 | на него настроены CORS и `scripts/gen_api_types.sh` |
| frontend (vite) | 5173 | прописан в `CORS_ORIGINS` и `.env.example` |

## Команды

| Команда | Что делает |
| --- | --- |
| `./scripts/check.sh` | ruff format --check, ruff check, pyright, pytest, frontend build, проверка актуальности типов |
| `./scripts/gen_api_types.sh` | генерирует `frontend/src/types/api.ts` из OpenAPI |
| `cd backend && uv run pytest -q` | только тесты |
| `cd backend && uv run seeded` | загружает seed из `data/seed` в локальную БД |
| `cd frontend && npm run dev` | dev-сервер фронтенда |

## Карта владельцев

Изменения в общих файлах делает **только тимлид**. Остальные работают в своих каталогах.

| Область | Файлы | Владелец |
| --- | --- | --- |
| Контракты и схемы | `backend/schemas/`, `frontend/src/types/api.ts` | тимлид |
| Инфраструктура | `.github/`, `scripts/`, `backend/pyproject.toml`, `frontend/package.json` | тимлид |
| Данные и ingest | `backend/app/ingest/`, `data/seed/` | data-owner |
| Backend API | `backend/app/api/`, `backend/app/core/` | backend-owner |
| Frontend | `frontend/src/` (кроме `types/api.ts`) | frontend-owner |

Конфликт: если задача требует правки файла не из твоей зоны — не правь, напиши тимлиду.

## Правила ревью

1. Один PR — одна задача Linear. Ссылка на идентификатор (`DD-XX`) в заголовке.
2. `./scripts/check.sh` зелёный до запроса ревью. Красный CI = ревью не начинается.
3. Новое поведение — с тестом. Багфикс — с тестом, который падал до фикса.
4. Не менять `backend/schemas/` и `frontend/src/types/api.ts` вручную: только через `scripts/gen_api_types.sh`.
5. Секреты только в `.env` (в репозиторий не попадает). В коде — чтение из настроек.
6. Публичные эндпоинты объявляются в `backend/app/api/`, а не в `main.py`.

## Orca worktree на задачу

```bash
orca worktree create dd-42-import-pdf     # отдельный worktree под задачу
cd <worktree>                              # работаем только там
./scripts/check.sh                         # проверки перед сдачей
```

Правила:

- Один worktree = один агент = одна задача.
- Ветка называется `dd-<номер>-<короткий-слаг>`.
- Не переключать ветки внутри чужого worktree.
- После сдачи задачи worktree удаляется, ветка пушится и открывается PR в `main`.

## Статусы в Linear (жёсткое правило)

Автосинка нет, поэтому статус меняется **руками и сразу**:

| Момент | Статус | Комментарий |
| --- | --- | --- |
| Берёшь задачу | `In Progress` **сразу** | «взял в работу» — кто, что делает |
| Сделал | `Done` **сразу** | что сделано, чем проверено, что вне скоупа |
| Нашёл блокер | без смены статуса | `blocked` + причина + кто разблокирует |
| Отдал на ревью (если правда кто-то ревьюит) | `In Review` | ссылка на коммит и вывод `check.sh` |
| Ушёл на другое, не доделав | остаётся `In Progress` | где остановился и почему |

- Сначала статус — потом код. Не «переведу потом».
- `Done` только при выполненных AC и зелёном `./scripts/check.sh`.
- Забыл перевести статус = задача не завершена, даже если код готов.
- Проверка перед `Done`: `./scripts/check.sh` (exit 0) + ручной смоук на 8000/5173.


## Что нельзя

- Прямой `git push` в `main` — только через PR из ветки `dd-<номер>-<слаг>`.
- Деплой на Fly/Railway/Render/Vercel без решения тимлида.
- Правка `.github/workflows/` без тимлида.
- Коммит `.env`, `*.db`, `node_modules/`, `.venv/`.
