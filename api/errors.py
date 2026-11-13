"""Единый формат ошибок HTTP API."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from contract.utility_rating import ScoringUnavailable
from core.logging import get_logger
from dossier.service import DatasetUnavailable, HouseNotFound

_logger = get_logger("api.errors", service="api")

ERROR_HEADER = "X-DomDossier-Error"


class InvalidRequestError(Exception):
    """Некорректный запрос клиента."""


def error_body(code: str, message: str) -> dict:
    """Собрать тело ошибки в едином формате."""
    return {"error": {"code": code, "message": message}}


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Ответ-ошибка: тело error_body и тот же код в заголовке ERROR_HEADER.

    Заголовок читает frontend nginx, не разбирая тело ответа api.
    """
    return JSONResponse(
        status_code=status_code,
        content=error_body(code, message),
        headers={ERROR_HEADER: code},
    )


async def _dataset_unavailable_handler(
    request: Request, exc: DatasetUnavailable
) -> JSONResponse:
    _logger.error(
        "HTTP_ERROR_RETURNED",
        "http error returned",
        status_code=503,
        reason="dataset_unavailable",
        error_type=type(exc).__name__,
    )
    return _error_response(503, "dataset_unavailable", "utility rating dataset is unavailable")


async def _scoring_unavailable_handler(
    request: Request, exc: ScoringUnavailable
) -> JSONResponse:
    _logger.error(
        "HTTP_ERROR_RETURNED",
        "http error returned",
        status_code=503,
        reason="scoring_unavailable",
        error_type=type(exc).__name__,
    )
    return _error_response(503, "scoring_unavailable", "utility rating scoring is unavailable")


async def _house_not_found_handler(
    request: Request, exc: HouseNotFound
) -> JSONResponse:
    _logger.error(
        "HTTP_ERROR_RETURNED",
        "http error returned",
        status_code=404,
        reason="house_not_found",
        error_type=type(exc).__name__,
    )
    return _error_response(404, "house_not_found", "house is not in the pilot sample")


async def _invalid_request_handler(
    request: Request, exc: InvalidRequestError
) -> JSONResponse:
    _logger.error(
        "HTTP_ERROR_RETURNED",
        "http error returned",
        status_code=422,
        reason="invalid_request",
        error_type=type(exc).__name__,
    )
    return _error_response(422, "invalid_request", str(exc) or "invalid request")


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    _logger.error(
        "HTTP_ERROR_RETURNED",
        "http error returned",
        status_code=422,
        reason="invalid_request",
        error_type=type(exc).__name__,
    )
    return _error_response(422, "invalid_request", "request parameters are invalid")


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    _logger.error(
        "HTTP_REQUEST_FAILED",
        "unhandled request failure",
        status_code=500,
        reason="unhandled_exception",
        error_type=type(exc).__name__,
    )
    return _error_response(500, "internal_error", "internal server error")


def register_error_handlers(app: FastAPI) -> None:
    """Зарегистрировать обработчики доменных и сетевых ошибок."""
    app.add_exception_handler(DatasetUnavailable, _dataset_unavailable_handler)
    app.add_exception_handler(ScoringUnavailable, _scoring_unavailable_handler)
    app.add_exception_handler(HouseNotFound, _house_not_found_handler)
    app.add_exception_handler(InvalidRequestError, _invalid_request_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
