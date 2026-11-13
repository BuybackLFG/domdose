"""FastAPI-приложение модуля коммунального рейтинга."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.errors import register_error_handlers
from api.routes import router
from core.config import Settings, load_settings
from core.logging import (
    ServiceName,
    get_logger,
    load_logging_settings,
    setup_logging,
    shutdown_logging,
)
from dossier.service import UtilityRatingService

_logger = get_logger("api.main", service="api")


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup: fail-fast настройка журнала до приёма трафика; shutdown в конце."""
    setup_logging(load_logging_settings(ServiceName.API))
    _logger.info("API_APP_CREATED", "api app created")
    yield
    shutdown_logging()


def create_app(settings: Settings) -> FastAPI:
    """Собрать приложение с сервисом досье в app.state.

    Логирование не настраивается и файлы не создаются до lifespan startup.
    """
    application = FastAPI(title="ДомДосье — коммунальный рейтинг", lifespan=_lifespan)
    application.state.service = UtilityRatingService(settings)
    application.include_router(router)
    register_error_handlers(application)
    return application


app = create_app(load_settings())
