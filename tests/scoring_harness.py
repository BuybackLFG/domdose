"""In-process дверь к internal scoring для тестов без сети.

В одном процессе api и scoring пишут разные execution.log: журнал scoring
лежит в подкаталоге scoring рядом с журналом из DOMDOSSE_LOG_FILE_PATH.
Модули реализации импортируются лениво: их отсутствие краснеет в тесте,
а не при сборке всего набора.
"""

from dataclasses import replace
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from core.logging import ServiceName, load_logging_settings, setup_logging


def scoring_log_path() -> Path:
    """Отдельный журнал scoring рядом с журналом текущего теста."""
    base = load_logging_settings(ServiceName.SCORING).file_path
    return base.parent / "scoring" / base.name


def _configure_scoring_log() -> None:
    """Идемпотентно направить сервис scoring в собственный файл."""
    settings = load_logging_settings(ServiceName.SCORING)
    setup_logging(replace(settings, file_path=scoring_log_path()))


def scoring_transport(application=None) -> httpx.MockTransport:
    """httpx.MockTransport в приложение scoring без сети и без lifespan.

    application по умолчанию — api.scoring_main.app.
    """
    if application is None:
        from api.scoring_main import app as application
    internal = TestClient(application)

    def handle(request: httpx.Request) -> httpx.Response:
        _configure_scoring_log()
        path = request.url.path
        if request.url.query:
            path += "?" + request.url.query.decode("ascii")
        response = internal.request(
            request.method,
            path,
            content=request.content,
            headers={"content-type": request.headers.get("content-type", "")},
        )
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )

    return httpx.MockTransport(handle)


def in_process_scoring_client():
    """sources.scoring_client.ScoringClient к in-process scoring."""
    from sources.scoring_client import ScoringClient

    return ScoringClient(base_url="http://scoring", transport=scoring_transport())
