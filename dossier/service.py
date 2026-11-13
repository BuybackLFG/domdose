"""Сервис досье: ленивый снимок датасета с расчётом рейтинга."""

import threading
from dataclasses import dataclass

from contract.utility_rating import CityRating, House, HouseRating, TimeWindow
from core.config import Settings
from sources.utility_rating_json import (
    UtilityRatingLoadError,
    load_utility_rating_files,
)
from utility_rating.dataset import parse_dataset
from utility_rating.scoring import score_city


class DatasetUnavailable(Exception):
    """Исходные данные рейтинга недоступны или непригодны для расчёта."""


class HouseNotFound(Exception):
    """Дом отсутствует в пилотной выборке."""


@dataclass(frozen=True)
class UtilityRatingSnapshot:
    """Успешно рассчитанный снимок: справочник, окно и рейтинг."""

    houses: tuple[House, ...]
    window: TimeWindow
    rating: CityRating


class UtilityRatingService:
    """Лениво загружает датасет и кэширует только полный успешный снимок."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._snapshot: UtilityRatingSnapshot | None = None

    def load_snapshot(self) -> UtilityRatingSnapshot:
        """Вернуть снимок, при необходимости загрузив и рассчитав данные."""
        with self._lock:
            if self._snapshot is not None:
                return self._snapshot
            try:
                raw, schema = load_utility_rating_files(
                    self._settings.dataset_path, self._settings.schema_path
                )
                dataset = parse_dataset(raw, schema)
                rating = score_city(dataset)
            except (UtilityRatingLoadError, TypeError, ValueError) as exc:
                raise DatasetUnavailable(
                    "utility rating dataset is unavailable"
                ) from exc
            snapshot = UtilityRatingSnapshot(
                houses=dataset.houses, window=dataset.window, rating=rating
            )
            self._snapshot = snapshot
            return snapshot

    def get_house(self, house_id: str) -> tuple[House, HouseRating]:
        """Найти дом и его рейтинг по идентификатору."""
        snapshot = self.load_snapshot()
        for house in snapshot.houses:
            if house.house_id == house_id:
                return house, snapshot.rating.ratings[house_id]
        raise HouseNotFound("house is not in the pilot sample")
