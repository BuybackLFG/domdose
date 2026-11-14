"""Файловый адаптер JSON-датасета коммунального рейтинга."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.logging import get_logger

_logger = get_logger("sources.utility_rating_json", service="api")


class UtilityRatingLoadError(Exception):
    """Ошибка чтения или разбора JSON-файлов датасета."""


def _failure_reason(exc: BaseException) -> str:
    """Код причины отказа чтения без путей и исходного текста ошибки."""
    if isinstance(exc, FileNotFoundError):
        return "file_not_found"
    if isinstance(exc, UnicodeDecodeError):
        return "invalid_encoding"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    return "read_failed"


def load_json_object(path: Path, *, file_kind: str | None = None) -> Mapping:
    """Прочитать JSON-файл и вернуть объект верхнего уровня."""
    name = Path(path).name
    try:
        with Path(path).open(encoding="utf-8") as stream:
            value: Any = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _logger.error(
            "JSON_FILE_LOAD_FAILED",
            "json file load failed",
            file_kind=file_kind,
            file_name=name,
            reason=_failure_reason(exc),
            error_type=type(exc).__name__,
        )
        raise UtilityRatingLoadError(f"cannot load json file: {name}") from exc
    if not isinstance(value, Mapping):
        _logger.error(
            "JSON_FILE_LOAD_FAILED",
            "json file must contain an object",
            file_kind=file_kind,
            file_name=name,
            reason="not_an_object",
            error_type="UtilityRatingLoadError",
        )
        raise UtilityRatingLoadError(f"json file must contain an object: {name}")
    _logger.info(
        "JSON_FILE_LOADED", "json file loaded", file_kind=file_kind, file_name=name
    )
    return value


def load_utility_rating_files(
    dataset_path: Path, schema_path: Path
) -> tuple[Mapping, Mapping]:
    """Загрузить сырой датасет и его JSON-схему без скоринга."""
    return (
        load_json_object(dataset_path, file_kind="dataset"),
        load_json_object(schema_path, file_kind="schema"),
    )
