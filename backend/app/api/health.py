"""Служебные эндпоинты."""

from fastapi import APIRouter

from schemas.service import HealthResponse

router = APIRouter(tags=["service"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
