"""Проверки детерминированного чек-листа на пилотных формах данных."""

from app.core.checklist import generate_checklist


def _house(**changes: object) -> dict[str, object]:
    house: dict[str, object] = {
        "house_id": "h06",
        "address": "Басаргина, 46",
        "year_built": 2012,
        "floors": 5,
        "material": None,
        "material_status": "not_published",
        "management_company": "МУПВ «Центральный»",
        "caprepair_status": "not_required_new",
        "source_urls": ["https://example.org/passport"],
    }
    house.update(changes)
    return house


def test_clean_house_has_grounded_questions() -> None:
    items = generate_checklist(_house(), [])

    assert 5 <= len(items) <= 8
    assert len({item["id"] for item in items}) == len(items)
    assert all(item["question"].endswith("?") for item in items)
    assert all(item["reason"] for item in items)
    assert all(item["source_event_ids"] == [] for item in items)
    assert any("2012" in item["reason"] for item in items)
    assert any("не опубликован" in item["reason"] for item in items)


def test_outage_question_cites_event_and_ignores_other_house() -> None:
    house = _house(house_id="h05", address="Шилкинская, 11")
    outage = {
        "event_id": "e005",
        "house_ids": ["h05"],
        "type": "cold_water",
        "date": "2026-10-16",
        "title": "Ограничение холодной воды",
        "severity": 2,
        "status": "verified",
    }
    unrelated = {**outage, "event_id": "e999", "house_ids": ["h01"]}

    items = generate_checklist(house, [unrelated, outage])

    assert 5 <= len(items) <= 8
    assert any(item["source_event_ids"] == ["e005"] for item in items)
    assert all("e999" not in item["source_event_ids"] for item in items)
    assert any("2026-10-16" in item["reason"] for item in items)


def test_order_does_not_depend_on_input_order() -> None:
    events = [
        {"id": "e2", "house_id": "h06", "type": "power", "date": "2026-11-01", "severity": 2},
        {"id": "e1", "house_id": "h06", "type": "power", "date": "2026-10-01", "severity": 1},
    ]
    assert generate_checklist(_house(), events) == generate_checklist(
        _house(), list(reversed(events))
    )


def test_no_unbacked_questions_when_house_has_no_facts() -> None:
    assert generate_checklist({"house_id": "h00"}, []) == []


def test_doc_2_house_uses_known_false_values_and_ignores_unverified_events() -> None:
    house = {
        "id": "example-house",
        "year": 2012,
        "floors": 5,
        "uk": "УК",
        "avariy": False,
        "caprepair": False,
        "source_urls": ["https://example.org/passport"],
    }
    event = {"id": "e1", "house_id": "example-house", "type": "power", "date": "2026-10-01"}
    items = generate_checklist(
        house, [{**event, "status": "quarantine"}, {**event, "confidence": 0.7}]
    )

    assert len(items) == 5
    assert all(not item["source_event_ids"] for item in items)
    assert {item["id"] for item in items} >= {"fact-avariy", "fact-caprepair_status"}
