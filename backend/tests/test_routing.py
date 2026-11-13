"""Публичные пути API и префикс `/api` — то, что ломается молча.

Исторический дефект: backend объявлял роутеры под `/api`, а nginx срезал этот
префикс перед проксированием. В результате `/api/health` отвечал 200 (он живёт
вне `/api`), а `/api/houses` и остальные реальные эндпоинты отдавали 404.
Тесты ниже фиксируют обе стороны стыка: путь в приложении и конфиг nginx.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import API_PREFIX, app

client = TestClient(app)

NGINX_CONF = Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf"

# Пути, которые фронтенд зовёт снаружи, ровно как в docs/api-contract.md.
PUBLIC_PATHS = ("/houses", "/compare", "/reports")


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_paths_live_under_api_prefix(path: str) -> None:
    schema = client.get("/openapi.json").json()

    assert f"{API_PREFIX}{path}" in schema["paths"], f"эндпоинт должен быть под {API_PREFIX}"


def test_health_available_with_and_without_prefix() -> None:
    """`/health` нужен Docker/Caddy, `/api/health` — внешнему контракту."""
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get(f"{API_PREFIX}/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ("/houses", "/houses/rus-65", "/compare", "/reports"))
def test_paths_without_prefix_do_not_exist(path: str) -> None:
    """Срезанный путь не должен отвечать: иначе nginx снова начнёт ломать маршруты.

    Если этот тест упадёт, значит в приложении появился дубль маршрута без `/api`,
    и срезающий nginx перестанет быть заметен на healthcheck.
    """
    assert client.get(path).status_code == 404


def test_nginx_forwards_api_prefix_untouched() -> None:
    """nginx обязан проксировать `/api/*` без `rewrite`, иначе реальные пути дадут 404."""
    conf = NGINX_CONF.read_text(encoding="utf-8")

    assert "location /api/" in conf
    assert "rewrite ^/api/" not in conf, (
        "nginx не должен срезать /api: backend сам смонтирован под ним"
    )
    assert "proxy_pass http://$backend_upstream:8000;" in conf
