import ast
import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.scoring_main import app as scoring_app
from core.config import Settings
from scoring_harness import scoring_transport
from sources.scoring_client import ScoringClient

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "dataset" / "utility-rating-dataset.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
CATEGORIES = ("hot_water", "cold_water", "electricity", "heating")
METRICS = ("frequency", "hours", "longest")
WINDOW_START = "2026-01-01T00:00:00+10:00"
WINDOW_END = "2026-01-31T00:00:00+10:00"
TARGET = "house_000001"
PARSE_URL = "/internal/v1/parse_dataset"
SCORE_URL = "/internal/v1/score_city"


def make_houses(count=20):
    return [
        {
            "house_id": f"house_{index:06d}",
            "address": f"Владивосток, улица Синтетическая {index:02d}, 1",
        }
        for index in range(1, count + 1)
    ]


def synthetic_raw():
    return {
        "schema_version": "1.0.0",
        "city": "Владивосток",
        "window": {"start": WINDOW_START, "end": WINDOW_END},
        "registry_source_url": "https://example.test/synthetic/registry",
        "registry_complete": True,
        "houses": make_houses(),
        "coverage": {category: "complete" for category in CATEGORIES},
        "events": [
            {
                "house_id": TARGET,
                "category": "electricity",
                "started_at": WINDOW_START,
                "ended_at": "2026-01-01T05:00:00+10:00",
                "kind": "emergency",
                "is_mass": False,
                "is_natural_disaster": False,
                "source_url": "https://example.test/synthetic/emergency-5h",
            },
            {
                "house_id": TARGET,
                "category": "electricity",
                "started_at": "2026-01-02T00:00:00+10:00",
                "ended_at": "2026-01-02T10:00:00+10:00",
                "kind": "planned",
                "is_mass": False,
                "is_natural_disaster": False,
                "source_url": "https://example.test/synthetic/planned-10h",
            },
        ],
    }


def ordered_events_raw():
    raw = synthetic_raw()
    raw["events"] = [
        {
            "house_id": TARGET,
            "category": "hot_water",
            "started_at": "2026-01-04T00:00:00+10:00",
            "ended_at": "2026-01-04T05:00:00+10:00",
            "kind": "emergency",
            "is_mass": False,
            "is_natural_disaster": False,
            "source_url": "https://example.test/synthetic/hot",
        },
        {
            "house_id": TARGET,
            "category": "cold_water",
            "started_at": "2026-01-03T00:00:00+10:00",
            "ended_at": "2026-01-03T05:00:00+10:00",
            "kind": "emergency",
            "is_mass": False,
            "is_natural_disaster": False,
            "source_url": "https://example.test/synthetic/cold-early-end",
        },
        {
            "house_id": TARGET,
            "category": "cold_water",
            "started_at": "2026-01-03T00:00:00+10:00",
            "ended_at": "2026-01-03T06:00:00+10:00",
            "kind": "emergency",
            "is_mass": False,
            "is_natural_disaster": False,
            "source_url": "https://example.test/synthetic/cold-source-a",
        },
        {
            "house_id": TARGET,
            "category": "cold_water",
            "started_at": "2026-01-03T00:00:00+10:00",
            "ended_at": "2026-01-03T06:00:00+10:00",
            "kind": "planned",
            "is_mass": False,
            "is_natural_disaster": False,
            "source_url": "https://example.test/synthetic/cold-source-c",
        },
        {
            "house_id": TARGET,
            "category": "electricity",
            "started_at": "2026-01-03T00:00:00+10:00",
            "ended_at": "2026-01-03T05:00:00+10:00",
            "kind": "emergency",
            "is_mass": False,
            "is_natural_disaster": False,
            "source_url": "https://example.test/synthetic/electricity-ended",
        },
        {
            "house_id": TARGET,
            "category": "electricity",
            "started_at": "2026-01-03T00:00:00+10:00",
            "ended_at": None,
            "kind": "emergency",
            "is_mass": False,
            "is_natural_disaster": False,
            "source_url": "https://example.test/synthetic/electricity-ongoing",
        },
        {
            "house_id": TARGET,
            "category": "heating",
            "started_at": "2026-01-02T00:00:00+10:00",
            "ended_at": "2026-01-02T05:00:00+10:00",
            "kind": "emergency",
            "is_mass": False,
            "is_natural_disaster": False,
            "source_url": "https://example.test/synthetic/heating",
        },
    ]
    return raw


