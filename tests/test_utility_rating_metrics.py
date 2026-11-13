import math
from datetime import datetime, timedelta, timezone

import pytest

from backend.contract.utility_rating import (
    House,
    MetricValues,
    OutageEvent,
    OutageKind,
    TimeWindow,
    UtilityCategory,
    UtilityDataset,
)
from backend.utility_rating import score_city

TZ = timezone(timedelta(hours=10))
WINDOW_START = datetime(2026, 1, 1, tzinfo=TZ)
WINDOW_END = WINDOW_START + timedelta(days=30)
ALL_CATEGORIES = frozenset(UtilityCategory)


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
    ended_at: datetime | None = WINDOW_START + timedelta(hours=1),
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
) -> UtilityDataset:
    return UtilityDataset(
        houses=make_houses() if houses is None else houses,
        events=events,
        window=TimeWindow(start=WINDOW_START, end=WINDOW_END),
        complete_categories=ALL_CATEGORIES,
    )


def score_category(
    events: tuple[OutageEvent, ...],
    *,
    category: UtilityCategory = UtilityCategory.ELECTRICITY,
    house_count: int = 1,
):
    dataset = make_dataset(events=events, houses=make_houses(house_count))
    return score_city(dataset).ratings["house-0"].categories[category]


def assert_metrics(
    actual: MetricValues,
    *,
    frequency: float,
    hours: float,
    longest: float,
) -> None:
    assert math.isclose(actual.frequency, frequency, abs_tol=1e-12)
    assert math.isclose(actual.hours, hours, abs_tol=1e-12)
    assert math.isclose(actual.longest, longest, abs_tol=1e-12)


@pytest.mark.parametrize(
    ("kind", "is_mass", "is_natural_disaster", "weight"),
    [
        pytest.param(OutageKind.EMERGENCY, False, False, 1.0, id="emergency"),
        pytest.param(OutageKind.EMERGENCY, True, False, 0.5, id="emergency-mass"),
        pytest.param(
            OutageKind.EMERGENCY, False, True, 0.5, id="emergency-disaster"
        ),
        pytest.param(
            OutageKind.EMERGENCY, True, True, 0.5, id="emergency-both-once"
        ),
        pytest.param(OutageKind.PLANNED, False, False, 0.4, id="planned"),
        pytest.param(OutageKind.PLANNED, True, False, 0.2, id="planned-mass"),
        pytest.param(OutageKind.PLANNED, False, True, 0.2, id="planned-disaster"),
        pytest.param(OutageKind.PLANNED, True, True, 0.2, id="planned-both-once"),
    ],
)
def test_event_weight_for_all_kind_and_flag_combinations(
    kind: OutageKind,
    is_mass: bool,
    is_natural_disaster: bool,
    weight: float,
) -> None:
    category = score_category(
        (
            make_event(
                ended_at=WINDOW_START + timedelta(hours=2),
                kind=kind,
                is_mass=is_mass,
                is_natural_disaster=is_natural_disaster,
            ),
        )
    )

    assert_metrics(
        category.metrics, frequency=weight, hours=2 * weight, longest=2 * weight
    )


def test_emergency_and_planned_metrics_example() -> None:
    category = score_category(
        (
            make_event(ended_at=WINDOW_START + timedelta(hours=5)),
            make_event(
                started_at=WINDOW_START + timedelta(days=1),
                ended_at=WINDOW_START + timedelta(days=1, hours=10),
                kind=OutageKind.PLANNED,
            ),
        )
    )

    assert_metrics(category.metrics, frequency=1.4, hours=9.0, longest=5.0)


@pytest.mark.parametrize(
    ("start_offset", "end_offset", "frequency", "hours"),
    [
        pytest.param(-2, 0, 0.0, 0.0, id="ends-exactly-at-window-start"),
        pytest.param(720, 722, 0.0, 0.0, id="starts-exactly-at-window-end"),
        pytest.param(-2, 3, 1.0, 3.0, id="clips-window-start"),
        pytest.param(718, 722, 1.0, 2.0, id="clips-window-end"),
        pytest.param(-2, 722, 1.0, 720.0, id="clips-whole-window"),
        pytest.param(10, None, 1.0, 710.0, id="open-ended-inside"),
        pytest.param(-2, None, 1.0, 720.0, id="open-ended-before-window"),
        pytest.param(10, 10, 1.0, 0.0, id="zero-duration-inside"),
    ],
)
def test_window_boundaries_and_duration_clipping(
    start_offset: int,
    end_offset: int | None,
    frequency: float,
    hours: float,
) -> None:
    category = score_category(
        (
            make_event(
                started_at=WINDOW_START + timedelta(hours=start_offset),
                ended_at=(
                    None
                    if end_offset is None
                    else WINDOW_START + timedelta(hours=end_offset)
                ),
            ),
        )
    )

    assert_metrics(
        category.metrics, frequency=frequency, hours=hours, longest=hours
    )


def test_events_do_not_mix_between_houses_or_categories() -> None:
    result = score_city(
        make_dataset(
            houses=make_houses(2),
            events=(
                make_event(ended_at=WINDOW_START + timedelta(hours=2)),
                make_event(
                    category=UtilityCategory.HOT_WATER,
                    ended_at=WINDOW_START + timedelta(hours=5),
                    kind=OutageKind.PLANNED,
                ),
                make_event(
                    house_id="house-1",
                    ended_at=WINDOW_START + timedelta(hours=10),
                ),
            ),
        )
    )

    target = result.ratings["house-0"].categories
    other = result.ratings["house-1"].categories
    assert_metrics(
        target[UtilityCategory.ELECTRICITY].metrics,
        frequency=1.0,
        hours=2.0,
        longest=2.0,
    )
    assert_metrics(
        target[UtilityCategory.HOT_WATER].metrics,
        frequency=0.4,
        hours=2.0,
        longest=2.0,
    )
    assert_metrics(
        other[UtilityCategory.ELECTRICITY].metrics,
        frequency=1.0,
        hours=10.0,
        longest=10.0,
    )
    assert_metrics(
        other[UtilityCategory.HOT_WATER].metrics,
        frequency=0.0,
        hours=0.0,
        longest=0.0,
    )


def test_no_events_is_zero_metrics_not_missing_data() -> None:
    result = score_city(make_dataset())

    for category in UtilityCategory:
        category_rating = result.ratings["house-0"].categories[category]
        assert_metrics(
            category_rating.metrics, frequency=0.0, hours=0.0, longest=0.0
        )
        assert_metrics(
            category_rating.penalties, frequency=0.0, hours=0.0, longest=0.0
        )
        assert category_rating.score == 1.0
    assert result.ratings["house-0"].overall_score == 1.0
