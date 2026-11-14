"""Контракт маркированных событий на границе api и internal scoring.

api: SCORING_REQUEST_COMPLETED (INFO) и SCORING_REQUEST_FAILED (ERROR)
с operation, reason и status; scoring: SCORING_OPERATION_COMPLETED (INFO)
и SCORING_OPERATION_REJECTED (WARNING) с operation, snapshot_id,
house_count или code. Содержимое набора в журналы не попадает.
"""

import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

import test_scoring_http as http_cases
from api.main import create_app
from api.scoring_main import app as scoring_app
from core.config import Settings
from scoring_harness import scoring_log_path, scoring_transport
from sources.scoring_client import ScoringClient
from test_logging import LINE_RE

OPERATIONS = {
    http_cases.PARSE_URL: "parse_dataset",
    http_cases.SCORE_URL: "score_city",
}
SNAPSHOT_RE = re.compile(r"^[0-9a-f]{64}$")
# Все синтетические адреса и source_url содержат эти фрагменты.
DATASET_TOKENS = ("Синтетическая", "example.test")


def log_records(path):
    """События журнала (level, marker, data); строка вне формата — отказ."""
    assert path.is_file(), f"execution.log is missing: {path}"
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = LINE_RE.fullmatch(line)
        assert match is not None, line
        records.append((match["level"], match["marker"], json.loads(match["data"])))
    return records


def with_marker(path, marker):
    """Пары (level, data) событий с маркером в порядке записи."""
    if not path.is_file():
        return []
    return [(level, data) for level, found, data in log_records(path) if found == marker]


def assert_no_dataset_content(*paths):
    """Ни адреса, ни source_url набора нет в журналах (в том числе \\u-форме)."""
    forbidden = set(DATASET_TOKENS)
    forbidden.update(json.dumps(token)[1:-1] for token in DATASET_TOKENS)
    for path in paths:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert sorted(token for token in forbidden if token in text) == [], path


def assert_status_field(data, expected):
    """status присутствует всегда: int HTTP-статус или null без ответа."""
    assert "status" in data, data
    assert type(data["status"]) is type(expected), data
    assert data["status"] == expected


@pytest.fixture
def dataset_settings(tmp_path):
    dataset_path = tmp_path / "synthetic-dataset.json"
    schema_path = tmp_path / "synthetic-schema.json"
    http_cases.write_json(dataset_path, http_cases.synthetic_raw())
    http_cases.write_json(schema_path, http_cases.SCHEMA)
    return Settings(dataset_path=dataset_path, schema_path=schema_path)


@pytest.fixture
def internal_client():
    with TestClient(scoring_app) as client:
        yield client


def call_public(settings, handle, url="/api/houses"):
    """Запрос к публичному api; scoring подменён handle. Возвращает операции."""
    paths = []

    def record(request):
        paths.append(request.url.path)
        return handle(request)

    client = ScoringClient(
        base_url="http://scoring", transport=httpx.MockTransport(record)
    )
    with TestClient(create_app(settings, scoring_client=client)) as public:
        response = public.get(url)
    assert set(paths) <= set(OPERATIONS), paths
    return response, [OPERATIONS[path] for path in paths]


def read_timeout(request):
    raise httpx.ReadTimeout("synthetic read timeout", request=request)


def connect_timeout(request):
    raise httpx.ConnectTimeout("synthetic connect timeout", request=request)


def connect_error(request):
    raise httpx.ConnectError("synthetic refused", request=request)


def redirect(request):
    return httpx.Response(302, headers={"location": "/ready"}, request=request)


def server_error(request):
    return httpx.Response(
        500,
        json={"error": {"code": "internal", "message": "synthetic"}},
        request=request,
    )


def snapshot_mismatch(request):
    return httpx.Response(
        409,
        json={"error": {"code": "snapshot_mismatch", "message": "synthetic"}},
        request=request,
    )


def not_json(request):
    return httpx.Response(
        200,
        content=b"not json",
        headers={"content-type": "application/json"},
        request=request,
    )


def wrong_shape(request):
    return httpx.Response(200, json={"unexpected": True}, request=request)


FAILURES = [
    pytest.param(read_timeout, "timeout", None, id="read-timeout"),
    pytest.param(connect_timeout, "timeout", None, id="connect-timeout"),
    pytest.param(connect_error, "transport", None, id="transport"),
    pytest.param(redirect, "redirect", 302, id="redirect"),
    pytest.param(server_error, "http_status", 500, id="http-500"),
    pytest.param(snapshot_mismatch, "snapshot_mismatch", 409, id="snapshot-409"),
    pytest.param(not_json, "invalid_response", 200, id="invalid-json"),
    pytest.param(wrong_shape, "invalid_response", 200, id="invalid-shape"),
]