def canonical_snapshot_id(raw, schema=SCHEMA):
    canonical = json.dumps(
        {"dataset": raw, "schema": schema},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def envelope(raw, schema=SCHEMA, snapshot_id=None):
    return {
        "dataset": raw,
        "schema": schema,
        "snapshot_id": canonical_snapshot_id(raw, schema)
        if snapshot_id is None
        else snapshot_id,
    }


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )


@pytest.fixture
def internal_client():
    with TestClient(scoring_app) as client:
        yield client


@pytest.fixture
def dataset_settings(tmp_path):
    dataset_path = tmp_path / "synthetic-dataset.json"
    schema_path = tmp_path / "synthetic-schema.json"
    write_json(dataset_path, synthetic_raw())
    write_json(schema_path, SCHEMA)
    return Settings(dataset_path=dataset_path, schema_path=schema_path)


def make_public_app(settings, transport):
    scoring_client = ScoringClient(
        base_url="http://scoring", transport=transport
    )
    return create_app(settings, scoring_client=scoring_client)


@pytest.fixture
def public_client(dataset_settings):
    transport = scoring_transport(scoring_app)
    with TestClient(make_public_app(dataset_settings, transport)) as client:
        yield client


def test_health_and_readiness_are_separate_and_stateless(internal_client):
    health = internal_client.get("/health")
    ready = internal_client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_parse_returns_canonical_snapshot_and_normalized_sourced_events(
    internal_client,
):
    raw = synthetic_raw()
    expected_snapshot = canonical_snapshot_id(raw)

    response = internal_client.post(PARSE_URL, json=envelope(raw))

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot_id"] == expected_snapshot
    assert len(payload["snapshot_id"]) == 64
    assert payload["dataset"]["window"] == raw["window"]
    assert payload["dataset"]["houses"] == raw["houses"]
    assert payload["dataset"]["events"] == raw["events"]
    assert [event["source_url"] for event in payload["dataset"]["events"]] == [
        "https://example.test/synthetic/emergency-5h",
        "https://example.test/synthetic/planned-10h",
    ]


def test_score_city_independent_twenty_house_golden(internal_client):
    raw = synthetic_raw()

    response = internal_client.post(SCORE_URL, json=envelope(raw))

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot_id"] == canonical_snapshot_id(raw)
    ratings = payload["ratings"]
    assert set(ratings) == {f"house_{index:06d}" for index in range(1, 21)}
    target = ratings[TARGET]
    assert target["overall_score"] == pytest.approx(0.5722911990971438)
    assert tuple(target["categories"]) == CATEGORIES
    electricity = target["categories"]["electricity"]
    # Для 20 домов средние равны (0.07, 0.45, 0.25); приор равен 1.
    assert electricity["metrics"] == {
        "frequency": 1.4,
        "hours": 9.0,
        "longest": 5.0,
    }
    assert electricity["penalties"] == pytest.approx({
        "frequency": math.log2(2.4 / 1.07) / 3,
        "hours": math.log2(10 / 1.45) / 3,
        "longest": math.log2(6 / 1.25) / 3,
    })
    assert electricity["score"] == pytest.approx(0.3222911990971438)
    for category, detail in target["categories"].items():
        assert set(detail["metrics"]) == set(METRICS)
        assert set(detail["penalties"]) == set(METRICS)
        if category != "electricity":
            assert detail["metrics"] == {name: 0.0 for name in METRICS}
            assert detail["penalties"] == {name: 0.0 for name in METRICS}
            assert detail["score"] == 1.0
    for house_id, rating in ratings.items():
        if house_id != TARGET:
            assert rating["overall_score"] == 1.0
            assert all(
                category["score"] == 1.0
                for category in rating["categories"].values()
            )


def test_complete_empty_events_are_valid_and_score_all_ones(internal_client):
    raw = synthetic_raw()
    raw["events"] = []

    parsed = internal_client.post(PARSE_URL, json=envelope(raw))
    scored = internal_client.post(SCORE_URL, json=envelope(raw))

    assert parsed.status_code == 200
    assert parsed.json()["dataset"]["events"] == []
    assert scored.status_code == 200
    assert len(scored.json()["ratings"]) == 20
    for rating in scored.json()["ratings"].values():
        assert rating["overall_score"] == 1.0
        for category in rating["categories"].values():
            assert category["metrics"] == {name: 0.0 for name in METRICS}
            assert category["penalties"] == {name: 0.0 for name in METRICS}
            assert category["score"] == 1.0


def test_invalid_schema_has_distinct_422_error(internal_client):
    raw = synthetic_raw()
    schema = {"type": "unknown"}

    response = internal_client.post(PARSE_URL, json=envelope(raw, schema))

    assert_error(response, 422, "schema_invalid")


