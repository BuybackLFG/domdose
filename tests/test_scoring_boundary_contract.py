"""Контракт границы api <-> internal scoring сверх формы ответов.

Эхо snapshot_id, отказ набора как отдельное событие, внутренняя ошибка
scoring, согласованность parse_dataset и score_city, закрытие клиента
и заголовок X-DomDossier-Error у ошибок публичного api.
"""

import json
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

import test_scoring_http as http_cases
from api.main import create_app
from api.scoring_main import app as scoring_app
from core.config import Settings
from dossier.service import UtilityRatingService
from scoring_harness import scoring_log_path, scoring_transport
from sources.scoring_client import ScoringClient
from test_scoring_logging import (
    OPERATIONS,
    assert_no_dataset_content,
    assert_status_field,
    call_public,
    with_marker,
)
from utility_rating.dataset import parse_dataset
from utility_rating.scoring import score_city

DATASET_CODES = ("schema_invalid", "dataset_invalid", "dataset_incomplete")
ERROR_HEADER = "x-domdossier-error"
# Каталоги проектных пакетов, где может жить ссылка на функцию расчёта.
PROJECT_PACKAGES = ("api", "contract", "core", "dossier", "sources", "utility_rating")


@pytest.fixture
def dataset_settings(tmp_path):
    dataset_path = tmp_path / "synthetic-dataset.json"
    schema_path = tmp_path / "synthetic-schema.json"
    http_cases.write_json(dataset_path, http_cases.synthetic_raw())
    http_cases.write_json(schema_path, http_cases.SCHEMA)
    return Settings(dataset_path=dataset_path, schema_path=schema_path)


def foreign_snapshot_id():
    """Канонический snapshot_id другого синтетического набора."""
    raw = http_cases.synthetic_raw()
    raw["events"] = []
    return http_cases.canonical_snapshot_id(raw)


def rewrite_operation(operation, rewrite):
    """Обработчик: in-process scoring, ответ 200 операции переписан rewrite."""
    proxy = scoring_transport()

    def handle(request):
        response = proxy.handle_request(request)
        if OPERATIONS.get(request.url.path) != operation:
            return response
        assert response.status_code == 200, response.read()
        body = json.loads(response.read())
        return httpx.Response(200, json=rewrite(body), request=request)

    return handle


def reject_operation(operation, status, body):
    """Обработчик: целевая операция отвечает status/body, прочие — scoring."""
    proxy = scoring_transport()

    def handle(request):
        if OPERATIONS.get(request.url.path) == operation:
            return httpx.Response(status, json=body, request=request)
        return proxy.handle_request(request)

    return handle


def dataset_error(code):
    return {"error": {"code": code, "message": "synthetic rejection"}}


# --- 1. Эхо snapshot_id ---------------------------------------------------


@pytest.mark.parametrize("operation", ("parse_dataset", "score_city"))
def test_foreign_snapshot_in_well_formed_200_is_scoring_failure(
    dataset_settings, isolated_execution_log, operation
):
    foreign = foreign_snapshot_id()
    assert foreign != http_cases.canonical_snapshot_id(http_cases.synthetic_raw())

    def replace_snapshot(body):
        return {**body, "snapshot_id": foreign}

    response, operations = call_public(
        dataset_settings, rewrite_operation(operation, replace_snapshot)
    )

    http_cases.assert_error(response, 503, "scoring_unavailable")
    assert operations[-1] == operation
    failed = with_marker(isolated_execution_log, "SCORING_REQUEST_FAILED")
    assert len(failed) == 1, failed
    level, data = failed[0]
    assert level == "ERROR"
    assert data["service"] == "api"
    assert data["operation"] == operation
    assert data["reason"] == "snapshot_mismatch"
    assert_status_field(data, 200)
    completed = with_marker(isolated_execution_log, "SCORING_REQUEST_COMPLETED")
    assert operation not in [data["operation"] for _, data in completed]
    assert with_marker(isolated_execution_log, "SNAPSHOT_READY") == []
    assert_no_dataset_content(isolated_execution_log)


# --- 3. Код отказа набора в журнале api -----------------------------------


