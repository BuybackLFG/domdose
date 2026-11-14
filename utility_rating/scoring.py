"""Чистый расчёт городского рейтинга коммунальной надёжности."""

import math
from datetime import datetime, timedelta
from typing import Mapping

from contract.utility_rating import (
    CategoryRating,
    CityRating,
    House,
    HouseRating,
    MetricValues,
    OutageEvent,
    OutageKind,
    TimeWindow,
    UtilityCategory,
    UtilityDataset,
)
from utility_rating.metrics import (
    clipped_duration_hours,
    event_weight,
    overlaps_window,
)

_WINDOW_LENGTH = timedelta(days=30)
_TZ_OFFSET = timedelta(hours=10)
_METRIC_WEIGHTS = MetricValues(0.4, 0.4, 0.2)
# Один взвешенный инцидент или час на шкале соответствующей метрики.
_METRIC_PRIORS = MetricValues(1.0, 1.0, 1.0)
_CATEGORY_WEIGHTS: Mapping[UtilityCategory, float] = {
    UtilityCategory.ELECTRICITY: 0.30,
    UtilityCategory.COLD_WATER: 0.25,
    UtilityCategory.HEATING: 0.25,
    UtilityCategory.HOT_WATER: 0.20,
}
_WORST_CATEGORY_CAP_MARGIN = 0.25
_ZERO_BUCKET = (0.0, 0.0, 0.0)


def score_city(dataset: UtilityDataset) -> CityRating:
    """Оценить все дома переданной выборки по окну датасета."""
    if not isinstance(dataset, UtilityDataset):
        raise TypeError("dataset must be UtilityDataset")
    houses = _validated_houses(dataset)
    window = _validated_window(dataset.window)
    _validated_categories(dataset)

    known_house_ids = frozenset(house.house_id for house in houses)
    metrics_by_house: dict[tuple[str, UtilityCategory], list[float]] = {}
    for event in dataset.events:
        _validate_event(event, known_house_ids)
        if not overlaps_window(event.started_at, event.ended_at, window):
            continue
        weight = event_weight(event)
        hours = weight * clipped_duration_hours(event, window)
        key = (event.house_id, event.category)
        bucket = metrics_by_house.setdefault(key, [0.0, 0.0, 0.0])
        bucket[0] += weight
        bucket[1] += hours
        bucket[2] = max(bucket[2], hours)

    house_count = len(houses)
    averages = {
        category: MetricValues(
            *(
                sum(
                    metrics_by_house.get((house.house_id, category), _ZERO_BUCKET)[index]
                    for house in houses
                )
                / house_count
                for index in range(3)
            )
        )
        for category in UtilityCategory
    }

    ratings: dict[str, HouseRating] = {}
    for house in houses:
        house_categories: dict[UtilityCategory, CategoryRating] = {}
        for category in UtilityCategory:
            metrics = MetricValues(
                *metrics_by_house.get((house.house_id, category), (0.0, 0.0, 0.0))
            )
            house_categories[category] = _score_category(metrics, averages[category])
        weakest = weakest_category(house_categories)
        ratings[house.house_id] = HouseRating(
            categories=house_categories,
            overall_score=_overall_score(house_categories, weakest),
            weakest=weakest,
        )
    return CityRating(ratings=ratings)


def weakest_category(
    categories: Mapping[UtilityCategory, CategoryRating],
) -> UtilityCategory:
    """Худшая категория дома: минимальная оценка из четырёх.

    При равенстве оценок выбирается первая в порядке UtilityCategory.
    """
    return min(UtilityCategory, key=lambda category: categories[category].score)


def _validated_houses(dataset: UtilityDataset) -> tuple[House, ...]:
    """Проверить справочник домов и вернуть его."""
    houses = dataset.houses
    if not isinstance(houses, tuple) or not houses:
        raise ValueError("houses must be a non-empty tuple")
    for house in houses:
        if not isinstance(house, House):
            raise TypeError("house must be House")
    house_ids = [house.house_id for house in houses]
    addresses = [house.address for house in houses]
    if any(not isinstance(value, str) for value in (*house_ids, *addresses)):
        raise TypeError("house_id and address must be str")
    if len(set(house_ids)) != len(house_ids):
        raise ValueError("house_id values must be unique")
    if len(set(addresses)) != len(addresses):
        raise ValueError("address values must be unique")
    return houses


