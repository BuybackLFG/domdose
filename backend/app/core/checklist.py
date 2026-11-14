"""Вопросы продавцу по событиям и сведениям о доме."""

from collections.abc import Iterable, Mapping
from typing import TypedDict


class ChecklistItem(TypedDict):
    id: str
    question: str
    reason: str
    source_event_ids: list[str]


RULES = {
    "events": {
        "hot_water": ("Ограничение ГВС", "Были ли повторные отключения ГВС после этого случая?"),
        "cold_water": (
            "Ограничение холодной воды",
            "Можете показать уведомления УК о повторных отключениях холодной воды?",
        ),
        "heat": ("Ограничение отопления", "Когда восстановили отопление и повторялся ли сбой?"),
        "power": ("Перебой электроснабжения", "Сообщала ли УК о причине и устранении перебоя?"),
        "accident": ("Авария", "Какие работы выполнили после аварии и есть ли акт об устранении?"),
        "flood": ("Подтопление", "Есть ли следы подтопления в подвале и акты его осмотра?"),
        "landslide": ("Оползень", "Проводилось ли обследование склона у дома после этого события?"),
        "typhoon": ("Тайфун", "Осматривала ли УК кровлю и водостоки после тайфуна?"),
        "wind": ("Сильный ветер", "Проверяла ли УК кровлю и фасад после сильного ветра?"),
        "ice": ("Гололёд", "Кто обрабатывает подходы к дому и как часто это делают?"),
        "elevator": ("Сбой лифта", "Можете показать акт последнего обслуживания лифта?"),
        "caprepair": ("Капремонт", "Какие работы завершили и можно ли посмотреть акты приёмки?"),
        "developer": (
            "Сообщение о застройщике",
            "Какие дефекты застройщик устранил по этому случаю?",
        ),
        "transport": (
            "Изменение транспорта",
            "Как после этого события изменился путь до остановки?",
        ),
    },
    "facts": {
        "year": (
            "Год постройки в паспорте — {}.",
            "Какие инженерные сети заменили после ввода дома и когда?",
        ),
        "floors": (
            "Этажность по паспорту — {}.",
            "Есть ли свежий акт осмотра лестничных клеток и кровли этого дома?",
        ),
        "uk": (
            "Управляющая организация по паспорту — {}.",
            "Можете показать последний отчёт управляющей организации о работах по дому?",
        ),
        "material": (
            "Материал по паспорту — {}.",
            "Есть ли свежий акт обследования наружных стен?",
        ),
        "material_missing": (
            "Материал стен в паспорте не опубликован.",
            "Можете показать техпаспорт с указанием материала несущих стен?",
        ),
        "wear": (
            "Износ по имеющейся оценке — {}%.",
            "Когда проводилось последнее обследование и можно ли посмотреть заключение?",
        ),
        "caprepair_year": (
            "В карточке капремонта указан год {}.",
            "Какие работы предусмотрены на этот год и где посмотреть актуальный график?",
        ),
        "caprepair_status": (
            "Сведения о капремонте в карточке дома: {}.",
            "Каким документом подтверждается текущий статус капремонта?",
        ),
        "avariy": (
            "Аварийность по карточке дома: {}.",
            "Можно ли сверить этот статус с действующей выпиской из реестра?",
        ),
    },
}

_CAPREPAIR_STATUSES = {
    "regional_program": "дом указан в региональной программе",
    "regional_program_postponed": "срок работ перенесён",
    "not_required_new": "работы для нового дома пока не требуются",
}


def _event_scope(house: Mapping[str, object], event: Mapping[str, object]) -> str | None:
    house_id = house.get("id") or house.get("house_id")
    match_type = event.get("match_type")
    if match_type == "citywide":
        return None
    direct_id = event.get("house_id")
    linked_ids = event.get("house_ids")
    if direct_id and direct_id != house_id:
        return None
    if isinstance(linked_ids, list) and house_id not in linked_ids:
        return None
    if (direct_id or isinstance(linked_ids, list)) and match_type == "street":
        return "улица"
    if (direct_id or isinstance(linked_ids, list)) and match_type in (None, "exact_address"):
        return "дом"
    district = house.get("district")
    districts = event.get("districts")
    if district and (
        event.get("district") == district or (isinstance(districts, list) and district in districts)
    ):
        return "район"
    return None


def _boolean_label(value: object) -> str | None:
    if isinstance(value, bool):
        return "да" if value else "нет"
    return None


def generate_checklist(
    house: Mapping[str, object], events: Iterable[Mapping[str, object]]
) -> list[ChecklistItem]:
    """Выбирает до восьми вопросов. Если подтверждений мало, пунктов будет меньше пяти."""
    candidates: list[tuple[str, str, str, str]] = []
    for event in events:
        event_type = event.get("type")
        event_id = event.get("id") or event.get("event_id")
        event_date = event.get("date")
        confidence = event.get("confidence")
        if event.get("status", "verified") != "verified" or (
            isinstance(confidence, (int, float)) and confidence < 0.8
        ):
            continue
        if (
            not isinstance(event_type, str)
            or event_type not in RULES["events"]
            or not isinstance(event_id, str)
            or not isinstance(event_date, str)
            or not event_id
            or not event_date
        ):
            continue
        scope = _event_scope(house, event)
        if scope is not None:
            candidates.append((event_date, event_id, event_type, scope))

    result: list[ChecklistItem] = []
    seen_types: set[str] = set()
    for event_date, event_id, event_type, scope in sorted(candidates, reverse=True):
        if event_type in seen_types:
            continue
        seen_types.add(event_type)
        label, question = RULES["events"][event_type]
        result.append(
            {
                "id": f"event-{event_type}",
                "question": question,
                "reason": f"{label}, {event_date}. Уровень привязки — {scope}.",
                "source_event_ids": [event_id],
            }
        )

    if house.get("source_urls"):
        caprepair_status = house.get("caprepair_status")
        caprepair_label = (
            _CAPREPAIR_STATUSES.get(caprepair_status) if isinstance(caprepair_status, str) else None
        )
        values = {
            "year": house.get("year") or house.get("year_built"),
            "floors": house.get("floors"),
            "uk": house.get("uk") or house.get("management_company"),
            "material": house.get("material"),
            "material_missing": (
                not house.get("material") and house.get("material_status") == "not_published"
            ),
            "wear": house.get("wear_pct"),
            "caprepair_year": house.get("caprepair_year"),
            "caprepair_status": (
                None
                if house.get("caprepair_year")
                else caprepair_label or _boolean_label(house.get("caprepair"))
            ),
            "avariy": _boolean_label(house.get("avariy")),
        }
        for key, (reason, question) in RULES["facts"].items():
            value = values[key]
            if value is None or value is False or value == "":
                continue
            result.append(
                {
                    "id": f"fact-{key}",
                    "question": question,
                    "reason": reason.format(value),
                    "source_event_ids": [],
                }
            )

    return result[:8]
