"""Индекс дома: итог, пять компонент, покрытие источников.

Главный инвариант контракта: веса компонент в сумме дают ровно 1.0, а сами
компоненты — ровно пять и все на месте. Это проверяется валидацией модели,
чтобы «магическое число» нельзя было отдать без объяснения.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from schemas.common import Factor, Score, SourceUrl, Weight

WEIGHT_TOLERANCE = 1e-6


class ComponentKey(StrEnum):
    """Пять компонент индекса. Порядок и вес задаёт B3, контракт фиксирует набор."""

    communications = "communications"
    nature = "nature"
    building = "building"
    transport = "transport"
    safety = "safety"


class Component(BaseModel):
    """Одна компонента индекса вместе с объяснением и источниками.

    Объяснение обязательно: жюри и пользователь должны видеть, из чего
    сложилась оценка, а не только число.
    """

    key: ComponentKey
    label: str = Field(min_length=1, max_length=100, description="Название для человека")
    score: Score
    weight: Weight
    explanation: str = Field(
        min_length=1,
        max_length=1000,
        description="Из чего сложилась оценка, человеческим языком",
    )
    source_urls: list[SourceUrl] = Field(
        default_factory=list, description="Источники, на которых основана компонента"
    )


class HouseIndex(BaseModel):
    """Объяснимый индекс дома.

    `coverage` — множитель того, насколько данные полны. Он не прячется внутри
    компонент, а отдаётся наружу, чтобы UI мог честно сказать «данных мало».
    """

    total: Score = Field(description="Итоговый индекс 0–100")
    components: list[Component] = Field(min_length=5, max_length=5)
    coverage: Factor
    coverage_note: str | None = Field(
        default=None, max_length=500, description="Чего не хватает данным, если coverage < 1"
    )
    computed_at: datetime = Field(description="Когда индекс посчитан, ISO 8601")

    @model_validator(mode="after")
    def _components_are_complete_and_normalized(self) -> "HouseIndex":
        keys = [component.key for component in self.components]
        if len(set(keys)) != len(keys):
            raise ValueError("компоненты индекса не должны повторяться")
        missing = set(ComponentKey) - set(keys)
        if missing:
            names = ", ".join(sorted(key.value for key in missing))
            raise ValueError(f"в индексе нет компонент: {names}")
        total_weight = sum(component.weight for component in self.components)
        if abs(total_weight - 1.0) > WEIGHT_TOLERANCE:
            raise ValueError(f"сумма весов компонент должна быть 1.0, получено {total_weight}")
        return self
