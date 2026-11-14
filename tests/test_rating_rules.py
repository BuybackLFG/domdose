"""Independent, SPEC-first rating rules on synthetic populations.

Every expected number is a hand oracle taken from SPEC.md, not from production
helpers.  Numeric equality uses atol=1e-9 as required by the acceptance clause.
"""

from __future__ import annotations

import copy
import math
from datetime import date, datetime, timedelta

import pytest
from test_rating_support import (
    CATEGORIES,
    CATEGORY_ORDER,
    SEASON_START,
    TZ10,
    WINDOW_END,
    assert_baseline,
    assert_category,
    assert_house,
    assert_report,
    category_rating,
    category_score,
    diagnostic_codes,
    house_rating,
    make_dataset,
    make_event,
    make_house,
    make_request,
    penalty,
)

from rating import CalculationReport, evaluate


def evaluate_house(
    data: dict,
    house_id: str = "h1",
    *,
    end: datetime = WINDOW_END,
) -> tuple[CalculationReport, object]:
    report = evaluate(copy.deepcopy(data), make_request(house_id, end=end))
    return report, house_rating(report, house_id)


def assert_codes(report: CalculationReport, *expected: str) -> None:
    actual = diagnostic_codes(report)
    for code in expected:
        assert code in actual, f"diagnostic {code!r} missing; got {sorted(actual)!r}"


def services(**values: str) -> dict[str, str]:
    return dict.fromkeys(CATEGORIES, "individual") | values


def one_house(
    *,
    city_houses: int | None = 10,
    heating_season_start: date | None = None,
    events: list[dict] | None = None,
    house_services: dict[str, str] | None = None,
) -> dict:
    return make_dataset(
        houses=[
            make_house("h1", services=house_services or {"electricity": "central"}),
        ],
        events=events or [],
        city_houses=city_houses,
        heating_season_start=heating_season_start,
    )