def dataset_failure(code):
    """Набор и схема, на которых настоящий scoring отвечает 422 с code."""
    raw = http_cases.synthetic_raw()
    schema = http_cases.SCHEMA
    if code == "schema_invalid":
        schema = {"type": "unknown"}
    elif code == "dataset_invalid":
        raw["unexpected"] = True
    else:
        raw["coverage"]["hot_water"] = "incomplete"
    return raw, schema


@pytest.mark.parametrize("code", DATASET_CODES)
def test_real_scoring_rejection_code_reaches_snapshot_load_failed(
    dataset_settings, isolated_execution_log, code
):
    raw, schema = dataset_failure(code)
    http_cases.write_json(dataset_settings.dataset_path, raw)
    http_cases.write_json(dataset_settings.schema_path, schema)

    response, operations = call_public(
        dataset_settings, scoring_transport().handle_request
    )

    http_cases.assert_error(response, 503, "dataset_unavailable")
    assert operations
    failed = with_marker(isolated_execution_log, "SNAPSHOT_LOAD_FAILED")
    assert [data["reason"] for _, data in failed] == [code]
    assert_no_dataset_content(isolated_execution_log, scoring_log_path())


@pytest.mark.parametrize("operation", ("parse_dataset", "score_city"))
@pytest.mark.parametrize("code", DATASET_CODES)
def test_any_operation_rejection_code_reaches_snapshot_load_failed(
    dataset_settings, isolated_execution_log, operation, code
):
    response, operations = call_public(
        dataset_settings, reject_operation(operation, 422, dataset_error(code))
    )

    http_cases.assert_error(response, 503, "dataset_unavailable")
    assert operations[-1] == operation
    failed = with_marker(isolated_execution_log, "SNAPSHOT_LOAD_FAILED")
    assert [data["reason"] for _, data in failed] == [code]


# --- 4. Отказ набора — не сбой транспорта ---------------------------------


@pytest.mark.parametrize("operation", ("parse_dataset", "score_city"))
@pytest.mark.parametrize("code", DATASET_CODES)
def test_dataset_rejection_is_one_warning_not_request_failure(
    dataset_settings, isolated_execution_log, operation, code
):
    response, operations = call_public(
        dataset_settings, reject_operation(operation, 422, dataset_error(code))
    )

    http_cases.assert_error(response, 503, "dataset_unavailable")
    assert operations[-1] == operation
    rejected = with_marker(isolated_execution_log, "SCORING_DATASET_REJECTED")
    assert len(rejected) == 1, rejected
    level, data = rejected[0]
    assert level == "WARNING"
    assert data["service"] == "api"
    assert data["operation"] == operation
    assert_status_field(data, 422)
    assert data["code"] == code
    assert with_marker(isolated_execution_log, "SCORING_REQUEST_FAILED") == []
    assert_no_dataset_content(isolated_execution_log)


@pytest.mark.parametrize("code", DATASET_CODES)
def test_real_scoring_rejection_logs_dataset_rejected_on_api(
    dataset_settings, isolated_execution_log, code
):
    raw, schema = dataset_failure(code)
    http_cases.write_json(dataset_settings.dataset_path, raw)
    http_cases.write_json(dataset_settings.schema_path, schema)

    response, operations = call_public(
        dataset_settings, scoring_transport().handle_request
    )

    http_cases.assert_error(response, 503, "dataset_unavailable")
    rejected = with_marker(isolated_execution_log, "SCORING_DATASET_REJECTED")
    assert [
        (level, data["operation"], data["status"], data["code"])
        for level, data in rejected
    ] == [("WARNING", operations[-1], 422, code)]
    assert with_marker(isolated_execution_log, "SCORING_REQUEST_FAILED") == []


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(dataset_error("not_a_dataset_code"), id="unknown-code"),
        pytest.param({"unexpected": True}, id="malformed-error-body"),
    ],
)
def test_unrecognized_422_stays_protocol_failure(
    dataset_settings, isolated_execution_log, body
):
    response, operations = call_public(
        dataset_settings, reject_operation("parse_dataset", 422, body)
    )

    http_cases.assert_error(response, 503, "scoring_unavailable")
    failed = with_marker(isolated_execution_log, "SCORING_REQUEST_FAILED")
    assert [
        (level, data["operation"], data["reason"], data["status"])
        for level, data in failed
    ] == [("ERROR", "parse_dataset", "invalid_response", 422)]
    assert with_marker(isolated_execution_log, "SCORING_DATASET_REJECTED") == []


