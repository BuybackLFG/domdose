import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from contract.utility_rating import (
    TimeWindow,
    UtilityCategory,
    UtilityDataset,
)
from utility_rating import score_city
from utility_rating.dataset import parse_dataset

SCHEMA = json.loads(
    (
        Path(__file__).parent.parent
        / "dataset"
        / "utility-rating-dataset.schema.json"
    ).read_text(encoding="utf-8")
)
WINDOW_START_TEXT = "2026-01-01T00:00:00+10:00"
WINDOW_END_TEXT = "2026-01-31T00:00:00+10:00"
WINDOW_START = datetime.fromisoformat(WINDOW_START_TEXT)
WINDOW_END = datetime.fromisoformat(WINDOW_END_TEXT)
CATEGORIES = ("hot_water", "cold_water", "electricity", "heating")
REMOVE = object()


def make_houses(count=20):
    return [
        {
            "house_id": f"house_{index:06d}",
            "address": f"Владивосток, улица Пилотная {index:02d}, 1",
        }
        for index in range(1, count + 1)
    ]


BASE_RAW = {
    "schema_version": "1.0.0",
    "city": "Владивосток",
    "window": {"start": WINDOW_START_TEXT, "end": WINDOW_END_TEXT},
    "registry_source_url": "https://example.test/registry/vladivostok/houses",
    "registry_complete": True,
    "houses": make_houses(),
    "coverage": {category: "complete" for category in CATEGORIES},
    "events": [
        {
            "house_id": "house_000001",
            "category": "electricity",
            "started_at": WINDOW_START_TEXT,
            "ended_at": "2026-01-01T05:00:00+10:00",
            "kind": "emergency",
            "is_mass": False,
            "is_natural_disaster": False,
            "source_url": "https://example.test/notices/electricity/emergency-5h",
        },
        {
            "house_id": "house_000001",
            "category": "electricity",
            "started_at": "2026-01-02T00:00:00+10:00",
            "ended_at": "2026-01-02T10:00:00+10:00",
            "kind": "planned",
            "is_mass": False,
            "is_natural_disaster": False,
            "source_url": "https://example.test/notices/electricity/planned-10h",
        },
    ],
}


def valid_raw():
    return deepcopy(BASE_RAW)


def changed_raw(path, value=REMOVE):
    raw = valid_raw()
    target = raw
    for part in path[:-1]:
        target = target[part]
    if value is REMOVE:
        del target[path[-1]]
    else:
        target[path[-1]] = deepcopy(value)
    return raw


def raw_with_event(started_at, ended_at):
    raw = valid_raw()
    event = deepcopy(raw["events"][0])
    event["started_at"] = started_at
    event["ended_at"] = ended_at
    raw["events"] = [event]
    return raw


def raw_with_unsorted_addresses():
    raw = valid_raw()
    first, second = raw["houses"][:2]
    first["address"], second["address"] = second["address"], first["address"]
    return raw


def raw_with_duplicate_event(source_url=None):
    raw = valid_raw()
    duplicate = deepcopy(raw["events"][0])
    if source_url is not None:
        duplicate["source_url"] = source_url
    raw["events"].insert(1, duplicate)
    return raw


def assert_metrics(category, expected):
    metrics = category.metrics
    actual = (metrics.frequency, metrics.hours, metrics.longest)
    assert actual == pytest.approx(expected)


def test_happy_path_maps_dto_and_preserves_independent_scoring_example():
    dataset = parse_dataset(valid_raw(), SCHEMA)

    assert isinstance(dataset, UtilityDataset)
    assert tuple(house.house_id for house in dataset.houses) == tuple(
        f"house_{index:06d}" for index in range(1, 21)
    )
    assert dataset.window == TimeWindow(WINDOW_START, WINDOW_END)
    assert dataset.complete_categories == frozenset(UtilityCategory)
    assert len(dataset.events) == 2
    assert not hasattr(dataset, "registry_source_url")
    assert all(not hasattr(event, "source_url") for event in dataset.events)

    result = score_city(dataset)
    target = result.ratings["house_000001"]
    electricity = target.categories[UtilityCategory.ELECTRICITY]
    assert_metrics(electricity, (1.4, 9.0, 5.0))
    # Средние 20 домов: (0.07, 0.45, 0.25); все ratio = 20, штрафы = 1.
    penalties = electricity.penalties
    assert (penalties.frequency, penalties.hours, penalties.longest) == (1.0,) * 3
    assert electricity.score == 0.0
    # weighted = 0.7, cap = 0 + 0.25.
    assert target.overall_score == 0.25

    for house_id, empty in result.ratings.items():
        if house_id == "house_000001":
            continue
        assert all(category.score == 1.0 for category in empty.categories.values())
        assert empty.overall_score == 1.0


def test_empty_events_with_complete_data_scores_all_ones():
    raw = valid_raw()
    raw["events"] = []

    result = score_city(parse_dataset(raw, SCHEMA))

    for house in result.ratings.values():
        assert all(category.score == 1.0 for category in house.categories.values())
        assert house.overall_score == 1.0


def test_rejects_schema_valid_incomplete_registry_failure_mode():
    raw = valid_raw()
    raw["registry_complete"] = False
    raw["houses"] = []
    raw["events"] = []
    raw["coverage"] = {category: "incomplete" for category in CATEGORIES}

    with pytest.raises(ValueError):
        parse_dataset(raw, SCHEMA)