def test_schema_mismatch_is_dataset_invalid_422(internal_client):
    raw = synthetic_raw()
    raw["unexpected"] = "not allowed"

    response = internal_client.post(PARSE_URL, json=envelope(raw))

    assert_error(response, 422, "dataset_invalid")


@pytest.mark.parametrize("failure", ("registry", "coverage", "19-houses"))
def test_complete_schema_but_unscoreable_dataset_is_incomplete_422(
    internal_client, failure
):
    raw = synthetic_raw()
    if failure == "registry":
        raw["registry_complete"] = False
        raw["houses"] = []
        raw["events"] = []
        raw["coverage"] = {category: "incomplete" for category in CATEGORIES}
    elif failure == "coverage":
        raw["coverage"]["heating"] = "incomplete"
    else:
        raw["houses"] = make_houses(19)

    response = internal_client.post(PARSE_URL, json=envelope(raw))

    assert_error(response, 422, "dataset_incomplete")


@pytest.mark.parametrize("url", (PARSE_URL, SCORE_URL))
def test_snapshot_mismatch_is_409_on_both_operations(internal_client, url):
    raw = synthetic_raw()

    response = internal_client.post(url, json=envelope(raw, snapshot_id="0" * 64))

    assert_error(response, 409, "snapshot_mismatch")


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(None, id="null"),
        pytest.param([], id="array"),
        pytest.param({}, id="empty-envelope"),
        pytest.param({"dataset": {}, "schema": {}}, id="missing-snapshot"),
        pytest.param(
            {"dataset": {}, "schema": {}, "snapshot_id": "bad"},
            id="bad-snapshot-format",
        ),
    ],
)
def test_invalid_envelope_is_400_not_dataset_failure(internal_client, body):
    response = internal_client.post(PARSE_URL, json=body)

    assert_error(response, 400, "invalid_envelope")


def test_unknown_envelope_field_and_malformed_json_are_400(internal_client):
    raw = synthetic_raw()
    extra = envelope(raw)
    extra["unexpected"] = True

    extra_response = internal_client.post(PARSE_URL, json=extra)
    malformed_response = internal_client.post(
        PARSE_URL, content=b"{", headers={"content-type": "application/json"}
    )

    assert_error(extra_response, 400, "invalid_envelope")
    assert_error(malformed_response, 400, "invalid_envelope")


def test_public_detail_adds_events_and_weakest_without_replacing_old_fields(
    public_client,
):
    response = public_client.get(f"/api/houses/{TARGET}")

    assert response.status_code == 200
    payload = response.json()
    assert {
        "scope",
        "window",
        "house_id",
        "address",
        "overall_score",
        "categories",
        "events",
        "weakest",
    } <= set(payload)
    assert payload["overall_score"] == pytest.approx(0.5722911990971438)
    assert payload["weakest"] == "electricity"
    assert [event["source_url"] for event in payload["events"]] == [
        "https://example.test/synthetic/planned-10h",
        "https://example.test/synthetic/emergency-5h",
    ]
    for event in payload["events"]:
        assert set(event) == {
            "house_id",
            "category",
            "started_at",
            "ended_at",
            "kind",
            "is_mass",
            "is_natural_disaster",
            "source_url",
        }


def test_public_events_global_order_and_weakest_tie_break(
    public_client, dataset_settings
):
    raw = ordered_events_raw()
    write_json(dataset_settings.dataset_path, raw)

    response = public_client.get(f"/api/houses/{TARGET}")

    assert response.status_code == 200
    payload = response.json()
    actual_order = [
        (
            event["started_at"],
            event["category"],
            event["ended_at"],
            event["source_url"],
        )
        for event in payload["events"]
    ]
    expected_order = [
        (
            "2026-01-04T00:00:00+10:00",
            "hot_water",
            "2026-01-04T05:00:00+10:00",
            "https://example.test/synthetic/hot",
        ),
        (
            "2026-01-03T00:00:00+10:00",
            "cold_water",
            "2026-01-03T05:00:00+10:00",
            "https://example.test/synthetic/cold-early-end",
        ),
        (
            "2026-01-03T00:00:00+10:00",
            "cold_water",
            "2026-01-03T06:00:00+10:00",
            "https://example.test/synthetic/cold-source-a",
        ),
        (
            "2026-01-03T00:00:00+10:00",
            "cold_water",
            "2026-01-03T06:00:00+10:00",
            "https://example.test/synthetic/cold-source-c",
        ),
        (
            "2026-01-03T00:00:00+10:00",
            "electricity",
            "2026-01-03T05:00:00+10:00",
            "https://example.test/synthetic/electricity-ended",
        ),
        (
            "2026-01-03T00:00:00+10:00",
            "electricity",
            None,
            "https://example.test/synthetic/electricity-ongoing",
        ),
        (
            "2026-01-02T00:00:00+10:00",
            "heating",
            "2026-01-02T05:00:00+10:00",
            "https://example.test/synthetic/heating",
        ),
    ]
    assert actual_order == expected_order
    assert payload["categories"]["hot_water"]["score"] == payload["categories"]["heating"]["score"]
    assert payload["categories"]["electricity"]["score"] < payload["categories"]["hot_water"]["score"]
    assert payload["weakest"] == "electricity"


