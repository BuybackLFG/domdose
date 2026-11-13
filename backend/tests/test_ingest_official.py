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
