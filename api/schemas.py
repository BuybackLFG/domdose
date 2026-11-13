"""HTTP-схемы ответов API коммунального рейтинга."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

CATEGORY_NAMES = ("hot_water", "cold_water", "electricity", "heating")


class Scope(BaseModel):
    """Контур расчёта: пилотная выборка ровно из 20 домов."""

    kind: Literal["pilot"]
    house_count: Literal[20]
    average_basis: Literal["pilot_only"]


class Window(BaseModel):
    """Скользящее окно расчёта [start, end)."""

    start: AwareDatetime
    end: AwareDatetime


class MetricValues(BaseModel):
    """Три конечные неотрицательные метрики или штрафа."""

    model_config = ConfigDict(from_attributes=True)

    frequency: float = Field(ge=0, allow_inf_nan=False)
    hours: float = Field(ge=0, allow_inf_nan=False)
    longest: float = Field(ge=0, allow_inf_nan=False)


class CategoryDetail(BaseModel):
    """Результат одной категории дома."""

    metrics: MetricValues
    penalties: MetricValues
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


class HouseCategories(BaseModel):
    """Ровно четыре категории в фиксированном порядке."""

    hot_water: CategoryDetail
    cold_water: CategoryDetail
    electricity: CategoryDetail
    heating: CategoryDetail


class HouseSummary(BaseModel):
    """Краткая карточка дома в списке."""

    model_config = ConfigDict(from_attributes=True)

    house_id: str
    address: str
    overall_score: float = Field(ge=0, le=1, allow_inf_nan=False)


class HouseListResponse(BaseModel):
    """Ответ списка домов пилотной выборки."""

    scope: Scope
    window: Window
    houses: list[HouseSummary]


class HouseDetailResponse(BaseModel):
    """Детальное досье одного дома."""

    scope: Scope
    window: Window
    house_id: str
    address: str
    overall_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    categories: HouseCategories