def test_scoring_client_disables_environment_redirects_and_sets_all_timeouts():
    client = ScoringClient(
        base_url="http://scoring",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    try:
        http_client = client._client
        assert http_client.trust_env is False
        assert http_client.follow_redirects is False
        for name in ("connect", "read", "write", "pool"):
            value = getattr(http_client.timeout, name)
            assert value is not None
            assert math.isfinite(value)
            assert value > 0
    finally:
        client.close()


@pytest.mark.parametrize("failure", ("redirect", "server-error", "timeout"))
def test_scoring_client_does_not_retry_or_hide_transport_failures(
    dataset_settings, failure
):
    requests = []

    def handle(request):
        requests.append(request)
        if failure == "redirect":
            return httpx.Response(302, headers={"location": "/ready"})
        if failure == "server-error":
            return httpx.Response(500, json={"error": {"code": "internal"}})
        raise httpx.ConnectTimeout("synthetic timeout", request=request)

    transport = httpx.MockTransport(handle)
    with TestClient(make_public_app(dataset_settings, transport)) as client:
        response = client.get("/api/houses")

    assert_error(response, 503, "scoring_unavailable")
    assert len(requests) == 1


def test_snapshot_mismatch_is_scoring_unavailable_not_dataset_unavailable(
    dataset_settings,
):
    def handle(request):
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "snapshot_mismatch",
                    "message": "synthetic mismatch",
                }
            },
            request=request,
        )

    transport = httpx.MockTransport(handle)
    with TestClient(make_public_app(dataset_settings, transport)) as client:
        response = client.get("/api/houses")

    assert_error(response, 503, "scoring_unavailable")


@pytest.mark.parametrize("failure", ("schema", "dataset", "incomplete"))
def test_scoring_dataset_errors_remain_dataset_unavailable(
    dataset_settings, failure
):
    raw = synthetic_raw()
    schema = deepcopy(SCHEMA)
    if failure == "schema":
        schema = {"type": "unknown"}
    elif failure == "dataset":
        raw["unexpected"] = True
    else:
        raw["coverage"]["hot_water"] = "incomplete"
    write_json(dataset_settings.dataset_path, raw)
    write_json(dataset_settings.schema_path, schema)
    transport = scoring_transport(scoring_app)

    with TestClient(make_public_app(dataset_settings, transport)) as client:
        response = client.get("/api/houses")

    assert_error(response, 503, "dataset_unavailable")


def test_existing_public_errors_and_liveness_are_preserved(
    public_client, dataset_settings
):
    assert public_client.get("/api/health").json() == {"status": "ok"}
    assert_error(
        public_client.get("/api/houses/house_999999"), 404, "house_not_found"
    )
    assert_error(
        public_client.get("/api/houses/not-a-house"), 422, "invalid_request"
    )

    dataset_settings.dataset_path.unlink()
    with TestClient(
        make_public_app(dataset_settings, scoring_transport(scoring_app))
    ) as missing_client:
        assert_error(missing_client.get("/api/ready"), 503, "dataset_unavailable")


def production_modules():
    for package in ("api", "contract", "core", "dossier", "sources"):
        yield from sorted((ROOT / package).rglob("*.py"))


@pytest.mark.parametrize("path", list(production_modules()), ids=lambda path: str(path))
def test_only_scoring_http_entrypoint_imports_utility_rating(path):
    if path == ROOT / "api" / "scoring_main.py":
        return
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    direct_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            direct_imports.extend(
                alias.name
                for alias in node.names
                if alias.name == "utility_rating"
                or alias.name.startswith("utility_rating.")
            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "utility_rating" or module.startswith("utility_rating."):
                direct_imports.append(module)

    assert direct_imports == [], (
        "scoring is available only through sources.ScoringClient and "
        f"api.scoring_main: {path.relative_to(ROOT)} imports {direct_imports}"
    )
