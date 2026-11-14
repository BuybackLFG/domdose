"""Shared, production-independent fixtures and oracles for rating tests.

The module builds only synthetic datasets (never real observations) and encodes
rules copied from SPEC.md.  It deliberately imports ``rating`` lazily, so the
instrument self-checks can run before the production package exists.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

TZ10 = timezone(timedelta(hours=10))
POLICY = "rating_observed_exposure_proxy_v1"
CATEGORIES = ("hot_water", "cold_water", "electricity", "heating")
CATEGORY_ORDER = ("electricity", "cold_water", "heating", "hot_water")
DISTRICTS = ("Ленинский", "Первомайский", "Первореченский", "Советский", "Фрунзенский")

PERIOD_FROM = date(2026, 9, 1)
PERIOD_TO = date(2026, 11, 13)
WINDOW_END = datetime(2026, 11, 13, 0, 0, tzinfo=TZ10)
WINDOW_START = WINDOW_END - timedelta(days=30)
SEASON_START = date(2026, 10, 20)
SOURCE_ID = "synthetic-source"


class _Unset:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "UNSET"


UNSET = _Unset()


def make_house(
    house_id: str,
    *,
    services: Mapping[str, str] | None = None,
    district: str = "Советский",
) -> dict[str, Any]:
    kinds = dict.fromkeys(CATEGORIES, "individual")
    if services:
        kinds.update(services)
    return {
        "id": house_id,
        "address": f"Synthetic {house_id}",
        "district": district,
        "fias_id": None,
        "lat": None,
        "lon": None,
        "year_built": None,
        "floors": 0,
        "apartments": None,
        "management_company": None,
        "services": kinds,
        "is_control": False,
        "passport_source_url": None,
    }


def make_source(
    source_id: str = SOURCE_ID,
    *,
    types: Sequence[str] = CATEGORIES,
    covered_from: date | None = PERIOD_FROM,
    covered_to: date | None = PERIOD_TO,
) -> dict[str, Any]:
    return {
        "id": source_id,
        "name": f"Synthetic source {source_id}",
        "url": "https://example.invalid/source",
        "types": list(types),
        "covered_from": covered_from.isoformat() if covered_from is not None else None,
        "covered_to": covered_to.isoformat() if covered_to is not None else None,
    }


def make_event(
    event_id: str,
    category: str,
    *,
    start: datetime,
    end: datetime | None = None,
    hours: float | None = None,
    basis: str | None = None,
    kind: str = "emergency",
    scope: str = "house",
    force: bool = False,
    affected: int | None = 1,
    linked: Sequence[str] = (),
    match: str = "exact",
    district: str = "Советский",
    source_id: str = SOURCE_ID,
) -> dict[str, Any]:
    """Build one dataset event.

    ``end`` is the actual endpoint for ``actual`` and the planned endpoint for
    ``planned``.  ``basis=None`` derives actual from a known end and unknown
    otherwise.  ``hours`` must agree with the endpoints when both are supplied.
    """
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    if basis is None:
        basis = "actual" if end is not None else "unknown"
    if basis in {"actual", "planned"}:
        if end is None:
            raise ValueError("actual/planned event requires an endpoint")
        measured = (end - start).total_seconds() / 3600.0
        duration = measured if hours is None else float(hours)
        if abs(duration - measured) > 1e-9:
            raise ValueError("hours disagree with endpoints")
    else:
        if end is not None or hours is not None:
            raise ValueError("unknown basis cannot carry a duration or endpoint")
        duration = None

    if basis == "actual":
        end_planned, end_actual = None, end
    elif basis == "planned":
        end_planned, end_actual = end, None
    else:
        end_planned, end_actual = None, None

    return {
        "id": event_id,
        "type": category,
        "kind": kind,
        "start": start.isoformat(),
        "end_planned": end_planned.isoformat() if end_planned is not None else None,
        "end_actual": end_actual.isoformat() if end_actual is not None else None,
        "duration_hours": duration,
        "duration_basis": basis,
        "cause": None,
        "organization": None,
        "scope": scope,
        "force_majeure": force,
        "houses_affected": affected,
        "districts": [district],
        "addresses_raw": "",
        "addresses": [],
        "houses": [{"house_id": house_id, "match": match} for house_id in linked],
        "sources": [
            {
                "source_id": source_id,
                "url": "https://example.invalid/event",
                "published_at": None,
            }
        ],
        "notes": None,
    }


def make_dataset(
    *,
    houses: Sequence[dict[str, Any]],
    events: Sequence[dict[str, Any]],
    city_houses: int | None = 10,
    heating_season_start: date | None = None,
    period: tuple[date, date] = (PERIOD_FROM, PERIOD_TO),
    limitations: Sequence[str] | None = None,
    sources: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    period_from, period_to = period
    source_list = (
        list(sources)
        if sources is not None
        else [make_source(covered_from=period_from, covered_to=period_to)]
    )
    return {
        "meta": {
            "schema_version": "1.0",
            "city": "Владивосток",
            "timezone": "Asia/Vladivostok",
            "period": {"from": period_from.isoformat(), "to": period_to.isoformat()},
            "heating_season_start": (
                heating_season_start.isoformat() if heating_season_start is not None else None
            ),
            "generated_at": "2026-11-13T18:00:00+10:00",
            "city_houses": {
                "total": city_houses,
                "by_district": dict.fromkeys(DISTRICTS),
                "source_url": None,
            },
            "sources": source_list,
            "limitations": list(limitations or ["Synthetic rating fixture, not observations"]),
        },
        "houses": list(houses),
        "events": list(events),
    }


def make_request(*house_ids: str, end: datetime = WINDOW_END, policy: Any = UNSET) -> Any:
    """Build CalculationRequest lazily so pure self-checks do not need rating."""
    from rating import CalculationRequest

    kwargs: dict[str, Any] = {
        "target_house_ids": tuple(house_ids),
        "end_exclusive": end,
    }
    if policy is not UNSET:
        kwargs["policy_version"] = policy
    return CalculationRequest(**kwargs)


def house_rating(report: Any, house_id: str) -> Any:
    found = [house for house in report.houses if house.house_id == house_id]
    assert len(found) == 1, f"expected one rating for {house_id}, got {len(found)}"
    return found[0]


def category_rating(house: Any, category: str) -> Any:
    found = [item for item in house.categories if item.type == category]
    assert len(found) == 1, f"expected one {category} category, got {len(found)}"
    return found[0]


def diagnostic_codes(report: Any) -> set[str]:
    return {diagnostic.code for diagnostic in report.diagnostics}


# ---------------------------------------------------------------------------
# Oracles transcribed from SPEC.md, never imported from production.
# ---------------------------------------------------------------------------


def penalty(ratio: float | None) -> float | None:
    """Piecewise linear in log2(r) through (1,0), (2,.33), (4,.67), (8,1)."""
    if ratio is None:
        return None
    if ratio <= 1:
        return 0.0
    if ratio >= 8:
        return 1.0
    anchors = ((1.0, 0.0), (2.0, 0.33), (4.0, 0.67), (8.0, 1.0))
    for (left_r, left_p), (right_r, right_p) in zip(anchors, anchors[1:]):
        if ratio <= right_r:
            position = (math.log2(ratio) - math.log2(left_r)) / (
                math.log2(right_r) - math.log2(left_r)
            )
            return left_p + (right_p - left_p) * position
    raise AssertionError("unreachable")


def category_score(frequency_ratio: float, hours_ratio: float, maximum_ratio: float) -> float:
    return 1.0 - (
        0.4 * penalty(frequency_ratio) + 0.4 * penalty(hours_ratio) + 0.2 * penalty(maximum_ratio)
    )


def normalized_overall(scores: Mapping[str, float]) -> float:
    """Weighted mean capped by min(category score)+0.25 for applicable categories."""
    raw = {"electricity": 0.30, "cold_water": 0.25, "heating": 0.25, "hot_water": 0.20}
    total = sum(raw[name] for name in scores)
    weighted = sum(raw[name] * score for name, score in scores.items()) / total
    return min(weighted, min(scores.values()) + 0.25)


# ---------------------------------------------------------------------------
# Assertion helpers shared with the instrument self-checks.
# ---------------------------------------------------------------------------


def assert_number(actual: Any, expected: Any, label: str) -> None:
    if expected is UNSET:
        return
    if expected is None:
        assert actual is None, f"{label}: expected None, got {actual!r}"
        return
    assert actual is not None, f"{label}: expected {expected!r}, got None"
    assert math.isfinite(actual), f"{label}: got nonfinite {actual!r}"
    assert math.isclose(actual, float(expected), rel_tol=0.0, abs_tol=1e-9), (
        f"{label}: expected {expected!r}, got {actual!r}"
    )


def assert_metrics(
    metrics: Any,
    *,
    frequency: Any = UNSET,
    hours: Any = UNSET,
    maximum: Any = UNSET,
    label: str = "metrics",
) -> None:
    if frequency is hours is maximum is UNSET:
        return
    assert metrics is not None, f"{label}: missing"
    assert_number(metrics.frequency, frequency, f"{label}.frequency")
    assert_number(metrics.hours, hours, f"{label}.hours")
    assert_number(metrics.maximum, maximum, f"{label}.maximum")


def assert_baseline(
    baseline: Any,
    *,
    frequency: Any = UNSET,
    hours: Any = UNSET,
    maximum: Any = UNSET,
    city_houses: Any = UNSET,
    exposures: Any = UNSET,
    maximum_method: Any = UNSET,
    label: str = "baseline",
) -> None:
    if frequency is hours is maximum is city_houses is exposures is maximum_method is UNSET:
        return
    assert baseline is not None, f"{label}: missing"
    assert_number(baseline.frequency, frequency, f"{label}.frequency")
    assert_number(baseline.hours, hours, f"{label}.hours")
    assert_number(baseline.maximum, maximum, f"{label}.maximum")
    if city_houses is not UNSET:
        assert baseline.city_houses == city_houses, (
            f"{label}.city_houses: expected {city_houses!r}, got {baseline.city_houses!r}"
        )
    if exposures is not UNSET:
        assert baseline.exposures == exposures, (
            f"{label}.exposures: expected {exposures!r}, got {baseline.exposures!r}"
        )
    if maximum_method is not UNSET:
        assert baseline.maximum_method == maximum_method, (
            f"{label}.maximum_method: expected {maximum_method!r}, got {baseline.maximum_method!r}"
        )


def assert_category(
    category: Any,
    *,
    type: str,
    state: str,
    frequency: Any = UNSET,
    hours: Any = UNSET,
    maximum: Any = UNSET,
    score: Any = UNSET,
    estimated: Any = UNSET,
    baseline: Mapping[str, Any] | None = None,
    ratios: Mapping[str, Any] | None = None,
    penalties: Mapping[str, Any] | None = None,
    reason: Any = UNSET,
) -> None:
    assert category.type == type, f"category.type: expected {type!r}, got {category.type!r}"
    assert category.state == state, f"{type}.state: expected {state!r}, got {category.state!r}"
    assert_metrics(
        category.metrics, frequency=frequency, hours=hours, maximum=maximum, label=f"{type}.metrics"
    )
    if score is not UNSET:
        assert_number(category.score, score, f"{type}.score")
    if estimated is not UNSET:
        assert category.estimated is estimated, (
            f"{type}.estimated: expected {estimated!r}, got {category.estimated!r}"
        )
    if reason is not UNSET:
        if reason is None:
            assert category.reason is None, f"{type}.reason: expected None, got {category.reason!r}"
        else:
            assert category.reason == reason, (
                f"{type}.reason: expected {reason!r}, got {category.reason!r}"
            )
    if baseline is not None:
        assert_baseline(category.baseline, label=f"{type}.baseline", **baseline)
    if ratios is not None:
        assert_metrics(category.ratios, label=f"{type}.ratios", **ratios)
    if penalties is not None:
        assert_metrics(category.penalties, label=f"{type}.penalties", **penalties)


def assert_house(
    house: Any,
    *,
    state: str,
    overall: Any = UNSET,
    effective_weights: Mapping[str, float] | None = None,
    limiting: Iterable[str] | None = None,
    categories: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    assert house.state == state, f"{house.house_id}.state: expected {state!r}, got {house.state!r}"
    if overall is not UNSET:
        assert_number(house.overall, overall, f"{house.house_id}.overall")
    actual_categories = [item.type for item in house.categories]
    assert tuple(actual_categories) == CATEGORY_ORDER, (
        f"{house.house_id}.categories: expected {CATEGORY_ORDER!r}, "
        f"got {tuple(actual_categories)!r}"
    )
    if categories is not None:
        for category_type, expectations in categories.items():
            assert_category(
                category_rating(house, category_type), type=category_type, **expectations
            )
    if effective_weights is not None:
        actual = {weight.type: weight.weight for weight in house.effective_weights}
        assert set(actual) == set(effective_weights), (
            f"{house.house_id}.effective_weights: expected {set(effective_weights)!r}, "
            f"got {set(actual)!r}"
        )
        for category_type, expected in effective_weights.items():
            assert_number(
                actual[category_type],
                expected,
                f"{house.house_id}.effective_weights[{category_type}]",
            )
        expected_total = 0.0 if not effective_weights else 1.0
        actual_total = sum(actual.values())
        assert math.isclose(actual_total, expected_total, rel_tol=0.0, abs_tol=1e-9), (
            f"{house.house_id}.effective_weights sum: {actual_total!r}"
        )
    if limiting is not None:
        assert set(house.limiting_categories) == set(limiting), (
            f"{house.house_id}.limiting_categories: expected {set(limiting)!r}, "
            f"got {set(house.limiting_categories)!r}"
        )


def assert_report(
    report: Any,
    *,
    policy: str = POLICY,
    start: datetime = WINDOW_START,
    end: datetime = WINDOW_END,
    houses: Mapping[str, Mapping[str, Any]] | None = None,
    limitations: Sequence[str] | None = None,
) -> None:
    assert report.policy_version == policy, (
        f"report.policy_version: expected {policy!r}, got {report.policy_version!r}"
    )
    assert report.window.start == start, (
        f"report.window.start: expected {start!r}, got {report.window.start!r}"
    )
    assert report.window.end_exclusive == end, (
        f"report.window.end_exclusive: expected {end!r}, got {report.window.end_exclusive!r}"
    )
    assert isinstance(report.houses, tuple), "report.houses must be a tuple"
    assert isinstance(report.diagnostics, tuple), "report.diagnostics must be a tuple"
    assert isinstance(report.limitations, tuple), "report.limitations must be a tuple"
    assert all(isinstance(item, str) for item in report.limitations), (
        "report.limitations must contain strings"
    )
    if limitations is not None:
        for item in limitations:
            assert item in report.limitations, f"report.limitations misses {item!r}"
    if houses is not None:
        assert tuple(item.house_id for item in report.houses) == tuple(houses), (
            "report.houses must follow the requested target order"
        )
        for house_id, expectations in houses.items():
            assert_house(house_rating(report, house_id), **expectations)
    for diagnostic in report.diagnostics:
        assert isinstance(diagnostic.code, str) and diagnostic.code, (
            "diagnostic.code must be a nonempty string"
        )
        assert isinstance(diagnostic.path, tuple), "diagnostic.path must be a tuple"
        assert all(
            isinstance(part, (str, int)) and not isinstance(part, bool) for part in diagnostic.path
        ), f"diagnostic.path has non path parts: {diagnostic.path!r}"
        assert isinstance(diagnostic.event_ids, tuple), "diagnostic.event_ids must be a tuple"
        assert all(isinstance(item, str) for item in diagnostic.event_ids), (
            "diagnostic.event_ids must contain strings"
        )
        assert isinstance(diagnostic.house_ids, tuple), "diagnostic.house_ids must be a tuple"
        assert all(isinstance(item, str) for item in diagnostic.house_ids), (
            "diagnostic.house_ids must contain strings"
        )


def assert_effective_weights_sum(house: Any, expected_total: float = 1.0) -> None:
    weights = [weight.weight for weight in house.effective_weights]
    assert math.isclose(sum(weights), expected_total, rel_tol=0.0, abs_tol=1e-9), weights


def assert_unchanged(before: Any, after: Any, label: str = "input") -> None:
    assert after == before, f"{label} mutation detected"


def assert_safe(error: BaseException, canary: str) -> None:
    """The public error must not echo raw input values anywhere reachable."""
    seen: set[int] = set()

    def visit(value: Any) -> None:
        if id(value) in seen:
            return
        seen.add(id(value))
        assert canary not in str(value), f"canary leaked through {type(value)!r}"
        assert canary not in repr(value), f"canary leaked through {type(value)!r}"
        if isinstance(value, BaseException):
            visit(vars(value))
            visit(value.args)
            if value.__cause__ is not None:
                visit(value.__cause__)
            if value.__context__ is not None:
                visit(value.__context__)
        elif isinstance(value, Mapping):
            for key, item in value.items():
                visit(key)
                visit(item)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                visit(item)

    visit(error)


def _reject_constant(token: str) -> None:
    raise AssertionError(f"nonfinite JSON constant: {token}")


def assert_finite_json(text: str) -> dict[str, Any]:
    """Parse JSON while refusing NaN/Infinity and all nonfinite floats."""
    parsed = json_loads_strict(text)
    assert_finite_object(parsed)
    return parsed


def json_loads_strict(text: str) -> Any:
    import json

    return json.loads(text, parse_constant=_reject_constant)


def assert_finite_object(value: Any, label: str = "value") -> None:
    if isinstance(value, float):
        assert math.isfinite(value), f"{label}: nonfinite float {value!r}"
    elif isinstance(value, Mapping):
        for key, item in value.items():
            assert_finite_object(item, f"{label}[{key!r}]")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_finite_object(item, f"{label}[{index}]")


def diagnostic_context(report: Any, code: str) -> list[Any]:
    return [diagnostic for diagnostic in report.diagnostics if diagnostic.code == code]
