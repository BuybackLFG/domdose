"""Internal HTTP-сервис расчёта: parse_dataset и score_city без состояния.

Единственная HTTP-дверь к чистому utility_rating. Журнал сервиса scoring
настраивается в lifespan; импорт модуля ничего не пишет.
"""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from contract.utility_rating import (
    DatasetRejected,
    ParsedDataset,
    SourcedEvent,
    UtilityDataset,
)
from core.logging import (
    ServiceName,
    get_logger,
    load_logging_settings,
    setup_logging,
    shutdown_logging,
)
from sources.scoring_protocol import (
    PARSE_DATASET_PATH,
    SCORE_CITY_PATH,
    Envelope,
    canonical_snapshot_id,
    dump_city_rating,
    dump_parsed_dataset,
    error_body,
)
from utility_rating.dataset import parse_dataset
from utility_rating.scoring import score_city

_logger = get_logger("api.scoring_main", service=ServiceName.SCORING)

_INVALID_ENVELOPE = "invalid_envelope"
_SNAPSHOT_MISMATCH = "snapshot_mismatch"

_Operation = Callable[[Envelope], tuple[dict, int]]


def _reject_constant(name: str) -> None:
    """NaN и Infinity не являются строгим JSON."""
    raise ValueError(f"non-standard JSON constant: {name}")


def _read_envelope(content: bytes) -> tuple[Envelope, str] | None:
    """Строгий JSON-конверт и канонический snapshot_id его содержимого.

    None — тело не JSON, не конверт или не представимо каноническим JSON.
    """
    try:
        envelope = Envelope.model_validate(
            json.loads(content, parse_constant=_reject_constant)
        )
        return envelope, canonical_snapshot_id(envelope.dataset, envelope.dataset_schema)
    except (TypeError, ValueError, ValidationError):
        return None


def _sourced_events(
    dataset: UtilityDataset, raw_events: list
) -> tuple[SourcedEvent, ...]:
    """Связать события с source_url проверенных записей.

    parse_dataset сохраняет порядок и соответствие записей один к одному.
    """
    return tuple(
        SourcedEvent(event=event, source_url=item["source_url"])
        for event, item in zip(dataset.events, raw_events, strict=True)
    )


def _parse(envelope: Envelope) -> tuple[dict, int]:
    """Операция parse_dataset: JSON-ответ и число домов."""
    dataset = parse_dataset(envelope.dataset, envelope.dataset_schema)
    parsed = ParsedDataset(
        snapshot_id=envelope.snapshot_id,
        houses=dataset.houses,
        window=dataset.window,
        events=_sourced_events(dataset, envelope.dataset["events"]),
    )
    return dump_parsed_dataset(parsed), len(dataset.houses)


def _score(envelope: Envelope) -> tuple[dict, int]:
    """Операция score_city: JSON-ответ и число домов."""
    dataset = parse_dataset(envelope.dataset, envelope.dataset_schema)
    rating = score_city(dataset)
    return dump_city_rating(envelope.snapshot_id, rating), len(dataset.houses)


def _rejected(operation: str, status: int, code: str, message: str) -> JSONResponse:
    """Отказ операции: одно событие WARNING и тело ошибки."""
    _logger.warning(
        "SCORING_OPERATION_REJECTED",
        "scoring operation rejected",
        operation=operation,
        code=code,
    )
    return JSONResponse(status_code=status, content=error_body(code, message))


async def _run(request: Request, operation: str, compute: _Operation) -> JSONResponse:
    """Проверить конверт и снимок, выполнить операцию вне event loop."""
    checked = _read_envelope(await request.body())
    if checked is None:
        return _rejected(
            operation, 400, _INVALID_ENVELOPE, "request body is not a valid envelope"
        )
    envelope, expected = checked
    if expected != envelope.snapshot_id:
        return _rejected(
            operation, 409, _SNAPSHOT_MISMATCH, "snapshot_id does not match content"
        )
    try:
        content, house_count = await run_in_threadpool(compute, envelope)
    except DatasetRejected as exc:
        return _rejected(operation, 422, exc.code.value, str(exc))
    except Exception as exc:
        _logger.error(
            "SCORING_OPERATION_FAILED",
            "scoring operation failed",
            operation=operation,
            error_type=type(exc).__name__,
        )
        raise
    _logger.info(
        "SCORING_OPERATION_COMPLETED",
        "scoring operation completed",
        operation=operation,
        snapshot_id=envelope.snapshot_id,
        house_count=house_count,
    )
    return JSONResponse(content=content)


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup: fail-fast настройка журнала scoring; shutdown в конце."""
    setup_logging(load_logging_settings(ServiceName.SCORING))
    _logger.info("SCORING_APP_STARTED", "scoring app started")
    yield
    shutdown_logging()


def create_app() -> FastAPI:
    """Собрать internal-приложение scoring без документации OpenAPI."""
    application = FastAPI(
        title="ДомДосье — internal scoring",
        lifespan=_lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @application.get("/health")
    def get_health() -> dict:
        """Процесс жив."""
        return {"status": "ok"}

    @application.get("/ready")
    def get_ready() -> dict:
        """Сервис без состояния готов принимать операции."""
        return {"status": "ready"}

    @application.post(PARSE_DATASET_PATH)
    async def post_parse_dataset(request: Request) -> JSONResponse:
        """Проверить и нормализовать набор."""
        return await _run(request, "parse_dataset", _parse)

    @application.post(SCORE_CITY_PATH)
    async def post_score_city(request: Request) -> JSONResponse:
        """Рассчитать рейтинг полного пилотного набора."""
        return await _run(request, "score_city", _score)

    return application


app = create_app()
