"""HTTP-адаптер internal scoring: конверт снимка, отказы и события журнала.

Скрывает транспорт, таймауты, коды ответа и проверку формы ответа.
Повторов нет, прокси окружения и редиректы не используются.
"""

import json
from typing import TypeVar

import httpx
from pydantic import ValidationError

from contract.utility_rating import (
    CityRating,
    DatasetRejected,
    DatasetRejectionCode,
    ParsedDataset,
    ScoringUnavailable,
)
from core.config import validate_scoring_url
from core.logging import EventLogger, ServiceName, get_logger
from sources.scoring_protocol import (
    PARSE_DATASET_PATH,
    SCORE_CITY_PATH,
    ErrorResponse,
    ParseResponse,
    ScoreResponse,
    canonical_snapshot_id,
    load_city_rating,
    load_parsed_dataset,
)

_MODULE = "sources.scoring_client"
_TIMEOUT = httpx.Timeout(connect=2.0, read=10.0, write=10.0, pool=2.0)

_Response = TypeVar("_Response", ParseResponse, ScoreResponse)


class ScoringClient:
    """Синхронный клиент операций parse_dataset и score_city.

    Создание клиента не пишет журнал и не обращается к сети.
    """

    def __init__(
        self, base_url: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._client = httpx.Client(
            base_url=validate_scoring_url(base_url),
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=_TIMEOUT,
            headers={"accept": "application/json"},
        )

    def close(self) -> None:
        """Закрыть пул соединений."""
        self._client.close()

    def parse_dataset(
        self, dataset: dict, schema: dict, *, service: ServiceName = ServiceName.API
    ) -> ParsedDataset:
        """Проверить набор в scoring и вернуть нормализованные данные.

        service — журнал вызывающего сервиса. Исключения: DatasetRejected
        (набор отклонён), ScoringUnavailable (сбой scoring или протокола).
        """
        body = self._post(
            "parse_dataset", PARSE_DATASET_PATH, ParseResponse, dataset, schema, service
        )
        return load_parsed_dataset(body)

    def score_city(
        self, dataset: dict, schema: dict, *, service: ServiceName = ServiceName.API
    ) -> CityRating:
        """Рассчитать рейтинг набора в scoring; исключения как у parse_dataset."""
        body = self._post(
            "score_city", SCORE_CITY_PATH, ScoreResponse, dataset, schema, service
        )
        return load_city_rating(body)

    def _post(
        self,
        operation: str,
        path: str,
        response_model: type[_Response],
        dataset: dict,
        schema: dict,
        service: ServiceName,
    ) -> _Response:
        """Отправить конверт, проверить ответ и записать одно событие."""
        try:
            snapshot_id = canonical_snapshot_id(dataset, schema)
        except (TypeError, ValueError) as exc:
            raise DatasetRejected(
                DatasetRejectionCode.DATASET_INVALID, "dataset is not strict JSON"
            ) from exc
        content = json.dumps(
            {"dataset": dataset, "schema": schema, "snapshot_id": snapshot_id},
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        logger = get_logger(_MODULE, service=service)
        try:
            response = self._client.post(
                path, content=content, headers={"content-type": "application/json"}
            )
        except httpx.TimeoutException as exc:
            raise _failure(logger, operation, "timeout", None) from exc
        except httpx.HTTPError as exc:
            raise _failure(logger, operation, "transport", None) from exc
        status = response.status_code
        if 300 <= status < 400:
            raise _failure(logger, operation, "redirect", status)
        if status == 409:
            raise _failure(logger, operation, "snapshot_mismatch", status)
        if status == 422:
            raise _rejection(logger, operation, response)
        if status != 200:
            raise _failure(logger, operation, "http_status", status)
        try:
            body = response_model.model_validate_json(response.content)
        except ValidationError as exc:
            raise _failure(logger, operation, "invalid_response", status) from exc
        if body.snapshot_id != snapshot_id:
            raise _failure(logger, operation, "snapshot_mismatch", status)
        logger.info(
            "SCORING_REQUEST_COMPLETED",
            "scoring request completed",
            operation=operation,
            status=status,
        )
        return body


def _log_failure(
    logger: EventLogger, operation: str, reason: str, status: int | None
) -> None:
    """Единственное событие неуспешного вызова операции."""
    logger.error(
        "SCORING_REQUEST_FAILED",
        "scoring request failed",
        operation=operation,
        reason=reason,
        status=status,
    )


def _failure(
    logger: EventLogger, operation: str, reason: str, status: int | None
) -> ScoringUnavailable:
    """Записать отказ вызова и вернуть исключение недоступности scoring."""
    _log_failure(logger, operation, reason, status)
    return ScoringUnavailable(f"scoring {operation} failed: {reason}")


def _rejection(
    logger: EventLogger, operation: str, response: httpx.Response
) -> Exception:
    """Отказ 422: DatasetRejected с кодом scoring или нарушение протокола.

    Отклонённый набор — WARNING SCORING_DATASET_REJECTED, не сбой вызова.
    """
    try:
        detail = ErrorResponse.model_validate_json(response.content).error
        code = DatasetRejectionCode(detail.code)
    except (ValidationError, ValueError):
        return _failure(logger, operation, "invalid_response", response.status_code)
    logger.warning(
        "SCORING_DATASET_REJECTED",
        "scoring rejected dataset",
        operation=operation,
        status=response.status_code,
        code=code.value,
    )
    return DatasetRejected(code, detail.message)
