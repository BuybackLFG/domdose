import json
from pathlib import Path

import pytest

from app.ingest.official import import_snapshot


def notification(**overrides: object) -> dict[str, object]:
    return {
        "house_id": "test-house",
        "type": "power",
        "date": "2026-11-13",
        "severity": 2,
        "source_url": "https://example.invalid/notice",
        "retrieved_at": "2026-11-12T09:00:00+10:00",
        "title": "Плановое отключение электричества",
        "summary": "Тестовое уведомление",
        **overrides,
    }


def write_snapshot(path: Path, rows: object) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def test_deduplicates_and_keeps_ids_and_output_stable(tmp_path: Path) -> None:
    source, output = tmp_path / "snapshot.json", tmp_path / "events.json"
    older = notification()
    newer = notification(retrieved_at="2026-11-12", severity=3, district="А")
    write_snapshot(source, [older, newer])

    assert import_snapshot(source, output) == 1
    first_output = output.read_bytes()
    [event] = json.loads(first_output)
    assert event == {**newer, "id": event["id"], "kind": "official", "confidence": 1.0}

    write_snapshot(source, [newer, older])
    assert import_snapshot(source, output) == 1
    assert output.read_bytes() == first_output

    write_snapshot(source, [older])
    import_snapshot(source, output)
    assert json.loads(output.read_bytes())[0]["id"] == event["id"]


def test_keeps_districts_separate_and_sorts_them(tmp_path: Path) -> None:
    source, output = tmp_path / "snapshot.json", tmp_path / "events.json"
    row = notification()
    del row["house_id"]
    write_snapshot(source, [{**row, "district": "Б"}, {**row, "district": "А"}])

    assert import_snapshot(source, output) == 2
    events = json.loads(output.read_bytes())
    assert [event["district"] for event in events] == ["А", "Б"]
    assert all("house_id" not in event for event in events)
    assert events[0]["id"] != events[1]["id"]


def test_resolves_full_address_to_same_event_as_house_id(tmp_path: Path) -> None:
    source, output = tmp_path / "snapshot.json", tmp_path / "events.json"
    houses = tmp_path / "houses.json"
    write_snapshot(
        houses,
        [{"id": "test-house", "address": "г. Владивосток, ул. Берёзовая, 5", "district": "А"}],
    )
    write_snapshot(source, [notification(district="А")])
    assert import_snapshot(source, output) == 1
    previous_output = output.read_bytes()

    row = notification(address="  Г. ВЛАДИВОСТОК,   УЛ. БЕРЕЗОВАЯ, 5  ")
    del row["house_id"]
    write_snapshot(source, [row])

    assert import_snapshot(source, output, houses=houses) == 1
    assert output.read_bytes() == previous_output


@pytest.mark.parametrize("field", ["house_id", "district"])
def test_rejects_conflicting_location_fields(tmp_path: Path, field: str) -> None:
    source, output = tmp_path / "snapshot.json", tmp_path / "events.json"
    houses = tmp_path / "houses.json"
    address = "г. Владивосток, ул. Берёзовая, 5"
    write_snapshot(houses, [{"id": "test-house", "address": address, "district": "А"}])
    row = notification(address=address, district="А")
    write_snapshot(source, [row])
    assert import_snapshot(source, output, houses=houses) == 1
    previous_output = output.read_bytes()

    write_snapshot(source, [{**row, field: "конфликт"}])
    with pytest.raises(ValueError, match=f"запись 1: {field}: не совпадает"):
        import_snapshot(source, output, houses=houses)

    assert output.read_bytes() == previous_output


