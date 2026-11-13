"""The single structural and semantic dataset validation door.

Structural validation is one JSON Schema Draft 2020-12 pass with format
checking against the packaged, unchanged dataset 1.0 schema. Semantic rules
are checked on the resulting immutable DTOs. Public refusals contain stable
codes and field/index paths only, never raw input, unknown key names or the
original exception chain.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from contract.errors import ContractIssue, ContractRefused
from contract.models import Dataset

_SCHEMA_FILE = "dataset.schema.json"
_DISTRICT_KEYS = (
    "Ленинский",
    "Первомайский",
    "Первореченский",
    "Советский",
    "Фрунзенский",
)
_INTEGRAL_HOUSE_FIELDS = ("year_built", "floors", "apartments")
# Half of the 0.01 hour rounding step used by the published source. A stored
# duration must agree with its actual/planned endpoints within this tolerance;
# the calculation uses the stored value.
_HOURS_TOLERANCE = 0.005
_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class _DuplicateKey(ValueError):
    """Internal marker: the JSON text repeats an object key."""


class _NonFiniteNumber(ValueError):
    """Internal marker: the JSON text contains NaN or Infinity."""


@lru_cache(maxsize=1)
def _packaged_schema() -> dict[str, Any]:
    """Load the packaged schema once; it is never exposed directly."""
    text = resources.files(__package__).joinpath(_SCHEMA_FILE).read_text(encoding="utf-8")
    return json.loads(text)


def dataset_schema() -> dict[str, Any]:
    """Return a fresh deep copy of the packaged dataset 1.0 schema."""
    return copy.deepcopy(_packaged_schema())


_FORMAT_CHECKER = FormatChecker()


@_FORMAT_CHECKER.checks("date-time")
def _is_rfc3339_datetime(value: object) -> bool:
    """RFC 3339 date-time shape, including an explicit offset."""
    if not isinstance(value, str) or _TIMESTAMP_PATTERN.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    """Reusable Draft 2020-12 validator with format checking."""
    return Draft202012Validator(_packaged_schema(), format_checker=_FORMAT_CHECKER)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey
        result[key] = value
    return result


def _reject_constant(_token: str) -> Any:
    raise _NonFiniteNumber


def _owned_copy(value: object) -> Any:
    """Copy a JSON-shaped mapping without mutating it or preserving proxies."""
    if isinstance(value, Mapping):
        return {key: _owned_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_owned_copy(item) for item in value]
    return copy.deepcopy(value)


def _load(value: Mapping[str, Any] | str | bytes) -> tuple[Any, list[ContractIssue]]:
    """Parse or copy the input into an owned JSON-shaped object."""
    if isinstance(value, Mapping):
        return _owned_copy(value), []
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            return None, [ContractIssue("INVALID-UTF8", ())]
        return _load_text(text)
    if isinstance(value, str):
        return _load_text(value)
    return None, [ContractIssue("INVALID-INPUT", ())]


def _load_text(text: str) -> tuple[Any, list[ContractIssue]]:
    try:
        instance = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except _DuplicateKey:
        return None, [ContractIssue("DUPLICATE-KEY", ())]
    except _NonFiniteNumber:
        return None, [ContractIssue("NONFINITE-NUMBER", ())]
    except json.JSONDecodeError:
        return None, [ContractIssue("INVALID-JSON", ())]
    return instance, []


def _unique(issues: list[ContractIssue]) -> list[ContractIssue]:
    """Drop duplicate issues while keeping first-seen order."""
    seen: set[tuple[str, tuple[str | int, ...]]] = set()
    result: list[ContractIssue] = []
    for issue in issues:
        key = (issue.code, issue.path)
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def _structural_issues(instance: object) -> list[ContractIssue]:
    """Map JSON Schema errors to safe issues without validator messages."""
    issues: list[ContractIssue] = []
    required_seen: set[tuple[str | int, ...]] = set()
    extra_seen: set[tuple[str | int, ...]] = set()
    for error in _validator().iter_errors(instance):
        path = tuple(error.absolute_path)
        if error.validator == "required":
            if path in required_seen:
                continue
            required_seen.add(path)
            required = error.validator_value
            if isinstance(error.instance, Mapping) and isinstance(required, (list, tuple)):
                for name in required:
                    if name not in error.instance:
                        issues.append(ContractIssue("MISSING-REQUIRED", path + (name,)))
            else:
                issues.append(ContractIssue("SCHEMA-REQUIRED", path))
        elif error.validator == "additionalProperties":
            if path in extra_seen:
                continue
            extra_seen.add(path)
            issues.append(ContractIssue("EXTRA-FORBIDDEN", path + ("$extra",)))
        else:
            kind = str(error.validator or "validation").upper().replace("_", "-")
            issues.append(ContractIssue(f"SCHEMA-{kind}", path))
    return _unique(issues)


def _dto_issues(error: ValidationError) -> list[ContractIssue]:
    """Map Pydantic errors to safe issues; unknown keys become ``$extra``."""
    issues: list[ContractIssue] = []
    for found in error.errors(
        include_url=False, include_input=False, include_context=False
    ):
        kind = str(found.get("type", "validation"))
        location = tuple(found.get("loc", ()))
        if kind == "extra_forbidden":
            path = location[:-1] + ("$extra",) if location else ("$extra",)
            issues.append(ContractIssue("EXTRA-FORBIDDEN", path))
            continue
        code = "DTO-" + (re.sub(r"[^A-Za-z0-9.-]+", "-", kind.upper()) or "VALIDATION")
        issues.append(ContractIssue(code, location))
    if not issues:
        issues.append(ContractIssue("DTO-VALIDATION", ()))
    return _unique(issues)


def _set_integral_int(container: dict[str, Any], key: str) -> None:
    """Turn a schema-legal integral JSON number into a Python integer."""
    current = container.get(key)
    if isinstance(current, float) and current.is_integer():
        container[key] = int(current)


def _normalise_integer_fields(instance: Any) -> None:
    """Normalise integral floats at every schema integer position.

    The supplied schema treats ``2.0`` as an integer. Pydantic strict integer
    fields do not, so the owned copy is normalised after schema validation.
    Booleans are deliberately left untouched and are rejected by the DTOs.
    """
    if not isinstance(instance, dict):
        return
    houses = instance.get("houses")
    if isinstance(houses, list):
        for house in houses:
            if isinstance(house, dict):
                for key in _INTEGRAL_HOUSE_FIELDS:
                    _set_integral_int(house, key)

    meta = instance.get("meta")
    if isinstance(meta, dict):
        city_houses = meta.get("city_houses")
        if isinstance(city_houses, dict):
            _set_integral_int(city_houses, "total")
            by_district = city_houses.get("by_district")
            if isinstance(by_district, dict):
                for key in _DISTRICT_KEYS:
                    _set_integral_int(by_district, key)

    events = instance.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                _set_integral_int(event, "houses_affected")


def _plus_10(value: datetime) -> bool:
    """Whether a timestamp carries exactly the +10:00 offset."""
    return value.utcoffset() == timedelta(hours=10)


def _duration_matches(start: datetime, endpoint: datetime, hours: float) -> bool:
    """Compare an endpoint duration in hours at the contract tolerance."""
    measured = (endpoint - start).total_seconds() / 3600
    return abs(measured - hours) <= _HOURS_TOLERANCE


def _semantic_issues(dataset: Dataset) -> list[ContractIssue]:
    """Check the SPEC invariants on typed, immutable values."""
    issues: list[ContractIssue] = []
    meta = dataset.meta
    period_from: date = meta.period.date_from
    period_to: date = meta.period.date_to
    if period_from > period_to:
        issues.append(ContractIssue("PERIOD-ORDER", ("meta", "period")))

    source_ids: set[str] = set()
    for index, source in enumerate(meta.sources):
        if source.id in source_ids:
            issues.append(ContractIssue("DUPLICATE-SOURCE-ID", ("meta", "sources", index, "id")))
        else:
            source_ids.add(source.id)
        if (
            source.covered_from is not None
            and source.covered_to is not None
            and source.covered_from > source.covered_to
        ):
            issues.append(
                ContractIssue("SOURCE-DATE-RANGE", ("meta", "sources", index))
            )

    house_ids: set[str] = set()
    for index, house in enumerate(dataset.houses):
        if house.id in house_ids:
            issues.append(ContractIssue("DUPLICATE-HOUSE-ID", ("houses", index, "id")))
        else:
            house_ids.add(house.id)
        if house.floors is not None and house.floors < 0:
            issues.append(ContractIssue("NEGATIVE-COUNT", ("houses", index, "floors")))
        if house.apartments is not None and house.apartments < 0:
            issues.append(ContractIssue("NEGATIVE-COUNT", ("houses", index, "apartments")))

    city_total = meta.city_houses.total
    if city_total is not None and city_total <= 0:
        issues.append(ContractIssue("CITY-TOTAL-NOT-POSITIVE", ("meta", "city_houses", "total")))
    for district, count in meta.city_houses.by_district.model_dump(by_alias=True).items():
        if count is not None and count < 0:
            issues.append(
                ContractIssue(
                    "NEGATIVE-COUNT",
                    ("meta", "city_houses", "by_district", district),
                )
            )

    if not _plus_10(meta.generated_at):
        issues.append(ContractIssue("TIMESTAMP-OFFSET", ("meta", "generated_at")))

    event_ids: set[str] = set()
    for index, event in enumerate(dataset.events):
        path: tuple[str | int, ...] = ("events", index)
        if event.id in event_ids:
            issues.append(ContractIssue("DUPLICATE-EVENT-ID", path + ("id",)))
        else:
            event_ids.add(event.id)

        if not _plus_10(event.start):
            issues.append(ContractIssue("TIMESTAMP-OFFSET", path + ("start",)))
        for field in ("end_planned", "end_actual"):
            endpoint = getattr(event, field)
            if endpoint is not None and not _plus_10(endpoint):
                issues.append(ContractIssue("TIMESTAMP-OFFSET", path + (field,)))
        for source_index, event_source in enumerate(event.sources):
            if (
                event_source.published_at is not None
                and not _plus_10(event_source.published_at)
            ):
                issues.append(
                    ContractIssue(
                        "TIMESTAMP-OFFSET",
                        path + ("sources", source_index, "published_at"),
                    )
                )

        if not period_from <= event.start.date() <= period_to:
            issues.append(ContractIssue("START-OUTSIDE-PERIOD", path + ("start",)))
        for field in ("end_planned", "end_actual"):
            endpoint = getattr(event, field)
            if endpoint is not None and endpoint < event.start:
                issues.append(ContractIssue("END-BEFORE-START", path + (field,)))

        if event.duration_hours is not None and event.duration_hours < 0:
            issues.append(ContractIssue("NEGATIVE-DURATION", path + ("duration_hours",)))
        if event.houses_affected is not None and event.houses_affected < 0:
            issues.append(
                ContractIssue("NEGATIVE-COUNT", path + ("houses_affected",))
            )
        if (
            event.houses_affected is not None
            and city_total is not None
            and event.houses_affected > city_total
        ):
            issues.append(
                ContractIssue("AFFECTED-EXCEEDS-CITY", path + ("houses_affected",))
            )

        if event.duration_basis == "actual":
            if event.end_actual is None:
                issues.append(ContractIssue("MISSING-ACTUAL-END", path + ("end_actual",)))
            elif event.duration_hours is None:
                issues.append(
                    ContractIssue("MISSING-DURATION", path + ("duration_hours",))
                )
            elif not _duration_matches(event.start, event.end_actual, event.duration_hours):
                issues.append(
                    ContractIssue("DURATION-MISMATCH", path + ("duration_hours",))
                )
        elif event.duration_basis == "planned":
            if event.end_actual is not None:
                issues.append(ContractIssue("PLANNED-HAS-ACTUAL", path + ("end_actual",)))
            elif event.end_planned is None:
                issues.append(
                    ContractIssue("MISSING-PLANNED-END", path + ("end_planned",))
                )
            elif event.duration_hours is None:
                issues.append(
                    ContractIssue("MISSING-DURATION", path + ("duration_hours",))
                )
            elif not _duration_matches(
                event.start, event.end_planned, event.duration_hours
            ):
                issues.append(
                    ContractIssue("DURATION-MISMATCH", path + ("duration_hours",))
                )
        elif event.duration_hours is not None:
            issues.append(
                ContractIssue("UNKNOWN-BASIS-HAS-DURATION", path + ("duration_hours",))
            )

        if not event.sources:
            issues.append(ContractIssue("EMPTY-EVENT-SOURCES", path + ("sources",)))
        seen_sources: set[str] = set()
        for source_index, event_source in enumerate(event.sources):
            if event_source.source_id in seen_sources:
                issues.append(
                    ContractIssue(
                        "DUPLICATE-EVENT-SOURCE",
                        path + ("sources", source_index, "source_id"),
                    )
                )
            else:
                seen_sources.add(event_source.source_id)
            if event_source.source_id not in source_ids:
                issues.append(
                    ContractIssue(
                        "UNKNOWN-SOURCE-REFERENCE",
                        path + ("sources", source_index, "source_id"),
                    )
                )

        seen_houses: set[str] = set()
        for house_index, event_house in enumerate(event.houses):
            if event_house.house_id in seen_houses:
                issues.append(
                    ContractIssue(
                        "DUPLICATE-EVENT-HOUSE",
                        path + ("houses", house_index, "house_id"),
                    )
                )
            else:
                seen_houses.add(event_house.house_id)
            if event_house.house_id not in house_ids:
                issues.append(
                    ContractIssue(
                        "UNKNOWN-HOUSE-REFERENCE",
                        path + ("houses", house_index, "house_id"),
                    )
                )

    return _unique(issues)


def read_dataset(value: Mapping[str, Any] | str | bytes) -> Dataset:
    """Validate JSON-shaped input and return the immutable dataset DTO.

    This is the only public structural and semantic validation door. The input
    mapping is never mutated.
    """
    try:
        instance, load_issues = _load(value)
    except Exception:
        instance, load_issues = None, [ContractIssue("INVALID-INPUT", ())]
    if load_issues:
        raise ContractRefused(load_issues)
    try:
        structural = _structural_issues(instance)
    except Exception:
        structural = [ContractIssue("SCHEMA-CHECK-FAILURE", ())]
    if structural:
        raise ContractRefused(structural)

    _normalise_integer_fields(instance)
    try:
        dataset = Dataset.model_validate(instance)
    except ValidationError as error:
        dto_issues = _dto_issues(error)
    except Exception:
        dto_issues = [ContractIssue("DTO-MODEL-FAILURE", ())]
    else:
        dto_issues = _semantic_issues(dataset)
    if dto_issues:
        raise ContractRefused(dto_issues)
    return dataset
