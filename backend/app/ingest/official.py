"""Преобразование локального снимка официальных уведомлений в JSON-массив событий.

Из backend: uv run python -m app.ingest.official SNAPSHOT.json EVENTS.json [--houses HOUSES.json]
Вход — проверенный редактором JSON-массив с type, date (YYYY-MM-DD), severity (1–3), source_url,
retrieved_at (YYYY-MM-DD или ISO 8601 со смещением), title, summary и house_id
или district. Если указаны оба, house_id задаёт ключ, а district сохраняется.
Для записи с address нужен каталог домов.
Совпадение по полному адресу даёт house_id и district, если район известен.
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

from schemas.events import EventType

# Единственный источник правды — контракт. Копия enum разъезжалась с ним молча.
EVENT_TYPES = frozenset(member.value for member in EventType)

type EventKey = tuple[str, str, str, str]
type HouseCatalog = dict[str, list[dict[str, str]]]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: ожидалась непустая строка")
    return value.strip()


def _address_key(address: str) -> str:
    normalized = " ".join(address.casefold().replace("ё", "е").split())
    return ",".join(part.strip() for part in normalized.split(","))


def _load_houses(path: Path) -> HouseCatalog:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("--houses: ожидался JSON-массив домов")

    catalog: HouseCatalog = {}
    house_ids: set[str] = set()
    for index, row in enumerate(raw, start=1):
        try:
            if not isinstance(row, dict):
                raise ValueError("ожидался объект")
            address = _address_key(_text(row.get("address"), "address"))
            house_id = _text(row.get("id"), "id")
            if house_id in house_ids:
                raise ValueError(f"id: повторяющийся идентификатор {house_id!r}")
            location = {"house_id": house_id}
            if row.get("district") is not None:
                location["district"] = _text(row["district"], "district")
        except ValueError as exc:
            raise ValueError(f"--houses, запись {index}: {exc}") from exc
        house_ids.add(house_id)
        catalog.setdefault(address, []).append(location)
    return catalog


def _address_location(address: str, houses: HouseCatalog | None) -> dict[str, str]:
    if houses is None:
        raise ValueError("address: требуется каталог --houses")
    matches = houses.get(_address_key(address), [])
    if not matches:
        raise ValueError(f"address: адрес {address!r} не найден в каталоге --houses")
    if len(matches) != 1:
        raise ValueError(f"address: адрес {address!r} неоднозначен в каталоге --houses")
    return matches[0]


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


def _event(
    raw: object, houses: HouseCatalog | None
) -> tuple[EventKey, datetime, dict[str, object]]:
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
    if "address" in raw:
        address = _text(raw["address"], "address")
        resolved_location = _address_location(address, houses)
        for field, value in location.items():
            if value != resolved_location.get(field):
                raise ValueError(f"{field}: не совпадает с каталогом для address {address!r}")
        location = resolved_location
    if not location:
        raise ValueError("требуется house_id, district или address")
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


def import_snapshot(source: Path, output: Path, *, houses: Path | None = None) -> int:
    """Записывает полный снимок и возвращает число уникальных событий."""
    if source.resolve() == output.resolve():
        raise ValueError("пути снимка и выходного файла должны различаться")
    if houses is not None and houses.resolve() == output.resolve():
        raise ValueError("пути каталога домов и выходного файла должны различаться")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("ожидался JSON-массив уведомлений")
    catalog = _load_houses(houses) if houses is not None else None

    events: dict[EventKey, tuple[tuple[datetime, str], dict[str, object]]] = {}
    for index, row in enumerate(raw, start=1):
        try:
            key, timestamp, event = _event(row, catalog)
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
    parser.add_argument("--houses", type=Path, help="каталог для точного сопоставления адресов")
    args = parser.parse_args()
    try:
        count = import_snapshot(args.snapshot, args.output, houses=args.houses)
    except (OSError, ValueError) as exc:
        print(f"official: {exc}", file=sys.stderr)
        return 1
    print(f"official: {count} событий записано в {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
