"""Чек-лист вопросов продавцу: пункт и причина, по которой он появился."""

from pydantic import BaseModel, Field


class ChecklistItem(BaseModel):
    """Вопрос продавцу, выведенный из конкретного факта или события дома.

    `reason` обязателен и должен ссылаться на событие или факт: общие вопросы
    вроде «узнайте всё» контрактом не предусмотрены.
    """

    id: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=500, description="Вопрос на русском")
    reason: str = Field(
        min_length=1,
        max_length=1000,
        description="Почему вопрос возник: факт или событие дома",
    )
    source_event_ids: list[str] = Field(
        default_factory=list,
        description="id событий, из которых выведен вопрос",
    )
