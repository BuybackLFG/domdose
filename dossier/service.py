"""Сервис досье: ленивый снимок датасета, проверенный и рассчитанный scoring."""

import threading
from collections.abc import Iterable
from dataclasses import dataclass

from contract.utility_rating import (
    CityRating,
    DatasetRejected,
    House,
    HouseRating,
    ScoringUnavailable,
    SourcedEvent,
    TimeWindow,
    category_rank,
    ended_rank,
)
from core.config import Settings
from core.logging import get_logger
from sources.scoring_client import ScoringClient
from sources.utility_rating_json import (
    UtilityRatingLoadError,
    load_utility_rating_files,
)

_logger = get_logger("dossier.service", service="api")


class DatasetUnavailable(Exception):
    """Исходные данные рейтинга недоступны или непригодны для расчёта."""


class HouseNotFound(Exception):
    """Дом отсутствует в пилотной выборке."""


@dataclass(frozen=True)
class UtilityRatingSnapshot:
    """Успешно рассчитанный снимок: справочник, окно, события и рейтинг."""

    houses: tuple[House, ...]
    window: TimeWindow
    events: tuple[SourcedEvent, ...]
    rating: CityRating


@dataclass(frozen=True)
class HouseDossier:
    """Досье дома: запись справочника, рейтинг и события в порядке показа."""

    house: House
    rating: HouseRating
    events: tuple[SourcedEvent, ...]


def _display_order(events: Iterable[SourcedEvent]) -> tuple[SourcedEvent, ...]:
    """Начало по убыванию, затем категория, окончание и source_url по возрастанию."""
    ordered = sorted(
        events,
        key=lambda item: (
            category_rank(item.event.category),
            ended_rank(item.event.ended_at),
            item.source_url,
        ),
    )
    # устойчивая сортировка сохраняет вторичный порядок при равном начале
    return tuple(sorted(ordered, key=lambda item: item.event.started_at, reverse=True))


def _log_load_failed(reason: str, exc: BaseException) -> None:
    """Событие отказа загрузки снимка без путей и содержимого набора."""
    _logger.error(
        "SNAPSHOT_LOAD_FAILED",
        "snapshot load failed",
        reason=reason,
        error_type=type(exc).__name__,
    )


class UtilityRatingService:
    """Лениво загружает датасет и кэширует только полный успешный снимок.

    scoring_client None — клиент internal scoring из Settings.scoring_url,
    которым владеет сервис; переданный снаружи клиент закрывает вызывающий.
    """

    def __init__(
        self, settings: Settings, scoring_client: ScoringClient | None = None
    ) -> None:
        self._settings = settings
        self._scoring_client = scoring_client
        self._owns_client = scoring_client is None
        self._lock = threading.Lock()
        self._snapshot: UtilityRatingSnapshot | None = None

    def _client(self) -> ScoringClient:
        """Клиент scoring; клиент по умолчанию создаётся при первом расчёте."""
        if self._scoring_client is None:
            self._scoring_client = ScoringClient(base_url=self._settings.scoring_url)
        return self._scoring_client

    def close(self) -> None:
        """Закрыть клиент scoring, созданный сервисом; внешний клиент не трогать."""
        with self._lock:
            if self._owns_client and self._scoring_client is not None:
                self._scoring_client.close()
                self._scoring_client = None

    def load_snapshot(self) -> UtilityRatingSnapshot:
        """Вернуть снимок, при необходимости загрузив и рассчитав данные.

        DatasetUnavailable — файлы или набор непригодны; ScoringUnavailable —
        сбой internal scoring.
        """
        with self._lock:
            if self._snapshot is not None:
                _logger.info(
                    "SNAPSHOT_CACHE_HIT", "snapshot cache hit", cache_state="hit"
                )
                return self._snapshot
            _logger.info("SNAPSHOT_LOAD_STARTED", "snapshot load started")
            try:
                raw, schema = load_utility_rating_files(
                    self._settings.dataset_path, self._settings.schema_path
                )
                client = self._client()
                parsed = client.parse_dataset(raw, schema)
                rating = client.score_city(raw, schema)
            except UtilityRatingLoadError as exc:
                _log_load_failed("source_read_failed", exc)
                raise DatasetUnavailable(
                    "utility rating dataset is unavailable"
                ) from exc
            except DatasetRejected as exc:
                _log_load_failed(exc.code.value, exc)
                raise DatasetUnavailable(
                    "utility rating dataset is unavailable"
                ) from exc
            except ScoringUnavailable as exc:
                _log_load_failed("scoring_unavailable", exc)
                raise
            if set(rating.ratings) != {house.house_id for house in parsed.houses}:
                exc = ScoringUnavailable("scoring ratings do not match parsed houses")
                _log_load_failed("scoring_inconsistent", exc)
                raise exc
            snapshot = UtilityRatingSnapshot(
                houses=parsed.houses,
                window=parsed.window,
                events=parsed.events,
                rating=rating,
            )
            self._snapshot = snapshot
            _logger.info(
                "SNAPSHOT_READY",
                "snapshot ready",
                snapshot_id=parsed.snapshot_id,
                house_count=len(parsed.houses),
                event_count=len(parsed.events),
            )
            return snapshot

    def get_house(self, house_id: str) -> HouseDossier:
        """Найти дом, его рейтинг и события по идентификатору."""
        snapshot = self.load_snapshot()
        for house in snapshot.houses:
            if house.house_id == house_id:
                return HouseDossier(
                    house=house,
                    rating=snapshot.rating.ratings[house_id],
                    events=_display_order(
                        item
                        for item in snapshot.events
                        if item.event.house_id == house_id
                    ),
                )
        _logger.warning("HOUSE_NOT_FOUND", "house not found", house_id=house_id)
        raise HouseNotFound("house is not in the pilot sample")
