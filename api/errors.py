"""Единый формат ошибок HTTP API."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from dossier.service import DatasetUnavailable, HouseNotFound


class InvalidRequestError(Exception):
    """Некорректный запрос клиента."""


def error_body(code: str, message: str) -> dict:
    """Собрать тело ошибки в едином формате."""
    return {"error": {"code": code, "message": message}}


async def _dataset_unavailable_handler(
    request: Request, exc: DatasetUnavailable
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=error_body("dataset_unavailable", "utility rating dataset is unavailable"),
    )


async def _house_not_found_handler(
    request: Request, exc: HouseNotFound
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=error_body("house_not_found", "house is not in the pilot sample"),
    )


async def _invalid_request_handler(
    request: Request, exc: InvalidRequestError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body("invalid_request", str(exc) or "invalid request"),
    )


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body("invalid_request", "request parameters are invalid"),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Зарегистрировать обработчики доменных и сетевых ошибок."""
    app.add_exception_handler(DatasetUnavailable, _dataset_unavailable_handler)
    app.add_exception_handler(HouseNotFound, _house_not_found_handler)
    app.add_exception_handler(InvalidRequestError, _invalid_request_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
