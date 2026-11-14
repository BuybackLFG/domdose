"""Independent guards against rating fakes not covered by the existing suite.

Only public rating API (CalculationRequest, CalculationReport, evaluate) and the
existing synthetic fixtures are used; production rating helpers are never imported.
Every expected number is derived by hand from SPEC.md and shown in a comment.
Synthetic datasets only.  The module imports ``rating`` at collection time, so an
absent package is a collection error, not a skipped guard.
"""

from __future__ import annotations

import copy
import math
from datetime import datetime

import pytest
from test_rating_support import (
    TZ10,
    WINDOW_END,
    WINDOW_START,
    assert_safe,
    category_rating,
    diagnostic_codes,
    house_rating,
    make_dataset,
    make_event,
    make_house,
)

from contract.dataset import Dataset
from contract.errors import ContractRefused
from rating import CalculationReport, CalculationRequest, evaluate


def central_house(house_id: str) -> dict:
    return make_house(house_id, services={"electricity": "central"})


def test_city_denominator_is_meta_total_not_sample_size():
    # Two listed houses, declared city fund N=100.  Both events are known and
    # inside W; n=1 for the target event and n=2 for the other event.
    events = [
        make_event(
            "evt-target",
            "electricity",
            start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
            end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
            affected=1,
            linked=("h1",),
        ),
        make_event(
            "evt-other",
            "electricity",
            start=datetime(2026, 11, 2, 12, 0, tzinfo=TZ10),
            end=datetime(2026, 11, 2, 13, 0, tzinfo=TZ10),
            affected=2,
            linked=("h2",),
        ),
    ]
    data = make_dataset(
        houses=[central_house("h1"), central_house("h2")],
        events=events,
        city_houses=100,
    )
    request = CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END)
    report = evaluate(copy.deepcopy(data), request)
    assert isinstance(report, CalculationReport)
    electricity = category_rating(house_rating(report, "h1"), "electricity")
    baseline = electricity.baseline

    # B_F = (1*1 + 2*1) / 100 = 0.03
    # B_H = (1*1*2 + 2*1*1) / 100 = 0.04
    assert baseline.city_houses == 100
    assert baseline.exposures == 3
    assert baseline.frequency == pytest.approx(0.03, abs=1e-9)
    assert baseline.hours == pytest.approx(0.04, abs=1e-9)
    # Q_M = (1*1*2 + 2*1*1) / (1 + 2) = 4/3, unlike B_H.
    assert baseline.maximum == pytest.approx(4.0 / 3.0, abs=1e-9)
    # Target F=1, H=2, M=2 -> ratios 1/0.03, 2/0.04, 2/(4/3).
    assert electricity.ratios.frequency == pytest.approx(1.0 / 0.03, abs=1e-9)
    assert electricity.ratios.hours == pytest.approx(50.0, abs=1e-9)
    assert electricity.ratios.maximum == pytest.approx(1.5, abs=1e-9)
    # R = 1 - (0.4*1 + 0.4*1 + 0.2*(0.33*log2(1.5))) = 0.161392...
    expected_score = 1.0 - 0.8 - 0.2 * 0.33 * math.log2(1.5)
    assert electricity.score == pytest.approx(expected_score, abs=1e-9)
    assert house_rating(report, "h1").overall == pytest.approx(expected_score, abs=1e-9)

    # The same events with N=2 give different city baselines; len(houses) would
    # have made the N=100 result equal to this one.
    small_data = make_dataset(
        houses=[central_house("h1"), central_house("h2")],
        events=events,
        city_houses=2,
    )
    small_report = evaluate(copy.deepcopy(small_data), request)
    small_baseline = category_rating(house_rating(small_report, "h1"), "electricity").baseline
    assert small_baseline.city_houses == 2
    # B_F = (1 + 2) / 2 = 1.5; B_H = (2 + 2) / 2 = 2.0
    assert small_baseline.frequency == pytest.approx(1.5, abs=1e-9)
    assert small_baseline.hours == pytest.approx(2.0, abs=1e-9)
    assert small_baseline.frequency != pytest.approx(baseline.frequency, abs=1e-9)


