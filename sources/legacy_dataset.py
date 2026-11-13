"""Адаптер legacy-датасета vl.ru/off в текущий контракт скоринга.

Читает старый `events_parsed.json` и текущий draft датасета, переносит
события старой выборки в опубликованную схему `utility-rating-dataset.schema.json`.
Собранный набор проверяется и оценивается через internal scoring до записи.
Допущения MVP задокументированы в `dataset/LEGACY_ADAPTATION.md`.
"""

import argparse
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from contract.utility_rating import ScoringUnavailable
from core.config import load_scoring_url
from core.logging import ServiceName, get_logger, load_logging_settings, setup_logging
from sources.scoring_client import ScoringClient

_logger = get_logger("sources.legacy_dataset", service="legacy")

_TZ = timezone(timedelta(hours=10))
_SCHEMA_NAME = "utility-rating-dataset.schema.json"
_CATEGORY_ORDER = {
    "hot_water": 0,
    "cold_water": 1,
    "electricity": 2,
    "heating": 3,
}
# обозначения улиц и домов, удаляемые при нормализации адреса
_STREET_WORDS = frozenset(
    {
        "улица", "ул", "проспект", "пр-кт", "пр", "переулок", "пер",
        "бульвар", "бул", "набережная", "наб", "площадь", "пл",
        "шоссе", "мкр",
    }
)
_HOUSE_WORDS = frozenset({"дом", "д"})
_NUMBER_RE = re.compile(r"^\d+[а-яa-z]?$")
_DISASTER_RE = re.compile(
    r"стих|погод|ливен|ураган|шторм|снегопад|гололед|сильн\S*\s*ветер"
)


def _normalize(text: str) -> str:
    """Нормализация: NFKC, ё→е, casefold, без точек и лишних пробелов."""
    text = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    text = text.replace(".", " ")
    return re.sub(r"[\s\u00a0]+", " ", text).strip()


def _tokens(text: str) -> list[str]:
    """Значимые токены без обозначений типа улица/ул/дом/д."""
    words = _STREET_WORDS | _HOUSE_WORDS
    return [token for token in _normalize(text).split() if token not in words]


def parse_address_key(address: str) -> tuple[frozenset[str], str | None]:
    """Ключ адреса: frozenset токенов улицы и точный casefold номер дома."""
    parts = [part.strip() for part in _normalize(address).split(",") if part.strip()]
    if parts and parts[0] == "владивосток":
        parts = parts[1:]
    street_tokens: list[str] = []
    number: str | None = None
    for part in parts:
        tokens = [
            token
            for token in part.split()
            if token not in _STREET_WORDS and token not in _HOUSE_WORDS
        ]
        if len(tokens) == 1 and _NUMBER_RE.fullmatch(tokens[0]):
            number = tokens[0]
        else:
            street_tokens.extend(tokens)
    return frozenset(street_tokens), number


def _parse_naive_local(text: str) -> datetime:
    """Naive timestamp legacy-файла принимается как локальное время Владивостока."""
    return datetime.fromisoformat(text).replace(tzinfo=_TZ)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _count_skip(stats: dict | None, key: str) -> None:
    """Увеличить счётчик пропуска записи без изменения результата сборки."""
    if stats is not None:
        stats[key] = stats.get(key, 0) + 1


