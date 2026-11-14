"""Synthetic data only; no real dataset or network resources."""

import copy

import pytest

DISTRICTS = ("Ленинский", "Первомайский", "Первореченский", "Советский", "Фрунзенский")


def synthetic_dataset():
    return {
        "meta": {
            "schema_version": "1.0",
            "city": "Владивосток",
            "timezone": "Asia/Vladivostok",
            "period": {"from": "2026-09-01", "to": "2026-11-13"},
            "heating_season_start": None,
            "generated_at": "2026-11-13T18:00:00+10:00",
            "city_houses": {
                "total": 10,
                "by_district": dict.fromkeys(DISTRICTS),
                "source_url": None,
            },
            "sources": [
                {
                    "id": "synthetic-source",
                    "name": "Synthetic",
                    "url": "https://example.invalid/source",
                    "types": ["electricity"],
                    "covered_from": "2026-09-01",
                    "covered_to": "2026-11-13",
                }
            ],
            "limitations": ["Synthetic test fixture, not observations"],
        },
        "houses": [
            {
                "id": "synthetic-house",
                "address": "Synthetic address",
                "district": "Советский",
                "fias_id": None,
                "lat": None,
                "lon": None,
                "year_built": None,
                "floors": 0,
                "apartments": None,
                "management_company": None,
                "services": dict.fromkeys(
                    ("hot_water", "cold_water", "electricity", "heating"), "unknown"
                ),
                "is_control": False,
                "passport_source_url": None,
            }
        ],
        "events": [
            {
                "id": "synthetic-event",
                "type": "electricity",
                "kind": "unknown",
                "start": "2026-10-03T21:30:00+10:00",
                "end_planned": "2026-10-04T00:30:00+10:00",
                "end_actual": "2026-10-04T01:30:00+10:00",
                "duration_hours": 4.0,
                "duration_basis": "actual",
                "cause": None,
                "organization": None,
                "scope": "house",
                "force_majeure": False,
                "houses_affected": 1,
                "districts": ["Советский"],
                "addresses_raw": "Synthetic address",
                "addresses": ["Synthetic address"],
                "houses": [{"house_id": "synthetic-house", "match": "exact"}],
                "sources": [
                    {
                        "source_id": "synthetic-source",
                        "url": "https://example.invalid/event",
                        "published_at": None,
                    }
                ],
                "notes": None,
            }
        ],
    }


@pytest.fixture
def data():
    return copy.deepcopy(synthetic_dataset())


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    # BaseSettings may consult environment; never depend on the host's configuration.
    import os

    for key in tuple(os.environ):
        if key.upper() in {"LOG_LEVEL", "LOG_FILE"}:
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    return tmp_path
