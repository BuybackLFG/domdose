import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app, create_app
from core.config import Settings

CATEGORIES = ("hot_water", "cold_water", "electricity", "heating")
METRICS = ("frequency", "hours", "longest")
WINDOW_START = "2026-01-01T00:00:00+10:00"
WINDOW_END = "2026-01-31T00:00:00+10:00"
SCHEMA_PATH = (
    Path(__file__).parent.parent / "dataset" / "utility-rating-dataset.schema.json"
)


def make_houses(count=20):
    return [
        {
            "house_id": f"house_{index:06d}",
            "address": f"Владивосток, улица Пилотная {index:02d}, 1",
        }
        for index in range(1, count + 1)
    ]


def valid_raw():
    return {
        "schema_version": "1.0.0",
        "city": "Владивосток",
        "window": {"start": WINDOW_START, "end": WINDOW_END},
        "registry_source_url": "https://example.test/registry/synthetic",
        "registry_complete": True,
        "houses": make_houses(),
        "coverage": {category: "complete" for category in CATEGORIES},
        "events": [
            {
                "house_id": "house_000001",
                "category": "electricity",
                "started_at": WINDOW_START,
                "ended_at": "2026-01-01T05:00:00+10:00",
                "kind": "emergency",
                "is_mass": False,
                "is_natural_disaster": False,
                "source_url": "https://example.test/synthetic/emergency",
            },
            {
                "house_id": "house_000001",
                "category": "electricity",
                "started_at": "2026-01-02T00:00:00+10:00",
                "ended_at": "2026-01-02T10:00:00+10:00",
                "kind": "planned",
                "is_mass": False,
                "is_natural_disaster": False,
                "source_url": "https://example.test/synthetic/planned",
            },
        ],
    }


@pytest.fixture
def paths(tmp_path):
    dataset_path = tmp_path / "synthetic-dataset.json"
    schema_path = tmp_path / "schema.json"
    schema_path.write_bytes(SCHEMA_PATH.read_bytes())
    dataset_path.write_text(
        json.dumps(valid_raw(), ensure_ascii=False, allow_nan=True), encoding="utf-8"
    )
    return dataset_path, schema_path


@pytest.fixture
def settings(paths):
    dataset_path, schema_path = paths
    return Settings(dataset_path=dataset_path, schema_path=schema_path)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=True), encoding="utf-8"
    )


def assert_error(response, status, code):
    assert response.status_code == status
    payload = response.json()
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"]


def assert_dataset_unavailable(response):
    assert_error(response, 503, "dataset_unavailable")


def test_module_app_import_and_health_do_not_require_dataset(tmp_path):
    missing = tmp_path / "missing.json"
    settings = Settings(dataset_path=missing, schema_path=missing)

    with TestClient(create_app(settings)) as local_client:
        assert local_client.get("/api/health").json() == {"status": "ok"}
    with TestClient(app) as module_client:
        response = module_client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_dataset_health_ready_list_and_detail(client, paths):
    dataset_path, _ = paths
    dataset_path.unlink()

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert_dataset_unavailable(client.get("/api/ready"))
    assert_dataset_unavailable(client.get("/api/houses"))
    assert_dataset_unavailable(client.get("/api/houses/house_000001"))


