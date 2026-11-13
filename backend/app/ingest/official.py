"""Преобразование локального снимка официальных уведомлений в JSON-массив событий.

Из backend: uv run python -m app.ingest.official SNAPSHOT.json EVENTS.json
Вход — проверенный редактором JSON-массив с type, date (YYYY-MM-DD), severity (1–3), source_url,
retrieved_at (YYYY-MM-DD или ISO 8601 со смещением), title, summary и house_id
или district. Если указаны оба, house_id задаёт ключ, а district сохраняется.
При дубликатах побеждает более позднее retrieved_at (дата считается полуночью UTC).
При равенстве побеждает лексикографически последняя каноническая JSON-запись.
Выход целиком заменяется после проверки снимка.
"""

import argparse
import json
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

EVENT_TYPES = {
    "hot_water",
    "accident",
    "power",
    "flood",
    "landslide",
    "typhoon",
    "ice",
    "elevator",
    "caprepair",
    "developer",
    "transport",
}

type EventKey = tuple[str, str, str, str]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: ожидалась непустая строка")
    return value.strip()


def _iso_date(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("ожидалась дата YYYY-MM-DD")
    return parsed


def _retrieval_time(value: str) -> datetime:
    try:
        if "T" not in value:
            return datetime.combine(_iso_date(value), time(), tzinfo=UTC)
        _iso_date(value.split("T", 1)[0])
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is not None:
            return timestamp
    except ValueError as exc:
        raise ValueError("retrieved_at: ожидалась дата ISO или время со смещением") from exc
    raise ValueError("retrieved_at: ожидалось смещение часового пояса")


def _event(raw: object) -> tuple[EventKey, datetime, dict[str, object]]:
    if not isinstance(raw, dict):
        raise ValueError("ожидался объект")
    if raw.get("kind", "official") != "official":
        raise ValueError("kind: ожидалось official")
    confidence = raw.get("confidence", 1.0)
    if isinstance(confidence, bool) or confidence != 1.0:
        raise ValueError("confidence: ожидалось число 1.0")
    location = {
        field: _text(raw[field], field)
        for field in ("house_id", "district")
        if raw.get(field) is not None
    }
    if not location:
        raise ValueError("требуется house_id или district")
    scope = "house_id" if "house_id" in location else "district"

    event_type = _text(raw.get("type"), "type")
    if event_type not in EVENT_TYPES:
        raise ValueError("type: неизвестный тип события")
    event_date = _text(raw.get("date"), "date")
    try:
        _iso_date(event_date)
    except ValueError as exc:
        raise ValueError("date: ожидалась дата YYYY-MM-DD") from exc
    severity = raw.get("severity")
    if type(severity) is not int or not 1 <= severity <= 3:
        raise ValueError("severity: ожидалось целое число от 1 до 3")
    source_url = _text(raw.get("source_url"), "source_url")
    try:
        url = urlsplit(source_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username is not None:
            raise ValueError
    except ValueError as exc:
        raise ValueError("source_url: ожидался абсолютный HTTP(S) URL без учётных данных") from exc
    retrieved_at = _text(raw.get("retrieved_at"), "retrieved_at")
    timestamp = _retrieval_time(retrieved_at)

    key = (scope, location[scope], event_type, event_date)
    event: dict[str, object] = {
        "id": str(uuid5(NAMESPACE_URL, f"domdose:official:{json.dumps(key)}")),
        **location,
        "type": event_type,
        "date": event_date,
        "severity": severity,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "confidence": 1.0,
        "kind": "official",
        "title": _text(raw.get("title"), "title"),
        "summary": _text(raw.get("summary"), "summary"),
    }
    return key, timestamp, event


def import_snapshot(source: Path, output: Path) -> int:
    """Записывает полный снимок и возвращает число уникальных событий."""
    if source.resolve() == output.resolve():
        raise ValueError("пути снимка и выходного файла должны различаться")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("ожидался JSON-массив уведомлений")

    events: dict[EventKey, tuple[tuple[datetime, str], dict[str, object]]] = {}
    for index, row in enumerate(raw, start=1):
        try:
            key, timestamp, event = _event(row)
        except ValueError as exc:
            raise ValueError(f"запись {index}: {exc}") from exc
        rank = (timestamp, json.dumps(event, sort_keys=True, ensure_ascii=False))
        if key not in events or rank > events[key][0]:
            events[key] = (rank, event)

    payload = json.dumps([events[key][1] for key in sorted(events)], ensure_ascii=False, indent=2)
    with TemporaryDirectory(dir=output.parent) as temporary:
        temporary_path = Path(temporary) / output.name
        temporary_path.write_text(payload + "\n", encoding="utf-8", newline="\n")
        temporary_path.replace(output)
    return len(events)


def main() -> int:
    parser = argparse.ArgumentParser(description="Импорт локального снимка уведомлений")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        count = import_snapshot(args.snapshot, args.output)
    except (OSError, ValueError) as exc:
        print(f"official: {exc}", file=sys.stderr)
        return 1
    print(f"official: {count} событий записано в {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
