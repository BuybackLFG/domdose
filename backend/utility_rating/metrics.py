"""Метрики категории: взвешивание событий и накопление по окну."""

from datetime import datetime

from backend.contract.utility_rating import OutageEvent, OutageKind, TimeWindow

_KIND_WEIGHT: dict[OutageKind, float] = {
    OutageKind.EMERGENCY: 1.0,
    OutageKind.PLANNED: 0.4,
}
_MASS_DISASTER_FACTOR = 0.5
_SECONDS_IN_HOUR = 3600.0


def event_weight(event: OutageEvent) -> float:
    """Итоговый вес события; массовое/стихийное понижение применяется один раз."""
    weight = _KIND_WEIGHT[event.kind]
    if event.is_mass or event.is_natural_disaster:
        weight *= _MASS_DISASTER_FACTOR
    return weight


def clipped_duration_hours(event: OutageEvent, window: TimeWindow) -> float:
    """Длительность события в часах, клиппированная к окну [start, end)."""
    clip_start = max(event.started_at, window.start)
    effective_end = window.end if event.ended_at is None else event.ended_at
    clip_end = min(effective_end, window.end)
    return (clip_end - clip_start).total_seconds() / _SECONDS_IN_HOUR


def overlaps_window(started_at: datetime, ended_at: datetime | None, window: TimeWindow) -> bool:
    """Пересекает ли событие полуоткрытое окно."""
    return started_at < window.end and (ended_at is None or ended_at > window.start)