def test_exposure_proxy_is_weighted_mean_not_city_mean_or_mean_maximum():
    # Repeated exposures of h1 plus one event of h2 with unequal n.
    events = [
        make_event(
            "evt-a",
            "electricity",
            start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
            end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
            affected=1,
            linked=("h1",),
        ),
        make_event(
            "evt-b",
            "electricity",
            start=datetime(2026, 11, 2, 12, 0, tzinfo=TZ10),
            end=datetime(2026, 11, 2, 13, 0, tzinfo=TZ10),
            affected=4,
            linked=("h1",),
        ),
        make_event(
            "evt-c",
            "electricity",
            start=datetime(2026, 11, 3, 12, 0, tzinfo=TZ10),
            end=datetime(2026, 11, 3, 15, 0, tzinfo=TZ10),
            affected=2,
            linked=("h2",),
        ),
    ]
    data = make_dataset(
        houses=[central_house("h1"), central_house("h2")],
        events=events,
        city_houses=10,
    )
    report = evaluate(
        copy.deepcopy(data),
        CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END),
    )
    electricity = category_rating(house_rating(report, "h1"), "electricity")

    # Q_M = (1*1*2 + 4*1*1 + 2*1*3) / (1 + 4 + 2) = 12/7.
    # B_H = 12/10 = 1.2 and the mean per-house maximum is (2 + 3) / 2 = 2.5;
    # neither equals the exposure-weighted mean, so both fakes are distinguishable.
    assert electricity.baseline.city_houses == 10
    assert electricity.baseline.exposures == 7
    assert electricity.baseline.hours == pytest.approx(1.2, abs=1e-9)
    assert electricity.baseline.maximum == pytest.approx(12.0 / 7.0, abs=1e-9)
    # Target h1: F=2, H=2+1=3, M=max(2,1)=2 -> ratio 2/(12/7)=7/6.
    assert electricity.metrics.frequency == pytest.approx(2.0, abs=1e-9)
    assert electricity.metrics.hours == pytest.approx(3.0, abs=1e-9)
    assert electricity.metrics.maximum == pytest.approx(2.0, abs=1e-9)
    assert electricity.ratios.maximum == pytest.approx(7.0 / 6.0, abs=1e-9)


def test_district_and_force_majeure_apply_the_half_modifier_once():
    # w = 1 for emergency, one 0.5 factor because mass OR force is true.
    data = make_dataset(
        houses=[central_house("h1")],
        events=[
            make_event(
                "evt-mass-and-force",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                scope="district",
                force=True,
                affected=1,
                linked=("h1",),
            )
        ],
        city_houses=2,
    )
    report = evaluate(
        copy.deepcopy(data),
        CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END),
    )
    electricity = category_rating(house_rating(report, "h1"), "electricity")

    # F = 1*0.5 = 0.5 (not 0.25), H = 2*0.5 = 1.0, M = 2*0.5 = 1.0.
    assert electricity.metrics.frequency == pytest.approx(0.5, abs=1e-9)
    assert electricity.metrics.hours == pytest.approx(1.0, abs=1e-9)
    assert electricity.metrics.maximum == pytest.approx(1.0, abs=1e-9)
    # B_F = 1*0.5/2 = 0.25; B_H = 1*0.5*2/2 = 0.5; Q_M = 1*0.5*2/1 = 1.0.
    assert electricity.baseline.frequency == pytest.approx(0.25, abs=1e-9)
    assert electricity.baseline.hours == pytest.approx(0.5, abs=1e-9)
    assert electricity.baseline.maximum == pytest.approx(1.0, abs=1e-9)
    # Ratios 2, 2, 1 -> R = 1 - 0.4*0.33 - 0.4*0.33 = 0.736.
    assert electricity.ratios.frequency == pytest.approx(2.0, abs=1e-9)
    assert electricity.ratios.hours == pytest.approx(2.0, abs=1e-9)
    assert house_rating(report, "h1").overall == pytest.approx(0.736, abs=1e-9)