def _validated_categories(dataset: UtilityDataset) -> frozenset[UtilityCategory]:
    """Проверить полноту категорий и вернуть контур."""
    complete = dataset.complete_categories
    if not isinstance(complete, frozenset):
        raise TypeError("complete_categories must be frozenset")
    if any(not isinstance(category, UtilityCategory) for category in complete):
        raise TypeError("complete_categories must contain UtilityCategory")
    if complete != frozenset(UtilityCategory):
        raise ValueError("complete_categories must include all four categories")
    return complete


def _validated_window(window: TimeWindow) -> TimeWindow:
    """Проверить окно: осознанные даты с +10 и ровно 30 дней."""
    if not isinstance(window, TimeWindow):
        raise TypeError("window must be TimeWindow")
    _check_moment(window.start, "window.start")
    _check_moment(window.end, "window.end")
    if window.end < window.start:
        raise ValueError("window end must not be before start")
    if window.end - window.start != _WINDOW_LENGTH:
        raise ValueError("window must be exactly 30 days")
    return window


def _validate_event(event: OutageEvent, known_house_ids: frozenset[str]) -> None:
    """Проверить типы и даты события до отсечения вне окна."""
    if not isinstance(event, OutageEvent):
        raise TypeError("event must be OutageEvent")
    if not isinstance(event.house_id, str) or event.house_id not in known_house_ids:
        raise ValueError(f"unknown house_id: {event.house_id!r}")
    if not isinstance(event.category, UtilityCategory):
        raise TypeError("event category must be UtilityCategory")
    if not isinstance(event.kind, OutageKind):
        raise TypeError("event kind must be OutageKind")
    if not isinstance(event.is_mass, bool) or not isinstance(
        event.is_natural_disaster, bool
    ):
        raise TypeError("event flags must be bool")
    _check_moment(event.started_at, "event.started_at")
    if event.ended_at is not None:
        _check_moment(event.ended_at, "event.ended_at")
        if event.ended_at < event.started_at:
            raise ValueError("event end must not be before start")


def _check_moment(value: datetime, field: str) -> None:
    """Проверить timezone-aware datetime со смещением +10:00."""
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be datetime")
    offset = value.utcoffset() if value.tzinfo is not None else None
    if offset is None:
        raise ValueError(f"{field} must be timezone-aware")
    if offset != _TZ_OFFSET:
        raise ValueError(f"{field} must use +10:00 offset")


def _score_category(metrics: MetricValues, average: MetricValues) -> CategoryRating:
    """Оценить категорию: штрафы за превышение среднего и итог."""
    penalties = MetricValues(
        *(
            _penalty(metric, avg, prior)
            for metric, avg, prior in zip(
                (metrics.frequency, metrics.hours, metrics.longest),
                (average.frequency, average.hours, average.longest),
                (_METRIC_PRIORS.frequency, _METRIC_PRIORS.hours, _METRIC_PRIORS.longest),
                strict=True,
            )
        )
    )
    score = 1.0 - sum(
        weight * penalty
        for weight, penalty in zip(
            (_METRIC_WEIGHTS.frequency, _METRIC_WEIGHTS.hours, _METRIC_WEIGHTS.longest),
            (penalties.frequency, penalties.hours, penalties.longest),
            strict=True,
        )
    )
    return CategoryRating(metrics=metrics, penalties=penalties, score=score)


def _penalty(metric: float, average: float, prior: float) -> float:
    """Сгладить сравнение с выборкой опорной единицей метрики."""
    if metric <= average:
        return 0.0
    return min(1.0, math.log2((metric + prior) / (average + prior)) / 3.0)


def _overall_score(
    categories: Mapping[UtilityCategory, CategoryRating], weakest: UtilityCategory
) -> float:
    """Взвешенная сумма с ограничением по худшей категории weakest."""
    weighted = sum(
        _CATEGORY_WEIGHTS[category] * rating.score
        for category, rating in categories.items()
    )
    worst = categories[weakest].score
    return min(weighted, worst + _WORST_CATEGORY_CAP_MARGIN)