# --- 5. Неожиданное исключение в операции scoring -------------------------


def replace_function(monkeypatch, original, replacement):
    """Подменить функцию во всех загруженных проектных модулях; число подмен."""
    replaced = 0
    for name, module in list(sys.modules.items()):
        if module is None or name.split(".")[0] not in PROJECT_PACKAGES:
            continue
        for attribute, value in list(vars(module).items()):
            if value is original:
                monkeypatch.setattr(module, attribute, replacement)
                replaced += 1
    return replaced


@pytest.mark.parametrize(
    ("url", "original"),
    [
        pytest.param(http_cases.PARSE_URL, parse_dataset, id="parse_dataset"),
        pytest.param(http_cases.SCORE_URL, score_city, id="score_city"),
    ],
)
def test_unexpected_operation_error_is_internal_error_with_one_event(
    monkeypatch, isolated_execution_log, url, original
):
    calls = []

    def broken(*args, **kwargs):
        calls.append(original.__name__)
        # Текст исключения несёт фрагменты набора: в ответ и журнал он не попадает.
        raise RuntimeError("synthetic failure Синтетическая example.test")

    assert replace_function(monkeypatch, original, broken) > 0
    raw = http_cases.synthetic_raw()

    with TestClient(scoring_app, raise_server_exceptions=False) as client:
        response = client.post(url, json=http_cases.envelope(raw))

    assert calls, "substituted computation was not called"
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json"), (
        response.text
    )
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == "internal_error"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert "Синтетическая" not in response.text
    assert "example.test" not in response.text
    failed = with_marker(isolated_execution_log, "SCORING_OPERATION_FAILED")
    assert len(failed) == 1, failed
    level, data = failed[0]
    assert level == "ERROR"
    assert data["service"] == "scoring"
    assert data["operation"] == OPERATIONS[url]
    assert data["error_type"] == "RuntimeError"
    assert with_marker(isolated_execution_log, "SCORING_OPERATION_COMPLETED") == []
    assert with_marker(isolated_execution_log, "SCORING_OPERATION_REJECTED") == []
    assert_no_dataset_content(isolated_execution_log)


# --- 6. Согласованность домов parse_dataset и score_city ------------------


def drop_house(body):
    ratings = dict(body["ratings"])
    ratings.pop("house_000020")
    return {**body, "ratings": ratings}


def foreign_house(body):
    ratings = dict(body["ratings"])
    ratings["house_000099"] = ratings.pop("house_000020")
    return {**body, "ratings": ratings}


def extra_house(body):
    ratings = dict(body["ratings"])
    ratings["house_000099"] = ratings["house_000020"]
    return {**body, "ratings": ratings}


@pytest.mark.parametrize("url", ("/api/houses", "/api/ready"))
@pytest.mark.parametrize(
    "rewrite",
    [
        pytest.param(drop_house, id="19-houses"),
        pytest.param(foreign_house, id="foreign-house-id"),
        pytest.param(extra_house, id="21-houses"),
    ],
)
def test_score_city_houses_must_equal_parsed_houses(
    dataset_settings, isolated_execution_log, url, rewrite
):
    response, operations = call_public(
        dataset_settings, rewrite_operation("score_city", rewrite), url
    )

    http_cases.assert_error(response, 503, "scoring_unavailable")
    assert "score_city" in operations
    failed = with_marker(isolated_execution_log, "SNAPSHOT_LOAD_FAILED")
    assert [data["reason"] for _, data in failed] == ["scoring_inconsistent"]
    assert with_marker(isolated_execution_log, "SNAPSHOT_READY") == []


# --- 9. Владение клиентом scoring -----------------------------------------


