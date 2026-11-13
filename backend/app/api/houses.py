"""Поиск домов и досье. Заглушки контракта: логика — в задачах B1 и B2."""

from fastapi import APIRouter, HTTPException, Query, status

from schemas import HOUSE_NOT_FOUND, Dossier, ErrorResponse, HouseList

router = APIRouter(prefix="/houses", tags=["houses"])


@router.get(
    "",
    response_model=HouseList,
    summary="Поиск домов по адресу или району",
)
def list_houses(
    q: str = Query(default="", max_length=200, description="Подстрока адреса или района"),
) -> HouseList:
    """Реализация — задача B1 (`app/core/search.py`)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="поиск домов ещё не реализован (B1)",
    )


@router.get(
    "/{house_id}",
    response_model=Dossier,
    responses={404: {"model": ErrorResponse, "description": HOUSE_NOT_FOUND}},
    summary="Досье дома: паспорт, индекс, факты, события, чек-лист",
)
def get_dossier(house_id: str) -> Dossier:
    """Реализация — задача B2 (`app/core/dossier.py`)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="досье ещё не реализовано (B2)",
    )
