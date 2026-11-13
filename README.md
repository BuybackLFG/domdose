# ДомДосье

Краткий MVP сервиса оценки надёжности покупки и аренды жилья во Владивостоке.
Пользователь вводит адрес или ссылку на объявление и получает досье конкретного дома.

Первый модуль — рейтинг надёжности коммунальных услуг по отключениям горячей и
холодной воды, электричества и отопления за скользящие 30 дней. Формула и веса —
в `docs/DOMAIN.md`.

## Текущее состояние

Реализованы чистое математическое ядро скоринга (`utility_rating`), строгий
JSON-загрузчик пилотной выборки, публичный FastAPI-слой (`api.main`), внутренний
HTTP-сервис расчёта (`api.scoring_main`), централизованное логирование
(`core/logging.py`) и frontend (`frontend/`). Введён Docker Compose из трёх сервисов
(`compose.yaml`). Документы прошлых итераций не являются источником требований.

Реальный приближённый MVP-датасет записывается в `dataset/output/utility-rating.json`
и не коммитится. Самостоятельный комплект для внешней модели находится в `dataset/`:
промпт, strict-схема и инструкция сохранения. Расчётный контур MVP — пилотная выборка
из 20 домов, по 4 в каждом из пяти районов; среднее и рейтинг относятся только к этой
выборке, а не ко всему городу. Без полного набора приложение показывает отсутствие
данных, а не тестовые значения.

## Стек

### Backend

* Python 3.13, FastAPI, Pydantic, Uvicorn, jsonschema;
* модульный монолит с абсолютными импортами, пакеты только в корне репозитория;
* чистые доменные расчёты без сети, базы и часов;
* pytest и Ruff;
* постоянного хранилища нет; PostgreSQL появится только при подтверждённой потребности.

Зависимости: `requirements.txt` (приложение) и `requirements-dev.txt` (плюс инструменты
проверки).

### Frontend

Фактический стек — `frontend/package.json` и `frontend/package-lock.json`:

* React 19, TypeScript 6 (strict), Vite 8;
* Tailwind CSS 4 через `@tailwindcss/vite`;
* Leaflet 1.9 с локальным `L.imageOverlay`, без онлайн-подложек;
* Inter Variable (`@fontsource-variable/inter`) и Tabler Icons;
* Vitest, Testing Library и jsdom;
* Oxlint;
* feature-структура `src/features`, единый API-клиент в `src/lib`, общая настройка
  тестов в `src/test`;
* относительный `/api` в development и production: Vite proxy в разработке, Nginx в
  Compose.

Lockfile создан Node.js 24 и npm 11.

## Архитектурный стиль

Предметная логика других приложений не переносится. Используются следующие
архитектурные принципы:

* небольшие пакеты по технической ответственности с явными дверями, а не одинаковые
  слои в каждом пакете;
* направленные зависимости без обратных ссылок;
* централизованные конфигурация и логирование;
* неизменяемые dataclass/Enum внутри и Pydantic на HTTP/конфигурационной границе;
* изоляция внешних источников адаптерами;
* абсолютные импорты;
* тесты-сторожа архитектурных границ и расчётных инвариантов.

Для MVP сохраняется KISS: новые слои и пакеты появляются вместе с реальным сценарием,
а не заранее пустыми каталогами.

## Backend: команды

Все команды выполняются из корня репозитория:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check api contract core dossier sources utility_rating tests
```

Локальный запуск без Docker — два процесса:

```powershell
# внутренний расчёт
.venv\Scripts\python.exe -m uvicorn api.scoring_main:app --port 8001
# публичный API (в другом терминале)
.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

По умолчанию `api` обращается к scoring по `http://127.0.0.1:8001`; другой адрес
задаётся `DOMDOSSE_SCORING_URL`. `--reload` применим только для разработки.

Публичные endpoints `api.main`:

* `GET /api/health` — процесс жив, датасет не читается;
* `GET /api/ready` — датасет доступен, полный для пилотного расчёта и посчитан;
* `GET /api/houses` — 20 домов и общие оценки;
* `GET /api/houses/{house_id}` — метрики, штрафы и оценки категорий дома.

Внутренний `api.scoring_main` отвечает на `GET /health` и `GET /ready` и выполняет
расчёт для `api`; браузеру и хосту в Compose он недоступен.

Первый успешный расчёт кэшируется до перезапуска процесса `api`; после замены датасета
нужен restart.

## Frontend: команды

Из каталога `frontend/` (scripts из `frontend/package.json`):

```powershell
npm ci
npm test
npm run lint
npm run build
npm run dev
```

`npm run dev` поднимает Vite на порту 5173 и проксирует `/api` на
`http://127.0.0.1:8000` (локальный uvicorn).

Изображение карты — локальный asset `frontend/public/maps/vladivostok-pilot.png` с
манифестом `vladivostok-pilot.manifest.json`. Источник, лицензия, bbox и команда
воспроизведения — в `map-preparation/README.md`.

## Переменные окружения

| Переменная | Сервис | Назначение |
|---|---|---|
| `DOMDOSSE_UTILITY_RATING_DATASET_PATH` | api | путь к JSON датасета; по умолчанию `dataset/output/utility-rating.json` |
| `DOMDOSSE_UTILITY_RATING_SCHEMA_PATH` | api | путь к схеме; по умолчанию `dataset/utility-rating-dataset.schema.json` |
| `DOMDOSSE_SCORING_URL` | api | базовый адрес внутреннего scoring (http/https без credentials и query); по умолчанию `http://127.0.0.1:8001`, в Compose `http://scoring:8001` |
| `DOMDOSSE_LOG_FILE_PATH` | api, scoring | файловый `execution.log`; по умолчанию `logs/<service>/execution.log` |
| `DOMDOSSE_LOG_LEVEL` | api, scoring | уровень журнала, по умолчанию `INFO` |
| `DOMDOSSE_LOG_STDOUT` | api, scoring | дублировать события в stdout (`true`/`false`), по умолчанию `true` |
| `DOMDOSSE_DATASET_DIR` | Compose | каталог хоста с `utility-rating.json`; по умолчанию `./dataset/output` |

