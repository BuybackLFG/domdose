"""Rating request/report contract, safe refusals and architectural boundaries."""

from __future__ import annotations

import ast
import copy
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_rating_support import (
    CATEGORY_ORDER,
    POLICY,
    TZ10,
    WINDOW_END,
    WINDOW_START,
    assert_finite_json,
    assert_finite_object,
    assert_house,
    assert_report,
    assert_safe,
    assert_unchanged,
    make_dataset,
    make_event,
    make_house,
    make_request,
    make_source,
)

from contract.dataset import Dataset, read_dataset
from contract.errors import ContractIssue, ContractRefused
from rating import CalculationReport, CalculationRequest, evaluate

CANARY = "DO_NOT_DISCLOSE_rating_canary"

ROOT = Path(__file__).resolve().parents[1]


def one_house_dataset() -> dict:
    return make_dataset(
        houses=[make_house("h1", services={"electricity": "central"})],
        events=[],
        city_houses=10,
    )


def all_categories_dataset() -> dict:
    return make_dataset(
        houses=[
            make_house(
                "h1",
                services=dict.fromkeys(CATEGORY_ORDER, "central"),
            )
        ],
        events=[
            make_event(
                "evt-electricity",
                "electricity",
                start=datetime(2026, 11, 1, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 1, 14, 0, tzinfo=TZ10),
                linked=("h1",),
            ),
            make_event(
                "evt-cold-water",
                "cold_water",
                start=datetime(2026, 11, 2, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 2, 13, 0, tzinfo=TZ10),
                linked=("h1",),
            ),
            make_event(
                "evt-heating",
                "heating",
                start=datetime(2026, 11, 3, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 3, 13, 0, tzinfo=TZ10),
                linked=("h1",),
            ),
            make_event(
                "evt-hot-water",
                "hot_water",
                start=datetime(2026, 11, 4, 12, 0, tzinfo=TZ10),
                end=datetime(2026, 11, 4, 15, 0, tzinfo=TZ10),
                linked=("h1",),
            ),
        ],
        city_houses=10,
        heating_season_start=date(2026, 10, 1),
    )


def issue_pairs(error: ContractRefused) -> set[tuple[str, tuple]]:
    assert isinstance(error.issues, tuple) and error.issues
    assert all(isinstance(issue, ContractIssue) for issue in error.issues)
    return {(issue.code, issue.path) for issue in error.issues}


# ---------------------------------------------------------------------------
# Request DTO
# ---------------------------------------------------------------------------


def test_request_schema_frozen_extra_forbidden_and_default_policy():
    request = CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END)
    assert set(CalculationRequest.model_fields) == {
        "target_house_ids",
        "end_exclusive",
        "policy_version",
    }
    assert request.target_house_ids == ("h1",)
    assert request.policy_version == POLICY
    assert request.end_exclusive == WINDOW_END
    with pytest.raises((ValidationError, AttributeError, TypeError)):
        request.policy_version = "changed"
    with pytest.raises(ValidationError):
        CalculationRequest(
            target_house_ids=("h1",),
            end_exclusive=WINDOW_END,
            unexpected=CANARY,
        )
    with pytest.raises(ValidationError):
        CalculationRequest(
            target_house_ids=("h1",),
            end_exclusive=WINDOW_END,
            policy_version="other_policy",
        )


def test_request_accepts_tuple_and_list_but_direct_iso_end_is_rejected():
    from_tuple = CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END)
    from_list = CalculationRequest(target_house_ids=["h1"], end_exclusive=WINDOW_END)
    assert from_tuple.target_house_ids == ("h1",)
    assert from_list.target_house_ids == ("h1",)
    assert isinstance(from_list.target_house_ids, tuple)
    with pytest.raises(ValidationError):
        CalculationRequest(
            target_house_ids=("h1",),
            end_exclusive="2026-11-13T00:00:00+10:00",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_house_ids": ()},
        {"target_house_ids": ("h1", "h1")},
        {"target_house_ids": (1,)},
        {"end_exclusive": datetime(2026, 11, 13)},
        {"end_exclusive": datetime(2026, 11, 13, tzinfo=timezone(timedelta(hours=9)))},
        {"policy_version": None},
    ],
)
def test_request_rejects_empty_duplicate_naive_wrong_offset_and_bad_types(kwargs):
    values = {"target_house_ids": ("h1",), "end_exclusive": WINDOW_END}
    values.update(kwargs)
    with pytest.raises(ValidationError):
        CalculationRequest(**values)


# ---------------------------------------------------------------------------
# evaluate input forms
# ---------------------------------------------------------------------------


