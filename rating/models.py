"""Public request/report DTOs and shared rating constants.

The request is strict and immutable: direct construction requires a timezone
aware ``datetime`` with the +10:00 offset.  The report models are immutable,
forbid undeclared fields and reject nonfinite numbers.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, model_validator

POLICY_VERSION = "rating_observed_exposure_proxy_v1"
MAXIMUM_METHOD = "exposure_mean_weighted_duration_v1"
CATEGORY_ORDER = ("electricity", "cold_water", "heating", "hot_water")
CATEGORY_WEIGHTS = {
    "electricity": 0.30,
    "cold_water": 0.25,
    "heating": 0.25,
    "hot_water": 0.20,
}
_TEN_HOURS = timedelta(hours=10)


def _as_tuple(value: object) -> object:
    """Accept JSON arrays while keeping the immutable tuple representation."""
    if isinstance(value, list):
        return tuple(value)
    return value


class CalculationRequest(BaseModel):
    """Explicit, immutable rating request; never reads a clock or environment."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )

    target_house_ids: Annotated[tuple[str, ...], BeforeValidator(_as_tuple)]
    end_exclusive: datetime
    policy_version: Literal["rating_observed_exposure_proxy_v1"] = POLICY_VERSION

    @model_validator(mode="after")
    def _check_request(self) -> CalculationRequest:
        ids = self.target_house_ids
        if not ids:
            raise ValueError("target_house_ids must not be empty")
        if any(not isinstance(item, str) or not item for item in ids):
            raise ValueError("target_house_ids must contain nonempty strings")
        if len(set(ids)) != len(ids):
            raise ValueError("target_house_ids must be unique")
        if self.end_exclusive.utcoffset() != _TEN_HOURS:
            raise ValueError("end_exclusive must carry the +10:00 offset")
        return self


class _ReportModel(BaseModel):
    """Immutable report value object with no undeclared or nonfinite values."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Window(_ReportModel):
    start: datetime
    end_exclusive: datetime


class MetricTriple(_ReportModel):
    frequency: float | None
    hours: float | None
    maximum: float | None


class Baseline(_ReportModel):
    frequency: float | None
    hours: float | None
    maximum: float | None
    city_houses: int | None
    exposures: int | None
    maximum_method: str


class CategoryRating(_ReportModel):
    type: str
    state: Literal["approximate", "unavailable", "not_applicable"]
    reason: str | None
    estimated: bool
    metrics: MetricTriple
    baseline: Baseline
    ratios: MetricTriple
    penalties: MetricTriple
    score: float | None


class EffectiveWeight(_ReportModel):
    type: str
    weight: float


class HouseRating(_ReportModel):
    house_id: str
    categories: tuple[CategoryRating, ...]
    state: Literal["approximate", "unavailable", "not_applicable"]
    overall: float | None
    effective_weights: tuple[EffectiveWeight, ...]
    limiting_categories: tuple[str, ...]


class SourceInterval(_ReportModel):
    start: date
    end: date


class SourceSpan(_ReportModel):
    type: str
    intervals: tuple[SourceInterval, ...]
    gaps: tuple[SourceInterval, ...]
    unknown_source_ids: tuple[str, ...]


class Diagnostic(_ReportModel):
    code: str
    path: tuple[str | int, ...]
    event_ids: tuple[str, ...]
    house_ids: tuple[str, ...]


class CalculationReport(_ReportModel):
    policy_version: str
    window: Window
    houses: tuple[HouseRating, ...]
    source_spans: tuple[SourceSpan, ...]
    limitations: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...]
