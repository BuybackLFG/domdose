"""Read-only search and dossier endpoints backed by the validated dataset."""

from fastapi import APIRouter, HTTPException, Query, status

from app.core.dataset import DatasetUnavailable, dossier, get_dataset, search
from schemas import HOUSE_NOT_FOUND, Dossier, ErrorResponse, HouseList

router = APIRouter(prefix="/houses", tags=["houses"])


def _dataset():
    try:
        return get_dataset()
    except DatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=HouseList, summary="Поиск домов по адресу или району")
def list_houses(q: str = Query(default="", max_length=200)) -> HouseList:
    return search(_dataset(), q)


@router.get(
    "/{house_id}",
    response_model=Dossier,
    responses={404: {"model": ErrorResponse, "description": HOUSE_NOT_FOUND}},
    summary="Досье дома",
)
def get_dossier(house_id: str) -> Dossier:
    result = dossier(_dataset(), house_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=HOUSE_NOT_FOUND)
    return result
