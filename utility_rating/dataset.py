"""Парсинг JSON-датасета в нормализованный вход скоринга.

Коды отказа: битая схема — schema_invalid; неполные registry/coverage
и меньше 20 домов — dataset_incomplete; остальное, включая структурные
дефекты, пропущенные слабой схемой, — dataset_invalid.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import Enum

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, UnknownType
from referencing.exceptions import Unresolvable

from contract.utility_rating import (
    DatasetRejected,
    DatasetRejectionCode,
    House,
    OutageEvent,
    OutageKind,
    TimeWindow,
    UtilityCategory,
    UtilityDataset,
    canonical_event_key,
)

_WINDOW_LENGTH = timedelta(days=30)
_TZ_OFFSET = timedelta(hours=10)
_COVERAGE_NAMES = tuple(category.value for category in UtilityCategory)
_COVERAGE_STATES = frozenset({"complete", "incomplete"})
_ARRAY = (list, tuple)
_PILOT_HOUSE_COUNT = 20


def parse_dataset(raw: Mapping, schema: Mapping) -> UtilityDataset:
    """Разобрать проверенный JSON-датасет в контрактный набор скоринга."""
    if not isinstance(raw, Mapping):
        raise TypeError("raw must be Mapping")
    if not isinstance(schema, Mapping):
        raise TypeError("schema must be Mapping")
    _validate_schema(raw, schema)
    _check_completeness(raw)
    window = _parse_window(_field(raw, "window", "dataset"))
    houses = _parse_houses(_typed(raw, "houses", "dataset", _ARRAY))
    house_ids = frozenset(house.house_id for house in houses)
    events = _parse_events(_typed(raw, "events", "dataset", _ARRAY), house_ids, window)
    return UtilityDataset(
        houses=houses,
        events=events,
        window=window,
        complete_categories=frozenset(UtilityCategory),
    )


def _invalid(message: str) -> DatasetRejected:
    """Отказ dataset_invalid: структура или значения набора неверны."""
    return DatasetRejected(DatasetRejectionCode.DATASET_INVALID, message)


def _field(record: object, key: str, owner: str) -> object:
    """Значение обязательного ключа JSON-объекта owner; иначе dataset_invalid."""
    if not isinstance(record, Mapping):
        raise _invalid(f"{owner} must be object")
    if key not in record:
        raise _invalid(f"{owner}.{key} is required")
    return record[key]


def _typed(record: object, key: str, owner: str, kind: type | tuple) -> object:
    """Обязательное значение заданного типа; иначе dataset_invalid."""
    value = _field(record, key, owner)
    if not isinstance(value, kind):
        raise _invalid(f"{owner}.{key} has invalid type")
    return value


def _member(kind: type[Enum], record: object, key: str, owner: str) -> Enum:
    """Член перечисления по значению ключа; неизвестное значение — dataset_invalid."""
    value = _field(record, key, owner)
    try:
        return kind(value)
    except ValueError as exc:
        raise _invalid(f"{owner}.{key} has unknown value") from exc


def _validate_schema(raw: Mapping, schema: Mapping) -> None:
    """Отклонить raw, не проходящий JSON Schema 2020-12."""
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(
            schema, format_checker=Draft202012Validator.FORMAT_CHECKER
        )
        errors = sorted(validator.iter_errors(raw), key=lambda error: error.json_path)
    except (SchemaError, UnknownType, Unresolvable) as exc:
        raise DatasetRejected(
            DatasetRejectionCode.SCHEMA_INVALID, "dataset schema is invalid"
        ) from exc
    if errors:
        details = "; ".join(f"{error.json_path}: {error.message}" for error in errors)
        raise DatasetRejected(
            DatasetRejectionCode.DATASET_INVALID,
            f"dataset does not match schema: {details}",
        )


def _check_completeness(raw: Mapping) -> None:
    """Для скоринга нужен полный справочник и четыре complete.

    Неверный тип или неизвестное состояние покрытия — dataset_invalid.
    """
    if _typed(raw, "registry_complete", "dataset", bool) is not True:
        raise DatasetRejected(
            DatasetRejectionCode.DATASET_INCOMPLETE,
            "registry_complete must be true for scoring",
        )
    coverage = _field(raw, "coverage", "dataset")
    states = [_field(coverage, name, "coverage") for name in _COVERAGE_NAMES]
    if not all(isinstance(state, str) and state in _COVERAGE_STATES for state in states):
        raise _invalid("coverage values must be complete or incomplete")
    incomplete = [
        name
        for name, state in zip(_COVERAGE_NAMES, states, strict=True)
        if state != "complete"
    ]
    if incomplete:
        raise DatasetRejected(
            DatasetRejectionCode.DATASET_INCOMPLETE,
            f"coverage must be complete: {', '.join(incomplete)}",
        )


def _parse_moment(text: object, field: str) -> datetime:
    """Разобрать ISO-moment с обязательным смещением +10:00."""
    try:
        moment = datetime.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise DatasetRejected(
            DatasetRejectionCode.DATASET_INVALID, f"{field} must be ISO datetime"
        ) from exc
    offset = moment.utcoffset() if moment.tzinfo is not None else None
    if offset != _TZ_OFFSET:
        raise DatasetRejected(
            DatasetRejectionCode.DATASET_INVALID, f"{field} must use +10:00 offset"
        )
    return moment


def _parse_window(raw_window: object) -> TimeWindow:
    """Разобрать окно длительностью ровно 30 суток."""
    start = _parse_moment(_field(raw_window, "start", "window"), "window.start")
    end = _parse_moment(_field(raw_window, "end", "window"), "window.end")
    if end - start != _WINDOW_LENGTH:
        raise DatasetRejected(
            DatasetRejectionCode.DATASET_INVALID, "window must be exactly 30 days"
        )
    return TimeWindow(start=start, end=end)


def _parse_houses(raw_houses: list | tuple) -> tuple[House, ...]:
    """Разобрать справочник: уникальность, порядок и нумерация без пропусков.

    Меньше 20 домов — dataset_incomplete, больше 20 — dataset_invalid.
    """
    if len(raw_houses) != _PILOT_HOUSE_COUNT:
        code = (
            DatasetRejectionCode.DATASET_INCOMPLETE
            if len(raw_houses) < _PILOT_HOUSE_COUNT
            else DatasetRejectionCode.DATASET_INVALID
        )
        raise DatasetRejected(code, "houses must contain exactly 20 pilot houses")
    houses = tuple(
        House(
            house_id=_typed(item, "house_id", "house", str),
            address=_typed(item, "address", "house", str),
        )
        for item in raw_houses
    )
    house_ids = [house.house_id for house in houses]
    address_keys = [house.address.casefold() for house in houses]
    if len(set(house_ids)) != len(house_ids):
        raise DatasetRejected(
            DatasetRejectionCode.DATASET_INVALID, "house_id values must be unique"
        )
    if len(set(address_keys)) != len(address_keys):
        raise DatasetRejected(
            DatasetRejectionCode.DATASET_INVALID,
            "address values must be unique by casefold",
        )
    for index, house_id in enumerate(house_ids, start=1):
        if house_id != f"house_{index:06d}":
            raise DatasetRejected(
                DatasetRejectionCode.DATASET_INVALID,
                "house_id sequence must be gapless from house_000001",
            )
    if address_keys != sorted(address_keys):
        raise DatasetRejected(
            DatasetRejectionCode.DATASET_INVALID,
            "houses must be ordered by casefold address",
        )
    return houses


def _parse_events(
    raw_events: list | tuple, house_ids: frozenset[str], window: TimeWindow
) -> tuple[OutageEvent, ...]:
    """Разобрать события: ссылки, окно, дедупликацию и детерминированный порядок."""
    events: list[OutageEvent] = []
    seen_incidents: set[tuple] = set()
    previous_key: tuple | None = None
    for item in raw_events:
        house_id = _typed(item, "house_id", "event", str)
        if house_id not in house_ids:
            raise DatasetRejected(
                DatasetRejectionCode.DATASET_INVALID, f"unknown house_id: {house_id!r}"
            )
        category = _member(UtilityCategory, item, "category", "event")
        started = _parse_moment(_field(item, "started_at", "event"), "started_at")
        raw_ended = _field(item, "ended_at", "event")
        ended = None if raw_ended is None else _parse_moment(raw_ended, "ended_at")
        if ended is not None and ended < started:
            raise DatasetRejected(
                DatasetRejectionCode.DATASET_INVALID,
                "event end must not be before start",
            )
        if ended == started and not window.start < started < window.end:
            raise DatasetRejected(
                DatasetRejectionCode.DATASET_INVALID,
                "zero-duration event must be strictly inside window",
            )
        if not (started < window.end and (ended is None or ended > window.start)):
            raise DatasetRejected(
                DatasetRejectionCode.DATASET_INVALID, "event must overlap the window"
            )
        event = OutageEvent(
            house_id=house_id,
            category=category,
            started_at=started,
            ended_at=ended,
            kind=_member(OutageKind, item, "kind", "event"),
            is_mass=_typed(item, "is_mass", "event", bool),
            is_natural_disaster=_typed(item, "is_natural_disaster", "event", bool),
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
            raise DatasetRejected(
                DatasetRejectionCode.DATASET_INVALID, "duplicate incident"
            )
        seen_incidents.add(incident)
        source_url = _typed(item, "source_url", "event", str)
        key = canonical_event_key(house_id, category, started, ended, source_url)
        if previous_key is not None and key < previous_key:
            raise DatasetRejected(
                DatasetRejectionCode.DATASET_INVALID,
                "events must be in deterministic order",
            )
        previous_key = key
        events.append(event)
    return tuple(events)
