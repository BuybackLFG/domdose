"""Validated, immutable dataset and its projections for the read-only API."""

from datetime import datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from contract.dataset import read_dataset
from contract.errors import ContractRefused
from contract.models import Dataset
from rating import CalculationRequest, evaluate
from rating.models import CalculationReport

from app.core.checklist import generate_checklist
from app.core.config import get_settings
from schemas import (
    ChecklistItem,
    Dossier,
    Event,
    EventKind,
    EventType,
    Fact,
    FactType,
    House,
    HouseList,
    HouseSummary,
    Source,
)

DEFAULT_DATASET = Path(__file__).resolve().parents[3] / "data/datasets/communal-outages-2026.json"


class DatasetUnavailable(Exception):
    """A safe operator-facing reason why the dataset cannot be served."""


def _safe_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        return bool(
            parsed.scheme in ("http", "https")
            and host
            and parsed.username is None
            and parsed.password is None
            and not any(c.isspace() for c in url)
            and parsed.port != 0
            and all(
                part
                and not part.startswith("-")
                and not part.endswith("-")
                and all(c.isalnum() or c == "-" for c in part)
                for part in host.encode("idna").decode("ascii").split(".")
            )
        )
    except (ValueError, UnicodeError):
        return False


@lru_cache(maxsize=1)
def get_dataset() -> Dataset:
    configured_path = get_settings().dataset_path
    path = Path(configured_path) if configured_path else DEFAULT_DATASET
    try:
        contents = path.read_bytes()
    except OSError as exc:
        raise DatasetUnavailable("Не удалось прочитать файл датасета") from exc
    try:
        dataset = read_dataset(contents)
    except ContractRefused as exc:
        codes = ", ".join(sorted({issue.code for issue in exc.issues}))
        raise DatasetUnavailable(f"Датасет не прошёл проверку: {codes}") from exc
    if not dataset.houses or not dataset.meta.sources:
        raise DatasetUnavailable("Датасет не содержит домов или источников")
    urls = [source.url for source in dataset.meta.sources]
    urls.extend(house.passport_source_url for house in dataset.houses if house.passport_source_url)
    urls.extend(source.url for event in dataset.events for source in event.sources)
    if not all(_safe_url(url) for url in urls):
        raise DatasetUnavailable("Датасет содержит некорректную ссылку источника")
    return dataset


def normalize(text: str) -> str:
    return " ".join(text.casefold().replace("ё", "е").split())


def search(dataset: Dataset, query: str) -> HouseList:
    normalized = normalize(query)
    items = [
        HouseSummary(id=h.id, address=h.address, district=h.district)
        for h in dataset.houses
        if normalized in normalize(f"{h.address} {h.district}")
    ]
    return HouseList(
        items=items,
        total=len(items),
        query=normalized,
        retrieved_at=dataset.meta.generated_at.date(),
    )


def rating_for(dataset: Dataset, house_id: str) -> CalculationReport:
    end = datetime.combine(
        dataset.meta.period.date_to + timedelta(days=1),
        time.min,
        tzinfo=dataset.meta.generated_at.tzinfo,
    )
    return evaluate(dataset, CalculationRequest(target_house_ids=(house_id,), end_exclusive=end))


def dossier(dataset: Dataset, house_id: str) -> Dossier | None:
    house = next((item for item in dataset.houses if item.id == house_id), None)
    if house is None:
        return None
    meta = dataset.meta
    source_urls = list(
        dict.fromkeys(
            [s.url for s in meta.sources]
            + ([house.passport_source_url] if house.passport_source_url else [])
        )
    )
    passport = House(
        id=house.id,
        address=house.address,
        district=house.district,
        lat=house.lat,
        lon=house.lon,
        year=house.year_built,
        floors=house.floors if house.floors and house.floors > 0 else None,
        uk=house.management_company,
        avariy=None,
        caprepair=None,
        source_urls=source_urls,
        retrieved_at=meta.generated_at,
    )
    mapping = {
        "hot_water": EventType.hot_water,
        "cold_water": EventType.cold_water,
        "electricity": EventType.power,
        "heating": EventType.heat,
    }
    labels = {
        "hot_water": "Отключение горячей воды",
        "cold_water": "Отключение холодной воды",
        "electricity": "Отключение электричества",
        "heating": "Отключение отопления",
    }
    events = []
    checklist_events = []
    for event in dataset.events:
        link = next((link for link in event.houses if link.house_id == house_id), None)
        if link is None:
            continue
        match = link.match
        events.append(
            Event(
                id=event.id,
                house_id=house_id,
                type=mapping[event.type],
                date=event.start.date(),
                severity=None,
                title=labels[event.type],
                summary=event.cause,
                source_url=event.sources[0].url,
                confidence=None,
                kind=EventKind.aggregator,
                match=match,
                outage_kind=event.kind,
                start=event.start,
                end_planned=event.end_planned,
                end_actual=event.end_actual,
                duration_hours=event.duration_hours,
                duration_basis=event.duration_basis,
            )
        )
        if match == "range":
            continue
        checklist_events.append(
            {
                "id": event.id,
                "house_id": house_id,
                "type": mapping[event.type],
                "date": event.start.date().isoformat(),
                "match_type": "street" if match == "street" else "exact_address",
            }
        )
    events.sort(key=lambda item: (item.date, item.id), reverse=True)
    facts = []
    if house.passport_source_url:
        for key, label, value in (
            ("year", "Год постройки", house.year_built),
            ("floors", "Этажность", house.floors),
            ("uk", "Управляющая организация", house.management_company),
        ):
            if value is not None:
                facts.append(
                    Fact(
                        id=key,
                        type=FactType.building,
                        label=label,
                        value=str(value),
                        source_url=house.passport_source_url,
                        retrieved_at=meta.generated_at.date(),
                    )
                )
    sources = [
        Source(name=s.name, url=s.url, retrieved_at=meta.generated_at.date()) for s in meta.sources
    ]
    if house.passport_source_url and house.passport_source_url not in {s.url for s in meta.sources}:
        sources.append(
            Source(
                name="Источник паспорта дома",
                url=house.passport_source_url,
                retrieved_at=meta.generated_at.date(),
            )
        )
    checklist_house = {
        "id": house_id,
        "source_urls": [house.passport_source_url] if house.passport_source_url else [],
        "year": house.year_built,
        "floors": house.floors,
        "uk": house.management_company,
    }
    return Dossier(
        house=passport,
        rating=rating_for(dataset, house_id),
        facts=facts,
        events=events,
        checklist=[
            ChecklistItem(**item) for item in generate_checklist(checklist_house, checklist_events)
        ],
        sources=sources,
    )