@pytest.mark.parametrize("district_fields", [{}, {"district": None}])
def test_resolves_house_with_unknown_district(
    tmp_path: Path, district_fields: dict[str, object]
) -> None:
    source, output = tmp_path / "snapshot.json", tmp_path / "events.json"
    houses = tmp_path / "houses.json"
    address = "Берёзовая, 5"
    write_snapshot(houses, [{"id": "test-house", "address": address, **district_fields}])
    write_snapshot(source, [notification()])
    assert import_snapshot(source, output) == 1
    previous_output = output.read_bytes()

    row = notification(address=address)
    del row["house_id"]
    write_snapshot(source, [row])
    assert import_snapshot(source, output, houses=houses) == 1
    assert output.read_bytes() == previous_output

    write_snapshot(source, [{**row, "district": "А"}])
    with pytest.raises(ValueError, match="запись 1: district: не совпадает"):
        import_snapshot(source, output, houses=houses)
    assert output.read_bytes() == previous_output


def test_duplicate_catalog_id_preserves_output(tmp_path: Path) -> None:
    source, output = tmp_path / "snapshot.json", tmp_path / "events.json"
    houses = tmp_path / "houses.json"
    write_snapshot(source, [notification()])
    import_snapshot(source, output)
    previous_output = output.read_bytes()
    write_snapshot(
        houses,
        [
            {"id": "test-house", "address": "Берёзовая, 5", "district": "А"},
            {"id": "test-house", "address": "Берёзовая, 7", "district": "А"},
        ],
    )
    write_snapshot(source, [notification(address="Берёзовая, 5")])

    with pytest.raises(ValueError, match="--houses, запись 2: id: .*test-house"):
        import_snapshot(source, output, houses=houses)
    assert output.read_bytes() == previous_output


@pytest.mark.parametrize(
    "address, catalog, use_catalog, error",
    [
        (
            "г. Владивосток, ул. Берёзовая, 5",
            ["г. Владивосток, ул. Берёзовая, 5 к. 1"],
            True,
            "не найден",
        ),
        ("ул. Берёзовая, 5", ["г. Владивосток, ул. Берёзовая, 5"], True, "не найден"),
        (
            "г. Владивосток, ул. Берёзовая, 5",
            ["г. Владивосток, ул. Берёзовая, 5", "г. Владивосток, ул. Березовая, 5"],
            True,
            "неоднозначен",
        ),
        ("г. Владивосток, ул. Берёзовая, 5", [], False, "--houses"),
    ],
)
def test_unresolved_address_preserves_output(
    tmp_path: Path, address: str, catalog: list[str], use_catalog: bool, error: str
) -> None:
    source, output = tmp_path / "snapshot.json", tmp_path / "events.json"
    houses = tmp_path / "houses.json"
    write_snapshot(
        houses,
        [
            {"id": f"house-{index}", "address": entry, "district": "А"}
            for index, entry in enumerate(catalog)
        ],
    )
    write_snapshot(source, [notification()])
    import_snapshot(source, output)
    previous_output = output.read_bytes()
    write_snapshot(source, [notification(), notification(address=address)])

    with pytest.raises(ValueError, match=f"запись 2: address: .*{error}"):
        import_snapshot(source, output, houses=houses if use_catalog else None)

    assert output.read_bytes() == previous_output


@pytest.mark.parametrize(
    "bad_fields, error",
    [
        ({"date": "2026-02-29"}, "date"),
        ({"retrieved_at": "2026-11-13T09:00:00"}, "retrieved_at"),
        ({"severity": True}, "severity"),
        ({"type": "unknown"}, "type"),
        ({"source_url": "file:///notices"}, "source_url"),
        ({"source_url": "https://user:password@example.invalid/notice"}, "source_url"),
        ({"house_id": None}, "house_id|district"),
        ({"kind": "ai"}, "kind"),
        ({"confidence": 0.5}, "confidence"),
        ({"confidence": True}, "confidence"),
    ],
)
def test_invalid_record_preserves_output(
    tmp_path: Path, bad_fields: dict[str, object], error: str
) -> None:
    source, output = tmp_path / "snapshot.json", tmp_path / "events.json"
    write_snapshot(source, [notification()])
    import_snapshot(source, output)
    previous_output = output.read_bytes()
    write_snapshot(source, [notification(), notification(**bad_fields)])

    with pytest.raises(ValueError, match=error):
        import_snapshot(source, output)

    assert output.read_bytes() == previous_output
