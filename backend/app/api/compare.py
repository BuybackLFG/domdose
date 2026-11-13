"""Сравнение домов. Заглушка контракта: логика — в задаче F5."""

from fastapi import APIRouter, HTTPException, Query, status

from schemas import CompareResponse

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get(
    "",
    response_model=CompareResponse,
    summary="Сравнить два дома по пяти компонентам индекса",
)
def compare_houses(
    ids: str = Query(description="Ровно два id через запятую: ids=rus-65,patrokl-12"),
) -> CompareResponse:
    """Реализация — задача F5 (`app/core/compare.py`).

    Проверка «ровно два id» живёт в роуте, а не в схеме: пользователю нужен 400
    с понятным текстом, а не 422 из валидатора Pydantic.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="сравнение ещё не реализовано (F5)",
    )
