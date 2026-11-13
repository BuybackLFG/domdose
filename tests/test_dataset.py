import copy
import json
import re

import pytest
from pydantic import ValidationError
from schema_original import ORIGINAL_SCHEMA

from contract.dataset import Dataset, dataset_schema, read_dataset
from contract.errors import ContractIssue, ContractRefused

CANARY = "DO_NOT_DISCLOSE_canary_7f31"


def put(value, path, replacement):
    node = value
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = replacement


def assert_safe(error, canary=CANARY):
    seen = set()

    def visit(value):
        if id(value) in seen:
            return
        seen.add(id(value))
        assert canary not in str(value)
        assert canary not in repr(value)
        if isinstance(value, BaseException):
            visit(vars(value))
            visit(value.args)
            if value.__cause__ is not None:
                visit(value.__cause__)
            if value.__context__ is not None:
                visit(value.__context__)
        elif isinstance(value, dict):
            for key, item in value.items():
                visit(key)
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(error)


def assert_issues(error, path):
    assert isinstance(error.issues, tuple) and error.issues
    assert all(isinstance(i, ContractIssue) for i in error.issues)
    assert all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", i.code) for i in error.issues)
    assert all(isinstance(i.path, tuple) for i in error.issues)
    assert any(i.path[: len(path)] == path for i in error.issues), error.issues


def test_schema_is_exact_fresh_copy():
    first = dataset_schema()
    assert first == ORIGINAL_SCHEMA
    first["properties"]["meta"]["required"].clear()
    first["$defs"]["outage_type"]["enum"].append("fake")
    assert dataset_schema() == ORIGINAL_SCHEMA
    assert dataset_schema() is not dataset_schema()


@pytest.mark.parametrize("encoding", ["mapping", "str", "bytes"])
def test_normalized_roundtrip_no_mutation(data, encoding):
    snapshot = copy.deepcopy(data)
    value = data if encoding == "mapping" else json.dumps(data, ensure_ascii=False)
    if encoding == "bytes":
        value = value.encode("utf-8")
    result = read_dataset(value)
    assert isinstance(result, Dataset)
    assert json.loads(result.model_dump_json(by_alias=True)) == snapshot
    assert (
        json.loads(
            read_dataset(result.model_dump_json(by_alias=True)).model_dump_json(by_alias=True)
        )
        == snapshot
    )
    assert data == snapshot
    assert isinstance(result.houses, tuple) and isinstance(result.events, tuple)
    assert isinstance(result.meta.sources, tuple) and isinstance(result.meta.limitations, tuple)
    assert isinstance(result.events[0].houses, tuple) and isinstance(
        result.events[0].sources, tuple
    )
    assert isinstance(result.events[0].districts, tuple) and isinstance(
        result.events[0].addresses, tuple
    )
    assert isinstance(result.meta.sources[0].types, tuple)
    for dto, field, replacement in [
        (result, "houses", ()),
        (result.meta, "city", "other"),
        (result.houses[0], "floors", 10),
        (result.houses[0].services, "heating", "central"),
        (result.events[0], "notes", "changed"),
        (result.events[0].houses[0], "match", "range"),
        (result.events[0].sources[0], "url", "other"),
        (result.meta.sources[0], "name", "other"),
        (result.meta.city_houses, "total", 11),
    ]:
        with pytest.raises((ValidationError, TypeError, AttributeError)):
            setattr(dto, field, replacement)


VALID_VARIANTS = [
    "empty",
    "planned",
    "unknown-no-end",
    "unknown-date-only",
    "period-first",
    "period-last",
    "zero-duration",
    "nullable-counts",
    "integer-float",
    "tolerance",
    "rounded-source",
    "alternate-ids",
    "zero-district",
    "all-categories-services",
]


