"""Таблица стадий parse_dataset -> DatasetRejected.code.

Вход каждой строки — валидный синтетический набор с одним дефектом своей
стадии: он проходит все предыдущие стадии. Строгая схема — схема репозитория;
разрешающая пропускает любой объект, чтобы дефект дошёл до разбора.
Сравниваются только тип исключения и код, не текст сообщения.
"""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

import test_scoring_http as http_cases
from api.scoring_main import app as scoring_app
from contract.utility_rating import DatasetRejected, DatasetRejectionCode
from test_scoring_logging import OPERATIONS, assert_no_dataset_content, with_marker
from utility_rating.dataset import parse_dataset

STRICT = http_cases.SCHEMA
PERMISSIVE = {"type": "object"}
INVALID = DatasetRejectionCode.DATASET_INVALID
INCOMPLETE = DatasetRejectionCode.DATASET_INCOMPLETE
SCHEMA_INVALID = DatasetRejectionCode.SCHEMA_INVALID
START = http_cases.WINDOW_START
END = http_cases.WINDOW_END
REMOVE = object()


def base():
    return http_cases.synthetic_raw()


def edit(*changes):
    """Набор с заменами (путь, значение); значение REMOVE удаляет ключ."""
    raw = base()
    for path, value in changes:
        target = raw
        for part in path[:-1]:
            target = target[part]
        if value is REMOVE:
            del target[path[-1]]
        else:
            target[path[-1]] = deepcopy(value)
    return raw


def one_event(started_at, ended_at, **fields):
    raw = base()
    event = deepcopy(raw["events"][0])
    event.update(started_at=started_at, ended_at=ended_at, **fields)
    raw["events"] = [event]
    return raw


def houses(count):
    return http_cases.make_houses(count)


def shifted_houses():
    """Нумерация без пропусков, но не с house_000001."""
    result = houses(20)
    for index, house in enumerate(result, start=2):
        house["house_id"] = f"house_{index:06d}"
    return result


def swapped_addresses():
    raw = base()
    first, second = raw["houses"][:2]
    first["address"], second["address"] = second["address"], first["address"]
    return raw


def casefold_duplicate_address():
    raw = base()
    city, street = raw["houses"][0]["address"].split(", ", 1)
    raw["houses"][1]["address"] = f"{city}, {street.upper()}"
    return raw


def duplicate_incident(source_url=None):
    raw = base()
    duplicate = deepcopy(raw["events"][0])
    if source_url is not None:
        duplicate["source_url"] = source_url
    raw["events"].insert(1, duplicate)
    return raw


def reversed_events():
    raw = base()
    raw["events"].reverse()
    return raw


def incomplete_registry_strict():
    raw = base()
    raw.update(
        registry_complete=False,
        houses=[],
        events=[],
        coverage={category: "incomplete" for category in raw["coverage"]},
    )
    return raw


