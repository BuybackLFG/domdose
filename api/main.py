"""FastAPI-приложение модуля коммунального рейтинга."""

from fastapi import FastAPI

from api.errors import register_error_handlers
from api.routes import router
from core.config import Settings, load_settings
from dossier.service import UtilityRatingService


def create_app(settings: Settings) -> FastAPI:
    """Собрать приложение с сервисом досье в app.state."""
    application = FastAPI(title="ДомДосье — коммунальный рейтинг")
    application.state.service = UtilityRatingService(settings)
    application.include_router(router)
    register_error_handlers(application)
    return application


app = create_app(load_settings())