def test_ready_and_happy_list_have_pilot_scope_and_twenty_houses(client):
    ready = client.get("/api/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}

    response = client.get("/api/houses")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == {
        "kind": "pilot",
        "house_count": 20,
        "average_basis": "pilot_only",
    }
    assert payload["window"] == {"start": WINDOW_START, "end": WINDOW_END}
    assert len(payload["houses"]) == 20
    for index, house in enumerate(payload["houses"], start=1):
        assert set(house) == {"house_id", "address", "overall_score"}
        assert house["house_id"] == f"house_{index:06d}"
        assert house["address"] == f"Владивосток, улица Пилотная {index:02d}, 1"
        assert house["overall_score"] == (0.25 if index == 1 else 1.0)


def test_happy_detail_exposes_exact_metrics_penalties_and_scores(client):
    response = client.get("/api/houses/house_000001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == {
        "kind": "pilot",
        "house_count": 20,
        "average_basis": "pilot_only",
    }
    assert payload["window"] == {"start": WINDOW_START, "end": WINDOW_END}
    assert payload["house_id"] == "house_000001"
    assert payload["address"] == "Владивосток, улица Пилотная 01, 1"
    assert payload["overall_score"] == 0.25
    assert tuple(payload["categories"]) == CATEGORIES
    electricity = payload["categories"]["electricity"]
    assert electricity["metrics"] == {
        "frequency": 1.4,
        "hours": 9.0,
        "longest": 5.0,
    }
    assert electricity["penalties"] == {metric: 1.0 for metric in METRICS}
    assert electricity["score"] == 0.0
    for name, category in payload["categories"].items():
        assert set(category) == {"metrics", "penalties", "score"}
        assert set(category["metrics"]) == set(METRICS)
        assert set(category["penalties"]) == set(METRICS)
        if name != "electricity":
            assert category["metrics"] == {metric: 0.0 for metric in METRICS}
            assert category["penalties"] == {metric: 0.0 for metric in METRICS}
            assert category["score"] == 1.0


def test_complete_data_with_empty_events_returns_zero_metrics_and_all_ones(
    client, paths
):
    dataset_path, _ = paths
    raw = valid_raw()
    raw["events"] = []
    write_json(dataset_path, raw)

    response = client.get("/api/houses")

    assert response.status_code == 200
    houses = response.json()["houses"]
    assert len(houses) == 20
    assert all(house["overall_score"] == 1.0 for house in houses)
    detail = client.get("/api/houses/house_000001")
    assert detail.status_code == 200
    for category in detail.json()["categories"].values():
        assert category["metrics"] == {metric: 0.0 for metric in METRICS}
        assert category["penalties"] == {metric: 0.0 for metric in METRICS}
        assert category["score"] == 1.0


@pytest.mark.parametrize("target", ("dataset", "schema"))
@pytest.mark.parametrize("content", ("missing", "empty", "malformed"))
def test_missing_empty_or_malformed_dataset_or_schema_is_unavailable(
    paths, settings, target, content
):
    path = paths[0 if target == "dataset" else 1]
    if content == "missing":
        path.unlink()
    else:
        path.write_text("" if content == "empty" else "{not json", encoding="utf-8")

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/ready")

    assert_dataset_unavailable(response)


def test_unknown_schema_type_is_dataset_unavailable(client, paths):
    write_json(paths[1], {"type": "unknown"})

    assert_dataset_unavailable(client.get("/api/ready"))


@pytest.mark.parametrize("failure", ("registry", "category", "19", "21"))
def test_incomplete_or_wrong_size_dataset_is_unavailable(paths, settings, failure):
    raw = valid_raw()
    if failure == "registry":
        raw["registry_complete"] = False
        raw["houses"] = []
        raw["events"] = []
        raw["coverage"] = {category: "incomplete" for category in CATEGORIES}
    elif failure == "category":
        raw["coverage"]["heating"] = "incomplete"
    else:
        raw["houses"] = make_houses(int(failure))
    write_json(paths[0], raw)

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/houses")

    assert_dataset_unavailable(response)


def test_house_errors_distinguish_not_found_invalid_format_and_unavailable(
    client, paths
):
    assert_error(client.get("/api/houses/house_999999"), 404, "house_not_found")
    assert_error(client.get("/api/houses/not-a-house"), 422, "invalid_request")

    paths[0].unlink()
    unavailable_settings = Settings(dataset_path=paths[0], schema_path=paths[1])
    with TestClient(create_app(unavailable_settings)) as unavailable_client:
        assert_dataset_unavailable(unavailable_client.get("/api/houses/house_999999"))
        assert_dataset_unavailable(unavailable_client.get("/api/houses/not-a-house"))


def test_failed_load_is_not_cached_and_recovers_after_file_fix(client, paths):
    paths[0].unlink()
    assert_dataset_unavailable(client.get("/api/ready"))
    assert_dataset_unavailable(client.get("/api/houses"))

    write_json(paths[0], valid_raw())

    assert client.get("/api/ready").json() == {"status": "ready"}
    assert client.get("/api/houses").status_code == 200


def test_successful_snapshot_is_cached_until_new_app(client, paths, settings):
    original = client.get("/api/houses/house_000001")
    assert original.status_code == 200

    paths[0].unlink()
    paths[1].unlink()

    cached = client.get("/api/houses/house_000001")
    assert cached.status_code == 200
    assert cached.json() == original.json()
    assert client.get("/api/ready").json() == {"status": "ready"}

    with TestClient(create_app(settings)) as new_client:
        assert_dataset_unavailable(new_client.get("/api/ready"))


@pytest.mark.parametrize("failure", ("timestamp", "nan"))
def test_invalid_timestamp_or_nan_temporal_input_is_unavailable(
    paths, settings, failure
):
    raw = valid_raw()
    if failure == "timestamp":
        raw["window"]["start"] = "2026-01-32T00:00:00+10:00"
    else:
        raw["window"]["start"] = float("nan")
    write_json(paths[0], raw)

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/ready")

    assert_dataset_unavailable(response)
