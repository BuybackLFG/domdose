# API-контракт «ДомДосье» (DOC-2)

Единственный источник правды — `backend/schemas/`. Документ описывает то же самое
словами, но при расхождении прав `schemas/`, а не этот файл: типы для фронтенда
генерируются из OpenAPI, то есть из кода.

## Правило заморозки

**Контракт меняет только техлид.** Задачи B1/B2/B3/B4/F1–F6/W1/W2 реализуют логику,
но не редактируют `backend/schemas/` и не правят `frontend/src/types/api.ts` руками.
Нужно новое поле — заявка техлиду, он меняет модель, генерирует типы, и только
после этого задача продолжается.

Почему так: `GET /api/houses` и `GET /api/houses/{id}` пишутся параллельно с UI.
Если обе стороны меняют форму ответа на ходу, интеграция ломается в момент демо.

## Эндпоинты

| Метод | Путь | Модель ответа | Задача |
| --- | --- | --- | --- |
| GET | `/health` | `HealthResponse` | I2 |
| GET | `/api/houses?q=` | `HouseList` | B1 |
| GET | `/api/houses/{id}` | `Dossier`, 404 → `ErrorResponse` | B2 |
| GET | `/api/compare?ids=a,b` | `CompareResponse` | F5 |
| POST | `/api/reports` | `ReportResult` (201) | W1 |

Роутеры в `app/` подключены с `API_PREFIX = "/api"`, и nginx в Docker-стеке
проксирует `/api/*` в backend **без переписывания пути**: `/api/houses`
уходит в `backend:8000/api/houses`. Срезать префикс нельзя — иначе реальные
эндпоинты отвечали бы 404, а `GET /api/health` маскировал бы это, потому что
health смонтирован ещё и без префикса для Docker/Caddy. Внешний контракт —
всегда с `/api`.

Сейчас эндпоинты отдают `501 Not Implemented` с телом `{"detail": "..."}`.
Это намеренно: форма ответа и валидация уже зафиксированы, а бизнес-логика
появится в своих задачах. Фронтенд может разрабатываться против типов и моков.

## Модели

### House
Паспорт дома, поля 1:1 с `data/seed/houses.json` (D2): `id`, `address`, `district`,
`lat`, `lon`, `year`, `floors`, `material`, `wear_pct`, `uk`, `avariy`, `caprepair`,
`developer`, `source_urls`, `retrieved_at`.

Неизвестное значение — `null`. `0` и пустая строка означают реальные данные,
а не «не знаем»: индекс обязан отличать отсутствие данных от плохих данных.

### HouseSummary / HouseList
`HouseSummary` — строка поиска: `id`, `address`, `district`, `index` (nullable),
`components` (краткие). `HouseList` — обёртка `items`, `total`, `query`,
`retrieved_at`. Обёртка, а не голый массив, чтобы позже добавить пагинацию без
ломающего изменения.

### HouseIndex / Component
`total` 0–100, `coverage` 0–1, `coverage_note` (чего не хватает),
`computed_at`. Ровно пять компонент с ключами `communications`, `nature`,
`building`, `transport`, `safety`.

Инварианты проверяются валидацией, а не соглашением:

- компонент ровно пять и они не повторяются;
- сумма `weight` равна `1.0` (допуск `1e-6`);
- у каждой компоненты есть `explanation` — индекс обязан быть объяснимым;
- `coverage` вынесен наружу, чтобы UI мог честно показать неполноту данных.

### Event
`id`, `house_id` | `district` (обязательно хотя бы одно), `type` (enum из 11
значений), `date`, `severity` 1–3, `title`, `summary`, `source_url`,
`confidence` 0–1, `kind` ∈ `official` | `ai` | `resident`.

Правила data-потока, зашитые в контракт: `official` → `confidence = 1.0`;
`ai` попадает в индекс только при `confidence ≥ 0.8`, ниже — в карантин;
`resident` создаётся через `POST /api/reports`.

### Fact / Source / DISCLAIMER
Факт обязан иметь `source_url` и `retrieved_at`. Дисклеймер —
`DISCLAIMER = "аналитика по открытым данным, не гарантия"` — живёт в коде
(`schemas/facts.py`) и по умолчанию подставляется в `Dossier`, чтобы его нельзя
было случайно переформулировать в одном месте и забыть в другом.

### ChecklistItem
`id`, `question`, `reason`, `source_event_ids`. `reason` обязателен: общие
вопросы вроде «узнайте всё» контрактом не предусмотрены.

### ReportCreate / ReportResult
Запрос: `house_id`, `type`, `text` (3–1000 символов, обрезается по краям),
`date` (по умолчанию сегодня), `anonymous = true`. Персональные данные
не предусмотрены.

Ответ: `event` (kind = resident), `index_before`, `index_after`, `change`
(`component` + `explanation`). Без объяснения «индекс упал» неотличим от бага.
Разницу `index_after - index_before` фронтенд считает сам: отдельного поля `delta`
в JSON нет, чтобы не держать рядом с границами второй источник правды.

### CompareResponse
`houses` — ровно два разных дома, `weaker_house_id` — один из них,
`summary` обязателен. Контракт запрещает «победителя без объяснения».

### ErrorResponse
`{"detail": "..."}`. 404 досье — дословно `house not found`. Ошибки валидации
(422) остаются встроенными в FastAPI: подменять их своим форматом значило бы
сломать инструменты, которые уже умеют их читать.

## Генерация типов

```bash
./scripts/gen_api_types.sh     # frontend/src/types/api.ts из OpenAPI
./scripts/check_api_types.sh   # проверка актуальности (входит в check.sh и CI)
```

`frontend/src/types/index.ts` — ручные алиасы над сгенерированными типами.
Добавлять туда интерфейсы нельзя, только `export type X = Schemas['X']`.

## Проверка

```bash
cd backend && uv run pytest tests/test_schemas.py -q
```

Тесты фиксируют: round-trip демо-досье, сумму весов, запрет неполного индекса,
обязательность `house_id`/`district` у события, ровно два разных дома в сравнении,
валидацию репорта, наличие всех эндпоинтов и моделей в OpenAPI и дословность
дисклеймера и `house not found`.