@pytest.mark.parametrize(("handle", "reason", "status"), FAILURES)
def test_failed_scoring_call_logs_exactly_one_error_with_reason(
    dataset_settings, isolated_execution_log, handle, reason, status
):
    response, operations = call_public(dataset_settings, handle)

    http_cases.assert_error(response, 503, "scoring_unavailable")
    assert len(operations) == 1
    failed = with_marker(isolated_execution_log, "SCORING_REQUEST_FAILED")
    assert len(failed) == 1, failed
    level, data = failed[0]
    assert level == "ERROR"
    assert data["service"] == "api"
    assert data["operation"] == operations[0]
    assert data["reason"] == reason
    assert_status_field(data, status)
    assert with_marker(isolated_execution_log, "SCORING_REQUEST_COMPLETED") == []
    assert_no_dataset_content(isolated_execution_log)


@pytest.mark.parametrize("failing", ("parse_dataset", "score_city"))
def test_failure_event_names_the_operation_that_failed(
    dataset_settings, isolated_execution_log, failing
):
    proxy = scoring_transport()

    def handle(request):
        if OPERATIONS.get(request.url.path) == failing:
            return server_error(request)
        return proxy.handle_request(request)

    response, operations = call_public(dataset_settings, handle, "/api/ready")

    assert failing in operations, (
        "readiness must call parse_dataset and score_city (AGENTS.md, section 25)"
    )
    assert operations.count(failing) == 1
    assert operations[-1] == failing
    http_cases.assert_error(response, 503, "scoring_unavailable")
    failed = with_marker(isolated_execution_log, "SCORING_REQUEST_FAILED")
    assert [
        (level, data["service"], data["operation"], data["reason"], data["status"])
        for level, data in failed
    ] == [("ERROR", "api", failing, "http_status", 500)]
    completed = with_marker(isolated_execution_log, "SCORING_REQUEST_COMPLETED")
    assert [
        (level, data["service"], data["operation"], data["status"])
        for level, data in completed
    ] == [("INFO", "api", operation, 200) for operation in operations[:-1]]
    assert_no_dataset_content(isolated_execution_log, scoring_log_path())


def test_successful_calls_log_completed_on_api_and_scoring(
    dataset_settings, isolated_execution_log
):
    response, operations = call_public(
        dataset_settings, scoring_transport().handle_request
    )

    assert response.status_code == 200
    assert len(response.json()["houses"]) == 20
    assert "score_city" in operations
    completed = with_marker(isolated_execution_log, "SCORING_REQUEST_COMPLETED")
    assert [
        (level, data["service"], data["operation"], data["status"])
        for level, data in completed
    ] == [("INFO", "api", operation, 200) for operation in operations]
    assert with_marker(isolated_execution_log, "SCORING_REQUEST_FAILED") == []
    scoring_log = scoring_log_path()
    expected_snapshot = http_cases.canonical_snapshot_id(http_cases.synthetic_raw())
    scored = with_marker(scoring_log, "SCORING_OPERATION_COMPLETED")
    assert [
        (level, data["service"], data["operation"], data["snapshot_id"])
        for level, data in scored
    ] == [("INFO", "scoring", operation, expected_snapshot) for operation in operations]
    assert all(data["house_count"] == 20 for _, data in scored)
    assert with_marker(scoring_log, "SCORING_OPERATION_REJECTED") == []
    api_text = isolated_execution_log.read_text(encoding="utf-8")
    assert "SCORING_OPERATION_" not in api_text
    assert "SCORING_REQUEST_" not in scoring_log.read_text(encoding="utf-8")
    assert_no_dataset_content(isolated_execution_log, scoring_log)


def no_events_raw():
    raw = http_cases.synthetic_raw()
    raw["events"] = []
    return raw


