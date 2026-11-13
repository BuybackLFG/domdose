"""Доменные типы модуля коммунального рейтинга."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping


class UtilityCategory(str, Enum):
    """Коммунальная категория."""

    HOT_WATER = "hot_water"
    COLD_WATER = "cold_water"
    ELECTRICITY = "electricity"
    HEATING = "heating"


class OutageKind(str, Enum):
    """Тип отключения."""

    EMERGENCY = "emergency"
    PLANNED = "planned"


@dataclass(frozen=True)
class TimeWindow:
    """Полуоткрытое окно расчёта [start, end)."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class House:
    """Дом городского справочника."""

    house_id: str
    address: str


@dataclass(frozen=True)
class OutageEvent:
    """Отключение; ended_at None означает продолжающееся событие."""

    house_id: str
    category: UtilityCategory
    started_at: datetime
    ended_at: datetime | None
    kind: OutageKind
    is_mass: bool
    is_natural_disaster: bool


@dataclass(frozen=True)
class UtilityDataset:
    """Нормализованный вход скоринга: справочник, события и контур расчёта."""

    houses: tuple[House, ...]
    events: tuple[OutageEvent, ...]
    window: TimeWindow
    complete_categories: frozenset[UtilityCategory]


@dataclass(frozen=True)
class MetricValues:
    """Три метрики категории дома или три штрафа."""

    frequency: float
    hours: float
    longest: float


@dataclass(frozen=True)
class CategoryRating:
    """Результат одной категории дома."""

    metrics: MetricValues
    penalties: MetricValues
    score: float


@dataclass(frozen=True)
class HouseRating:
    """Результат дома по всем категориям и общий рейтинг."""

    categories: Mapping[UtilityCategory, CategoryRating]
    overall_score: float


@dataclass(frozen=True)
class CityRating:
    """Результат расчёта набора домов по ключу house_id."""

    ratings: Mapping[str, HouseRating]
