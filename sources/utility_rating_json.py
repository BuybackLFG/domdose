"""Файловый адаптер JSON-датасета коммунального рейтинга."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class UtilityRatingLoadError(Exception):
    """Ошибка чтения или разбора JSON-файлов датасета."""


def load_json_object(path: Path) -> Mapping:
    """Прочитать JSON-файл и вернуть объект верхнего уровня."""
    try:
        with Path(path).open(encoding="utf-8") as stream:
            value: Any = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UtilityRatingLoadError(f"cannot load json file: {Path(path).name}") from exc
    if not isinstance(value, Mapping):
        raise UtilityRatingLoadError(f"json file must contain an object: {Path(path).name}")
    return value


def load_utility_rating_files(
    dataset_path: Path, schema_path: Path
) -> tuple[Mapping, Mapping]:
    """Загрузить сырой датасет и его JSON-схему без скоринга."""
    return load_json_object(dataset_path), load_json_object(schema_path)