def build_dataset(
    legacy_records: list, current_draft: dict, stats: dict | None = None
) -> dict:
    """Собрать датасет опубликованной схемы из legacy-событий и текущего draft.

    Houses, window и registry-поля берутся из draft; его events не используются.
    coverage принудительно complete по решению владельца для приближённого MVP.
    Необязательный stats заполняется счётчиками пропущенных записей.
    """
    window_start = _parse_naive_local(current_draft["window"]["start"])
    window_end = _parse_naive_local(current_draft["window"]["end"])
    houses = current_draft["houses"]

    address_index: dict[tuple[frozenset[str], str | None], list[str]] = {}
    for house in houses:
        address_index.setdefault(parse_address_key(house["address"]), []).append(
            house["house_id"]
        )

    # дедуп по (house_id, category, started, ended): source_url минимального
    # vl_id, флаги OR, при конфликте kind побеждает emergency
    merged: dict[tuple, dict] = {}
    for record in legacy_records:
        started = _parse_naive_local(record["start"])
        # полуоткрытое окно [start, end): событие входит при start < window_end
        # и (end is None или end > window_start); end null запись пропускается
        if not started < window_end:
            _count_skip(stats, "outside_window")
            continue
        raw_end = record.get("end")
        if raw_end is None:
            _count_skip(stats, "missing_end")
            continue
        ended = _parse_naive_local(raw_end)
        if not ended > window_start:
            _count_skip(stats, "outside_window")
            continue

        old_houses = record.get("houses") or []
        house_ids: list[str] = []
        for old_house in old_houses:
            key = (
                frozenset(_tokens(old_house.get("street", ""))),
                _normalize(old_house.get("num", "")) or None,
            )
            house_ids.extend(address_index.get(key, ()))
        if not house_ids:
            _count_skip(stats, "unmatched")
            continue

        declared_n = record.get("declared_n")
        is_mass = (
            (isinstance(declared_n, int) and declared_n >= 2)
            or len(old_houses) >= 2
            or len(set(house_ids)) >= 2
        )
        cause = _normalize(record.get("cause", ""))
        is_disaster = bool(_DISASTER_RE.search(cause))
        # planned только при прямом слове "планов"; иначе emergency (допущение MVP)
        kind = "planned" if "планов" in cause else "emergency"
        vl_id = record.get("vl_id")
        source_url = record["source_url"]
        category = record["type"]

        for house_id in sorted(set(house_ids)):
            event_key = (house_id, category, started, ended)
            existing = merged.get(event_key)
            if existing is None:
                merged[event_key] = {
                    "house_id": house_id,
                    "category": category,
                    "started_at": started,
                    "ended_at": ended,
                    "kind": kind,
                    "is_mass": is_mass,
                    "is_natural_disaster": is_disaster,
                    "source_url": source_url,
                    "_vl_id": vl_id if isinstance(vl_id, int) else None,
                }
            else:
                if kind == "emergency":
                    existing["kind"] = "emergency"
                existing["is_mass"] = existing["is_mass"] or is_mass
                existing["is_natural_disaster"] = (
                    existing["is_natural_disaster"] or is_disaster
                )
                candidate = (vl_id if isinstance(vl_id, int) else None, source_url)
                current = (existing["_vl_id"], existing["source_url"])
                takes_url = candidate[0] is not None and (
                    current[0] is None or candidate[0] < current[0]
                )
                takes_url = takes_url or (
                    candidate[0] is None
                    and current[0] is None
                    and candidate[1] < current[1]
                )
                if takes_url:
                    existing["source_url"] = source_url
                    existing["_vl_id"] = vl_id

    def _ended_key(event: dict) -> tuple:
        ended = event["ended_at"]
        return (1, None) if ended is None else (0, ended)

    ordered = sorted(
        merged.values(),
        key=lambda event: (
            event["house_id"],
            _CATEGORY_ORDER[event["category"]],
            event["started_at"],
            _ended_key(event),
            event["source_url"],
        ),
    )
    events = [
        {
            "house_id": event["house_id"],
            "category": event["category"],
            "started_at": event["started_at"].isoformat(),
            "ended_at": event["ended_at"].isoformat(),
            "kind": event["kind"],
            "is_mass": event["is_mass"],
            "is_natural_disaster": event["is_natural_disaster"],
            "source_url": event["source_url"],
        }
        for event in ordered
    ]
    return {
        "schema_version": current_draft["schema_version"],
        "city": current_draft["city"],
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
        "registry_source_url": current_draft["registry_source_url"],
        "registry_complete": True,
        "houses": houses,
        "coverage": {name: "complete" for name in _CATEGORY_ORDER},
        "events": events,
    }


