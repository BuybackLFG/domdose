"""Приём live-репортов жильцов. Заглушка контракта: логика — в задаче W1."""

from fastapi import APIRouter, HTTPException, status

from schemas import ReportCreate, ReportResult

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post(
    "",
    response_model=ReportResult,
    status_code=status.HTTP_201_CREATED,
    summary="Отправить сообщение жильца и пересчитать индекс",
)
def create_report(payload: ReportCreate) -> ReportResult:
    """Реализация — задача W1 (`app/core/reports.py`, вызов scoring).

    `payload` принимается и валидируется уже сейчас: форма запроса — часть
    контракта, даже пока бизнес-логики нет. Невалидный запрос получит 422
    до того, как дойдёт до этой строки.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="приём репортов ещё не реализован (W1)",
    )
