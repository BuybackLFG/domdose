"""Единый формат ошибок API.

FastAPI отдаёт `HTTPException(detail="...")` как `{"detail": "..."}`, поэтому
`ErrorResponse` описывает именно эту форму. Ошибки валидации (422) остаются
встроенными: у них `detail` — список, и подменять его своим форматом значило бы
сломать инструменты, которые уже умеют читать FastAPI.
"""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Ошибка с человекочитаемым `detail`. Код ошибки — в HTTP-статусе."""

    detail: str = Field(
        min_length=1,
        max_length=500,
        description="Что пошло не так, пригодно для показа пользователю",
    )


HOUSE_NOT_FOUND = "house not found"
"""Дословный текст 404 досье (B2). Менять только вместе с тестом."""
