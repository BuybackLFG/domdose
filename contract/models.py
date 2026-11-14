"""Immutable Pydantic DTOs for the dataset 1.0 shape.

Models forbid unknown fields and are frozen. Scalars are strict; JSON arrays
are accepted and retained as tuples. The semantic cross-field rules live in
:mod:`contract.dataset` and are checked by its single public read door.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _as_tuple(value: object) -> object:
    """JSON arrays arrive as lists; the DTO keeps them as immutable tuples."""
    if isinstance(value, list):
        return tuple(value)
    return value


def _as_date(value: object) -> object:
    """Parse the schema's ISO date string; other inputs stay for strict checks."""
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError("invalid date") from None
    return value


def _as_datetime(value: object) -> object:
    """Parse an ISO timestamp; the +10:00 rule is a semantic check."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("invalid timestamp") from None
    return value


DateValue = Annotated[date, BeforeValidator(_as_date)]
DatetimeValue = Annotated[datetime, BeforeValidator(_as_datetime)]
ArrayOf = BeforeValidator(_as_tuple)


class FrozenModel(BaseModel):
    """Strict, immutable base model with no undeclared fields."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )


District = Literal["Ленинский", "Первомайский", "Первореченский", "Советский", "Фрунзенский"]
OutageType = Literal["hot_water", "cold_water", "electricity", "heating"]
ServiceKind = Literal["central", "individual", "none", "unknown"]
EventKind = Literal["planned", "emergency", "unknown"]
DurationBasis = Literal["actual", "planned", "unknown"]
Scope = Literal["house", "group", "district", "city"]
MatchKind = Literal["exact", "range", "street"]


class Period(FrozenModel):
    date_from: DateValue = Field(alias="from")
    date_to: DateValue = Field(alias="to")


class DistrictCounts(FrozenModel):
    leninsky: int | None = Field(alias="Ленинский")
    pervomaisky: int | None = Field(alias="Первомайский")
    perorechensky: int | None = Field(alias="Первореченский")
    sovetsky: int | None = Field(alias="Советский")
    frunzensky: int | None = Field(alias="Фрунзенский")


class CityHouses(FrozenModel):
    total: int | None
    by_district: DistrictCounts
    source_url: str | None


class Source(FrozenModel):
    id: str
    name: str
    url: str
    types: Annotated[tuple[OutageType, ...], ArrayOf]
    covered_from: DateValue | None
    covered_to: DateValue | None


class Meta(FrozenModel):
    schema_version: Literal["1.0"]
    city: Literal["Владивосток"]
    timezone: Literal["Asia/Vladivostok"]
    period: Period
    heating_season_start: DateValue | None
    generated_at: DatetimeValue
    city_houses: CityHouses
    sources: Annotated[tuple[Source, ...], ArrayOf]
    limitations: Annotated[tuple[str, ...], ArrayOf]


class Services(FrozenModel):
    hot_water: ServiceKind
    cold_water: ServiceKind
    electricity: ServiceKind
    heating: ServiceKind


class House(FrozenModel):
    id: str
    address: str
    district: District
    fias_id: str | None
    lat: float | None
    lon: float | None
    year_built: int | None
    floors: int | None
    apartments: int | None
    management_company: str | None
    services: Services
    is_control: bool
    passport_source_url: str | None


class EventHouse(FrozenModel):
    house_id: str
    match: MatchKind


class EventSource(FrozenModel):
    source_id: str
    url: str
    published_at: DatetimeValue | None


class Event(FrozenModel):
    id: str
    type: OutageType
    kind: EventKind
    start: DatetimeValue
    end_planned: DatetimeValue | None
    end_actual: DatetimeValue | None
    duration_hours: float | None
    duration_basis: DurationBasis
    cause: str | None
    organization: str | None
    scope: Scope
    force_majeure: bool
    houses_affected: int | None
    districts: Annotated[tuple[District, ...], ArrayOf]
    addresses_raw: str
    addresses: Annotated[tuple[str, ...], ArrayOf]
    houses: Annotated[tuple[EventHouse, ...], ArrayOf]
    sources: Annotated[tuple[EventSource, ...], ArrayOf]
    notes: str | None


class Dataset(FrozenModel):
    meta: Meta
    houses: Annotated[tuple[House, ...], ArrayOf]
    events: Annotated[tuple[Event, ...], ArrayOf]