@pytest.fixture
def client_registry(monkeypatch):
    """Учёт созданных и закрытых ScoringClient через публичный класс.

    Клиент без transport получает in-process scoring вместо сети.
    """
    created, closed = [], []
    original_init = ScoringClient.__init__
    original_close = ScoringClient.close

    def init(self, *args, **kwargs):
        created.append(self)
        if kwargs.get("transport") is None and len(args) < 2:
            kwargs["transport"] = scoring_transport()
        original_init(self, *args, **kwargs)

    def close(self):
        closed.append(self)
        original_close(self)

    monkeypatch.setattr(ScoringClient, "__init__", init)
    monkeypatch.setattr(ScoringClient, "close", close)
    return created, closed


def test_app_owned_scoring_client_is_closed_on_shutdown(
    dataset_settings, client_registry
):
    created, closed = client_registry

    with TestClient(create_app(dataset_settings)) as public:
        assert public.get("/api/houses").status_code == 200
        assert len(created) >= 1, "app did not build its own scoring client"

    assert all(any(item is client for item in closed) for client in created), (
        "app-owned scoring client is not closed when lifespan ends"
    )


def test_injected_scoring_client_is_not_closed_by_app(
    dataset_settings, client_registry
):
    created, closed = client_registry
    injected = ScoringClient(base_url="http://scoring")

    try:
        app = create_app(dataset_settings, scoring_client=injected)
        with TestClient(app) as public:
            assert public.get("/api/houses").status_code == 200

        assert created == [injected]
        assert all(item is not injected for item in closed)
    finally:
        ScoringClient.close(injected)


# --- 10a. Заголовок X-DomDossier-Error у ошибок публичного api -------------


def assert_error_header(response, status, code):
    http_cases.assert_error(response, status, code)
    assert response.headers.get(ERROR_HEADER) == code, dict(response.headers)


def test_missing_dataset_ready_carries_error_header(tmp_path):
    missing = tmp_path / "missing.json"
    settings = Settings(dataset_path=missing, schema_path=missing)
    client = ScoringClient(base_url="http://scoring", transport=scoring_transport())

    with TestClient(create_app(settings, scoring_client=client)) as public:
        assert_error_header(public.get("/api/ready"), 503, "dataset_unavailable")
        assert_error_header(public.get("/api/houses"), 503, "dataset_unavailable")


@pytest.mark.parametrize("code", DATASET_CODES)
def test_scoring_422_ready_carries_dataset_unavailable_header(
    dataset_settings, code
):
    raw, schema = dataset_failure(code)
    http_cases.write_json(dataset_settings.dataset_path, raw)
    http_cases.write_json(dataset_settings.schema_path, schema)

    response, _ = call_public(
        dataset_settings, scoring_transport().handle_request, "/api/ready"
    )

    assert_error_header(response, 503, "dataset_unavailable")


def test_unavailable_scoring_ready_carries_scoring_unavailable_header(
    dataset_settings,
):
    def refused(request):
        raise httpx.ConnectError("synthetic refused", request=request)

    response, _ = call_public(dataset_settings, refused, "/api/ready")

    assert_error_header(response, 503, "scoring_unavailable")


def test_client_errors_carry_their_code_header(dataset_settings):
    client = ScoringClient(base_url="http://scoring", transport=scoring_transport())

    with TestClient(create_app(dataset_settings, scoring_client=client)) as public:
        assert_error_header(
            public.get("/api/houses/house_999999"), 404, "house_not_found"
        )
        assert_error_header(
            public.get("/api/houses/not-a-house"), 422, "invalid_request"
        )


def test_unhandled_error_carries_internal_error_header(
    dataset_settings, monkeypatch
):
    def broken(self):
        raise RuntimeError("synthetic unhandled failure")

    monkeypatch.setattr(UtilityRatingService, "load_snapshot", broken)
    client = ScoringClient(base_url="http://scoring", transport=scoring_transport())
    app = create_app(dataset_settings, scoring_client=client)

    with TestClient(app, raise_server_exceptions=False) as public:
        response = public.get("/api/ready")

    assert_error_header(response, 500, "internal_error")


def test_successful_ready_has_no_error_header(dataset_settings):
    client = ScoringClient(base_url="http://scoring", transport=scoring_transport())

    with TestClient(create_app(dataset_settings, scoring_client=client)) as public:
        response = public.get("/api/ready")

    assert response.status_code == 200
    assert ERROR_HEADER not in response.headers
