"""Тесты адаптера legacy-датасета на synthetic-записях."""

import json
import sys
from pathlib import Path

import httpx
import pytest

from scoring_harness import in_process_scoring_client, scoring_transport
from sources.legacy_dataset import (
    build_dataset,
    main,
    parse_address_key,
    write_output,
)
from utility_rating.dataset import parse_dataset
from utility_rating.scoring import score_city

REPO_ROOT = Path(__file__).parent.parent
SCHEMA = json.loads(
    (REPO_ROOT / "dataset" / "utility-rating-dataset.schema.json").read_text(
        encoding="utf-8"
    )
)
WINDOW = {"start": "2026-10-14T00:00:00+10:00", "end": "2026-11-13T00:00:00+10:00"}


def make_draft(addresses: list[str]) -> dict:
    """Draft с валидным для parse_dataset справочником из адресов."""
    ordered = sorted(
        (
            {"house_id": f"house_{index:06d}", "address": address}
            for index, address in enumerate(addresses, start=1)
        ),
        key=lambda house: house["address"].casefold(),
    )
    for index, house in enumerate(ordered, start=1):
        house["house_id"] = f"house_{index:06d}"
    return {
        "schema_version": "1.0.0",
        "city": "Владивосток",
        "window": WINDOW,
        "registry_source_url": "https://example.org/registry/",
        "registry_complete": False,
        "houses": ordered,
        "coverage": {name: "incomplete" for name in SCHEMA["$defs"]["coverage"]["properties"]},
        "events": [],
    }


def make_record(
    vl_id: int,
    start: str,
    end: str | None,
    *,
    street: str = "Тестовая ул.",
    num: str = "1",
    type_: str = "electricity",
    cause: str = "авария",
    declared_n: int = 1,
    url: str | None = None,
) -> dict:
    return {
        "source_url": url or f"https://www.vl.ru/off/blackout/{vl_id}.html",
        "vl_id": vl_id,
        "type": type_,
        "start": start,
        "end": end,
        "cause": cause,
        "declared_n": declared_n,
        "houses": [{"street": street, "num": num}],
    }


def house_id_of(draft: dict, address_part: str) -> str:
    for house in draft["houses"]:
        if address_part.casefold() in house["address"].casefold():
            return house["house_id"]
    raise AssertionError(f"address not found: {address_part}")


ADDRESSES = [
    "Владивосток, улица Пригородная 1-я, дом 1",
    "Владивосток, улица Тестовая, дом 1",
    "Владивосток, улица Тестовая, дом 2",
    "Владивосток, проспект Образцовый, дом 7",
    "Владивосток, переулок Дальний, дом 3",
] + [
    f"Владивосток, улица Заполнитель, дом {number}"
    for number in range(4, 19)
]


def test_token_order_address_match() -> None:
    draft = make_draft(ADDRESSES)
    record = make_record(
        1, "2026-10-15T10:00:00", "2026-10-15T12:00:00",
        street="1-я Пригородная ул.", num="1",
    )
    dataset = build_dataset([record], draft)
    events = dataset["events"]
    assert len(events) == 1
    assert events[0]["house_id"] == house_id_of(draft, "Пригородная")
    assert events[0]["started_at"] == "2026-10-15T10:00:00+10:00"


def test_window_filter_and_missing_end_drop() -> None:
    draft = make_draft(ADDRESSES)
    records = [
        make_record(1, "2026-10-13T23:00:00", "2026-10-14T01:00:00"),  # пересекает start
        make_record(2, "2026-11-12T23:00:00", "2026-11-13T01:00:00"),  # пересекает end
        make_record(3, "2026-10-13T20:00:00", "2026-10-13T21:00:00"),  # до окна
        make_record(4, "2026-11-13T00:00:00", "2026-11-13T01:00:00"),  # start == window_end
        make_record(5, "2026-10-20T10:00:00", None),  # end null: пропуск
        make_record(6, "2026-10-13T23:00:00", "2026-10-14T00:00:00"),  # end == window_start
    ]
    dataset = build_dataset(records, draft)
    starts = sorted(event["started_at"] for event in dataset["events"])
    assert starts == [
        "2026-10-13T23:00:00+10:00",
        "2026-11-12T23:00:00+10:00",
    ]


def test_kind_mass_and_disaster_flags() -> None:
    draft = make_draft(ADDRESSES)
    records = [
        make_record(1, "2026-10-15T10:00:00", "2026-10-15T11:00:00",
                    cause="Плановые работы"),
        make_record(2, "2026-10-16T10:00:00", "2026-10-16T11:00:00",
                    cause="порыв штормового ветра"),
        make_record(3, "2026-10-17T10:00:00", "2026-10-17T11:00:00",
                    cause="авария", declared_n=2),
    ]
    kinds = [event["kind"] for event in build_dataset(records, draft)["events"]]
    assert kinds == ["planned", "emergency", "emergency"]
    flags = [
        (event["is_mass"], event["is_natural_disaster"])
        for event in build_dataset(records, draft)["events"]
    ]
    assert flags == [(False, False), (False, True), (True, False)]


def test_mass_by_multiple_houses_in_one_record() -> None:
    draft = make_draft(ADDRESSES)
    record = make_record(1, "2026-10-15T10:00:00", "2026-10-15T11:00:00")
    record["houses"] = [
        {"street": "Тестовая ул.", "num": "1"},
        {"street": "Тестовая ул.", "num": "2"},
    ]
    dataset = build_dataset([record], draft)
    assert len(dataset["events"]) == 2
    assert all(event["is_mass"] for event in dataset["events"])