def test_evaluate_accepts_dataset_mapping_string_bytes_and_request_mapping():
    data = one_house_dataset()
    dataset_json = json.dumps(data, ensure_ascii=False)
    request = CalculationRequest(target_house_ids=("h1",), end_exclusive=WINDOW_END)
    reports = [
        evaluate(copy.deepcopy(data), request),
        evaluate(dataset_json, request),
        evaluate(dataset_json.encode("utf-8"), request),
        evaluate(read_dataset(copy.deepcopy(data)), request),
        evaluate(
            copy.deepcopy(data),
            {
                "target_house_ids": ["h1"],
                "end_exclusive": "2026-11-13T00:00:00+10:00",
                "policy_version": POLICY,
            },
        ),
    ]
    for report in reports:
        assert isinstance(report, CalculationReport)
        assert report.model_dump() == reports[0].model_dump()
    assert reports[0].policy_version == POLICY


def test_request_json_string_or_bytes_is_refused_as_invalid_request():
    data = one_house_dataset()
    payload = {
        "target_house_ids": ["h1"],
        "end_exclusive": "2026-11-13T00:00:00+10:00",
    }
    canary_payload = {**payload, "target_house_ids": [CANARY]}
    for request in (
        json.dumps(payload),
        json.dumps(canary_payload, ensure_ascii=False),
        b"{not json",
        "строка",
    ):
        # Only a Mapping (or a validated DTO) is a request; JSON text and bytes of
        # the request are malformed input, not a serialized shortcut.
        with pytest.raises(ContractRefused) as caught:
            evaluate(copy.deepcopy(data), request)
        error = caught.value
        assert isinstance(error.issues, tuple) and error.issues
        assert any(issue.code == "INVALID_REQUEST" for issue in error.issues), error.issues
        assert_safe(error, CANARY)


def test_direct_dataset_is_revalidated_through_read_dataset():
    data = one_house_dataset()
    duplicate = copy.deepcopy(data)
    duplicate["houses"].append(copy.deepcopy(duplicate["houses"][0]))
    # Structural DTO construction may accept duplicate IDs; evaluate must not trust it.
    unvalidated_dto = Dataset(**duplicate)
    with pytest.raises(ContractRefused):
        evaluate(unvalidated_dto, make_request("h1"))
    validated_dto = Dataset(**data)
    report = evaluate(validated_dto, make_request("h1"))
    assert report.houses[0].house_id == "h1"


# ---------------------------------------------------------------------------
# Safe typed refusals
# ---------------------------------------------------------------------------


def test_unknown_house_is_refused_with_code_path_and_safe_error():
    data = one_house_dataset()
    for request in (
        make_request("h1", CANARY),
        {
            "target_house_ids": ["h1", CANARY],
            "end_exclusive": "2026-11-13T00:00:00+10:00",
        },
    ):
        with pytest.raises(ContractRefused) as caught:
            evaluate(copy.deepcopy(data), request)
        error = caught.value
        assert_safe(error, CANARY)
        assert ("UNKNOWN_HOUSE", ("target_house_ids", 1)) in issue_pairs(error)


def test_unknown_policy_is_refused_with_code_path_and_safe_error():
    data = one_house_dataset()
    forged = CalculationRequest.model_construct(
        target_house_ids=("h1",),
        end_exclusive=WINDOW_END,
        policy_version=CANARY,
    )
    for request in (
        forged,
        {
            "target_house_ids": ["h1"],
            "end_exclusive": "2026-11-13T00:00:00+10:00",
            "policy_version": CANARY,
        },
    ):
        with pytest.raises(ContractRefused) as caught:
            evaluate(copy.deepcopy(data), request)
        error = caught.value
        assert_safe(error, CANARY)
        assert ("UNKNOWN_POLICY", ("policy_version",)) in issue_pairs(error)


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (
            {"target_house_ids": [], "end_exclusive": "2026-11-13T00:00:00+10:00"},
            "INVALID_REQUEST",
        ),
        (
            {
                "target_house_ids": ["h1", "h1"],
                "end_exclusive": "2026-11-13T00:00:00+10:00",
            },
            "INVALID_REQUEST",
        ),
        (
            {"target_house_ids": ["h1"], "end_exclusive": "2026-11-13T00:00:00"},
            "INVALID_REQUEST",
        ),
        (
            {
                "target_house_ids": ["h1"],
                "end_exclusive": "2026-11-13T00:00:00+10:00",
                CANARY: CANARY,
            },
            "INVALID_REQUEST",
        ),
        (
            {
                "target_house_ids": ["h1"],
                "end_exclusive": "2026-11-13T00:00:00+10:00",
                "policy_version": CANARY,
            },
            "UNKNOWN_POLICY",
        ),
    ],
)
def test_malformed_request_mapping_is_typed_and_safe(payload, expected_code):
    with pytest.raises(ContractRefused) as caught:
        evaluate(one_house_dataset(), payload)
    error = caught.value
    assert_safe(error, CANARY)
    assert error.issues
    assert any(issue.code == expected_code for issue in error.issues), error.issues


