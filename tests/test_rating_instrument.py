"""Safe test-only doubles proving the rating checks reject broken results.

No production module is imported or mutated here.  These doubles mirror the
mutants named by SPEC.md so the measurement itself is calibrated while the
production ``rating`` package is still absent.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest
from test_rating_support import (
    UNSET,
    WINDOW_END,
    WINDOW_START,
    assert_baseline,
    assert_category,
    assert_finite_json,
    assert_finite_object,
    assert_house,
    assert_number,
    assert_report,
    assert_safe,
    assert_unchanged,
    category_score,
    normalized_overall,
    penalty,
)

ORDER = ("electricity", "cold_water", "heating", "hot_water")


def metrics(
    frequency: float | None = 0.0,
    hours: float | None = 0.0,
    maximum: float | None = 0.0,
) -> SimpleNamespace:
    return SimpleNamespace(frequency=frequency, hours=hours, maximum=maximum)


def baseline(
    frequency: float | None = 0.0,
    hours: float | None = 0.0,
    maximum: float | None = 0.0,
    *,
    city_houses: int | None = 10,
    exposures: int | None = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        frequency=frequency,
        hours=hours,
        maximum=maximum,
        city_houses=city_houses,
        exposures=exposures,
        maximum_method="exposure_mean_weighted_duration_v1",
    )


def category(
    category_type: str = "electricity",
    *,
    state: str = "approximate",
    frequency: float | None = 0.0,
    hours: float | None = 0.0,
    maximum: float | None = 0.0,
    score: float | None = 1.0,
    estimated: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        type=category_type,
        state=state,
        reason=None,
        metrics=metrics(frequency, hours, maximum),
        baseline=baseline(),
        ratios=metrics(None, None, None),
        penalties=metrics(0.0, 0.0, 0.0),
        score=score,
        estimated=estimated,
    )


def house(
    *,
    state: str = "approximate",
    overall: float | None = 1.0,
    weights: tuple[tuple[str, float], ...] = (),
    limiting: tuple[str, ...] = (),
    categories: tuple[SimpleNamespace, ...] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        house_id="h1",
        categories=categories or tuple(category(name) for name in ORDER),
        overall=overall,
        state=state,
        effective_weights=tuple(
            SimpleNamespace(type=name, weight=value) for name, value in weights
        ),
        limiting_categories=limiting,
    )


def report(
    *,
    houses: tuple[SimpleNamespace, ...] = (),
    start=WINDOW_START,
    end=WINDOW_END,
    diagnostics: tuple[SimpleNamespace, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        policy_version="rating_observed_exposure_proxy_v1",
        window=SimpleNamespace(start=start, end_exclusive=end),
        houses=houses,
        diagnostics=diagnostics,
        limitations=("Synthetic limitation",),
    )


def test_penalty_oracle_matches_contract_knots_and_midpoints():
    assert penalty(1) == 0.0
    assert penalty(2) == pytest.approx(0.33, abs=1e-12)
    assert penalty(4) == pytest.approx(0.67, abs=1e-12)
    assert penalty(8) == 1.0
    assert penalty(math.sqrt(2)) == pytest.approx(0.165, abs=1e-12)
    assert penalty(2 * math.sqrt(2)) == pytest.approx(0.5, abs=1e-12)
    assert penalty(4 * math.sqrt(2)) == pytest.approx(0.835, abs=1e-12)
    assert category_score(4, 4, 1) == pytest.approx(0.464, abs=1e-12)
    assert normalized_overall({"electricity": 0.2, "cold_water": 1.0}) == pytest.approx(
        0.45, abs=1e-12
    )


def test_category_checker_catches_null_to_zero_mutant():
    check = {
        "type": "electricity",
        "state": "unavailable",
        "frequency": 1.0,
        "hours": None,
        "maximum": None,
        "score": None,
    }
    assert_category(
        category(state="unavailable", frequency=1.0, hours=None, maximum=None, score=None),
        **check,
    )
    mutant = category(state="unavailable", frequency=1.0, hours=0.0, maximum=0.0, score=None)
    with pytest.raises(AssertionError, match="hours"):
        assert_category(mutant, **check)


def test_baseline_checker_catches_sample_population_denominator():
    assert_baseline(baseline(frequency=0.1, hours=0.2, maximum=2.0), frequency=0.1)
    mutant = baseline(frequency=1.0, hours=2.0, maximum=2.0)
    with pytest.raises(AssertionError, match="baseline.frequency"):
        assert_baseline(mutant, frequency=0.1)


def test_baseline_checker_catches_proxy_replaced_by_mean_hours():
    assert_baseline(baseline(frequency=0.1, hours=0.2, maximum=2.0), maximum=2.0)
    mutant = baseline(frequency=0.1, hours=0.2, maximum=0.2)
    with pytest.raises(AssertionError, match="baseline.maximum"):
        assert_baseline(mutant, maximum=2.0)


def test_category_checker_catches_double_discount_mutant():
    assert_category(
        category(frequency=0.5, hours=1.0, maximum=1.0),
        type="electricity",
        state="approximate",
        frequency=0.5,
    )
    mutant = category(frequency=0.25, hours=0.5, maximum=0.5)
    with pytest.raises(AssertionError, match="frequency"):
        assert_category(mutant, type="electricity", state="approximate", frequency=0.5)


def test_house_checker_catches_silent_omission_of_unavailable_category():
    known = house(
        state="unavailable",
        overall=1.0,
        weights=(("cold_water", 1.0),),
    )
    with pytest.raises(AssertionError, match="overall"):
        assert_house(known, state="unavailable", overall=None)


def test_category_checker_catches_ambiguous_match_treated_as_zero():
    zero = category(state="approximate", frequency=0.0, hours=0.0, maximum=0.0, score=1.0)
    with pytest.raises(AssertionError, match="state"):
        assert_category(
            zero,
            type="electricity",
            state="unavailable",
            frequency=None,
            hours=None,
            maximum=None,
            score=None,
        )


def test_category_checker_catches_missing_planned_estimate():
    actual = category(estimated=False)
    with pytest.raises(AssertionError, match="estimated"):
        assert_category(actual, type="electricity", state="approximate", estimated=True)


def test_house_checker_catches_zero_denominator_inconsistency_as_success():
    inconsistent = house(state="unavailable", overall=1.0)
    with pytest.raises(AssertionError, match="overall"):
        assert_house(inconsistent, state="unavailable", overall=None)


def test_house_checker_catches_unnormalized_weights():
    fake = house(weights=(("electricity", 0.30), ("cold_water", 0.25)))
    with pytest.raises(AssertionError, match="effective_weights"):
        assert_house(
            fake,
            state="approximate",
            effective_weights={"electricity": 0.30 / 0.55, "cold_water": 0.25 / 0.55},
        )


def test_house_checker_sums_empty_weights_as_zero_and_known_as_one():
    empty = house(state="not_applicable", overall=None, weights=())
    assert_house(empty, state="not_applicable", overall=None, effective_weights={})
    normalized = house(
        weights=(
            ("electricity", 0.30),
            ("cold_water", 0.25),
            ("heating", 0.25),
            ("hot_water", 0.20),
        )
    )
    assert_house(
        normalized,
        state="approximate",
        effective_weights={
            "electricity": 0.30,
            "cold_water": 0.25,
            "heating": 0.25,
            "hot_water": 0.20,
        },
    )
    unnormalized = house(weights=(("electricity", 0.30), ("cold_water", 0.25)))
    with pytest.raises(AssertionError, match="effective_weights sum"):
        assert_house(
            unnormalized,
            state="approximate",
            effective_weights={"electricity": 0.30, "cold_water": 0.25},
        )


def test_report_checker_catches_window_off_by_one():
    wrong = report(end=WINDOW_END.replace(hour=1))
    with pytest.raises(AssertionError, match="window.end_exclusive"):
        assert_report(wrong)


def test_input_mutation_checker_catches_a_mutated_mapping():
    before = {"houses": [{"id": "h1"}]}
    after = {"houses": [{"id": "h2"}]}
    assert_unchanged(before, {"houses": [{"id": "h1"}]})
    with pytest.raises(AssertionError, match="mutation"):
        assert_unchanged(before, after)


def test_finite_json_checker_catches_nan_and_infinity():
    with pytest.raises(AssertionError, match="nonfinite JSON"):
        assert_finite_json(json.dumps({"value": float("nan")}))
    with pytest.raises(AssertionError, match="nonfinite JSON"):
        assert_finite_json(json.dumps({"value": float("inf")}))
    with pytest.raises(AssertionError, match="nonfinite float"):
        assert_finite_object({"value": float("-inf")})


def test_safe_error_checker_catches_a_raw_value_canary():
    error = ValueError("synthetic-probe")
    error.__context__ = ValueError("DO_NOT_DISCLOSE_rating_canary")
    with pytest.raises(AssertionError, match="canary"):
        assert_safe(error, "DO_NOT_DISCLOSE_rating_canary")


def test_number_checker_catches_a_literal_wrong_value():
    with pytest.raises(AssertionError, match="expected"):
        assert_number(1.0, 0.1, "probe")
    assert_number(None, None, "probe")
    assert_number(1.0, UNSET, "probe")
    with pytest.raises(AssertionError, match="got None"):
        assert_number(None, 1.0, "probe")
    with pytest.raises(AssertionError, match="expected 1.0"):
        assert_number(2.0, 1.0, "probe")
