"""Публичный контракт API «ДомДосье».

Единственный источник правды для backend и frontend. Всё, что объявлено здесь,
попадает в `/openapi.json`, а оттуда — в `frontend/src/types/api.ts`.

Правило: контракт меняет только техлид. Задачи B1/B2/B3/B4/F1–F6/W1/W2
меняют код, но не эти модели. Подробности — `docs/api-contract.md`.
"""

from schemas.checklist import ChecklistItem
from schemas.common import Confidence, Factor, Score, Severity, SourceUrl, Weight
from schemas.compare import CompareResponse
from schemas.dossier import Dossier
from schemas.errors import HOUSE_NOT_FOUND, ErrorResponse
from schemas.events import Event, EventKind, EventType
from schemas.facts import DISCLAIMER, Fact, FactType, Source
from schemas.houses import ComponentBrief, House, HouseList, HouseSummary
from schemas.index import Component, ComponentKey, HouseIndex
from schemas.reports import IndexChange, ReportCreate, ReportResult

__all__ = [
    "DISCLAIMER",
    "HOUSE_NOT_FOUND",
    "ChecklistItem",
    "CompareResponse",
    "Component",
    "ComponentBrief",
    "ComponentKey",
    "Confidence",
    "Dossier",
    "ErrorResponse",
    "Event",
    "EventKind",
    "EventType",
    "Fact",
    "FactType",
    "Factor",
    "House",
    "HouseIndex",
    "HouseList",
    "HouseSummary",
    "IndexChange",
    "ReportCreate",
    "ReportResult",
    "Score",
    "Severity",
    "Source",
    "SourceUrl",
    "Weight",
]