STAGES = [
    # Схема.
    pytest.param(base(), {"type": "unknown"}, SCHEMA_INVALID, id="schema-broken"),
    pytest.param(
        base(), {"$ref": "#/$defs/missing"}, SCHEMA_INVALID, id="schema-unresolvable"
    ),
    pytest.param(edit((("unexpected",), True)), STRICT, INVALID, id="schema-mismatch"),
    # Полнота справочника и покрытия.
    pytest.param(
        incomplete_registry_strict(), STRICT, INCOMPLETE, id="registry-incomplete"
    ),
    pytest.param(
        edit((("registry_complete",), False)),
        PERMISSIVE,
        INCOMPLETE,
        id="registry-incomplete-with-houses",
    ),
    pytest.param(
        edit((("coverage", "heating"), "incomplete")),
        STRICT,
        INCOMPLETE,
        id="coverage-incomplete",
    ),
    # Окно.
    pytest.param(
        edit((("window", "end"), "2026-01-30T00:00:00+10:00")),
        STRICT,
        INVALID,
        id="window-29-days",
    ),
    pytest.param(
        edit((("window", "end"), "2026-02-01T00:00:00+10:00")),
        STRICT,
        INVALID,
        id="window-31-days",
    ),
    pytest.param(
        edit((("window", "end"), "2025-12-02T00:00:00+10:00")),
        STRICT,
        INVALID,
        id="window-end-before-start",
    ),
    pytest.param(
        edit((("window", "end"), "2026-01-30T23:00:00+09:00")),
        PERMISSIVE,
        INVALID,
        id="window-offset-not-plus-10",
    ),
    pytest.param(
        edit((("window", "start"), "2025-12-31T14:00:00Z")),
        PERMISSIVE,
        INVALID,
        id="window-offset-utc",
    ),
    pytest.param(
        edit((("window", "start"), "2026-01-01T00:00:00")),
        PERMISSIVE,
        INVALID,
        id="window-naive",
    ),
    pytest.param(
        edit((("window", "start"), "01.01.2026 00:00")),
        PERMISSIVE,
        INVALID,
        id="window-not-iso",
    ),
    pytest.param(
        edit((("window", "start"), 20260101)),
        PERMISSIVE,
        INVALID,
        id="window-not-string",
    ),
    # Число домов.
    pytest.param(edit((("houses",), houses(19))), STRICT, INCOMPLETE, id="19-houses"),
    pytest.param(edit((("houses",), houses(1))), STRICT, INCOMPLETE, id="1-house"),
    pytest.param(edit((("houses",), houses(21))), STRICT, INVALID, id="21-houses"),
    pytest.param(edit((("houses",), houses(40))), STRICT, INVALID, id="40-houses"),
    # Справочник.
    pytest.param(
        edit((("houses", 1, "house_id"), "house_000001")),
        STRICT,
        INVALID,
        id="duplicate-house-id",
    ),
    pytest.param(
        edit((("houses", 1, "address"), base()["houses"][0]["address"])),
        STRICT,
        INVALID,
        id="duplicate-address",
    ),
    pytest.param(
        casefold_duplicate_address(), STRICT, INVALID, id="duplicate-address-casefold"
    ),
    pytest.param(
        edit((("houses", 19, "house_id"), "house_000021")),
        STRICT,
        INVALID,
        id="house-id-gap",
    ),
    pytest.param(
        edit((("houses",), shifted_houses()), (("events",), [])),
        STRICT,
        INVALID,
        id="house-id-not-from-one",
    ),
    pytest.param(swapped_addresses(), STRICT, INVALID, id="house-order"),
    # События.
    pytest.param(
        edit((("events", 0, "house_id"), "house_000021")),
        STRICT,
        INVALID,
        id="event-unknown-house",
    ),
    pytest.param(
        one_event("2026-01-02T10:00:00+10:00", "2026-01-02T00:00:00+10:00"),
        STRICT,
        INVALID,
        id="event-end-before-start",
    ),
    pytest.param(one_event(START, START), STRICT, INVALID, id="instant-at-start"),
    pytest.param(one_event(END, END), STRICT, INVALID, id="instant-at-end"),
    pytest.param(
        one_event("2025-12-01T00:00:00+10:00", "2025-12-02T00:00:00+10:00"),
        STRICT,
        INVALID,
        id="event-before-window",
    ),
    pytest.param(
        one_event("2026-02-01T00:00:00+10:00", None),
        STRICT,
        INVALID,
        id="ongoing-event-after-window",
    ),
    pytest.param(
        one_event("2025-12-31T23:00:00+10:00", START),
        STRICT,
        INVALID,
        id="event-ends-at-window-start",
    ),
    pytest.param(
        one_event(END, "2026-01-31T01:00:00+10:00"),
        STRICT,
        INVALID,
        id="event-starts-at-window-end",
    ),
    pytest.param(duplicate_incident(), STRICT, INVALID, id="identical-duplicate"),
    pytest.param(
        duplicate_incident("https://example.test/synthetic/emergency-5h-copy"),
        STRICT,
        INVALID,
        id="duplicate-incident-other-source",
    ),
    pytest.param(reversed_events(), STRICT, INVALID, id="event-order"),
    pytest.param(
        one_event("2026-01-01T23:00:00+09:00", None),
        PERMISSIVE,
        INVALID,
        id="event-offset-not-plus-10",
    ),
    pytest.param(
        one_event("2026-01-02 garbage", None),
        PERMISSIVE,
        INVALID,
        id="event-not-iso",
    ),
]


@pytest.mark.parametrize(("raw", "schema", "code"), STAGES)
def test_each_stage_rejects_with_its_code(raw, schema, code):
    with pytest.raises(DatasetRejected) as caught:
        parse_dataset(raw, schema)

    assert caught.value.code is code