def test_invalid_dataset_is_refused_safely_through_evaluate():
    data = one_house_dataset()
    data[CANARY] = CANARY
    with pytest.raises(ContractRefused) as caught:
        evaluate(data, make_request("h1"))
    assert_safe(caught.value, CANARY)
    assert caught.value.issues


# ---------------------------------------------------------------------------
# Report schema, ordering and source-span quality
# ---------------------------------------------------------------------------


def test_report_schema_window_category_order_limitations_and_source_spans():
    data = all_categories_dataset()
    report = evaluate(copy.deepcopy(data), make_request("h1"))
    assert isinstance(report, CalculationReport)
    assert_report(report)
    assert report.policy_version == POLICY
    assert report.window.start == WINDOW_START
    assert report.window.end_exclusive == WINDOW_END
    assert report.window.start.utcoffset() == timedelta(hours=10)
    assert report.window.end_exclusive.utcoffset() == timedelta(hours=10)
    assert report.limitations == tuple(data["meta"]["limitations"])
    assert isinstance(report.source_spans, tuple)
    assert tuple(span.type for span in report.source_spans) == CATEGORY_ORDER
    for span in report.source_spans:
        assert isinstance(span.intervals, tuple)
        assert isinstance(span.gaps, tuple)
        assert isinstance(span.unknown_source_ids, tuple)
        assert all(isinstance(item, str) for item in span.unknown_source_ids)
        for interval in span.intervals:
            assert type(interval.start) is date
            assert type(interval.end) is date
            assert interval.start <= interval.end
    electricity_span = report.source_spans[0]
    assert [(interval.start, interval.end) for interval in electricity_span.intervals] == [
        (date(2026, 10, 14), date(2026, 11, 12))
    ]
    assert electricity_span.gaps == ()
    assert electricity_span.unknown_source_ids == ()

    house = report.houses[0]
    assert tuple(item.type for item in house.categories) == CATEGORY_ORDER
    for item in house.categories:
        assert item.state in {"approximate", "unavailable", "not_applicable"}
        assert hasattr(item, "reason")
        assert hasattr(item, "estimated")
        assert hasattr(item, "metrics")
        assert hasattr(item, "baseline")
        assert hasattr(item, "ratios")
        assert hasattr(item, "penalties")
        assert hasattr(item, "score")
    assert hasattr(house, "effective_weights")
    assert hasattr(house, "limiting_categories")
    assert isinstance(house.effective_weights, tuple)
    assert isinstance(house.limiting_categories, tuple)


def test_source_spans_report_leading_internal_and_trailing_gaps():
    data = make_dataset(
        houses=[make_house("h1", services={"electricity": "central"})],
        events=[],
        city_houses=10,
        sources=[
            make_source(
                "s-gap-1",
                types=CATEGORY_ORDER,
                covered_from=date(2026, 10, 20),
                covered_to=date(2026, 10, 25),
            ),
            make_source(
                "s-gap-2",
                types=CATEGORY_ORDER,
                covered_from=date(2026, 10, 27),
                covered_to=date(2026, 11, 10),
            ),
        ],
    )
    report = evaluate(copy.deepcopy(data), make_request("h1"))
    span = report.source_spans[0]
    assert span.type == "electricity"
    assert [(interval.start, interval.end) for interval in span.intervals] == [
        (date(2026, 10, 20), date(2026, 10, 25)),
        (date(2026, 10, 27), date(2026, 11, 10)),
    ]
    assert [(interval.start, interval.end) for interval in span.gaps] == [
        (date(2026, 10, 14), date(2026, 10, 19)),
        (date(2026, 10, 26), date(2026, 10, 26)),
        (date(2026, 11, 11), date(2026, 11, 12)),
    ]
    assert span.unknown_source_ids == ()


def test_source_spans_report_unknown_source_dates():
    data = make_dataset(
        houses=[make_house("h1", services={"electricity": "central"})],
        events=[],
        city_houses=10,
        sources=[
            make_source(
                "s-unknown-date",
                types=CATEGORY_ORDER,
                covered_from=date(2026, 10, 20),
                covered_to=None,
            )
        ],
    )
    report = evaluate(copy.deepcopy(data), make_request("h1"))
    for span in report.source_spans:
        assert "s-unknown-date" in span.unknown_source_ids
        assert all(isinstance(item, str) for item in span.unknown_source_ids)


def test_report_houses_follow_requested_target_order():
    data = make_dataset(
        houses=[
            make_house("h1", services={"electricity": "central"}),
            make_house("h2", services={"electricity": "central"}),
            make_house("h3", services={"electricity": "central"}),
        ],
        events=[],
        city_houses=10,
    )
    report = evaluate(copy.deepcopy(data), make_request("h3", "h1", "h2"))
    assert tuple(house.house_id for house in report.houses) == ("h3", "h1", "h2")
    for house in report.houses:
        assert_house(house, state="approximate", overall=1.0)


