import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from contract.utility_rating import (
    House,
    MetricValues,
    OutageEvent,
    OutageKind,
    TimeWindow,
    UtilityCategory,
    UtilityDataset,
)
from utility_rating import score_city

TZ = timezone(timedelta(hours=10))
WINDOW_START = datetime(2026, 1, 1, tzinfo=TZ)
WINDOW_END = WINDOW_START + timedelta(days=30)
ALL_CATEGORIES = frozenset(UtilityCategory)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "utility_rating" / "two_houses.json"


def make_houses(count: int = 1) -> tuple[House, ...]:
    return tuple(
        House(house_id=f"house-{index}", address=f"Synthetic address {index}")
        for index in range(count)
    )


def make_event(
    *,
    house_id: str = "house-0",
    category: UtilityCategory = UtilityCategory.ELECTRICITY,
    started_at: datetime = WINDOW_START,
    ended_at: datetime | None = WINDOW_START + timedelta(hours=2),
    kind: OutageKind = OutageKind.EMERGENCY,
    is_mass: bool = False,
    is_natural_disaster: bool = False,
) -> OutageEvent:
    return OutageEvent(
        house_id=house_id,
        category=category,
        started_at=started_at,
        ended_at=ended_at,
        kind=kind,
        is_mass=is_mass,
        is_natural_disaster=is_natural_disaster,
    )


def make_dataset(
    events: tuple[OutageEvent, ...] = (),
    houses: tuple[House, ...] | None = None,
    *,
    window: TimeWindow | None = None,
    complete_categories: frozenset[UtilityCategory] = ALL_CATEGORIES,
) -> UtilityDataset:
    return UtilityDataset(
        houses=make_houses() if houses is None else houses,
        events=events,
        window=TimeWindow(WINDOW_START, WINDOW_END) if window is None else window,
        complete_categories=complete_categories,
    )


def assert_values(actual: MetricValues, expected: MetricValues) -> None:
    for field in ("frequency", "hours", "longest"):
        assert math.isclose(
            getattr(actual, field), getattr(expected, field), abs_tol=1e-12
        )


def load_two_house_dataset() -> UtilityDataset:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return UtilityDataset(
        houses=tuple(House(**house) for house in raw["houses"]),
        events=tuple(
            OutageEvent(
                house_id=event["house_id"],
                category=UtilityCategory(event["category"]),
                started_at=datetime.fromisoformat(event["started_at"]),
                ended_at=datetime.fromisoformat(event["ended_at"]),
                kind=OutageKind(event["kind"]),
                is_mass=event["is_mass"],
                is_natural_disaster=event["is_natural_disaster"],
            )
            for event in raw["events"]
        ),
        window=TimeWindow(
            start=datetime.fromisoformat(raw["window"]["start"]),
            end=datetime.fromisoformat(raw["window"]["end"]),
        ),
        complete_categories=frozenset(
            UtilityCategory(category) for category in raw["complete_categories"]
        ),
    )


@pytest.mark.parametrize(
    ("house_count", "expected_penalty"),
    [
        pytest.param(2, 1 / 3, id="two-times-average"),
        pytest.param(4, 2 / 3, id="four-times-average"),
        pytest.param(8, 1.0, id="eight-times-average"),
        pytest.param(16, 1.0, id="above-eight-times-saturates"),
    ],
)
def test_penalty_log_scale_and_saturation(
    house_count: int, expected_penalty: float
) -> None:
    result = score_city(
        make_dataset(events=(make_event(),), houses=make_houses(house_count))
    )
    category = result.ratings["house-0"].categories[UtilityCategory.ELECTRICITY]

    # Пустые дома входят в знаменатель: каждая метрика целевого дома в N раз выше среднего.
    assert_values(
        category.penalties,
        MetricValues(expected_penalty, expected_penalty, expected_penalty),
    )
    assert math.isclose(category.score, 1.0 - expected_penalty, abs_tol=1e-12)


def test_no_penalty_at_or_below_city_average() -> None:
    result = score_city(
        make_dataset(
            houses=make_houses(2),
            events=(
                make_event(ended_at=WINDOW_START + timedelta(hours=1)),
                make_event(
                    house_id="house-1", ended_at=WINDOW_START + timedelta(hours=2)
                ),
            ),
        )
    )
    category = result.ratings["house-0"].categories[UtilityCategory.ELECTRICITY]

    # frequency равна среднему; hours и longest меньше среднего.
    assert_values(category.penalties, MetricValues(0.0, 0.0, 0.0))
    assert category.score == 1.0


