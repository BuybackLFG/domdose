"""Доменные типы модуля коммунального рейтинга."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, StrEnum
from typing import Mapping


class DatasetRejectionCode(StrEnum):
    """Код отказа набора: битая схема, неверный набор или неполный набор."""

    SCHEMA_INVALID = "schema_invalid"
    DATASET_INVALID = "dataset_invalid"
    DATASET_INCOMPLETE = "dataset_incomplete"


class DatasetRejected(ValueError):
    """Набор или схема непригодны для расчёта; code — класс причины."""

    def __init__(self, code: DatasetRejectionCode, message: str) -> None:
        super().__init__(message)
        self.code = DatasetRejectionCode(code)


class ScoringUnavailable(Exception):
    """Внутренний сервис расчёта недоступен или ответил вне протокола."""


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


# Единственный источник порядка категорий — порядок объявления UtilityCategory.
_CATEGORY_RANK = {category: index for index, category in enumerate(UtilityCategory)}


def category_rank(category: str) -> int:
    """Позиция категории в порядке объявления UtilityCategory.

    Принимает член UtilityCategory или его строковое значение;
    KeyError — неизвестная категория.
    """
    return _CATEGORY_RANK[category]


def ended_rank(ended_at: datetime | None) -> tuple[int, datetime | None]:
    """Ключ окончания события: известные окончания раньше продолжающихся (None)."""
    return (1, None) if ended_at is None else (0, ended_at)


def canonical_event_key(
    house_id: str,
    category: str,
    started_at: datetime,
    ended_at: datetime | None,
    source_url: str,
) -> tuple:
    """Ключ канонического порядка событий файла набора по возрастанию.

    Порядок: house_id, категория, начало, окончание (None последним), source_url.
    """
    return (
        house_id,
        category_rank(category),
        started_at,
        ended_rank(ended_at),
        source_url,
    )


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
    """Результат дома: категории, общий рейтинг и худшая категория."""

    categories: Mapping[UtilityCategory, CategoryRating]
    overall_score: float
    weakest: UtilityCategory


@dataclass(frozen=True)
class CityRating:
    """Результат расчёта набора домов по ключу house_id."""

    ratings: Mapping[str, HouseRating]


@dataclass(frozen=True)
class SourcedEvent:
    """Отключение вместе с адресом источника для показа в досье."""

    event: OutageEvent
    source_url: str


@dataclass(frozen=True)
class ParsedDataset:
    """Проверенный расчётом набор: снимок, справочник, окно и события."""

    snapshot_id: str
    houses: tuple[House, ...]
    window: TimeWindow
    events: tuple[SourcedEvent, ...]