@pytest.mark.parametrize("variant", VALID_VARIANTS)
def test_valid_boundaries_and_unknowns(data, variant):
    event = data["events"][0]
    if variant == "empty":
        data["houses"] = []
        data["events"] = []
        data["meta"]["sources"] = []
    elif variant == "planned":
        event.update(end_actual=None, duration_basis="planned", duration_hours=3.0)
    elif variant.startswith("unknown"):
        event.update(duration_basis="unknown", duration_hours=None)
        if variant == "unknown-no-end":
            event.update(end_actual=None, end_planned=None)
        else:
            event.update(start="2026-10-03T00:00:00+10:00", notes="Date only")
    elif variant.startswith("period-"):
        day = data["meta"]["period"]["from" if variant == "period-first" else "to"]
        event.update(
            start=day + "T00:00:00+10:00",
            end_actual=None,
            end_planned=None,
            duration_hours=None,
            duration_basis="unknown",
        )
    elif variant == "zero-duration":
        event.update(end_actual=event["start"], end_planned=None, duration_hours=0)
    elif variant == "nullable-counts":
        data["meta"]["city_houses"]["total"] = None
        event["houses_affected"] = None
    elif variant == "integer-float":
        data["houses"][0]["floors"] = 2.0
        data["meta"]["city_houses"]["total"] = 10.0
        event["houses_affected"] = 1.0
    elif variant == "tolerance":
        event["duration_hours"] += 5e-10
    elif variant == "rounded-source":
        event["duration_hours"] += 0.003333
    elif variant == "alternate-ids":
        data["houses"][0]["id"] = "other-house"
        data["meta"]["sources"][0]["id"] = "other-source"
        event["id"] = "other-event"
        event["houses"][0]["house_id"] = "other-house"
        event["sources"][0]["source_id"] = "other-source"
    elif variant == "zero-district":
        data["meta"]["city_houses"]["by_district"]["Советский"] = 0
        event["houses_affected"] = 0
    elif variant == "all-categories-services":
        for index, category in enumerate(("hot_water", "cold_water", "electricity", "heating")):
            extra = copy.deepcopy(event)
            extra.update(id=f"event-{index}", type=category)
            data["events"].append(extra)
        data["houses"][0]["services"].update(
            hot_water="central", cold_water="individual", electricity="none"
        )
    before = copy.deepcopy(data)
    result = read_dataset(data)
    assert json.loads(result.model_dump_json(by_alias=True)) == before
    assert data == before


INVALID_VALUES = [
    (("meta", "city"), "other"),
    (("meta", "schema_version"), "2.0"),
    (("meta", "timezone"), "UTC"),
    (("events", 0, "type"), "unknown"),
    (("events", 0, "kind"), "other"),
    (("events", 0, "scope"), "other"),
    (("events", 0, "duration_basis"), "other"),
    (("events", 0, "houses", 0, "match"), "other"),
    (("houses", 0, "district"), "other"),
    (("houses", 0, "services", "heating"), "other"),
    (("houses", 0, "floors"), "2"),
    (("houses", 0, "floors"), True),
    (("houses", 0, "floors"), 1.5),
    (("houses", 0, "floors"), -1),
    (("houses", 0, "apartments"), -1),
    (("houses", 0, "lat"), "43.0"),
    (("houses", 0, "lat"), True),
    (("houses", 0, "lat"), float("nan")),
    (("houses", 0, "lon"), float("inf")),
    (("houses", 0, "is_control"), "false"),
    (("events", 0, "force_majeure"), 0),
    (("events", 0, "duration_hours"), "4"),
    (("events", 0, "duration_hours"), True),
    (("events", 0, "duration_hours"), -1),
    (("events", 0, "duration_hours"), float("inf")),
    (("events", 0, "duration_hours"), float("nan")),
    (("events", 0, "duration_hours"), 4.006),
    (("events", 0, "duration_hours"), None),
    (("events", 0, "houses_affected"), -1),
    (("events", 0, "houses_affected"), 11),
    (("meta", "city_houses", "total"), 0),
    (("meta", "city_houses", "total"), -1),
    (("meta", "city_houses", "total"), True),
    (("meta", "city_houses", "by_district", "Советский"), -1),
    (("meta", "period", "from"), "2026-11-14"),
    (("meta", "period", "from"), "2026-02-30"),
    (("meta", "period", "from"), "20260901"),
    (("meta", "heating_season_start"), "2026-10-15T00:00:00+10:00"),
    (("meta", "sources", 0, "covered_from"), "2026-11-14"),
    (("events", 0, "start"), "2026-08-31T23:59:59+10:00"),
    (("events", 0, "start"), "2026-11-14T00:00:00+10:00"),
    (("events", 0, "start"), "2026-10-03T21:30:00"),
    (("events", 0, "start"), "2026-10-03T21:30:00+09:00"),
    (("events", 0, "end_actual"), "2026-10-03T20:00:00+10:00"),
    (("events", 0, "end_planned"), "2026-10-03T20:00:00+10:00"),
    (("events", 0, "end_actual"), None),
    (("events", 0, "sources", 0, "source_id"), "missing-source"),
    (("events", 0, "houses", 0, "house_id"), "missing-house"),
    (("events", 0, "sources"), []),
]
# Check every timestamp-bearing position independently, not just event.start.
for timestamp_path in [
    ("meta", "generated_at"),
    ("events", 0, "end_planned"),
    ("events", 0, "end_actual"),
    ("events", 0, "sources", 0, "published_at"),
]:
    for timestamp in ["2026-10-04T01:30:00Z", "2026-10-04T01:30:00+11:00", "not-a-date"]:
        INVALID_VALUES.append((timestamp_path, timestamp))


