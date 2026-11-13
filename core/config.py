"""Настройки приложения из переменных окружения."""

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_DATASET_ENV = "DOMDOSSE_UTILITY_RATING_DATASET_PATH"
_SCHEMA_ENV = "DOMDOSSE_UTILITY_RATING_SCHEMA_PATH"

_DEFAULT_DATASET_PATH = _REPO_ROOT / "dataset" / "output" / "utility-rating.json"
_DEFAULT_SCHEMA_PATH = _REPO_ROOT / "dataset" / "utility-rating-dataset.schema.json"


@dataclass(frozen=True)
class Settings:
    """Пути к файлам датасета и схемы коммунального рейтинга."""

    dataset_path: Path
    schema_path: Path


def _resolve(path: str) -> Path:
    """Относительные пути трактовать от корня репозитория."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate


def load_settings() -> Settings:
    """Собрать настройки из окружения; файлы здесь не читаются."""
    return Settings(
        dataset_path=_resolve(os.environ.get(_DATASET_ENV, str(_DEFAULT_DATASET_PATH))),
        schema_path=_resolve(os.environ.get(_SCHEMA_ENV, str(_DEFAULT_SCHEMA_PATH))),
    )
