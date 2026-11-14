"""Контракт API: модели, инварианты индекса, демо-досье и форма OpenAPI.

Эти тесты — единственная защита от «поехавшего» контракта: если они зелёные,
фронтенд может писать код по сгенерированным типам, не читая бэкенд.
"""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import API_PREFIX, app
from schemas import (
    DISCLAIMER,
    HOUSE_NOT_FOUND,
    ChecklistItem,
    CompareResponse,
    Component,
    ComponentKey,
    Dossier,
    Event,
    EventKind,
    EventType,
    Fact,
    FactType,
    House,
    HouseIndex,
    HouseSummary,
    IndexChange,
    ReportCreate,
    ReportResult,
    Source,
)
from schemas.index import WEIGHT_TOLERANCE

client = TestClient(app)

COMPUTED_AT = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
RETRIEVED_AT = date(2026, 11, 1)

WEIGHTS: dict[ComponentKey, float] = {
    ComponentKey.communications: 0.30,
    ComponentKey.nature: 0.25,
    ComponentKey.building: 0.20,
    ComponentKey.transport: 0.15,
    ComponentKey.safety: 0.10,
}


def make_house() -> House:
    return House(
        id="rus-65",
        address="Владивосток, Русская, 65",
        district="Фрунзенский",
        lat=43.1155,
        lon=131.8855,
        year=1975,
        floors=9,
        material="панель",
        wear_pct=42,
        uk="УК Фрунзенского района",
        avariy=False,
        caprepair=True,
        developer=None,
        source_urls=["https://dom.gosuslugi.ru/"],
        retrieved_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
    )


def make_index(total: float = 68.4, coverage: float = 0.82) -> HouseIndex:
    return HouseIndex(
        total=total,
        components=[
            Component(
                key=key,
                label=key.value,
                score=70.0,
                weight=weight,
                explanation="из чего сложилась оценка",
                source_urls=["https://vl.ru/"],
            )
            for key, weight in WEIGHTS.items()
        ],
        coverage=coverage,
        coverage_note=None,
        computed_at=COMPUTED_AT,
    )


def make_event() -> Event:
    return Event(
        id="ev-1",
        house_id="rus-65",
        type=EventType.hot_water,
        date=date(2026, 10, 12),
        severity=2,
        title="Отключение горячей воды",
        summary="Плановое отключение на 10 дней",
        source_url="https://vl.ru/off",
        confidence=1.0,
        kind=EventKind.official,
    )


def make_dossier(index: HouseIndex | None = None) -> Dossier:
    return Dossier(
        house=make_house(),
        index=make_index() if index is None else index,
        facts=[
            Fact(
                id="fact-1",
                type=FactType.building,
                label="Год постройки",
                value="1975",
                source_url="https://dom.gosuslugi.ru/",
                retrieved_at=RETRIEVED_AT,
            )
        ],
        events=[make_event()],
        checklist=[
            ChecklistItem(
                id="chk-1",
                question="Как часто отключают горячую воду?",
                reason="В ленте есть отключение от 2026-10-12",
                source_event_ids=["ev-1"],
            )
        ],
        sources=[
            Source(name="ГИС ЖКХ", url="https://dom.gosuslugi.ru/", retrieved_at=RETRIEVED_AT)
        ],
    )


def test_demo_dossier_serializes_roundtrip() -> None:
    dossier = make_dossier()
    payload = dossier.model_dump(mode="json")
    assert Dossier.model_validate(payload) == dossier

    assert payload["disclaimer"] == DISCLAIMER
    assert payload["index"]["components"]
    assert payload["events"][0]["kind"] == "official"
    assert payload["events"][0]["source_url"].startswith("https://")


def test_weights_sum_to_one() -> None:
    assert abs(sum(WEIGHTS.values()) - 1.0) < WEIGHT_TOLERANCE
    assert len(WEIGHTS) == len(ComponentKey)


def test_index_rejects_wrong_weight_sum() -> None:
    components = [component.model_copy() for component in make_index().components]
    components[0] = components[0].model_copy(update={"weight": 0.5})
    with pytest.raises(ValidationError, match="сумма весов"):
        HouseIndex(
            total=50.0,
            components=components,
            coverage=1.0,
            computed_at=COMPUTED_AT,
        )


def test_index_rejects_missing_component() -> None:
    components = [component.model_copy() for component in make_index().components][:4]
    with pytest.raises(ValidationError, match="at least 5 items"):
        HouseIndex(
            total=50.0,
            components=components,
            coverage=1.0,
            computed_at=COMPUTED_AT,
        )