def test_window_outside_dataset_is_diagnosed_but_does_not_raise():
    data = one_house_dataset()
    for end in (
        datetime(2026, 11, 20, 0, 0, tzinfo=TZ10),
        datetime(2026, 9, 20, 0, 0, tzinfo=TZ10),
    ):
        report = evaluate(copy.deepcopy(data), make_request("h1", end=end))
        codes = {diagnostic.code for diagnostic in report.diagnostics}
        assert "WINDOW_OUTSIDE_DATASET" in codes, codes
        assert isinstance(report.houses, tuple)


# ---------------------------------------------------------------------------
# Determinism, mutation and JSON finiteness
# ---------------------------------------------------------------------------


def test_evaluate_does_not_mutate_inputs_and_report_is_deterministic():
    data = all_categories_dataset()
    data["events"][0]["houses"][0]["match"] = "range"
    data["meta"]["sources"][0]["covered_to"] = "2026-10-20"
    request = make_request("h1")
    before = copy.deepcopy(data)
    request_before = request.model_dump()
    report_one = evaluate(data, request)
    assert_unchanged(before, data)
    assert request.model_dump() == request_before
    report_two = evaluate(data, request)
    assert report_two.model_dump() == report_one.model_dump()
    assert report_two.diagnostics == report_one.diagnostics
    codes = {diagnostic.code for diagnostic in report_one.diagnostics}
    assert {"AMBIGUOUS_MATCH", "SOURCE_COVERAGE_UNPROVEN"} <= codes
    assert isinstance(report_one.houses, tuple)
    assert isinstance(report_one.diagnostics, tuple)


def test_report_json_is_finite_and_json_compatible():
    report = evaluate(all_categories_dataset(), make_request("h1"))
    dump = report.model_dump()
    assert_finite_object(dump)
    text = report.model_dump_json()
    assert isinstance(text, str)
    parsed = assert_finite_json(text)
    assert parsed["policy_version"] == POLICY
    assert len(parsed["houses"]) == 1
    assert len(parsed["source_spans"]) == 4


# ---------------------------------------------------------------------------
# Architecture: no core/settings/clock/IO/FastAPI and no hidden side effects
# ---------------------------------------------------------------------------


FORBIDDEN_ROOTS = {
    "core",
    "fastapi",
    "pydantic_settings",
    "os",
    "socket",
    "requests",
    "httpx",
    "urllib",
    "subprocess",
    "pathlib",
    "tempfile",
    "shutil",
    "io",
    "time",
}
FORBIDDEN_CALLS = {"open", "eval", "exec", "__import__"}
FORBIDDEN_ATTRS = {
    "now",
    "utcnow",
    "today",
    "getenv",
    "write_text",
    "write_bytes",
    "mkdir",
    "unlink",
    "time",
    "time_ns",
}


def architecture_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_ROOTS:
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_ROOTS:
                bad.append(node.module)
        elif isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name) and function.id in FORBIDDEN_CALLS:
                bad.append(function.id)
            if isinstance(function, ast.Attribute) and function.attr in FORBIDDEN_ATTRS:
                bad.append(function.attr)
        elif isinstance(node, ast.Attribute) and node.attr == "environ":
            bad.append("environ")
    return bad


def rating_sources() -> list[Path]:
    package = ROOT / "rating"
    if package.is_dir():
        return sorted(package.glob("**/*.py"))
    module = ROOT / "rating.py"
    return [module] if module.exists() else []


def test_rating_imports_only_public_contracts_and_has_no_clock_or_io():
    files = rating_sources()
    assert files, "rating package/module is absent"
    for file in files:
        source = file.read_text(encoding="utf-8-sig")
        violations = architecture_violations(source)
        assert not violations, (file, violations)


@pytest.mark.parametrize(
    "source",
    [
        "import core",
        "from core.config import Settings",
        "import fastapi",
        "from pydantic_settings import BaseSettings",
        "from os import getenv",
        "value = datetime.now()",
        "value = date.today()",
        "value = time.time()",
        "open('dataset.json')",
        "os.environ['X']",
    ],
)
def test_architecture_probe_catches_forbidden_source(source):
    assert architecture_violations(source)


def root_snapshot():
    root = logging.getLogger()
    return (root.handlers[:], root.level, root.propagate, root.disabled)


def test_evaluate_has_no_hidden_files_logging_or_stdout(isolated_env, capsys):
    snapshot = root_snapshot()
    report = evaluate(one_house_dataset(), make_request("h1"))
    assert report.houses[0].house_id == "h1"
    assert list(isolated_env.iterdir()) == []
    assert root_snapshot() == snapshot
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