def test_null_duration_is_not_zero_and_empty_journal_is_zero():
    unknown = make_dataset(
        houses=[central_house("h1")],
        events=[
            make_event(
                "evt-unknown-duration",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                basis="unknown",
                affected=1,
                linked=("h1",),
            )
        ],
        city_houses=2,
    )
    report = evaluate(
        copy.deepcopy(unknown),
        CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END),
    )
    electricity = category_rating(house_rating(report, "h1"), "electricity")
    # Frequency is known: F=1, B_F=(1*1)/2=0.5.  Hours and maximum stay None.
    assert electricity.state == "unavailable"
    assert electricity.metrics.frequency == pytest.approx(1.0, abs=1e-9)
    assert electricity.metrics.hours is None
    assert electricity.metrics.maximum is None
    assert electricity.baseline.frequency == pytest.approx(0.5, abs=1e-9)
    assert electricity.baseline.hours is None
    assert electricity.baseline.maximum is None
    assert electricity.score is None
    assert "UNKNOWN_DURATION" in diagnostic_codes(report)

    empty = make_dataset(houses=[central_house("h1")], events=[], city_houses=10)
    empty_report = evaluate(
        copy.deepcopy(empty),
        CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END),
    )
    empty_electricity = category_rating(house_rating(empty_report, "h1"), "electricity")
    # An empty known journal is zeros: F=H=M=0, B_F=B_H=Q_M=0, score 1.0.
    assert empty_electricity.metrics.frequency == 0.0
    assert empty_electricity.metrics.hours == 0.0
    assert empty_electricity.metrics.maximum == 0.0
    assert empty_electricity.baseline.frequency == 0.0
    assert empty_electricity.baseline.hours == 0.0
    assert empty_electricity.baseline.maximum == 0.0
    assert empty_electricity.baseline.exposures == 0
    assert empty_electricity.score == pytest.approx(1.0, abs=1e-9)
    assert "NO_OBSERVED_EVENTS" in diagnostic_codes(empty_report)


def test_diagnostics_are_deterministic_and_event_conditioned():
    data = make_dataset(
        houses=[central_house("h1")],
        events=[
            make_event(
                "evt-unknown-kind",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                kind="unknown",
                affected=1,
                linked=("h1",),
            )
        ],
        city_houses=10,
    )
    request = CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END)
    first = evaluate(copy.deepcopy(data), request)
    second = evaluate(copy.deepcopy(data), request)
    assert isinstance(first.diagnostics, tuple)
    assert first.diagnostics == second.diagnostics
    codes = tuple(item.code for item in first.diagnostics)
    assert codes == tuple(item.code for item in second.diagnostics)
    # The kind is unknown but the duration is known: UNKNOWN_KIND only.
    assert "UNKNOWN_DURATION" not in codes
    unknown_kind = [item for item in first.diagnostics if item.code == "UNKNOWN_KIND"]
    assert len(unknown_kind) == 1
    assert unknown_kind[0].event_ids == ("evt-unknown-kind",)
    event_codes = {
        "UNKNOWN_KIND",
        "UNKNOWN_DURATION",
        "UNKNOWN_OVERLAP",
        "AMBIGUOUS_MATCH",
        "PLANNED_DURATION_USED",
    }
    for item in first.diagnostics:
        if item.code in event_codes:
            assert set(item.event_ids) <= {"evt-unknown-kind"}


def test_forged_request_and_duplicate_house_dto_are_refused():
    data = make_dataset(houses=[central_house("h1")], events=[], city_houses=10)
    forged = CalculationRequest.model_construct(
        target_house_ids=("h1",),
        end_exclusive=WINDOW_END,
        policy_version="чужое",
    )
    with pytest.raises(ContractRefused) as caught:
        evaluate(copy.deepcopy(data), forged)
    assert any(issue.code == "UNKNOWN_POLICY" for issue in caught.value.issues), caught.value.issues

    bad_type = CalculationRequest.model_construct(
        target_house_ids=("h1",),
        end_exclusive=WINDOW_END,
        policy_version=123,
    )
    with pytest.raises(ContractRefused) as caught:
        evaluate(copy.deepcopy(data), bad_type)
    assert any(
        issue.code == "INVALID_REQUEST" for issue in caught.value.issues
    ), caught.value.issues

    # A Dataset DTO must still pass the whole-dataset semantic gate.
    duplicate = make_dataset(
        houses=[central_house("h1"), central_house("h1")],
        events=[],
        city_houses=10,
    )
    unvalidated_dto = Dataset(**duplicate)
    with pytest.raises(ContractRefused) as caught:
        evaluate(
            unvalidated_dto,
            CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END),
        )
    assert caught.value.issues