ORDER = [
    pytest.param(
        edit((("unexpected",), True)),
        {"type": "unknown"},
        SCHEMA_INVALID,
        id="broken-schema-before-mismatch",
    ),
    pytest.param(
        edit((("unexpected",), True), (("coverage", "heating"), "incomplete")),
        STRICT,
        INVALID,
        id="mismatch-before-completeness",
    ),
    pytest.param(
        edit(
            (("coverage", "heating"), "incomplete"),
            (("window", "end"), "2026-01-30T00:00:00+10:00"),
        ),
        STRICT,
        INCOMPLETE,
        id="completeness-before-window",
    ),
    pytest.param(
        edit(
            (("window", "end"), "2026-01-30T00:00:00+10:00"),
            (("houses",), houses(19)),
        ),
        STRICT,
        INVALID,
        id="window-before-house-count",
    ),
    pytest.param(
        edit((("houses",), houses(19)), (("events", 0, "house_id"), "house_000020")),
        STRICT,
        INCOMPLETE,
        id="house-count-before-events",
    ),
]


@pytest.mark.parametrize(("raw", "schema", "code"), ORDER)
def test_earlier_stage_decides_the_code(raw, schema, code):
    with pytest.raises(DatasetRejected) as caught:
        parse_dataset(raw, schema)

    assert caught.value.code is code


def structural(path):
    return edit((path, REMOVE))


# Структурные дефекты, которые разрешающая схема пропускает к разбору.
STRUCTURAL = [
    pytest.param(edit((("events", 0, "category"), "gas")), id="unknown-category"),
    pytest.param(edit((("events", 0, "kind"), "unknown")), id="unknown-kind"),
    pytest.param(structural(("registry_complete",)), id="missing-registry-complete"),
    pytest.param(structural(("coverage",)), id="missing-coverage"),
    pytest.param(structural(("coverage", "heating")), id="missing-coverage-category"),
    pytest.param(structural(("window",)), id="missing-window"),
    pytest.param(structural(("window", "end")), id="missing-window-end"),
    pytest.param(structural(("houses",)), id="missing-houses"),
    pytest.param(structural(("houses", 0, "house_id")), id="missing-house-id"),
    pytest.param(structural(("houses", 0, "address")), id="missing-address"),
    pytest.param(structural(("events",)), id="missing-events"),
    pytest.param(structural(("events", 0, "house_id")), id="missing-event-house"),
    pytest.param(structural(("events", 0, "category")), id="missing-category"),
    pytest.param(structural(("events", 0, "started_at")), id="missing-started-at"),
    pytest.param(structural(("events", 0, "ended_at")), id="missing-ended-at"),
    pytest.param(structural(("events", 0, "kind")), id="missing-kind"),
    pytest.param(structural(("events", 0, "is_mass")), id="missing-is-mass"),
    pytest.param(
        structural(("events", 0, "is_natural_disaster")), id="missing-natural"
    ),
    pytest.param(structural(("events", 0, "source_url")), id="missing-source-url"),
]


@pytest.mark.parametrize("raw", STRUCTURAL)
def test_permissive_schema_structural_defect_is_dataset_invalid(raw):
    with pytest.raises(DatasetRejected) as caught:
        parse_dataset(raw, PERMISSIVE)

    assert caught.value.code is INVALID


@pytest.mark.parametrize("url", list(OPERATIONS))
@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(edit((("events", 0, "category"), "gas")), id="unknown-category"),
        pytest.param(edit((("events", 0, "kind"), "unknown")), id="unknown-kind"),
        pytest.param(structural(("events", 0, "kind")), id="missing-kind"),
        pytest.param(structural(("registry_complete",)), id="missing-registry"),
    ],
)
def test_scoring_http_structural_defect_is_422_not_500(
    isolated_execution_log, url, raw
):
    with TestClient(scoring_app, raise_server_exceptions=False) as client:
        response = client.post(url, json=http_cases.envelope(raw, PERMISSIVE))

    http_cases.assert_error(response, 422, "dataset_invalid")
    rejected = with_marker(isolated_execution_log, "SCORING_OPERATION_REJECTED")
    assert [(level, data["code"]) for level, data in rejected] == [
        ("WARNING", "dataset_invalid")
    ]
    assert with_marker(isolated_execution_log, "SCORING_OPERATION_FAILED") == []
    assert_no_dataset_content(isolated_execution_log)


@pytest.mark.parametrize("count", (21, 25))
def test_scoring_http_oversized_registry_is_dataset_invalid(internal_client, count):
    raw = edit((("houses",), houses(count)))

    response = internal_client.post(
        http_cases.PARSE_URL, json=http_cases.envelope(raw)
    )

    http_cases.assert_error(response, 422, "dataset_invalid")


@pytest.fixture
def internal_client():
    with TestClient(scoring_app) as client:
        yield client