def test_zero_average_of_duration_metrics_does_not_hide_frequency_penalty() -> None:
    result = score_city(
        make_dataset(
            houses=make_houses(2),
            events=(
                make_event(
                    started_at=WINDOW_START + timedelta(hours=1),
                    ended_at=WINDOW_START + timedelta(hours=1),
                ),
            ),
        )
    )
    category = result.ratings["house-0"].categories[UtilityCategory.ELECTRICITY]

    assert_values(category.metrics, MetricValues(1.0, 0.0, 0.0))
    assert_values(category.penalties, MetricValues(1 / 3, 0.0, 0.0))
    assert math.isclose(category.score, 1 - 0.4 / 3, abs_tol=1e-12)


def test_longest_metric_has_independent_twenty_percent_weight() -> None:
    target_event = make_event(ended_at=WINDOW_START + timedelta(hours=4))
    other_events = tuple(
        make_event(
            house_id="house-1",
            started_at=WINDOW_START + timedelta(days=index),
            ended_at=WINDOW_START + timedelta(days=index, hours=1),
        )
        for index in range(4)
    )
    result = score_city(
        make_dataset(houses=make_houses(2), events=(target_event, *other_events))
    )
    category = result.ratings["house-0"].categories[UtilityCategory.ELECTRICITY]

    # ratio longest = 4 / ((4 + 1) / 2) = 8/5; остальные штрафы нулевые.
    longest_penalty = math.log2(8 / 5) / 3
    assert_values(
        category.penalties, MetricValues(0.0, 0.0, longest_penalty)
    )
    assert math.isclose(category.score, 1 - 0.2 * longest_penalty, abs_tol=1e-12)


def test_hours_metric_has_independent_forty_percent_weight() -> None:
    target_events = tuple(
        make_event(
            started_at=WINDOW_START + timedelta(days=index),
            ended_at=WINDOW_START + timedelta(days=index, hours=4),
            kind=OutageKind.PLANNED,
        )
        for index in range(4)
    )
    other_events = (
        make_event(
            house_id="house-1", ended_at=WINDOW_START + timedelta(hours=4)
        ),
        make_event(
            house_id="house-1",
            started_at=WINDOW_START + timedelta(hours=1),
            ended_at=WINDOW_START + timedelta(hours=1),
        ),
    )
    result = score_city(
        make_dataset(houses=make_houses(2), events=(*target_events, *other_events))
    )
    category = result.ratings["house-0"].categories[UtilityCategory.ELECTRICITY]

    # Целевой дом: (f, h, l) = (1.6, 6.4, 1.6), другой: (2, 4, 4).
    hours_penalty = math.log2(16 / 13) / 3
    assert_values(category.penalties, MetricValues(0.0, hours_penalty, 0.0))
    assert math.isclose(category.score, 1 - 0.4 * hours_penalty, abs_tol=1e-12)


@pytest.mark.parametrize(
    ("category", "weight"),
    [
        pytest.param(UtilityCategory.ELECTRICITY, 0.30, id="electricity"),
        pytest.param(UtilityCategory.COLD_WATER, 0.25, id="cold-water"),
        pytest.param(UtilityCategory.HEATING, 0.25, id="heating"),
        pytest.param(UtilityCategory.HOT_WATER, 0.20, id="hot-water"),
    ],
)
def test_category_weights_are_applied_before_cap(
    category: UtilityCategory, weight: float
) -> None:
    result = score_city(
        make_dataset(
            houses=make_houses(2), events=(make_event(category=category),)
        )
    )
    house = result.ratings["house-0"]

    # Категория равна 2/3, остальные равны 1; cap равен 11/12.
    assert math.isclose(house.categories[category].score, 2 / 3, abs_tol=1e-12)
    expected = min(1 - weight / 3, 11 / 12)
    assert math.isclose(house.overall_score, expected, abs_tol=1e-12)


def test_zero_electricity_score_caps_overall_at_quarter() -> None:
    result = score_city(
        make_dataset(houses=make_houses(8), events=(make_event(),))
    )
    house = result.ratings["house-0"]

    assert house.categories[UtilityCategory.ELECTRICITY].score == 0.0
    for category in ALL_CATEGORIES - {UtilityCategory.ELECTRICITY}:
        assert house.categories[category].score == 1.0
    # weighted = 0.7, но worst_category + 0.25 = 0.25.
    assert house.overall_score == 0.25