FORGED_DATASET_CANARY = "DO_NOT_DISCLOSE_forged_dataset_canary"


@pytest.mark.parametrize("meta", [FORGED_DATASET_CANARY, object()], ids=["text", "object"])
def test_forged_dataset_dto_is_refused_safely_without_leaks(capsys, meta):
    """model_construct bypasses validation; evaluate must refuse without echoing values."""
    forged = Dataset.model_construct(meta=meta, houses=(), events=())
    with pytest.raises(ContractRefused) as caught:
        evaluate(
            forged,
            CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END),
        )
    assert caught.value.issues
    assert_safe(caught.value, FORGED_DATASET_CANARY)
    captured = capsys.readouterr()
    assert FORGED_DATASET_CANARY not in captured.out
    assert FORGED_DATASET_CANARY not in captured.err


def test_rounding_tolerance_uses_stored_duration_not_endpoints():
    # Owner decision A: a stored duration is authoritative within the 0.005 h
    # rounding tolerance; the endpoints agree within that tolerance but must
    # not replace the stored value in metrics or baselines.
    event = make_event(
        "evt-rounded",
        "electricity",
        start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
        end=datetime(2026, 11, 1, 16, 0, tzinfo=TZ10),
        linked=("h1",),
    )
    event["duration_hours"] = 4.003
    data = make_dataset(
        houses=[central_house("h1")],
        events=[event],
        city_houses=1,
    )
    report = evaluate(
        copy.deepcopy(data),
        CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END),
    )
    electricity = category_rating(house_rating(report, "h1"), "electricity")
    assert electricity.metrics.hours == pytest.approx(4.003, abs=1e-9)
    assert electricity.metrics.maximum == pytest.approx(4.003, abs=1e-9)
    assert electricity.baseline.hours == pytest.approx(4.003, abs=1e-9)
    assert electricity.baseline.maximum == pytest.approx(4.003, abs=1e-9)


def test_zero_duration_at_window_start_counts_once():
    # W is half-open and includes its start, so a zero-length event exactly at
    # W.start is inside the window and must be counted once.
    data = make_dataset(
        houses=[central_house("h1")],
        events=[
            make_event(
                "evt-zero-at-start",
                "electricity",
                start=WINDOW_START,
                end=WINDOW_START,
                linked=("h1",),
            )
        ],
        city_houses=1,
    )
    report = evaluate(
        copy.deepcopy(data),
        CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END),
    )
    electricity = category_rating(house_rating(report, "h1"), "electricity")
    assert electricity.metrics.frequency == pytest.approx(1.0, abs=1e-9)
    assert electricity.metrics.hours == pytest.approx(0.0, abs=1e-9)
    assert electricity.metrics.maximum == pytest.approx(0.0, abs=1e-9)
    assert "NO_OBSERVED_EVENTS" not in diagnostic_codes(report)


def test_extreme_city_population_gives_partial_report_not_overflow():
    # A schema-valid but unrepresentable city fund must not raise OverflowError;
    # the baseline becomes unavailable and the report stays partial.
    data = make_dataset(houses=[central_house("h1")], events=[], city_houses=10**310)
    report = evaluate(
        copy.deepcopy(data),
        CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END),
    )
    electricity = category_rating(house_rating(report, "h1"), "electricity")
    assert electricity.state == "unavailable"
    assert electricity.baseline.frequency is None
    assert house_rating(report, "h1").overall is None
    assert "BASELINE_UNAVAILABLE" in diagnostic_codes(report)