# ---------------------------------------------------------------------------
# Window intersection and clipping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "start", "end", "expected_count", "expected_hours"),
    [
        (
            "carry-in",
            datetime(2026, 10, 13, 12, 0, tzinfo=TZ10),
            datetime(2026, 10, 14, 12, 0, tzinfo=TZ10),
            1.0,
            12.0,
        ),
        (
            "starts-at-window-start",
            datetime(2026, 10, 14, 0, 0, tzinfo=TZ10),
            datetime(2026, 10, 14, 6, 0, tzinfo=TZ10),
            1.0,
            6.0,
        ),
        (
            "ends-at-window-end",
            datetime(2026, 11, 12, 18, 0, tzinfo=TZ10),
            datetime(2026, 11, 13, 0, 0, tzinfo=TZ10),
            1.0,
            6.0,
        ),
        (
            "carry-out",
            datetime(2026, 11, 12, 18, 0, tzinfo=TZ10),
            datetime(2026, 11, 13, 6, 0, tzinfo=TZ10),
            1.0,
            6.0,
        ),
        (
            "starts-at-window-end",
            datetime(2026, 11, 13, 0, 0, tzinfo=TZ10),
            datetime(2026, 11, 13, 6, 0, tzinfo=TZ10),
            0.0,
            0.0,
        ),
        (
            "ends-at-window-start",
            datetime(2026, 10, 13, 12, 0, tzinfo=TZ10),
            datetime(2026, 10, 14, 0, 0, tzinfo=TZ10),
            0.0,
            0.0,
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_window_intersection_clips_and_counts_once(
    label, start, end, expected_count, expected_hours
):
    anchor_start = datetime(2026, 11, 1, 12, 0, tzinfo=TZ10)
    data = make_dataset(
        houses=[
            make_house("h1", services={"electricity": "central"}),
            make_house("h2", services={"electricity": "central"}),
        ],
        events=[
            make_event("evt-target", "electricity", start=start, end=end, linked=("h1",)),
            make_event(
                "evt-anchor",
                "electricity",
                start=anchor_start,
                end=anchor_start + timedelta(hours=1),
                linked=("h2",),
            ),
        ],
        city_houses=2,
    )
    _report, house = evaluate_house(data)
    assert_category(
        category_rating(house, "electricity"),
        type="electricity",
        state="approximate",
        frequency=expected_count,
        hours=expected_hours,
        maximum=expected_hours,
    )


def test_zero_duration_event_counts_frequency_and_zero_hours():
    start = datetime(2026, 11, 1, 12, 0, tzinfo=TZ10)
    data = one_house(
        city_houses=1,
        events=[make_event("evt-zero", "electricity", start=start, end=start, linked=("h1",))],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert_category(
        electricity,
        type="electricity",
        state="approximate",
        frequency=1.0,
        hours=0.0,
        maximum=0.0,
        score=1.0,
        estimated=False,
    )
    assert_baseline(
        electricity.baseline,
        frequency=1.0,
        hours=0.0,
        maximum=0.0,
        city_houses=1,
        exposures=1,
        maximum_method="exposure_mean_weighted_duration_v1",
    )
    assert electricity.ratios.frequency == pytest.approx(1.0, abs=1e-9)
    assert electricity.ratios.hours is None
    assert electricity.ratios.maximum is None
    assert electricity.penalties.frequency == pytest.approx(0.0, abs=1e-9)
    assert electricity.penalties.hours == pytest.approx(0.0, abs=1e-9)
    assert electricity.penalties.maximum == pytest.approx(0.0, abs=1e-9)
    assert house.overall == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Event weights and the single mass/force modifier
# ---------------------------------------------------------------------------


def test_emergency_and_planned_weights_hours_maximum_and_estimate():
    data = one_house(
        city_houses=4,
        events=[
            make_event(
                "evt-emergency",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            ),
            make_event(
                "evt-planned",
                "electricity",
                start=datetime(2026, 11, 2, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 2, 17, 0, tzinfo=TZ10),
                basis="planned",
                kind="planned",
                linked=("h1",),
            ),
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert_category(
        electricity,
        type="electricity",
        state="approximate",
        frequency=1.4,
        hours=4.0,
        maximum=2.0,
        score=0.464,
        estimated=True,
        ratios={"frequency": 4.0, "hours": 4.0, "maximum": 1.0},
        penalties={"frequency": 0.67, "hours": 0.67, "maximum": 0.0},
    )
    assert_baseline(
        electricity.baseline,
        frequency=0.35,
        hours=1.0,
        maximum=2.0,
        city_houses=4,
        exposures=2,
        maximum_method="exposure_mean_weighted_duration_v1",
    )
    assert_codes(report, "PLANNED_DURATION_USED")
    assert_house(
        house,
        state="approximate",
        overall=0.464,
        effective_weights={"electricity": 1.0},
        limiting=("electricity",),
    )


def test_estimated_uses_duration_basis_not_event_kind():
    data = one_house(
        city_houses=1,
        events=[
            make_event(
                "evt-basis-planned",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                basis="planned",
                kind="emergency",
                linked=("h1",),
            )
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert electricity.estimated is True
    assert electricity.metrics.frequency == pytest.approx(1.0, abs=1e-9)
    assert electricity.metrics.hours == pytest.approx(2.0, abs=1e-9)
    assert_codes(report, "PLANNED_DURATION_USED")


def test_planned_duration_in_city_baseline_also_marks_house_estimated():
    data = make_dataset(
        houses=[
            make_house("h1", services={"electricity": "central"}),
            make_house("h2", services={"electricity": "central"}),
        ],
        events=[
            make_event(
                "evt-planned-other",
                "electricity",
                start=datetime(2026, 11, 2, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 2, 14, 0, tzinfo=TZ10),
                basis="planned",
                kind="planned",
                linked=("h2",),
            )
        ],
        city_houses=10,
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert electricity.metrics.frequency == pytest.approx(0.0, abs=1e-9)
    assert electricity.metrics.hours == pytest.approx(0.0, abs=1e-9)
    assert electricity.metrics.maximum == pytest.approx(0.0, abs=1e-9)
    assert electricity.estimated is True
    assert electricity.score == pytest.approx(1.0, abs=1e-9)
    assert_baseline(electricity.baseline, frequency=0.04, hours=0.08, maximum=0.8)
    assert_codes(report, "PLANNED_DURATION_USED")


@pytest.mark.parametrize(
    ("scope", "kind", "force", "basis", "expected_weight"),
    [
        ("district", "emergency", False, "actual", 0.5),
        ("district", "emergency", True, "actual", 0.5),
        ("city", "planned", True, "actual", 0.2),
        ("group", "emergency", False, "actual", 1.0),
        ("group", "emergency", True, "actual", 0.5),
        ("house", "emergency", False, "actual", 1.0),
        ("house", "planned", False, "actual", 0.4),
        ("house", "emergency", True, "actual", 0.5),
        ("district", "emergency", True, "planned", 0.5),
    ],
)
def test_mass_or_force_modifier_applied_once(scope, kind, force, basis, expected_weight):
    data = one_house(
        city_houses=2,
        events=[
            make_event(
                "evt-weight",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                basis=basis,
                kind=kind,
                scope=scope,
                force=force,
                linked=("h1",),
            )
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert_category(
        electricity,
        type="electricity",
        state="approximate",
        frequency=expected_weight,
        hours=2.0 * expected_weight,
        maximum=2.0 * expected_weight,
        score=0.736,
        estimated=(basis == "planned"),
        ratios={"frequency": 2.0, "hours": 2.0, "maximum": 1.0},
        penalties={"frequency": 0.33, "hours": 0.33, "maximum": 0.0},
    )
    if basis == "planned":
        assert_codes(report, "PLANNED_DURATION_USED")


# ---------------------------------------------------------------------------
# Unavailable and conservative inputs
# ---------------------------------------------------------------------------


def test_unknown_kind_makes_category_unavailable():
    data = one_house(
        city_houses=10,
        events=[
            make_event(
                "evt-unknown-kind",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                kind="unknown",
                linked=("h1",),
            )
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert_category(
        electricity,
        type="electricity",
        state="unavailable",
        frequency=None,
        hours=None,
        maximum=None,
        score=None,
    )
    assert_baseline(electricity.baseline, frequency=None, hours=None, maximum=None)
    assert_house(
        house,
        state="unavailable",
        overall=None,
        effective_weights={"electricity": 1.0},
        limiting=(),
    )
    assert_codes(report, "UNKNOWN_KIND", "BASELINE_UNAVAILABLE")


@pytest.mark.parametrize("match", ["range", "street"])
def test_range_or_street_match_makes_category_unavailable(match):
    data = one_house(
        city_houses=10,
        events=[
            make_event(
                f"evt-{match}",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
                match=match,
            )
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert_category(
        electricity,
        type="electricity",
        state="unavailable",
        frequency=None,
        hours=None,
        maximum=None,
        score=None,
    )
    assert_house(
        house,
        state="unavailable",
        overall=None,
        effective_weights={"electricity": 1.0},
        limiting=(),
    )
    assert_codes(report, "AMBIGUOUS_MATCH")


def test_null_duration_keeps_frequency_known_but_hours_maximum_unavailable():
    data = one_house(
        city_houses=2,
        events=[
            make_event(
                "evt-null-duration",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                basis="unknown",
                linked=("h1",),
            )
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert_category(
        electricity,
        type="electricity",
        state="unavailable",
        frequency=1.0,
        hours=None,
        maximum=None,
        score=None,
    )
    assert_baseline(electricity.baseline, frequency=0.5, hours=None, maximum=None)
    assert_house(house, state="unavailable", overall=None, limiting=())
    assert_codes(report, "UNKNOWN_DURATION")


def test_unknown_overlap_before_window_is_conservatively_unavailable():
    data = one_house(
        city_houses=2,
        events=[
            make_event(
                "evt-uncertain-overlap",
                "electricity",
                start=datetime(2026, 10, 10, 12, 0, tzinfo=TZ10),
                basis="unknown",
                linked=("h1",),
            )
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert_category(
        electricity,
        type="electricity",
        state="unavailable",
        frequency=None,
        hours=None,
        maximum=None,
        score=None,
    )
    assert_baseline(electricity.baseline, frequency=None, hours=None, maximum=None)
    assert_house(house, state="unavailable", overall=None, limiting=())
    assert_codes(report, "UNKNOWN_OVERLAP")


def test_city_total_unknown_makes_baseline_unavailable():
    data = one_house(
        city_houses=None,
        events=[
            make_event(
                "evt-known",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            )
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert electricity.metrics.frequency == pytest.approx(1.0, abs=1e-9)
    assert_baseline(
        electricity.baseline,
        frequency=None,
        hours=None,
        maximum=None,
        city_houses=None,
    )
    assert_category(
        electricity,
        type="electricity",
        state="unavailable",
        frequency=1.0,
        hours=2.0,
        maximum=2.0,
        score=None,
    )
    assert_house(house, state="unavailable", overall=None, limiting=())
    assert_codes(report, "BASELINE_UNAVAILABLE")


# ---------------------------------------------------------------------------
# City baselines, zero-event houses and the exposure proxy
# ---------------------------------------------------------------------------


def test_city_population_includes_zero_event_houses():
    data = one_house(
        city_houses=10,
        events=[
            make_event(
                "evt-known",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            )
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert_category(
        electricity,
        type="electricity",
        state="approximate",
        frequency=1.0,
        hours=2.0,
        maximum=2.0,
        score=0.2,
        estimated=False,
        ratios={"frequency": 10.0, "hours": 10.0, "maximum": 1.0},
        penalties={"frequency": 1.0, "hours": 1.0, "maximum": 0.0},
    )
    assert_baseline(
        electricity.baseline,
        frequency=0.1,
        hours=0.2,
        maximum=2.0,
        city_houses=10,
        exposures=1,
        maximum_method="exposure_mean_weighted_duration_v1",
    )
    assert_house(
        house,
        state="approximate",
        overall=0.2,
        effective_weights={"electricity": 1.0},
        limiting=("electricity",),
    )
    assert_codes(report, "PROXY_BASELINE_USED")


def test_exposure_proxy_denominator_repeats_exposures_and_uses_unequal_n():
    data = make_dataset(
        houses=[
            make_house("h1", services={"electricity": "central"}),
            make_house("h3"),
            make_house("h4"),
        ],
        events=[
            make_event(
                "evt-1",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                affected=1,
                linked=("h1",),
            ),
            make_event(
                "evt-2",
                "electricity",
                start=datetime(2026, 11, 2, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 2, 13, 30, tzinfo=TZ10),
                basis="planned",
                kind="planned",
                affected=3,
                linked=("h3",),
            ),
            make_event(
                "evt-3",
                "electricity",
                start=datetime(2026, 11, 3, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 3, 12, 0, tzinfo=TZ10),
                affected=2,
            ),
            make_event(
                "evt-4",
                "electricity",
                start=datetime(2026, 11, 4, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 4, 13, 0, tzinfo=TZ10),
                affected=4,
                linked=("h1",),
            ),
        ],
        city_houses=10,
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    baseline = electricity.baseline
    assert_baseline(
        baseline,
        frequency=0.82,
        hours=0.78,
        maximum=0.78,
        city_houses=10,
        exposures=10,
        maximum_method="exposure_mean_weighted_duration_v1",
    )
    assert electricity.metrics.frequency == pytest.approx(2.0, abs=1e-9)
    assert electricity.metrics.hours == pytest.approx(3.0, abs=1e-9)
    assert electricity.metrics.maximum == pytest.approx(2.0, abs=1e-9)
    assert electricity.ratios.frequency == pytest.approx(2.0 / 0.82, abs=1e-9)
    assert electricity.ratios.hours == pytest.approx(3.0 / 0.78, abs=1e-9)
    assert electricity.ratios.maximum == pytest.approx(2.0 / 0.78, abs=1e-9)
    expected_score = category_score(2.0 / 0.82, 3.0 / 0.78, 2.0 / 0.78)
    assert electricity.score == pytest.approx(expected_score, abs=1e-9)
    assert house.overall == pytest.approx(expected_score, abs=1e-9)
    assert electricity.estimated is True
    assert_codes(report, "PLANNED_DURATION_USED", "PROXY_BASELINE_USED")


def test_empty_journal_yields_zero_baselines_and_named_diagnostics():
    data = one_house(city_houses=10)
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert_category(
        electricity,
        type="electricity",
        state="approximate",
        frequency=0.0,
        hours=0.0,
        maximum=0.0,
        score=1.0,
        estimated=False,
        ratios={"frequency": None, "hours": None, "maximum": None},
        penalties={"frequency": 0.0, "hours": 0.0, "maximum": 0.0},
    )
    assert_baseline(
        electricity.baseline,
        frequency=0.0,
        hours=0.0,
        maximum=0.0,
        city_houses=10,
        exposures=0,
        maximum_method="exposure_mean_weighted_duration_v1",
    )
    assert_house(
        house,
        state="approximate",
        overall=1.0,
        effective_weights={"electricity": 1.0},
        limiting=("electricity",),
    )
    assert report.limitations == tuple(data["meta"]["limitations"])
    assert_codes(
        report,
        "NO_OBSERVED_EVENTS",
        "PROXY_BASELINE_USED",
        "SOURCE_COVERAGE_UNPROVEN",
    )
    assert "WINDOW_OUTSIDE_DATASET" not in diagnostic_codes(report)


def test_positive_observation_with_zero_baseline_is_inconsistent():
    data = one_house(
        city_houses=10,
        events=[
            make_event(
                "evt-zero-affected",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                affected=0,
                linked=("h1",),
            )
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert_category(
        electricity,
        type="electricity",
        state="unavailable",
        frequency=1.0,
        hours=2.0,
        maximum=2.0,
        score=None,
    )
    assert electricity.penalties.frequency is None
    assert electricity.penalties.hours is None
    assert electricity.penalties.maximum is None
    assert_baseline(
        electricity.baseline,
        frequency=0.0,
        hours=0.0,
        maximum=0.0,
        exposures=0,
    )
    assert_house(house, state="unavailable", overall=None, limiting=())
    assert_codes(report, "BASELINE_INCONSISTENT")


def test_unknown_affected_count_is_not_silently_dropped_from_baseline():
    data = one_house(
        city_houses=10,
        events=[
            make_event(
                "evt-known",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                affected=1,
                linked=("h1",),
            ),
            make_event(
                "evt-unknown-n",
                "electricity",
                start=datetime(2026, 11, 2, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 2, 14, 0, tzinfo=TZ10),
                affected=None,
            ),
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert electricity.metrics.frequency == pytest.approx(1.0, abs=1e-9)
    assert_baseline(electricity.baseline, frequency=None, hours=None, maximum=None)
    assert_house(house, state="unavailable", overall=None, limiting=())
    assert_codes(report, "UNKNOWN_AFFECTED_COUNT", "BASELINE_UNAVAILABLE")


def test_unknown_baseline_weight_is_not_silently_dropped():
    data = one_house(
        city_houses=10,
        events=[
            make_event(
                "evt-known",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                affected=1,
                linked=("h1",),
            ),
            make_event(
                "evt-unknown-weight",
                "electricity",
                start=datetime(2026, 11, 2, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 2, 14, 0, tzinfo=TZ10),
                kind="unknown",
                affected=2,
            ),
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert electricity.metrics.frequency == pytest.approx(1.0, abs=1e-9)
    assert_baseline(electricity.baseline, frequency=None, hours=None, maximum=None)
    assert_house(house, state="unavailable", overall=None, limiting=())
    assert_codes(report, "UNKNOWN_KIND", "BASELINE_UNAVAILABLE")


def test_unknown_baseline_duration_keeps_frequency_but_not_hours():
    data = one_house(
        city_houses=10,
        events=[
            make_event(
                "evt-known",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                affected=1,
                linked=("h1",),
            ),
            make_event(
                "evt-unknown-duration",
                "electricity",
                start=datetime(2026, 11, 2, 12, 0, tzinfo=TZ10),
                basis="unknown",
                affected=2,
            ),
        ],
    )
    report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert electricity.metrics.frequency == pytest.approx(1.0, abs=1e-9)
    assert_baseline(electricity.baseline, frequency=0.3, hours=None, maximum=None)
    assert_house(house, state="unavailable", overall=None, limiting=())
    assert_codes(report, "UNKNOWN_DURATION", "BASELINE_UNAVAILABLE")


# ---------------------------------------------------------------------------
# Penalty knots and the sqrt(2) midpoint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("city_houses", "expected_penalty", "expected_score"),
    [(1, 0.0, 1.0), (2, 0.33, 0.736), (4, 0.67, 0.464), (8, 1.0, 0.2)],
)
def test_penalty_exact_knots(city_houses, expected_penalty, expected_score):
    data = one_house(
        city_houses=city_houses,
        events=[
            make_event(
                "evt-knot",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            )
        ],
    )
    _report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    assert electricity.ratios.frequency == pytest.approx(city_houses, abs=1e-9)
    assert electricity.ratios.hours == pytest.approx(city_houses, abs=1e-9)
    assert electricity.ratios.maximum == pytest.approx(1.0, abs=1e-9)
    assert electricity.penalties.frequency == pytest.approx(expected_penalty, abs=1e-9)
    assert electricity.penalties.hours == pytest.approx(expected_penalty, abs=1e-9)
    assert electricity.penalties.maximum == pytest.approx(0.0, abs=1e-9)
    assert electricity.score == pytest.approx(expected_score, abs=1e-9)
    assert house.overall == pytest.approx(expected_score, abs=1e-9)


def test_penalty_midpoint_at_sqrt_two_is_0165():
    extra_hours = 2.0 * math.sqrt(2.0) - 2.0
    extra_start = datetime(2026, 11, 2, 12, 0, tzinfo=TZ10)
    data = make_dataset(
        houses=[
            make_house("h1", services={"electricity": "central"}),
            make_house("h2"),
        ],
        events=[
            make_event(
                "evt-target",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            ),
            make_event(
                "evt-extra",
                "electricity",
                start=extra_start,
                end=extra_start + timedelta(hours=extra_hours),
                scope="district",
                affected=2,
            ),
        ],
        city_houses=2,
    )
    _report, house = evaluate_house(data)
    electricity = category_rating(house, "electricity")
    # Q_M = (1*1*2 + 2*0.5*(2*sqrt(2)-2)) / (1+2) = 2*sqrt(2)/3.
    # The target maximum is 2, so the maximum ratio is 2/(2*sqrt(2)/3) = 3/sqrt(2).
    maximum_ratio = 3.0 / math.sqrt(2.0)
    maximum_penalty = 0.33 + 0.34 * (math.log2(maximum_ratio) - 1.0)
    expected_score = 1.0 - 0.4 * 0.165 - 0.2 * maximum_penalty
    assert electricity.ratios.frequency == pytest.approx(1.0, abs=1e-9)
    assert electricity.ratios.hours == pytest.approx(math.sqrt(2.0), abs=1e-9)
    assert electricity.ratios.maximum == pytest.approx(maximum_ratio, abs=1e-9)
    assert electricity.penalties.frequency == pytest.approx(0.0, abs=1e-9)
    assert electricity.penalties.hours == pytest.approx(0.165, abs=1e-9)
    assert electricity.penalties.maximum == pytest.approx(maximum_penalty, abs=1e-9)
    assert electricity.score == pytest.approx(expected_score, abs=1e-9)
    assert house.overall == pytest.approx(expected_score, abs=1e-9)


# ---------------------------------------------------------------------------
# Category eligibility, weights, renormalisation and the cap
# ---------------------------------------------------------------------------


def test_no_central_services_is_not_applicable():
    data = make_dataset(
        houses=[
            make_house(
                "h1",
                services={
                    "electricity": "none",
                    "cold_water": "individual",
                    "heating": "none",
                    "hot_water": "individual",
                },
            )
        ],
        events=[
            make_event(
                "evt-ignored",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            )
        ],
    )
    _report, house = evaluate_house(data)
    empty = {
        "state": "not_applicable",
        "frequency": None,
        "hours": None,
        "maximum": None,
        "score": None,
    }
    assert_house(
        house,
        state="not_applicable",
        overall=None,
        effective_weights={},
        limiting=(),
        categories={name: empty for name in CATEGORY_ORDER},
    )


def test_unknown_service_is_unavailable_even_without_central_services():
    data = make_dataset(
        houses=[
            make_house(
                "h1",
                services={
                    "electricity": "central",
                    "cold_water": "individual",
                    "heating": "none",
                    "hot_water": "unknown",
                },
            )
        ],
        events=[
            make_event(
                "evt-electricity",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            )
        ],
        city_houses=10,
    )
    report, house = evaluate_house(data)
    assert_house(
        house,
        state="unavailable",
        overall=None,
        effective_weights={"electricity": 1.0},
        limiting=(),
    )
    assert_category(
        category_rating(house, "electricity"),
        type="electricity",
        state="approximate",
        frequency=1.0,
        score=0.2,
    )
    assert category_rating(house, "hot_water").state == "unavailable"
    assert_codes(report, "SERVICE_UNKNOWN")


def test_before_season_heating_is_not_applicable_and_not_reclassified():
    window_end = datetime(2026, 10, 20, 0, 0, tzinfo=TZ10)
    data = make_dataset(
        houses=[
            make_house("h1", services={"hot_water": "central", "heating": "central"}),
            make_house("h2", services={"hot_water": "central"}),
        ],
        events=[
            make_event(
                "evt-heating-before-season",
                "heating",
                start=datetime(2026, 10, 15, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 10, 15, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            ),
            make_event(
                "evt-hot-water-anchor",
                "hot_water",
                start=datetime(2026, 10, 15, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 10, 15, 13, 0, tzinfo=TZ10),
                linked=("h2",),
            ),
        ],
        city_houses=2,
        heating_season_start=date(2026, 10, 21),
    )
    report, house = evaluate_house(data, end=window_end)
    assert_report(report, start=window_end - timedelta(days=30), end=window_end)
    assert_category(
        category_rating(house, "heating"),
        type="heating",
        state="not_applicable",
        frequency=None,
        hours=None,
        maximum=None,
        score=None,
    )
    hot_water = category_rating(house, "hot_water")
    assert_category(
        hot_water,
        type="hot_water",
        state="approximate",
        frequency=0.0,
        hours=0.0,
        maximum=0.0,
        score=1.0,
    )
    assert_baseline(hot_water.baseline, frequency=0.5, hours=0.5, maximum=1.0)
    assert_house(
        house,
        state="approximate",
        overall=1.0,
        effective_weights={"hot_water": 1.0},
        limiting=("hot_water",),
    )
    assert_codes(report, "SOURCE_COVERAGE_UNPROVEN")
    assert "HEATING_SEASON_UNKNOWN" not in diagnostic_codes(report)


def test_unknown_season_makes_central_heating_unavailable():
    data = one_house(
        city_houses=10,
        house_services={"heating": "central"},
        heating_season_start=None,
        events=[
            make_event(
                "evt-heating",
                "heating",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            )
        ],
    )
    report, house = evaluate_house(data)
    assert_category(
        category_rating(house, "heating"),
        type="heating",
        state="unavailable",
        frequency=None,
        hours=None,
        maximum=None,
        score=None,
    )
    assert_house(house, state="unavailable", overall=None, limiting=())
    assert_codes(report, "HEATING_SEASON_UNKNOWN")


def test_short_season_clips_heating_and_ignores_before_season_events():
    data = make_dataset(
        houses=[make_house("h1", services={"heating": "central"})],
        events=[
            make_event(
                "evt-pre-season",
                "heating",
                start=datetime(2026, 10, 15, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 10, 15, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            ),
            make_event(
                "evt-cross-season",
                "heating",
                start=datetime(2026, 10, 19, 23, 0, tzinfo=TZ10),
                end=datetime(2026, 10, 20, 3, 0, tzinfo=TZ10),
                linked=("h1",),
            ),
            make_event(
                "evt-after-season",
                "heating",
                start=datetime(2026, 10, 21, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 10, 21, 13, 0, tzinfo=TZ10),
                linked=("h1",),
            ),
        ],
        city_houses=1,
        heating_season_start=SEASON_START,
    )
    _report, house = evaluate_house(data)
    heating = category_rating(house, "heating")
    expected_penalty = penalty(1.5)
    expected_score = 1.0 - 0.2 * expected_penalty
    assert_category(
        heating,
        type="heating",
        state="approximate",
        frequency=2.0,
        hours=4.0,
        maximum=3.0,
        score=expected_score,
        ratios={"frequency": 1.0, "hours": 1.0, "maximum": 1.5},
        penalties={"frequency": 0.0, "hours": 0.0, "maximum": expected_penalty},
    )
    assert_baseline(
        heating.baseline,
        frequency=2.0,
        hours=4.0,
        maximum=2.0,
        exposures=2,
    )
    assert house.overall == pytest.approx(expected_score, abs=1e-9)


def test_category_weights_renormalize_and_min_score_cap_applies():
    data = one_house(
        city_houses=10,
        house_services={"electricity": "central", "cold_water": "central"},
        events=[
            make_event(
                "evt-electricity",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            )
        ],
    )
    report, house = evaluate_house(data)
    cold_water = category_rating(house, "cold_water")
    assert_category(
        cold_water,
        type="cold_water",
        state="approximate",
        frequency=0.0,
        hours=0.0,
        maximum=0.0,
        score=1.0,
        ratios={"frequency": None, "hours": None, "maximum": None},
        penalties={"frequency": 0.0, "hours": 0.0, "maximum": 0.0},
    )
    assert_codes(report, "NO_OBSERVED_EVENTS")
    assert_house(
        house,
        state="approximate",
        overall=0.45,
        effective_weights={
            "electricity": 0.30 / 0.55,
            "cold_water": 0.25 / 0.55,
        },
        limiting=("electricity",),
    )
    assert house.limiting_categories == ("electricity",)


def test_unavailable_central_category_is_not_silently_dropped():
    data = one_house(
        city_houses=10,
        house_services={"electricity": "central", "cold_water": "central"},
        events=[
            make_event(
                "evt-electricity",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                kind="unknown",
                linked=("h1",),
            )
        ],
    )
    _report, house = evaluate_house(data)
    assert_category(
        category_rating(house, "electricity"),
        type="electricity",
        state="unavailable",
        score=None,
    )
    assert_category(
        category_rating(house, "cold_water"),
        type="cold_water",
        state="approximate",
        score=1.0,
    )
    assert_house(
        house,
        state="unavailable",
        overall=None,
        effective_weights={
            "electricity": 0.30 / 0.55,
            "cold_water": 0.25 / 0.55,
        },
        limiting=(),
    )
    assert house.overall is None


def test_limiting_categories_include_all_minimum_ties_in_fixed_order():
    data = make_dataset(
        houses=[
            make_house(
                "h1",
                services=dict.fromkeys(CATEGORY_ORDER, "central"),
            )
        ],
        events=[],
        city_houses=10,
        heating_season_start=date(2026, 10, 1),
    )
    _report, house = evaluate_house(data)
    assert_house(
        house,
        state="approximate",
        overall=1.0,
        effective_weights={
            "electricity": 0.30,
            "cold_water": 0.25,
            "heating": 0.25,
            "hot_water": 0.20,
        },
        limiting=CATEGORY_ORDER,
    )
    assert house.limiting_categories == CATEGORY_ORDER
    assert tuple(item.type for item in house.categories) == CATEGORY_ORDER
