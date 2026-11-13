"""HTTP-маршруты API коммунального рейтинга."""

import re

from fastapi import APIRouter, Request

from api.errors import InvalidRequestError
from api.schemas import (
    CATEGORY_NAMES,
    CategoryDetail,
    HouseCategories,
    HouseDetailResponse,
    HouseListResponse,
    HouseSummary,
    MetricValues,
    Scope,
    Window,
)
from contract.utility_rating import UtilityCategory
from dossier.service import UtilityRatingService

router = APIRouter(prefix="/api")

_HOUSE_ID_PATTERN = re.compile(r"^house_[0-9]{6}$")


def _get_service(request: Request) -> UtilityRatingService:
    return request.app.state.service


def _scope() -> Scope:
    return Scope(kind="pilot", house_count=20, average_basis="pilot_only")


@router.get("/health")
def get_health() -> dict:
    """Проверка живости без загрузки датасета."""
    return {"status": "ok"}


@router.get("/ready")
def get_ready(request: Request) -> dict:
    """Проверка готовности: датасет загружается и считается."""
    _get_service(request).load_snapshot()
    return {"status": "ready"}


@router.get("/houses", response_model=HouseListResponse)
def list_houses(request: Request) -> HouseListResponse:
    """Список 20 домов пилотной выборки с общим рейтингом."""
    snapshot = _get_service(request).load_snapshot()
    houses = [
        HouseSummary(
            house_id=house.house_id,
            address=house.address,
            overall_score=snapshot.rating.ratings[house.house_id].overall_score,
        )
        for house in snapshot.houses
    ]
    return HouseListResponse(
        scope=_scope(),
        window=Window(start=snapshot.window.start, end=snapshot.window.end),
        houses=houses,
    )


@router.get("/houses/{house_id}", response_model=HouseDetailResponse)
def get_house(house_id: str, request: Request) -> HouseDetailResponse:
    """Детальное досье дома; формат идентификатора — ^house_[0-9]{6}$."""
    service = _get_service(request)
    snapshot = service.load_snapshot()
    if _HOUSE_ID_PATTERN.fullmatch(house_id) is None:
        raise InvalidRequestError("house_id must match ^house_[0-9]{6}$")
    house, house_rating = service.get_house(house_id)
    categories = HouseCategories(
        **{
            name: CategoryDetail(
                metrics=MetricValues.model_validate(
                    house_rating.categories[UtilityCategory(name)].metrics
                ),
                penalties=MetricValues.model_validate(
                    house_rating.categories[UtilityCategory(name)].penalties
                ),
                score=house_rating.categories[UtilityCategory(name)].score,
            )
            for name in CATEGORY_NAMES
        }
    )
    return HouseDetailResponse(
        scope=_scope(),
        window=Window(start=snapshot.window.start, end=snapshot.window.end),
        house_id=house.house_id,
        address=house.address,
        overall_score=house_rating.overall_score,
        categories=categories,
    )
