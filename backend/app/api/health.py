"""Liveness and dataset readiness endpoints."""

from fastapi import APIRouter, HTTPException

from app.core.dataset import DatasetUnavailable, get_dataset
from schemas.service import HealthResponse

router = APIRouter(tags=["service"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    try:
        get_dataset()
    except DatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return HealthResponse(status="ok")
