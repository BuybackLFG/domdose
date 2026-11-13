"""Служебные модели: healthcheck."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Ответ `/health`. `ok` — единственное валидное состояние на демо."""

    status: Literal["ok"] = Field(description="ok, если сервис жив")
