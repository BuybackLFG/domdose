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

Реальный приближённый MVP-датасет `dataset/output/utility-rating.json` по решению
владельца отслеживается в Git, поэтому Compose и локальный api работают сразу после
checkout; прочие выгрузки в `dataset/output/` не коммитятся. Самостоятельный комплект для внешней модели находится в `dataset/`:
промпт, strict-схема и инструкция сохранения. Расчётный контур MVP — пилотная выборка
из 20 домов, по 4 в каждом из пяти районов; среднее и рейтинг относятся только к этой
выборке, а не ко всему городу. Без полного набора приложение показывает отсутствие
данных, а не тестовые значения.

## Быстрый старт

Нужен только Docker с Compose v2. Всё необходимое для запуска лежит в репозитории:
датасет `dataset/output/utility-rating.json`, подложка карты `frontend/public/maps/`,
точные версии зависимостей `constraints.txt` и `frontend/package-lock.json`. Сеть нужна
только на этапе сборки образов (pip, npm, базовые образы); во время работы сервисы во
внешний интернет не обращаются.

```powershell
git clone <url репозитория> domdossier
cd domdossier
git checkout <ветка>
docker compose up -d --build
docker compose ps
```

Приложение: http://127.0.0.1:8080. Подробности — в разделе «Docker Compose».

## Стек

### Backend

* Python 3.13, FastAPI, Pydantic, Uvicorn, jsonschema;
* модульный монолит с абсолютными импортами, пакеты только в корне репозитория;
* чистые доменные расчёты без сети, базы и часов;
* pytest и Ruff;
* постоянного хранилища нет; PostgreSQL появится только при подтверждённой потребности.

Зависимости: `requirements.txt` (приложение, диапазоны версий), `requirements-dev.txt`
(плюс инструменты проверки) и `constraints.txt` — точные версии всех прикладных пакетов,
включая транзитивные, фактически разрешённые `pip` для Linux-образов `api` и `scoring`.
Образы ставят `requirements.txt` только вместе с `-c constraints.txt`; инструменты
проверки (`pytest`, `ruff`) в `constraints.txt` не входят.

Обновление `constraints.txt` (из корня репозитория, сеть нужна только на этом шаге;
образ — тот же тег и digest, что в `FROM` обоих Python-Dockerfile):

```powershell
docker run --rm -e PIP_DISABLE_PIP_VERSION_CHECK=1 -e PIP_ROOT_USER_ACTION=ignore -v "${PWD}\requirements.txt:/req/requirements.txt:ro" python:3.13.18-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 sh -c "pip install --no-cache-dir -q -r /req/requirements.txt && pip freeze" | Set-Content -Encoding ascii constraints.txt
docker compose build
```

Обновлять при изменении `requirements.txt` или базового образа, затем прогнать тесты.

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

Чтобы версии прикладных пакетов локального окружения совпали с образами, установку
можно ограничить тем же файлом:
`.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -c constraints.txt`
(инструменты проверки и Windows-only зависимости, например `colorama`, им не
ограничиваются).

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

Каждый ответ-ошибка `api` вида `{"error": {"code": ...}}` несёт тот же код в заголовке
`X-DomDossier-Error` (`dataset_unavailable`, `scoring_unavailable`, `house_not_found`,
`invalid_request`, `internal_error`). Отклонённый scoring набор (`schema_invalid`,
`dataset_invalid`, `dataset_incomplete`) — публично 503 `dataset_unavailable`.

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

Подложка карты — локальные assets одного кадра 2:1 в `frontend/public/maps/`: обзорный
уровень `vladivostok-pilot.png`, детальный `vladivostok-pilot-detail.png` и манифест
`vladivostok-pilot.manifest.json` (bounds, `detail.min_zoom`, `max_zoom`). Leaflet держит один
`L.imageOverlay` и подменяет его источник на детальный уровень при зуме не меньше
`detail.min_zoom`. Источник, лицензия, рамка и команды воспроизведения — в
`map-preparation/README.md`.

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
| `frontend` | `frontend/Dockerfile`, контекст — `frontend/` | SPA под Nginx, локальная карта, proxy `/api/` на `api:8000`, ворота данных для документов SPA |

