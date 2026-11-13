"""Досье дома — ответ `GET /api/houses/{id}` (задача B2)."""

from pydantic import BaseModel, Field

from schemas.checklist import ChecklistItem
from schemas.events import Event
from schemas.facts import DISCLAIMER, Fact, Source
from schemas.houses import House
from schemas.index import HouseIndex


class Dossier(BaseModel):
    """Полное досье: паспорт, индекс, факты, лента событий, чек-лист, источники.

    Это главный ответ продукта. Собирается в `app/core/dossier.py`, контракт
    принадлежит `schemas/` и меняется только техлидом.
    """

    house: House
    index: HouseIndex | None = Field(
        default=None,
        description="null, если индекс ещё не посчитан: досье без индекса валидно",
    )
    facts: list[Fact] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    disclaimer: str = Field(
        default=DISCLAIMER,
        description="Дисклеймер, показывается пользователю дословно",
    )
