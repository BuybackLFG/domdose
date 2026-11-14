"""Read-only API against the committed canonical dataset."""

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.dataset import _safe_url, get_dataset
from app.main import app

client = TestClient(app)


def test_search_and_dossier_use_dataset() -> None:
    assert client.get("/api/ready").status_code == 200
    result = client.get("/api/houses", params={"q": "  КОВАЛЬЧУКА  "}).json()
    assert result["query"] == "ковальчука"
    assert any(item["id"] == "h-01" for item in result["items"])
    response = client.get("/api/houses/h-01")
    assert response.status_code == 200
    body = response.json()
    assert body["house"]["address"] == "ул. Ковальчука, 26"
    assert body["house"]["avariy"] is None and body["house"]["caprepair"] is None
    assert body["house"]["year"] is None and body["facts"] == []
    assert body["index"] is None
    assert body["rating"]["houses"][0]["overall"] is None
    assert body["rating"]["houses"][0]["state"] == "unavailable"
    assert body["rating"]["source_spans"] and body["rating"]["limitations"]
    assert body["sources"] and body["events"] and body["checklist"]
    assert all(event["source_url"].startswith("https://") for event in body["events"])
    assert all(event["confidence"] is None for event in body["events"])
    assert client.get("/api/houses/missing").status_code == 404


def test_readiness_reports_missing_and_invalid_data(tmp_path, monkeypatch) -> None:
    for path in (tmp_path / "missing.json", tmp_path / "invalid.json"):
        if path.name == "invalid.json":
            path.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("DATASET_PATH", str(path))
        get_settings.cache_clear()
        get_dataset.cache_clear()
        response = client.get("/api/ready")
        assert response.status_code == 503
        assert "датасет" in response.json()["detail"].lower()
    monkeypatch.delenv("DATASET_PATH")
    get_settings.cache_clear()
    get_dataset.cache_clear()


def test_source_url_validation() -> None:
    assert _safe_url("https://www.vl.ru/off/")
    for url in (
        "https://user@example.com/",
        "https:///path",
        "javascript:alert(1)",
        "https://example.com:bad/",
        "https://bad host/",
    ):
        assert not _safe_url(url)
