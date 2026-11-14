"""HTTP-схемы ответов API коммунального рейтинга."""

from typing import Literal, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

CategoryName = Literal["hot_water", "cold_water", "electricity", "heating"]
CATEGORY_NAMES: tuple[str, ...] = get_args(CategoryName)


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

    hot_water: CategoryDetail | None
    cold_water: CategoryDetail | None
    electricity: CategoryDetail | None
    heating: CategoryDetail | None


class HouseSummary(BaseModel):
    """Индекс найденных записей или null; покрытие источника неизвестно."""

    model_config = ConfigDict(from_attributes=True)

    house_id: str
    address: str
    overall_score: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    event_count: int = Field(ge=0)
    coverage: Literal["unknown"] = "unknown"


class HouseListResponse(BaseModel):
    """Ответ списка домов пилотной выборки."""

    scope: Scope
    window: Window
    houses: list[HouseSummary]


class HouseEvent(BaseModel):
    """Отключение дома; ended_at null — продолжающееся событие."""

    house_id: str
    category: CategoryName
    started_at: AwareDatetime
    ended_at: AwareDatetime | None
    kind: Literal["emergency", "planned"]
    is_mass: bool
    is_natural_disaster: bool
    source_url: str


class HouseDetailResponse(BaseModel):
    """Досье по найденным записям; null не означает отсутствие отключений."""

    scope: Scope
    window: Window
    house_id: str
    address: str
    overall_score: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    event_count: int = Field(ge=0)
    coverage: Literal["unknown"] = "unknown"
    categories: HouseCategories
    weakest: CategoryName | None
    events: list[HouseEvent]
