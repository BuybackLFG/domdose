#!/usr/bin/env python3
"""Local readiness report: what blocks a rating score for each house.

Reads one dataset file, evaluates the approved rating method for every listed
house and reports, per category, the state and the concrete fact that must be
supplied before a score can exist. Read-only: no network, no data repair, no
environment or clock access.

Usage:
  .venv/Scripts/python.exe scripts/rating_readiness.py \
      --dataset data/datasets/communal-outages-2026.json \
      --end 2026-11-13T00:00:00+10:00 --out .local/rating-readiness.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from contract.dataset import read_dataset
from rating import CalculationRequest, evaluate

TZ10 = timedelta(hours=10)

ACTION_BY_REASON = {
    "UNKNOWN_SERVICE": "FILL_SERVICE_PASSPORT",
    "HEATING_SEASON_UNKNOWN": "SET_HEATING_SEASON_START",
    "BASELINE_UNAVAILABLE": "FILL_CITY_POPULATION_OR_AFFECTED_COUNT",
    "UNKNOWN_KIND": "CLASSIFY_EVENT_KIND",
    "UNKNOWN_DURATION": "FILL_EVENT_DURATION",
    "UNKNOWN_OVERLAP": "FILL_EVENT_TIMING",
    "UNKNOWN_AFFECTED_COUNT": "FILL_AFFECTED_COUNT",
    "AMBIGUOUS_MATCH": "RESOLVE_HOUSE_MATCH",
    "BASELINE_INCONSISTENT": "REVIEW_BASELINE",
}


def _category_entry(category: object) -> dict[str, object]:
    reason = category.reason
    return {
        "state": category.state,
        "reason": reason,
        "score": category.score,
        "action": ACTION_BY_REASON.get(reason) if reason else None,
    }


def build_report(dataset_path: Path, end_exclusive: datetime) -> dict[str, object]:
    dataset = read_dataset(dataset_path.read_text(encoding="utf-8"))
    ids = tuple(house.id for house in dataset.houses)
    if not ids:
        return {
            "dataset": str(dataset_path),
            "window": {
                "start": (end_exclusive - timedelta(days=30)).isoformat(),
                "end_exclusive": end_exclusive.isoformat(),
            },
            "city_population": dataset.meta.city_houses.total,
            "global_blockers": ["NO_HOUSES"],
            "data_quality_warnings": [],
            "unknown_kind_events": {"count": 0, "by_type": {}},
            "unknown_service_houses": [],
            "score_possible_houses": [],
            "houses": [],
        }
    request = CalculationRequest(target_house_ids=ids, end_exclusive=end_exclusive)
    report = evaluate(dataset, request)

    event_types = {event.id: event.type for event in dataset.events}
    unknown_kind = Counter(
        event_types[event_id]
        for event_id in (
            event_id
            for diagnostic in report.diagnostics
            if diagnostic.code == "UNKNOWN_KIND"
            for event_id in diagnostic.event_ids
        )
        if event_id in event_types
    )

    houses: list[dict[str, object]] = []
    for house in report.houses:
        blocking = sorted(
            {category.type for category in house.categories if category.state == "unavailable"}
        )
        houses.append(
            {
                "house_id": house.house_id,
                "state": house.state,
                "overall": house.overall,
                "blocking_categories": blocking,
                "categories": {
                    category.type: _category_entry(category) for category in house.categories
                },
            }
        )

    total = dataset.meta.city_houses.total
    unknown_services = sorted(
        house.id
        for house in dataset.houses
        if any(kind == "unknown" for kind in house.services.model_dump().values())
    )
    blockers: list[str] = []
    if total is None:
        blockers.append("CITY_POPULATION_UNKNOWN")
    if unknown_kind:
        blockers.append("EVENT_KIND_UNKNOWN")
    if unknown_services:
        blockers.append("SERVICE_PASSPORTS_INCOMPLETE")
    if dataset.meta.heating_season_start is None:
        blockers.append("HEATING_SEASON_UNKNOWN")

    zero_affected = sum(1 for event in dataset.events if event.houses_affected == 0)
    fewer_than_addresses = sum(
        1
        for event in dataset.events
        if event.houses_affected is not None and event.houses_affected < len(event.addresses)
    )
    no_links = sum(1 for event in dataset.events if not event.houses)
    warnings: list[dict[str, object]] = []
    if zero_affected:
        warnings.append({"code": "AFFECTED_COUNT_ZERO_PRESENT", "count": zero_affected})
    if fewer_than_addresses:
        warnings.append({"code": "AFFECTED_LESS_THAN_ADDRESSES", "count": fewer_than_addresses})
    if no_links:
        warnings.append({"code": "EVENTS_WITHOUT_HOUSE_LINKS", "count": no_links})

    return {
        "dataset": str(dataset_path),
        "window": {
            "start": report.window.start.isoformat(),
            "end_exclusive": report.window.end_exclusive.isoformat(),
        },
        "city_population": total,
        "global_blockers": blockers,
        "data_quality_warnings": warnings,
        "unknown_kind_events": {"count": sum(unknown_kind.values()), "by_type": dict(unknown_kind)},
        "unknown_service_houses": unknown_services,
        "score_possible_houses": [
            house["house_id"] for house in houses if house["overall"] is not None
        ],
        "houses": houses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--end", default="2026-11-13T00:00:00+10:00")
    parser.add_argument("--out")
    args = parser.parse_args()

    end = datetime.fromisoformat(args.end)
    if end.utcoffset() != TZ10:
        parser.error("--end must carry the +10:00 offset")
    result = build_report(Path(args.dataset), end)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    possible = result["score_possible_houses"]
    print(
        f"houses={len(result['houses'])} score_possible={len(possible)} "
        f"blockers={','.join(result['global_blockers']) or 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