@pytest.mark.parametrize("url", list(OPERATIONS))
@pytest.mark.parametrize(
    "make_raw",
    (http_cases.synthetic_raw, no_events_raw),
    ids=("events", "no-events"),
)
def test_scoring_success_logs_operation_snapshot_and_house_count(
    internal_client, isolated_execution_log, url, make_raw
):
    raw = make_raw()

    response = internal_client.post(url, json=http_cases.envelope(raw))

    assert response.status_code == 200
    completed = with_marker(isolated_execution_log, "SCORING_OPERATION_COMPLETED")
    assert len(completed) == 1, completed
    level, data = completed[0]
    assert level == "INFO"
    assert data["service"] == "scoring"
    assert data["operation"] == OPERATIONS[url]
    assert SNAPSHOT_RE.fullmatch(data["snapshot_id"])
    assert data["snapshot_id"] == http_cases.canonical_snapshot_id(raw)
    assert data["house_count"] == 20
    assert with_marker(isolated_execution_log, "SCORING_OPERATION_REJECTED") == []
    assert_no_dataset_content(isolated_execution_log)


def empty_envelope():
    return {"json": {}}


def malformed_json():
    return {"content": b"{", "headers": {"content-type": "application/json"}}


def invalid_schema():
    return {"json": http_cases.envelope(http_cases.synthetic_raw(), {"type": "unknown"})}


def unexpected_field():
    raw = http_cases.synthetic_raw()
    raw["unexpected"] = "not allowed"
    return {"json": http_cases.envelope(raw)}


def address_probe():
    raw = http_cases.synthetic_raw()
    raw["houses"][0]["address"] += " "
    return {"json": http_cases.envelope(raw)}


def source_url_probe():
    raw = http_cases.synthetic_raw()
    raw["events"][0]["source_url"] = "https://example.test/synthetic/leak probe"
    return {"json": http_cases.envelope(raw)}


def incomplete_coverage():
    raw = http_cases.synthetic_raw()
    raw["coverage"]["heating"] = "incomplete"
    return {"json": http_cases.envelope(raw)}


def wrong_snapshot():
    raw = http_cases.synthetic_raw()
    return {"json": http_cases.envelope(raw, snapshot_id="0" * 64)}


REJECTIONS = [
    pytest.param(empty_envelope, 400, "invalid_envelope", id="empty-envelope"),
    pytest.param(malformed_json, 400, "invalid_envelope", id="malformed-json"),
    pytest.param(invalid_schema, 422, "schema_invalid", id="schema-invalid"),
    pytest.param(unexpected_field, 422, "dataset_invalid", id="unexpected-field"),
    pytest.param(address_probe, 422, "dataset_invalid", id="address-probe"),
    pytest.param(source_url_probe, 422, "dataset_invalid", id="source-url-probe"),
    pytest.param(incomplete_coverage, 422, "dataset_incomplete", id="incomplete"),
    pytest.param(wrong_snapshot, 409, "snapshot_mismatch", id="snapshot-mismatch"),
]


@pytest.mark.parametrize("url", list(OPERATIONS))
@pytest.mark.parametrize(("make_request", "status", "code"), REJECTIONS)
def test_scoring_rejection_logs_one_warning_with_http_error_code(
    internal_client, isolated_execution_log, url, make_request, status, code
):
    response = internal_client.post(url, **make_request())

    http_cases.assert_error(response, status, code)
    rejected = with_marker(isolated_execution_log, "SCORING_OPERATION_REJECTED")
    assert len(rejected) == 1, rejected
    level, data = rejected[0]
    assert level == "WARNING"
    assert data["service"] == "scoring"
    assert data["operation"] == OPERATIONS[url]
    assert data["code"] == response.json()["error"]["code"]
    assert with_marker(isolated_execution_log, "SCORING_OPERATION_COMPLETED") == []
    assert_no_dataset_content(isolated_execution_log)


@pytest.mark.parametrize("probe", ("address", "source_url"))
def test_dataset_rejected_through_api_leaks_no_content_to_either_log(
    dataset_settings, isolated_execution_log, probe
):
    raw = http_cases.synthetic_raw()
    if probe == "address":
        raw["houses"][0]["address"] += " "
    else:
        raw["events"][0]["source_url"] = "https://example.test/synthetic/leak probe"
    http_cases.write_json(dataset_settings.dataset_path, raw)

    response, operations = call_public(
        dataset_settings, scoring_transport().handle_request
    )

    http_cases.assert_error(response, 503, "dataset_unavailable")
    assert len(operations) == 1
    rejected = with_marker(scoring_log_path(), "SCORING_OPERATION_REJECTED")
    assert [(data["operation"], data["code"]) for _, data in rejected] == [
        (operations[0], "dataset_invalid")
    ]
    assert_no_dataset_content(isolated_execution_log, scoring_log_path())
