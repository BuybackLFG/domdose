"""Точка сборки FastAPI-приложения.

Правило: публичные эндпоинты живут в `app/api/`, здесь только подключение.
Контракт ответов — в `backend/schemas/`, его меняет только техлид.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.compare import router as compare_router
from app.api.health import router as health_router
from app.api.houses import router as houses_router
from app.api.reports import router as reports_router
from app.core.config import get_settings
from schemas import ErrorResponse

API_PREFIX = "/api"
"""Префикс публичного API. nginx в проде проксирует `/api/*` как есть, без среза."""


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ДомДосье API",
        version="0.1.0",
        description="Досье на дом из открытых данных: поиск, индекс, события, чек-лист.",
        responses={
            500: {
                "model": ErrorResponse,
                "description": "Внутренняя ошибка",
            }
        },
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # /health — для Docker/Caddy (внутренний healthcheck, идёт напрямую в backend).
    # /api/health — тот же ответ для внешнего контракта: снаружи всё живёт под /api.
    # В OpenAPI не попадает: это операционная ручка, а не часть контракта API.
    app.include_router(health_router)
    app.include_router(health_router, prefix=API_PREFIX, include_in_schema=False)
    app.include_router(houses_router, prefix=API_PREFIX)
    app.include_router(compare_router, prefix=API_PREFIX)
    app.include_router(reports_router, prefix=API_PREFIX)
    return app


app = create_app()