Относительные пути считаются от корня репозитория. Настройки читаются централизованно
в `core`.

## Docker Compose

`compose.yaml` описывает ровно три сервиса:

| Сервис | Образ | Ответственность |
|---|---|---|
| `api` | `api/Dockerfile`, контекст — корень | FastAPI `api.main:app` на 8000, чтение датасета и cache, сценарий досье |
| `scoring` | `api/scoring.Dockerfile`, контекст — корень | stateless `api.scoring_main:app` на 8001, единственная дверь к `utility_rating` |
| `frontend` | `frontend/Dockerfile`, контекст — `frontend/` | SPA под Nginx, локальная карта, proxy `/api/` на `api:8000` |

Базовые образы закреплены тегом и digest: `python:3.13.18-slim-trixie`,
`node:24.22.3-alpine` (только стадия сборки), `nginx:1.30.6-alpine`. Python-зависимости
ставятся `pip install --no-cache-dir -r requirements.txt`, frontend — `npm ci` по
lockfile. Корневой `.dockerignore` пропускает в контекст только пакеты приложения,
`requirements.txt` и схему датасета; реальные выгрузки `dataset/output`, `.env`, `.git`,
`tests` и `frontend` в образы `api` и `scoring` не попадают. Python-сервисы работают от
непривилегированного пользователя с read-only корневой файловой системой.

Сеть:

* `internal` (`internal: true`) — общая сеть трёх сервисов без выхода наружу;
  `api` и `scoring` подключены только к ней и не публикуют портов;
* `edge` — обычная сеть только для `frontend`: Docker не публикует порт контейнера,
  подключённого исключительно к internal-сети. Цена: у контейнера `frontend` есть
  технически возможный исходящий доступ, хотя Nginx наружу не обращается;
* единственный опубликованный порт — `127.0.0.1:8080` → `frontend:80`.

Браузер обращается только к `frontend`, `frontend` — к `api`, `api` — к `scoring`.
Nginx не проксирует `scoring`.

Датасет монтируется только в `api`, read-only:
`${DOMDOSSE_DATASET_DIR:-./dataset/output}` → `/data/dataset`.

Журналы — отдельный named volume у каждого сервиса, файл
`/var/log/domdossier/execution.log` внутри контейнера:

* `api_logs`, `scoring_logs` — маркированные события `core/logging.py`;
* `frontend_logs` — access-строки Nginx в формате
  `[TIMESTAMP] [LEVEL] [frontend] [HTTP_REQUEST] ... | data={...}` (путь без query) и
  error-строки в штатном формате Nginx. Успешные внутренние healthcheck-запросы не
  пишутся, отказы пишутся.

Центрального сервера логов нет; `docker compose logs` — вспомогательный вывод.

Health и readiness (healthcheck каждого сервиса проверяет обе):

| Сервис | Liveness | Readiness |
|---|---|---|
| `api` | `GET /api/health` | `GET /api/ready` |
| `scoring` | `GET /health` | `GET /ready` |
| `frontend` | `GET /health` | `GET /ready` — `index.html`, карта и её манифест на месте, иначе 503; healthcheck дополнительно запрашивает `/maps/vladivostok-pilot.png` |

Порядок старта: `scoring` healthy → `api` → `frontend` healthy. `stop_grace_period`
у всех — 30s; uvicorn завершает запросы за `--timeout-graceful-shutdown 25`, Nginx
останавливается по `SIGQUIT` (graceful).

Команды (из корня репозитория):

```powershell
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs --no-color api scoring frontend
docker compose restart api scoring frontend
docker compose down
```

`docker compose down` выполняется без `-v`: удаление volumes с журналами — отдельная
необратимая операция. Другой каталог датасета:
`$env:DOMDOSSE_DATASET_DIR = "C:\path\to\dataset-dir"` перед `docker compose up -d`.

Смена датасета: заменить `utility-rating.json` в смонтированном каталоге, выполнить
`docker compose restart api` и дождаться `healthy` в `docker compose ps` (readiness
повторно читает и считает набор). Nginx разрешает адрес `api` при старте; если `api`
пересоздан (`up -d` после изменения конфигурации или образа), перезапустить и
`frontend`. Ошибка нового набора оставляет `api` неготовым.

## Ветки

* `main` — общая основа, регламент и принятые изменения;
* `module/<имя>` — отдельная ветка каждого прикладного модуля (`module/utility-rating`,
  `module/frontend`, `module/compose`);
* изменения одного модуля не смешиваются с реализацией другого;
* remote `origin` существует, но push по регламенту не выполняется; коммиты остаются
  в локальном репозитории.

## Регламент и агенты

* `AGENTS.md` — обязательные правила проекта, команды и границы;
* `main-persona.md` — роль главного оркестратора и выбор моделей;
* `agents/` — определения специализированных ролей;
* `docs/DOMAIN.md` — предметные правила рейтинга;
* `dataset/README.md` — запуск сбора и путь итогового датасета;
* `map-preparation/README.md` — подготовка локального изображения карты.

## Локальная среда

Проверено в среде создания проекта: Python 3.13, Node.js 24, npm 11, Docker Engine 29
и Docker Compose v5.