def test_independent_two_house_example_from_fixture() -> None:
    result = score_city(load_two_house_dataset())

    assert set(result.ratings) == {"house-target", "house-empty"}
    target = result.ratings["house-target"]
    electricity = target.categories[UtilityCategory.ELECTRICITY]
    assert_values(electricity.metrics, MetricValues(1.4, 9.0, 5.0))

    # Средние по двум домам: (0.7, 4.5, 2.5); все ratio = 2, штрафы = 1/3.
    city_average = (0.7, 4.5, 2.5)
    house_metrics = (1.4, 9.0, 5.0)
    for house_value, average in zip(house_metrics, city_average, strict=True):
        assert math.isclose(house_value / average, 2.0, abs_tol=1e-12)
        assert math.isclose(math.log2(house_value / average) / 3, 1 / 3)
    assert_values(electricity.penalties, MetricValues(1 / 3, 1 / 3, 1 / 3))
    assert math.isclose(electricity.score, 2 / 3, abs_tol=1e-12)

    for category in ALL_CATEGORIES - {UtilityCategory.ELECTRICITY}:
        assert target.categories[category].score == 1.0
    # weighted = 0.30*(2/3) + 0.25 + 0.25 + 0.20 = 0.9; cap = 11/12.
    assert 0.9 < 11 / 12
    assert math.isclose(target.overall_score, 0.9, abs_tol=1e-12)

    empty = result.ratings["house-empty"]
    assert all(empty.categories[category].score == 1.0 for category in ALL_CATEGORIES)
    assert empty.overall_score == 1.0


def test_rejects_empty_house_directory() -> None:
    with pytest.raises((ValueError, TypeError)):
        score_city(make_dataset(houses=()))


@pytest.mark.parametrize("missing_category", list(UtilityCategory))
def test_rejects_incomplete_category_data(missing_category: UtilityCategory) -> None:
    with pytest.raises((ValueError, TypeError)):
        score_city(
            make_dataset(
                complete_categories=ALL_CATEGORIES - {missing_category}
            )
        )


def test_rejects_event_for_unknown_house() -> None:
    with pytest.raises((ValueError, TypeError)):
        score_city(make_dataset(events=(make_event(house_id="unknown"),)))


@pytest.mark.parametrize(
    "dataset_factory",
    [
        pytest.param(
            lambda: make_dataset(
                window=TimeWindow(WINDOW_START.replace(tzinfo=None), WINDOW_END)
            ),
            id="naive-window-start",
        ),
        pytest.param(
            lambda: make_dataset(
                window=TimeWindow(WINDOW_START, WINDOW_END.replace(tzinfo=None))
            ),
            id="naive-window-end",
        ),
        pytest.param(
            lambda: make_dataset(
                events=(make_event(started_at=WINDOW_START.replace(tzinfo=None)),)
            ),
            id="naive-event-start",
        ),
        pytest.param(
            lambda: make_dataset(
                events=(make_event(ended_at=WINDOW_START.replace(tzinfo=None)),)
            ),
            id="naive-event-end",
        ),
    ],
)
def test_rejects_naive_datetimes(dataset_factory) -> None:
    with pytest.raises((ValueError, TypeError)):
        score_city(dataset_factory())


@pytest.mark.parametrize(
    "dataset_factory",
    [
        pytest.param(
            lambda: make_dataset(
                events=(
                    make_event(
                        started_at=WINDOW_START + timedelta(hours=2),
                        ended_at=WINDOW_START + timedelta(hours=1),
                    ),
                )
            ),
            id="event-end-before-start",
        ),
        pytest.param(
            lambda: make_dataset(
                window=TimeWindow(
                    WINDOW_START, WINDOW_START - timedelta(microseconds=1)
                )
            ),
            id="window-end-before-start",
        ),
    ],
)
def test_rejects_end_before_start(dataset_factory) -> None:
    with pytest.raises((ValueError, TypeError)):
        score_city(dataset_factory())


@pytest.mark.parametrize("invalid_value", [-1.0, math.nan, math.inf, -math.inf])
def test_rejects_negative_and_non_finite_temporal_inputs(invalid_value: float) -> None:
    # Числовой timestamp не является timezone-aware datetime и должен отклоняться.
    with pytest.raises((ValueError, TypeError)):
        score_city(make_dataset(events=(make_event(started_at=invalid_value),)))
