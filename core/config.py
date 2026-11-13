"""Настройки приложения из переменных окружения."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

_REPO_ROOT = Path(__file__).resolve().parents[1]

_DATASET_ENV = "DOMDOSSE_UTILITY_RATING_DATASET_PATH"
_SCHEMA_ENV = "DOMDOSSE_UTILITY_RATING_SCHEMA_PATH"
_SCORING_URL_ENV = "DOMDOSSE_SCORING_URL"

_DEFAULT_DATASET_PATH = _REPO_ROOT / "dataset" / "output" / "utility-rating.json"
_DEFAULT_SCHEMA_PATH = _REPO_ROOT / "dataset" / "utility-rating-dataset.schema.json"
_DEFAULT_SCORING_URL = "http://127.0.0.1:8001"
_SCORING_URL_SCHEMES = frozenset({"http", "https"})


def validate_scoring_url(url: str) -> str:
    """Проверить базовый URL internal scoring и вернуть его.

    Допустимы только http/https с хостом, без credentials, query,
    fragment и пробельных символов; иначе ValueError.
    """
    if not isinstance(url, str) or not url or any(char.isspace() for char in url):
        raise ValueError("scoring url must be a non-empty string without spaces")
    parts = urlsplit(url)
    if parts.scheme not in _SCORING_URL_SCHEMES:
        raise ValueError("scoring url scheme must be http or https")
    if "@" in parts.netloc:
        raise ValueError("scoring url must not contain credentials")
    if "?" in url or "#" in url:
        raise ValueError("scoring url must not contain query or fragment")
    if not parts.hostname:
        raise ValueError("scoring url must contain a host")
    # чтение port поднимает ValueError на нечисловом или вне 0..65535
    if parts.port == 0:
        raise ValueError("scoring url port must be positive")
    return url


@dataclass(frozen=True)
class Settings:
    """Пути к файлам датасета и схемы, базовый URL internal scoring."""

    dataset_path: Path
    schema_path: Path
    scoring_url: str = _DEFAULT_SCORING_URL

    def __post_init__(self) -> None:
        validate_scoring_url(self.scoring_url)


def _resolve(path: str) -> Path:
    """Относительные пути трактовать от корня репозитория."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate


def load_scoring_url() -> str:
    """Базовый URL internal scoring из DOMDOSSE_SCORING_URL с проверкой."""
    return validate_scoring_url(
        os.environ.get(_SCORING_URL_ENV, _DEFAULT_SCORING_URL)
    )


def load_settings() -> Settings:
    """Собрать настройки из окружения; файлы здесь не читаются."""
    return Settings(
        dataset_path=_resolve(os.environ.get(_DATASET_ENV, str(_DEFAULT_DATASET_PATH))),
        schema_path=_resolve(os.environ.get(_SCHEMA_ENV, str(_DEFAULT_SCHEMA_PATH))),
        scoring_url=load_scoring_url(),
    )
