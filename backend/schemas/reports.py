"""Live-репорт жильца — `POST /api/reports` (задача W1)."""

from datetime import date as Date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from schemas.events import Event, EventType
from schemas.index import ComponentKey


class ReportCreate(BaseModel):
    """Запрос жильца о проблеме дома.

    `anonymous` по умолчанию `true`: контракт не предполагает хранения имени,
    телефона и любых других персональных данных, в том числе в `text`.
    """

    house_id: str = Field(min_length=1, max_length=100)
    type: EventType
    text: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=1000),
    ] = Field(description="Что случилось, словами жильца")
    date: Date | None = Field(default=None, description="Когда случилось; по умолчанию сегодня")
    anonymous: bool = Field(default=True, description="Репорт всегда анонимный на демо")


class IndexChange(BaseModel):
    """Изменение индекса после репорта, с указанием просевшей компоненты.

    Без `component` и `explanation` «индекс упал» неотличим от бага, поэтому
    оба поля обязательны.
    """

    component: ComponentKey = Field(description="Компонента, на которую повлиял репорт")
    explanation: str = Field(
        min_length=1,
        max_length=1000,
        description="Почему индекс изменился именно так",
    )


class ReportResult(BaseModel):
    """Ответ на репорт: созданное событие и индекс до и после пересчёта."""

    event: Event = Field(description="Созданное событие, kind = resident")
    index_before: float = Field(ge=0, le=100)
    index_after: float = Field(ge=0, le=100)
    change: IndexChange

    @property
    def delta(self) -> float:
        """Насколько изменился индекс. Отрицательное значение — индекс просел.

        Вычисляемое свойство, а не поле схемы: в JSON его нет, чтобы не завести
        второй источник правды рядом с `index_before`/`index_after`.
        """
        return self.index_after - self.index_before
