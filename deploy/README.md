# Деплой на VPS

Схема: `Caddy (TLS, 80/443)` → `frontend (nginx, статика + /api)` → `backend (uvicorn:8000)`.

Всё описано в `docker-compose.prod.yml`, конфиг Caddy — `deploy/Caddyfile`.

## Что нужно на сервере

- Docker Engine + Compose plugin (`docker compose version` должен работать);
- открытые порты 80 и 443;
- A-запись домена, указывающая на IP сервера (для автоматического TLS от Let's Encrypt).

## Первый запуск

```bash
# на сервере
git clone --branch pred_main https://github.com/BuybackLFG/domdose.git
cd domdose

cp .env.prod.example .env
$EDITOR .env            # DOMAIN, ACME_EMAIL, CORS_ORIGINS

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl -f https://$DOMAIN/ready
```

## Обновление

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Простой на время сборки — секунды; база лежит в docker-volume `db-data` и переживает
пересоздание контейнеров.

## Проверка после деплоя

| Что | Как | Ожидание |
| --- | --- | --- |
| Caddy жив | `curl -f https://$DOMAIN/health` | `ok` |
| Готовность данных | `curl -f https://$DOMAIN/api/ready` | HTTP 200; при отсутствии или ошибке датасета — 503 |
| Список и досье | `curl -f https://$DOMAIN/api/houses`, затем `/api/houses/<id>` | HTTP 200, реальные данные |
| Frontend | `curl -f https://$DOMAIN/` | 200, HTML |
| CORS | открыть сайт, статус backend на главной | `ok` |
| Контейнеры | `docker compose -f docker-compose.prod.yml ps` | все `healthy` |

## Локальная проверка конфигов (без VPS)

```bash
docker compose -f docker-compose.prod.yml up -d --build
curl -H "Host: localhost" http://127.0.0.1/health
curl -f http://127.0.0.1/ready
curl -f http://127.0.0.1/api/houses
curl -f http://127.0.0.1/api/houses/h-01
docker compose -f docker-compose.prod.yml down
```

Для локального запуска задайте `DOMAIN=http://localhost` в `.env`; Caddy будет работать по HTTP.
Образ backend собирается из корня репозитория и включает runtime-пакет и датасет
`data/datasets/communal-outages-2026.json`. Проверка готовности проверяет этот
датасет; `DATASET_PATH` позволяет указать другой путь внутри контейнера.
Фронтенд использует относительные URL `/api/...`, production использует API.
CI дополнительно проверяет запрос браузера и отказ готовности при отсутствии данных.

Так проверяется вся связка, кроме TLS: сертификат Caddy выпустит только на реальном домене.

## Откат

```bash
git log --oneline -5
git checkout <предыдущий-коммит>
docker compose -f docker-compose.prod.yml up -d --build
```

## Секреты

`.env` на сервере в git не попадает (см. `.gitignore`). В репозитории только
`.env.prod.example` с пустыми значениями.

## Ограничения текущего этапа

- Деплой ручной: CI проверяет код, сборку образов и smoke-тест стека, но ничего не выкатывает.
- Автодеплой по push в `main` — отдельное решение (нужен ssh-ключ в GitHub Secrets).
- SQLite в volume: один инстанс backend, без горизонтального масштабирования.