def test_dedup_merges_flags_kind_and_min_vl_id_url() -> None:
    draft = make_draft(ADDRESSES)
    first = make_record(
        100, "2026-10-15T10:00:00", "2026-10-15T11:00:00",
        cause="плановые работы", url="https://www.vl.ru/off/blackout/100.html",
    )
    second = make_record(
        50, "2026-10-15T10:00:00", "2026-10-15T11:00:00",
        cause="авария после шторма", url="https://www.vl.ru/off/blackout/50.html",
    )
    third = make_record(
        200, "2026-10-15T10:00:00", "2026-10-15T12:00:00",  # другой end: не склеить
        cause="авария", url="https://www.vl.ru/off/blackout/200.html",
    )
    dataset = build_dataset([first, second, third], draft)
    events = dataset["events"]
    assert len(events) == 2
    merged = next(e for e in events if e["ended_at"].endswith("11:00:00+10:00"))
    assert merged["kind"] == "emergency"
    assert merged["is_mass"] is False
    assert merged["is_natural_disaster"] is True
    assert merged["source_url"] == "https://www.vl.ru/off/blackout/50.html"


def test_output_parses_and_scores_deterministically(tmp_path: Path) -> None:
    draft = make_draft(ADDRESSES)
    records = [
        make_record(1, "2026-10-15T10:00:00", "2026-10-15T12:00:00"),
        make_record(2, "2026-10-16T10:00:00", "2026-10-16T11:00:00",
                    type_="hot_water", cause="плановые работы", street="Тестовая ул.", num="2"),
    ]
    dataset = build_dataset(records, draft)
    output = tmp_path / "out" / "utility-rating.json"
    write_output(dataset, output)
    raw = json.loads(output.read_text(encoding="utf-8"))
    parsed = parse_dataset(raw, SCHEMA)
    rating = score_city(parsed)
    assert len(rating.ratings) == 20
    scores = [item.overall_score for item in rating.ratings.values()]
    assert len(set(scores)) >= 2  # дом с событиями и без различаются
    # детерминизм: повторная сборка даёт тот же файл
    dataset2 = build_dataset(records, draft)
    output2 = tmp_path / "out2" / "utility-rating.json"
    write_output(dataset2, output2)
    assert output.read_bytes() == output2.read_bytes()


def test_write_output_refuses_overwrite_without_force(tmp_path: Path) -> None:
    output = tmp_path / "utility-rating.json"
    write_output({"a": 1}, output)
    with pytest.raises(FileExistsError):
        write_output({"a": 2}, output)
    assert json.loads(output.read_text(encoding="utf-8")) == {"a": 1}
    write_output({"a": 2}, output, force=True)
    assert json.loads(output.read_text(encoding="utf-8")) == {"a": 2}


@pytest.mark.parametrize("failure", ("event", "schema"))
def test_main_validation_failure_preserves_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    legacy = tmp_path / "legacy.json"
    current = tmp_path / "current.json"
    schema = tmp_path / "schema.json"
    output = tmp_path / "utility-rating.json"
    end = "2026-10-15T09:00:00" if failure == "event" else "2026-10-15T11:00:00"
    legacy.write_text(
        json.dumps([make_record(1, "2026-10-15T10:00:00", end)]),
        encoding="utf-8",
    )
    current.write_text(json.dumps(make_draft(ADDRESSES)), encoding="utf-8")
    schema.write_text(json.dumps({"type": 1} if failure == "schema" else SCHEMA), encoding="utf-8")
    sentinel = b'{"sentinel": "keep"}\n'
    output.write_bytes(sentinel)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "legacy_dataset.py",
            "--legacy", str(legacy),
            "--current", str(current),
            "--output", str(output),
            "--schema", str(schema),
            "--force",
        ],
    )

    with pytest.raises(ValueError):
        main(scoring_client=in_process_scoring_client())
    assert output.read_bytes() == sentinel


def test_main_checks_rating_through_injected_scoring_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ловит обход ScoringClient: проверка рейтинга идёт по internal HTTP."""
    from sources.scoring_client import ScoringClient

    legacy = tmp_path / "legacy.json"
    current = tmp_path / "current.json"
    schema = tmp_path / "schema.json"
    output = tmp_path / "utility-rating.json"
    records = [make_record(1, "2026-10-15T10:00:00", "2026-10-15T12:00:00")]
    legacy.write_text(json.dumps(records), encoding="utf-8")
    current.write_text(json.dumps(make_draft(ADDRESSES)), encoding="utf-8")
    schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
    proxy = scoring_transport()
    paths = []

    def handle(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return proxy.handle_request(request)

    client = ScoringClient(
        base_url="http://scoring", transport=httpx.MockTransport(handle)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "legacy_dataset.py",
            "--legacy", str(legacy),
            "--current", str(current),
            "--output", str(output),
            "--schema", str(schema),
        ],
    )

    main(scoring_client=client)

    assert "/internal/v1/score_city" in paths
    assert set(paths) <= {"/internal/v1/parse_dataset", "/internal/v1/score_city"}
    assert json.loads(output.read_text(encoding="utf-8")) == build_dataset(
        records, make_draft(ADDRESSES)
    )


def test_parse_address_key_normalization() -> None:
    left = parse_address_key("Владивосток, улица 1-я Пригородная, дом 1")
    right = parse_address_key("Владивосток, 1-я Пригородная ул., д. 1")
    assert left == right
    upper_yo = parse_address_key("Владивосток, ул. Ёлочная, д. 20А")
    assert upper_yo[1] == "20а"
    assert upper_yo == parse_address_key("Владивосток, ул. Елочная, д. 20А")
