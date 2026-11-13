"""Парсинг JSON-датасета в нормализованный вход скоринга."""

from collections.abc import Mapping
from datetime import datetime, timedelta

from jsonschema import Draft202012Validator

from backend.contract.utility_rating import (
    House,
    OutageEvent,
    OutageKind,
    TimeWindow,
    UtilityCategory,
    UtilityDataset,
)

_WINDOW_LENGTH = timedelta(days=30)
_TZ_OFFSET = timedelta(hours=10)
_CATEGORY_ORDER = {
    "hot_water": 0,
    "cold_water": 1,
    "electricity": 2,
    "heating": 3,
}
_COVERAGE_NAMES = tuple(_CATEGORY_ORDER)
_PILOT_HOUSE_COUNT = 20


def parse_dataset(raw: Mapping, schema: Mapping) -> UtilityDataset:
    """Разобрать проверенный JSON-датасет в контрактный набор скоринга."""
    if not isinstance(raw, Mapping):
        raise TypeError("raw must be Mapping")
    if not isinstance(schema, Mapping):
        raise TypeError("schema must be Mapping")
    _validate_schema(raw, schema)
    _check_completeness(raw)
    window = _parse_window(raw["window"])
    houses = _parse_houses(raw["houses"])
    house_ids = frozenset(house.house_id for house in houses)
    events = _parse_events(raw["events"], house_ids, window)
    return UtilityDataset(
        houses=houses,
        events=events,
        window=window,
        complete_categories=frozenset(UtilityCategory),
    )


def _validate_schema(raw: Mapping, schema: Mapping) -> None:
    """Отклонить raw, не проходящий JSON Schema 2020-12."""
    validator = Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    errors = sorted(validator.iter_errors(raw), key=lambda error: error.json_path)
    if errors:
        details = "; ".join(f"{error.json_path}: {error.message}" for error in errors)
        raise ValueError(f"dataset does not match schema: {details}")


def _check_completeness(raw: Mapping) -> None:
    """Для скоринга нужен полный справочник и четыре complete."""
    if raw["registry_complete"] is not True:
        raise ValueError("registry_complete must be true for scoring")
    coverage = raw["coverage"]
    incomplete = [name for name in _COVERAGE_NAMES if coverage[name] != "complete"]
    if incomplete:
        raise ValueError(f"coverage must be complete: {', '.join(incomplete)}")


def _parse_moment(text: str, field: str) -> datetime:
    """Разобрать ISO-moment с обязательным смещением +10:00."""
    try:
        moment = datetime.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be ISO datetime") from exc
    offset = moment.utcoffset() if moment.tzinfo is not None else None
    if offset != _TZ_OFFSET:
        raise ValueError(f"{field} must use +10:00 offset")
    return moment


def _parse_window(raw_window: Mapping) -> TimeWindow:
    """Разобрать окно длительностью ровно 30 суток."""
    start = _parse_moment(raw_window["start"], "window.start")
    end = _parse_moment(raw_window["end"], "window.end")
    if end - start != _WINDOW_LENGTH:
        raise ValueError("window must be exactly 30 days")
    return TimeWindow(start=start, end=end)


def _parse_houses(raw_houses: list) -> tuple[House, ...]:
    """Разобрать справочник: уникальность, порядок и нумерация без пропусков."""
    if len(raw_houses) != _PILOT_HOUSE_COUNT:
        raise ValueError("houses must contain exactly 20 pilot houses")
    houses = tuple(
        House(house_id=item["house_id"], address=item["address"])
        for item in raw_houses
    )
    house_ids = [house.house_id for house in houses]
    address_keys = [house.address.casefold() for house in houses]
    if len(set(house_ids)) != len(house_ids):
        raise ValueError("house_id values must be unique")
    if len(set(address_keys)) != len(address_keys):
        raise ValueError("address values must be unique by casefold")
    for index, house_id in enumerate(house_ids, start=1):
        if house_id != f"house_{index:06d}":
            raise ValueError("house_id sequence must be gapless from house_000001")
    if address_keys != sorted(address_keys):
        raise ValueError("houses must be ordered by casefold address")
    return houses


def _ended_key(ended: datetime | None) -> tuple[int, datetime | None]:
    """Ключ сортировки: непустые окончания раньше null."""
    return (1, None) if ended is None else (0, ended)


def _parse_events(
    raw_events: list, house_ids: frozenset[str], window: TimeWindow
) -> tuple[OutageEvent, ...]:
    """Разобрать события: ссылки, окно, дедупликацию и детерминированный порядок."""
    events: list[OutageEvent] = []
    seen_incidents: set[tuple] = set()
    previous_key: tuple | None = None
    for item in raw_events:
        house_id = item["house_id"]
        if house_id not in house_ids:
            raise ValueError(f"unknown house_id: {house_id!r}")
        category = UtilityCategory(item["category"])
        started = _parse_moment(item["started_at"], "started_at")
        ended = (
            None
            if item["ended_at"] is None
            else _parse_moment(item["ended_at"], "ended_at")
        )
        if ended is not None and ended < started:
            raise ValueError("event end must not be before start")
        if ended == started and not window.start < started < window.end:
            raise ValueError("zero-duration event must be strictly inside window")
        if not (started < window.end and (ended is None or ended > window.start)):
            raise ValueError("event must overlap the window")
        event = OutageEvent(
            house_id=house_id,
            category=category,
            started_at=started,
            ended_at=ended,
            kind=OutageKind(item["kind"]),
            is_mass=item["is_mass"],
            is_natural_disaster=item["is_natural_disaster"],
        )
        incident = (
            house_id,
            category,
            started,
            ended,
            event.kind,
            event.is_mass,
            event.is_natural_disaster,
        )
        if incident in seen_incidents:
            raise ValueError("duplicate incident")
        seen_incidents.add(incident)
        key = (
            house_id,
            _CATEGORY_ORDER[item["category"]],
            started,
            _ended_key(ended),
            item["source_url"],
        )
        if previous_key is not None and key < previous_key:
            raise ValueError("events must be in deterministic order")
        previous_key = key
        events.append(event)
    return tuple(events)