@pytest.mark.parametrize("category", CATEGORIES)
def test_rejects_any_incomplete_coverage(category):
    raw = changed_raw(("coverage", category), "incomplete")

    with pytest.raises(ValueError):
        parse_dataset(raw, SCHEMA)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(changed_raw(("unexpected",), "value"), id="extra-field"),
        pytest.param(changed_raw(("city",)), id="missing-required"),
        pytest.param(
            changed_raw(("registry_complete",), "true"), id="wrong-type"
        ),
        pytest.param(
            changed_raw(("events", 0, "category"), "gas"), id="unknown-category"
        ),
        pytest.param(
            changed_raw(("events", 0, "kind"), "unknown"), id="unknown-kind"
        ),
        pytest.param(
            changed_raw(("window", "end"), "2026-01-31T00:00:00+09:00"),
            id="wrong-timezone",
        ),
        pytest.param(
            changed_raw(("window", "start"), "2026-13-99T00:00:00+10:00"),
            id="impossible-calendar-date",
        ),
    ],
)
def test_rejects_schema_invalid_raw(raw):
    with pytest.raises(ValueError):
        parse_dataset(raw, SCHEMA)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(changed_raw(("houses",), []), id="empty-complete-registry"),
        pytest.param(changed_raw(("houses",), make_houses(19)), id="19-houses"),
        pytest.param(changed_raw(("houses",), make_houses(21)), id="21-houses"),
        pytest.param(
            changed_raw(("events", 0, "house_id"), "house_000021"),
            id="unknown-event-house",
        ),
        pytest.param(
            changed_raw(("houses", 1, "house_id"), "house_000001"),
            id="duplicate-house-id",
        ),
        pytest.param(
            changed_raw(
                ("houses", 1, "address"), BASE_RAW["houses"][0]["address"]
            ),
            id="duplicate-address",
        ),
        pytest.param(
            changed_raw(("houses", 19, "house_id"), "house_000021"),
            id="house-id-sequence-gap",
        ),
        pytest.param(raw_with_unsorted_addresses(), id="address-order"),
    ],
)
def test_rejects_invalid_registry_or_house_reference(raw):
    with pytest.raises(ValueError):
        parse_dataset(raw, SCHEMA)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(
            changed_raw(("window", "end"), "2026-01-30T00:00:00+10:00"),
            id="window-not-30-days",
        ),
        pytest.param(
            changed_raw(("window", "end"), "2025-12-31T00:00:00+10:00"),
            id="window-end-before-start",
        ),
        pytest.param(
            raw_with_event(
                "2025-12-01T00:00:00+10:00", "2025-12-02T00:00:00+10:00"
            ),
            id="event-outside-window",
        ),
        pytest.param(
            raw_with_event(WINDOW_START_TEXT, WINDOW_START_TEXT),
            id="zero-at-window-start",
        ),
        pytest.param(
            raw_with_event(WINDOW_END_TEXT, WINDOW_END_TEXT),
            id="zero-at-window-end",
        ),
        pytest.param(
            raw_with_event("2025-12-31T23:00:00+10:00", WINDOW_START_TEXT),
            id="ends-exactly-at-window-start",
        ),
        pytest.param(
            raw_with_event(WINDOW_END_TEXT, "2026-01-31T01:00:00+10:00"),
            id="starts-exactly-at-window-end",
        ),
    ],
)
def test_rejects_invalid_window_or_event_outside_half_open_window(raw):
    with pytest.raises(ValueError):
        parse_dataset(raw, SCHEMA)


def test_accepts_zero_duration_strictly_inside_window():
    raw = raw_with_event(
        "2026-01-15T12:00:00+10:00", "2026-01-15T12:00:00+10:00"
    )

    result = score_city(parse_dataset(raw, SCHEMA))
    category = result.ratings["house_000001"].categories[
        UtilityCategory.ELECTRICITY
    ]

    assert_metrics(category, (1.0, 0.0, 0.0))


@pytest.mark.parametrize(
    ("started_at", "ended_at", "expected_hours"),
    [
        pytest.param(
            "2025-12-31T22:00:00+10:00", None, 720.0, id="ongoing-null-end"
        ),
        pytest.param(
            "2026-01-30T00:00:00+10:00",
            "2026-02-01T00:00:00+10:00",
            24.0,
            id="end-after-window",
        ),
    ],
)
def test_accepts_and_clips_ongoing_or_extended_events(
    started_at, ended_at, expected_hours
):
    raw = raw_with_event(started_at, ended_at)

    result = score_city(parse_dataset(raw, SCHEMA))
    category = result.ratings["house_000001"].categories[
        UtilityCategory.ELECTRICITY
    ]

    assert_metrics(category, (1.0, expected_hours, expected_hours))


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(raw_with_duplicate_event(), id="identical-duplicate"),
        pytest.param(
            raw_with_duplicate_event(
                "https://example.test/notices/electricity/emergency-5h-copy"
            ),
            id="same-incident-other-source",
        ),
    ],
)
def test_rejects_duplicate_incidents(raw):
    with pytest.raises(ValueError):
        parse_dataset(raw, SCHEMA)


def test_rejects_non_deterministic_event_order():
    raw = valid_raw()
    raw["events"].reverse()

    with pytest.raises(ValueError):
        parse_dataset(raw, SCHEMA)


@pytest.mark.parametrize("argument", ("raw", "schema"))
@pytest.mark.parametrize("invalid", (None, [], "not-a-mapping", 1))
def test_rejects_non_mapping_raw_or_schema(argument, invalid):
    raw = invalid if argument == "raw" else valid_raw()
    schema = invalid if argument == "schema" else SCHEMA

    with pytest.raises(TypeError):
        parse_dataset(raw, schema)