def write_output(dataset: dict, output_path: Path, force: bool = False) -> None:
    """Атомарно записать датасет: временный файл + replace, без перезаписи без --force."""
    if output_path.exists() and not force:
        raise FileExistsError(
            f"output already exists: {output_path}; pass --force to overwrite"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=output_path.parent, prefix=output_path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dataset, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
        os.replace(temp_name, output_path)
    except BaseException:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise


def _log_rating_summary(
    dataset: dict, schema: dict, scoring_client: ScoringClient
) -> None:
    """Проверить и оценить датасет через internal scoring и записать сводку.

    DatasetRejected (ValueError) — набор отклонён; ScoringUnavailable — сбой
    scoring. Оба отказа прерывают адаптацию до записи output.
    """
    rating = scoring_client.score_city(dataset, schema, service=ServiceName.LEGACY)
    counts = {name: 0 for name in _CATEGORY_ORDER}
    affected: set[str] = set()
    for event in dataset["events"]:
        counts[event["category"]] += 1
        affected.add(event["house_id"])
    scores = [item.overall_score for item in rating.ratings.values()]
    _logger.info(
        "LEGACY_RATING_SUMMARY",
        "rating summary",
        event_count=len(dataset["events"]),
        affected_house_count=len(affected),
        house_count=len(dataset["houses"]),
        hot_water_count=counts["hot_water"],
        cold_water_count=counts["cold_water"],
        electricity_count=counts["electricity"],
        heating_count=counts["heating"],
        good_count=sum(1 for score in scores if score >= 0.8),
        medium_count=sum(1 for score in scores if 0.4 <= score < 0.8),
        bad_count=sum(1 for score in scores if score < 0.4),
        min_score=round(min(scores), 4),
        max_score=round(max(scores), 4),
        distinct_score_count=len(set(scores)),
    )


def _adaptation_reason(exc: BaseException) -> str:
    """Код причины отказа адаптации без путей и исходного текста ошибки."""
    if isinstance(exc, FileNotFoundError):
        return "file_not_found"
    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)):
        return "invalid_json"
    if isinstance(exc, FileExistsError):
        return "output_exists"
    if isinstance(exc, ScoringUnavailable):
        return "scoring_unavailable"
    if isinstance(exc, ValueError):
        return "validation_failed"
    return "adaptation_failed"


def main(scoring_client: ScoringClient | None = None) -> None:
    """Точка входа адаптера: fail-fast настройка журнала до чтения файлов.

    scoring_client None — клиент по DOMDOSSE_SCORING_URL; такой клиент
    закрывается по завершении.
    """
    setup_logging(load_logging_settings(ServiceName.LEGACY))
    parser = argparse.ArgumentParser(
        description="Адаптировать legacy events_parsed.json в датасет скоринга."
    )
    parser.add_argument("--legacy", required=True, type=Path, help="старый events_parsed.json")
    parser.add_argument("--current", required=True, type=Path, help="текущий pilot_dataset_draft.json")
    parser.add_argument("--output", required=True, type=Path, help="путь нового датасета")
    parser.add_argument("--schema", type=Path, default=None, help="путь JSON Schema")
    parser.add_argument("--force", action="store_true", help="разрешить перезапись output")
    args = parser.parse_args()

    owned_client: ScoringClient | None = None
    try:
        schema_path = args.schema or args.current.parent / _SCHEMA_NAME
        legacy_records = _load_json(args.legacy)
        current_draft = _load_json(args.current)
        stats: dict = {}
        dataset = build_dataset(legacy_records, current_draft, stats=stats)
        schema = _load_json(schema_path)
        outside_window = stats.get("outside_window", 0)
        missing_end = stats.get("missing_end", 0)
        unmatched = stats.get("unmatched", 0)
        _logger.info(
            "LEGACY_DATASET_BUILT",
            "dataset built",
            input_record_count=len(legacy_records),
            output_event_count=len(dataset["events"]),
        )
        _logger.info(
            "LEGACY_RECORDS_SKIPPED",
            "records skipped",
            skipped_count=outside_window + missing_end + unmatched,
            outside_window_count=outside_window,
            missing_end_count=missing_end,
            unmatched_address_count=unmatched,
        )
        if scoring_client is None:
            owned_client = scoring_client = ScoringClient(base_url=load_scoring_url())
        _log_rating_summary(dataset, schema, scoring_client)
        write_output(dataset, args.output, force=args.force)
        _logger.info(
            "LEGACY_OUTPUT_WRITTEN",
            "output written",
            file_name=args.output.name,
            event_count=len(dataset["events"]),
        )
    except Exception as exc:
        _logger.error(
            "LEGACY_ADAPTATION_FAILED",
            "adaptation failed",
            reason=_adaptation_reason(exc),
            error_type=type(exc).__name__,
        )
        raise
    finally:
        if owned_client is not None:
            owned_client.close()


if __name__ == "__main__":
    main()