@pytest.mark.parametrize("path,replacement", INVALID_VALUES)
def test_invalid_value_refused_with_path(data, path, replacement):
    put(data, path, replacement)
    before = copy.deepcopy(data)
    with pytest.raises(ContractRefused) as caught:
        read_dataset(data)
    # Range validation may point to either endpoint of the same range.
    cross_field = {
        "from",
        "covered_from",
        "end_actual",
        "end_planned",
        "duration_hours",
        "houses_affected",
    }
    expected = path[:-1] if path[-1] in cross_field else path
    assert_issues(caught.value, expected)
    assert repr(data) == repr(before)


@pytest.mark.parametrize(
    "collection,path",
    [
        (("houses",), ("houses",)),
        (("events",), ("events",)),
        (("meta", "sources"), ("meta", "sources")),
        (("events", 0, "houses"), ("events", 0, "houses")),
        (("events", 0, "sources"), ("events", 0, "sources")),
    ],
)
def test_duplicate_ids_and_links(data, collection, path):
    node = data
    for key in collection:
        node = node[key]
    node.append(copy.deepcopy(node[0]))
    with pytest.raises(ContractRefused) as caught:
        read_dataset(data)
    assert_issues(caught.value, path)


@pytest.mark.parametrize(
    "basis,actual,planned,duration",
    [
        ("planned", "2026-10-04T01:30:00+10:00", "2026-10-04T00:30:00+10:00", 3),
        ("planned", None, None, 3),
        ("planned", None, "2026-10-04T00:30:00+10:00", 4),
        ("planned", None, "2026-10-04T00:30:00+10:00", None),
        ("unknown", None, None, 0),
        ("unknown", "2026-10-04T01:30:00+10:00", None, 4),
    ],
)
def test_basis_rules(data, basis, actual, planned, duration):
    data["events"][0].update(
        duration_basis=basis, end_actual=actual, end_planned=planned, duration_hours=duration
    )
    with pytest.raises(ContractRefused) as caught:
        read_dataset(data)
    assert_issues(caught.value, ("events", 0))


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("meta",),
        ("houses", 0),
        ("houses", 0, "services"),
        ("events", 0),
        ("events", 0, "houses", 0),
        ("events", 0, "sources", 0),
    ],
)
def test_extra_keys_are_safe(data, path):
    node = data
    for key in path:
        node = node[key]
    node[CANARY] = CANARY
    with pytest.raises(ContractRefused) as caught:
        read_dataset(data)
    assert_safe(caught.value)
    assert_issues(caught.value, path)
    assert any(
        len(i.path) > len(path)
        and isinstance(i.path[len(path)], str)
        and i.path[len(path)]
        and CANARY not in i.path[len(path)]
        for i in caught.value.issues
    )


@pytest.mark.parametrize("value", [CANARY, {"meta": CANARY}, '{"meta":"' + CANARY + '"', b"\xff"])
def test_malformed_or_root_input_is_safe(value):
    with pytest.raises(ContractRefused) as caught:
        read_dataset(value)
    assert_safe(caught.value)
    assert_issues(caught.value, ())


@pytest.mark.parametrize(
    "path,value",
    [
        ((), CANARY),
        (("houses", 0, "floors"), "2"),
        (("events", 0, "force_majeure"), "false"),
        (("events", 0, "houses", 0), {"house_id": "synthetic-house", "match": "exact", "extra": 1}),
    ],
)
def test_direct_dto_construction_forbids_extras_and_coercions(data, path, value):
    if path:
        put(data, path, value)
    else:
        data["extra"] = value
    with pytest.raises((ValidationError, ContractRefused, TypeError, ValueError)):
        Dataset(**data)


@pytest.mark.parametrize(
    "path",
    [
        ("meta", "city"),
        ("houses", 0, "fias_id"),
        ("events", 0, "end_actual"),
        ("events", 0, "notes"),
    ],
)
def test_required_fields_even_when_nullable(data, path):
    node = data
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    with pytest.raises(ContractRefused) as caught:
        read_dataset(data)
    assert_issues(caught.value, path)


def test_error_probe_catches_leaky_mutant():
    # A safe test-only double proves the canary guard rejects hidden context too.
    error = ValueError("safe message")
    error.__context__ = ValueError(CANARY)
    with pytest.raises(AssertionError):
        assert_safe(error)


def test_roundtrip_probe_catches_empty_literal_mutant(data):
    with pytest.raises(AssertionError):
        assert {} == data
