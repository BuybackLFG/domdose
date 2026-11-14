"""Протокол internal scoring: конверт, канонический snapshot_id и ответы.

Одна форма проводного контракта для обеих сторон: api.scoring_main
сериализует ответы, sources.scoring_client проверяет их и переводит
в доменные типы contract.
"""

import hashlib
import json
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from contract.utility_rating import (
    CategoryRating,
    CityRating,
    House,
    HouseRating,
    MetricValues,
    OutageEvent,
    OutageKind,
    ParsedDataset,
    SourcedEvent,
    TimeWindow,
    UtilityCategory,
)

PARSE_DATASET_PATH = "/internal/v1/parse_dataset"
SCORE_CITY_PATH = "/internal/v1/score_city"
_SNAPSHOT_ID_PATTERN = r"^[0-9a-f]{64}$"


def canonical_snapshot_id(dataset: dict, schema: dict) -> str:
    """sha256 канонического JSON {"dataset", "schema"}.

    ValueError или TypeError — значение не представимо строгим JSON
    (NaN, Infinity, не-JSON типы, непарные суррогаты).
    """
    canonical = json.dumps(
        {"dataset": dataset, "schema": schema},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _Wire(BaseModel):
    """Строгая неизменяемая модель без лишних полей."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Envelope(_Wire):
    """Запрос операции: сырой набор, его схема и канонический snapshot_id."""

    dataset: dict[str, Any]
    dataset_schema: dict[str, Any] = Field(alias="schema")
    snapshot_id: str = Field(pattern=_SNAPSHOT_ID_PATTERN)


class ErrorDetail(_Wire):
    """Код и текст отказа."""

    code: str
    message: str


class ErrorResponse(_Wire):
    """Ответ-отказ internal scoring."""

    error: ErrorDetail


class _WindowBody(_Wire):
    start: AwareDatetime
    end: AwareDatetime


class _HouseBody(_Wire):
    house_id: str
    address: str


class _EventBody(_Wire):
    house_id: str
    category: UtilityCategory
    started_at: AwareDatetime
    ended_at: AwareDatetime | None
    kind: OutageKind
    is_mass: bool
    is_natural_disaster: bool
    source_url: str


class _DatasetBody(_Wire):
    window: _WindowBody
    houses: list[_HouseBody]
    events: list[_EventBody]


class ParseResponse(_Wire):
    """Ответ parse_dataset: нормализованный набор с источниками событий."""

    snapshot_id: str = Field(pattern=_SNAPSHOT_ID_PATTERN)
    dataset: _DatasetBody


class _MetricsBody(_Wire):
    frequency: float = Field(ge=0, allow_inf_nan=False)
    hours: float = Field(ge=0, allow_inf_nan=False)
    longest: float = Field(ge=0, allow_inf_nan=False)


class _CategoryBody(_Wire):
    metrics: _MetricsBody
    penalties: _MetricsBody
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


class _CategoriesBody(_Wire):
    hot_water: _CategoryBody
    cold_water: _CategoryBody
    electricity: _CategoryBody
    heating: _CategoryBody


class _HouseRatingBody(_Wire):
    overall_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    weakest: UtilityCategory
    categories: _CategoriesBody


class ScoreResponse(_Wire):
    """Ответ score_city: рейтинги домов по house_id."""

    snapshot_id: str = Field(pattern=_SNAPSHOT_ID_PATTERN)
    ratings: dict[str, _HouseRatingBody]


def _metrics_body(values: MetricValues) -> _MetricsBody:
    return _MetricsBody(
        frequency=values.frequency, hours=values.hours, longest=values.longest
    )


def _metrics(body: _MetricsBody) -> MetricValues:
    return MetricValues(frequency=body.frequency, hours=body.hours, longest=body.longest)


def dump_parsed_dataset(parsed: ParsedDataset) -> dict:
    """JSON-ответ parse_dataset из доменного набора."""
    return ParseResponse(
        snapshot_id=parsed.snapshot_id,
        dataset=_DatasetBody(
            window=_WindowBody(start=parsed.window.start, end=parsed.window.end),
            houses=[
                _HouseBody(house_id=house.house_id, address=house.address)
                for house in parsed.houses
            ],
            events=[
                _EventBody(
                    house_id=item.event.house_id,
                    category=item.event.category,
                    started_at=item.event.started_at,
                    ended_at=item.event.ended_at,
                    kind=item.event.kind,
                    is_mass=item.event.is_mass,
                    is_natural_disaster=item.event.is_natural_disaster,
                    source_url=item.source_url,
                )
                for item in parsed.events
            ],
        ),
    ).model_dump(mode="json")


def load_parsed_dataset(body: ParseResponse) -> ParsedDataset:
    """Доменный набор из проверенного ответа parse_dataset."""
    dataset = body.dataset
    return ParsedDataset(
        snapshot_id=body.snapshot_id,
        houses=tuple(
            House(house_id=house.house_id, address=house.address)
            for house in dataset.houses
        ),
        window=TimeWindow(start=dataset.window.start, end=dataset.window.end),
        events=tuple(
            SourcedEvent(
                event=OutageEvent(
                    house_id=item.house_id,
                    category=item.category,
                    started_at=item.started_at,
                    ended_at=item.ended_at,
                    kind=item.kind,
                    is_mass=item.is_mass,
                    is_natural_disaster=item.is_natural_disaster,
                ),
                source_url=item.source_url,
            )
            for item in dataset.events
        ),
    )


def dump_city_rating(snapshot_id: str, rating: CityRating) -> dict:
    """JSON-ответ score_city из доменного рейтинга."""
    return ScoreResponse(
        snapshot_id=snapshot_id,
        ratings={
            house_id: _HouseRatingBody(
                overall_score=house.overall_score,
                weakest=house.weakest,
                categories=_CategoriesBody(
                    **{
                        category.value: _CategoryBody(
                            metrics=_metrics_body(house.categories[category].metrics),
                            penalties=_metrics_body(
                                house.categories[category].penalties
                            ),
                            score=house.categories[category].score,
                        )
                        for category in UtilityCategory
                    }
                ),
            )
            for house_id, house in rating.ratings.items()
        },
    ).model_dump(mode="json")


def load_city_rating(body: ScoreResponse) -> CityRating:
    """Доменный рейтинг из проверенного ответа score_city."""
    return CityRating(
        ratings={
            house_id: HouseRating(
                categories={
                    category: CategoryRating(
                        metrics=_metrics(getattr(house.categories, category.value).metrics),
                        penalties=_metrics(
                            getattr(house.categories, category.value).penalties
                        ),
                        score=getattr(house.categories, category.value).score,
                    )
                    for category in UtilityCategory
                },
                overall_score=house.overall_score,
                weakest=house.weakest,
            )
            for house_id, house in body.ratings.items()
        }
    )
