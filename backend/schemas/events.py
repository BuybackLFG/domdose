"""Событие дома: отключение, авария, погодный риск.

Один и тот же тип используется в досье, в ленте и в live-репортах жильцов,
поэтому enum `EventType` — общий словарь для data-потока (D3/D4) и API (B2/W1).
"""

from datetime import date as Date
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from schemas.common import Confidence, Severity, SourceUrl


class EventType(StrEnum):
    """Тип события. Значения зафиксированы: их видят и data-owner, и фронтенд."""

    hot_water = "hot_water"
    cold_water = "cold_water"
    heat = "heat"
    accident = "accident"
    power = "power"
    flood = "flood"
    landslide = "landslide"
    typhoon = "typhoon"
    wind = "wind"
    ice = "ice"
    elevator = "elevator"
    caprepair = "caprepair"
    developer = "developer"
    transport = "transport"


class EventKind(StrEnum):
    """Происхождение события.

    official — официальный источник, confidence = 1.0;
    ai — извлечено LLM из новостей, в индекс идёт только при confidence >= 0.8;
    resident — сообщение жильца через live-краудсорсинг.
    """

    official = "official"
    ai = "ai"
    resident = "resident"


class Event(BaseModel):
    """Событие в ленте дома.

    `id` нужен как ключ в UI и для `ChecklistItem.source_event_ids`.
    Привязано либо к дому, либо к району (события без конкретного адреса).
    """

    id: str = Field(min_length=1, max_length=200, description="Стабильный идентификатор события")
    house_id: str | None = Field(default=None, description="slug дома из houses.json")
    district: str | None = Field(default=None, description="Район, если событие не про дом")
    type: EventType
    date: Date = Field(description="Дата события, ISO")
    severity: Severity
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=2000)
    source_url: SourceUrl
    confidence: Confidence = 1.0
    kind: EventKind = EventKind.official

    @model_validator(mode="after")
    def _needs_house_or_district(self) -> "Event":
        if not self.house_id and not self.district:
            raise ValueError("событие должно быть привязано к house_id или district")
        return self