def test_index_rejects_duplicate_component() -> None:
    components = [component.model_copy() for component in make_index().components]
    components[1] = components[1].model_copy(update={"key": ComponentKey.communications})
    with pytest.raises(ValidationError, match="не должны повторяться"):
        HouseIndex(
            total=50.0,
            components=components,
            coverage=1.0,
            computed_at=COMPUTED_AT,
        )


def test_dossier_allows_missing_index() -> None:
    dossier = Dossier(house=make_house(), index=None)
    assert dossier.index is None
    assert dossier.disclaimer == DISCLAIMER


def test_event_needs_house_or_district() -> None:
    with pytest.raises(ValidationError, match="house_id или district"):
        Event(
            id="ev-2",
            type=EventType.accident,
            date=date(2026, 10, 1),
            severity=3,
            title="Авария",
            source_url="https://vl.ru/",
        )


def test_event_type_enum_is_single_source_of_truth() -> None:
    """Импортер обязан брать типы из контракта, а не держать свою копию.

    Копия enum уже расходилась: импортер не знал про cold_water/heat/wind,
    и валидный по контракту снимок отвергался. Тест ловит возврат к дублю.
    """
    from app.ingest.official import EVENT_TYPES

    assert frozenset(member.value for member in EventType) == EVENT_TYPES


def test_event_accepts_district_only() -> None:
    event = Event.model_validate(
        {
            "id": "ev-3",
            "district": "Первомайский",
            "type": "typhoon",
            "date": "2026-08-20",
            "severity": 3,
            "title": "Тайфун",
            "source_url": "https://primgidromet.ru/",
        }
    )
    assert event.house_id is None
    assert event.confidence == 1.0


def test_compare_requires_two_distinct_houses() -> None:
    dossier = make_dossier()
    with pytest.raises(ValidationError, match="два разных дома"):
        CompareResponse(houses=[dossier, dossier], weaker_house_id="rus-65", summary="равны")

    with pytest.raises(ValidationError, match="weaker_house_id"):
        CompareResponse(
            houses=[
                dossier,
                make_dossier().model_copy(
                    update={"house": make_house().model_copy(update={"id": "patrokl-12"})}
                ),
            ],
            weaker_house_id="unknown",
            summary="сравнение",
        )


def test_report_result_delta_is_negative_when_index_drops() -> None:
    result = ReportResult(
        event=make_event(),
        index_before=68.4,
        index_after=64.1,
        change=IndexChange(
            component=ComponentKey.communications,
            explanation="жалоба на горячую воду",
        ),
    )
    assert result.delta == pytest.approx(-4.3)


def test_report_create_is_validated() -> None:
    payload = ReportCreate(
        house_id="rus-65",
        type=EventType.hot_water,
        text="  нет горячей воды третий день  ",
    )
    assert payload.text == "нет горячей воды третий день"
    assert payload.anonymous is True

    with pytest.raises(ValidationError):
        ReportCreate(house_id="rus-65", type=EventType.hot_water, text="  ")


def test_house_summary_allows_unscored_house() -> None:
    summary = HouseSummary(id="rus-65", address="Русская, 65", district="Фрунзенский")
    assert summary.index is None
    assert summary.components == []


def test_openapi_documents_all_endpoints() -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert "/health" in paths
    for path in ("/houses", "/houses/{house_id}", "/compare", "/reports"):
        assert f"{API_PREFIX}{path}" in paths, f"в OpenAPI нет {API_PREFIX}{path}"

    assert paths[f"{API_PREFIX}/reports"]["post"]["responses"]["201"]
    assert "404" in paths[f"{API_PREFIX}/houses/{{house_id}}"]["get"]["responses"]

    models = schema["components"]["schemas"]
    for model in (
        "House",
        "Dossier",
        "Event",
        "Component",
        "ChecklistItem",
        "ReportCreate",
        "ReportResult",
        "CompareResponse",
        "HouseList",
        "ErrorResponse",
    ):
        assert model in models, f"в OpenAPI нет модели {model}"


def test_house_not_found_detail_is_frozen() -> None:
    assert HOUSE_NOT_FOUND == "house not found"


def test_placeholder_endpoints_answer_not_implemented() -> None:
    house = client.get(f"{API_PREFIX}/houses")
    dossier = client.get(f"{API_PREFIX}/houses/rus-65")
    compare = client.get(f"{API_PREFIX}/compare", params={"ids": "a,b"})
    report = client.post(
        f"{API_PREFIX}/reports",
        json={"house_id": "rus-65", "type": "hot_water", "text": "нет воды"},
    )

    for response in (house, dossier, compare, report):
        assert response.status_code == 501
        assert "detail" in response.json()


def test_health_still_ok() -> None:
    assert client.get("/health").json() == {"status": "ok"}