Базовые образы закреплены тегом и digest: `python:3.13.18-slim-trixie`,
`node:24.22.3-alpine` (только стадия сборки), `nginx:1.30.6-alpine`. Python-зависимости
ставятся `pip install --no-cache-dir -r requirements.txt -c constraints.txt` (точные
версии, см. «Backend»), frontend — `npm ci` по lockfile. Каждый Python-образ получает
ровно модули замыкания импортов своей точки входа и `__init__.py` их пакетов: в `api` нет
`api/scoring_main.py` и `utility_rating`, в `scoring` нет `api/main.py`, `routes.py`,
`schemas.py`, `errors.py`, `dossier`, `core/config.py` и клиентского кода `sources`;
CLI-адаптер `sources/legacy_dataset.py` не попадает ни в один. Новый модуль в графе
импортов точки входа добавляется в её `COPY` и в allowlist корневого `.dockerignore`.
Корневой `.dockerignore` пропускает в контекст только эти файлы, `requirements.txt`,
`constraints.txt` и схему датасета; реальные выгрузки `dataset/output`, `.env`, `.git`,
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
Nginx не проксирует `scoring`. Адрес `api` Nginx переразрешает в runtime через DNS
Docker (`resolver 127.0.0.11 valid=10s`, upstream `server api:8000 resolve`): старт
`frontend` не требует разрешимого `api`, пересоздание `api` не требует перезапуска
`frontend`.

Ворота данных: документы SPA (`/`, `/index.html` и SPA-fallback) отдаются только при
готовности `api` — Nginx проверяет `GET /api/ready` подзапросом `auth_request` (без
query и тела клиента). Иначе 503, короткая страница «Данные недоступны» без SPA и
заголовок `X-DomDossier-Error` с кодом из `api` (`dataset_unavailable`,
`scoring_unavailable`) или `api_unavailable`, если `api` не ответил кодом (не запущен,
недоступен). `/assets/` и `/maps/` воротами не закрыты: без документа SPA они
бесполезны и данных досье не содержат. `/api/` проксируется как есть.

Датасет монтируется только в `api`, read-only:
`${DOMDOSSE_DATASET_DIR:-./dataset/output}` → `/data/dataset`.

Журналы — отдельный named volume у каждого сервиса, файл
`/var/log/domdossier/execution.log` внутри контейнера:

* `api_logs`, `scoring_logs` — маркированные события `core/logging.py`;
* `frontend_logs` — access-строки Nginx в формате
  `[TIMESTAMP] [LEVEL] [frontend] [HTTP_REQUEST] ... | data={...}` (путь без query,
  `upstream_status`, `error_code` из отправленного `X-DomDossier-Error`). error-строки
  пишутся только уровня `crit` и выше в штатном формате Nginx (они могут содержать
  строку запроса с query); штатные отказы запросов видны в access-строках. Успешные
  внутренние healthcheck-запросы не пишутся, отказы пишутся.

Центрального сервера логов нет; `docker compose logs` — вспомогательный вывод.

Health и readiness (healthcheck каждого сервиса проверяет обе):

| Сервис | Liveness | Readiness |
|---|---|---|
| `api` | `GET /api/health` | `GET /api/ready` |
| `scoring` | `GET /health` | `GET /ready` |
| `frontend` | `GET /health` (без `api`) | `GET /ready` — `index.html`, оба изображения карты (`vladivostok-pilot.png`, `vladivostok-pilot-detail.png`) и манифест на месте и `api` готов, иначе 503 с `reason`; healthcheck дополнительно запрашивает `/maps/vladivostok-pilot.png` |

Порядок старта: `scoring` healthy → `api` → `frontend` после запуска (не готовности)
`api`: при отсутствующем или битом датасете `api` неготов, а `frontend` всё равно
стартует и отдаёт 503 с кодом причины; его healthcheck при этом `unhealthy`. `stop_grace_period`
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
повторно читает и считает набор). Ошибка нового набора оставляет `api` неготовым, а
документы SPA — закрытыми воротами с кодом причины.

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
