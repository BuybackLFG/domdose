"""Независимый контракт централизованного логирования и run-артефактов."""

import ast
import importlib
import json
import logging
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import test_api_utility_rating as api_cases
import test_legacy_dataset_adapter as legacy_cases
from core.logging import (
    LoggingSettings,
    append_test_result,
    create_run_directory,
    get_logger,
    load_logging_settings,
    mark_not_run,
    service_execution_log,
    setup_logging,
    shutdown_logging,
    write_env_snapshot,
)

REPO_ROOT = Path(__file__).parent.parent
LINE_RE = re.compile(
    r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)\] "
    r"\[(?P<level>[A-Z]+)\] \[(?P<module>[^]]+)\] "
    r"\[(?P<marker>[A-Z][A-Z0-9_]{1,63})\] (?P<message>.*) \| "
    r"data=(?P<data>\{.*\})$"
)


@pytest.fixture(autouse=True)
def isolated_logging():
    shutdown_logging()
    yield
    shutdown_logging()


def configure(service: str, path: Path, *, stdout: bool = False) -> LoggingSettings:
    settings = LoggingSettings(service=service, file_path=path, stdout=stdout)
    setup_logging(settings)
    return settings


def events(path: Path) -> list[tuple[str, dict]]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = LINE_RE.fullmatch(line)
        assert match is not None, line
        result.append((match["marker"], json.loads(match["data"])))
    return result


def event(path: Path, marker: str) -> dict:
    matches = [data for found, data in events(path) if found == marker]
    assert len(matches) == 1, (marker, matches)
    return matches[0]


def api_settings(tmp_path: Path, raw: dict | None = None):
    dataset_path = tmp_path / "synthetic-dataset.json"
    schema_path = tmp_path / "schema.json"
    schema_path.write_bytes(api_cases.SCHEMA_PATH.read_bytes())
    dataset_path.write_text(
        json.dumps(raw or api_cases.valid_raw(), ensure_ascii=False),
        encoding="utf-8",
    )
    return api_cases.Settings(dataset_path=dataset_path, schema_path=schema_path)


def test_exact_format_json_service_file_and_stdout(tmp_path, capsys):
    path = tmp_path / "execution.log"
    configure("api", path, stdout=True)

    get_logger("dossier.service", service="api").info(
        "SNAPSHOT_READY", "snapshot ready", house_count=20, event_count=0
    )

    line = path.read_text(encoding="utf-8").strip()
    match = LINE_RE.fullmatch(line)
    assert match is not None
    assert match["level"] == "INFO"
    assert match["module"] == "dossier.service"
    assert match["marker"] == "SNAPSHOT_READY"
    assert json.loads(match["data"]) == {
        "service": "api",
        "house_count": 20,
        "event_count": 0,
    }
    captured = capsys.readouterr()
    assert captured.out.strip() == line
    assert captured.err == ""


def test_stdout_can_be_disabled_without_disabling_file(tmp_path, capsys):
    path = tmp_path / "execution.log"
    configure("api", path)
    get_logger("api.routes", service="api").info("API_READY", "ready", house_count=20)

    assert event(path, "API_READY") == {"service": "api", "house_count": 20}
    assert capsys.readouterr().out == ""


def test_setup_is_idempotent_and_conflicting_file_is_rejected(tmp_path):
    path = tmp_path / "execution.log"
    settings = configure("api", path)
    setup_logging(settings)
    first = get_logger("dossier.service", service="api")
    second = get_logger("dossier.service", service="api")

    first.info("SNAPSHOT_CACHE_HIT", "cache hit", cache_state="hit")
    second.info("SNAPSHOT_CACHE_HIT", "cache hit", cache_state="hit")

    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    with pytest.raises(RuntimeError):
        setup_logging(
            LoggingSettings(
                service="api", file_path=tmp_path / "other.log", stdout=False
            )
        )


def test_services_are_split_and_root_and_uvicorn_are_untouched(tmp_path):
    root = logging.getLogger()
    uvicorn = logging.getLogger("uvicorn")
    before = (root.level, tuple(root.handlers), uvicorn.level, tuple(uvicorn.handlers))
    api_path = tmp_path / "api.log"
    scoring_path = tmp_path / "scoring.log"
    configure("api", api_path)
    configure("scoring", scoring_path)

    get_logger("dossier.service", service="api").info("API_READY", "ready")
    get_logger("api.scoring_main", service="scoring").info(
        "SCORING_SCORE_SUCCEEDED", "scored", house_count=20
    )

    assert event(api_path, "API_READY")["service"] == "api"
    assert event(scoring_path, "SCORING_SCORE_SUCCEEDED")["service"] == "scoring"
    assert "SCORING_SCORE_SUCCEEDED" not in api_path.read_text(encoding="utf-8")
    assert "API_READY" not in scoring_path.read_text(encoding="utf-8")
    assert before == (
        root.level,
        tuple(root.handlers),
        uvicorn.level,
        tuple(uvicorn.handlers),
    )


def test_environment_config_and_invalid_values(tmp_path, monkeypatch):
    monkeypatch.setenv("DOMDOSSE_LOG_FILE_PATH", "custom/execution.log")
    monkeypatch.setenv("DOMDOSSE_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DOMDOSSE_LOG_STDOUT", "false")

    settings = load_logging_settings("api")

    assert settings.file_path == REPO_ROOT / "custom" / "execution.log"
    assert settings.level == "DEBUG"
    assert settings.stdout is False
    monkeypatch.setenv("DOMDOSSE_LOG_LEVEL", "VERBOSE")
    with pytest.raises(ValueError):
        load_logging_settings("api")
    monkeypatch.setenv("DOMDOSSE_LOG_LEVEL", "INFO")
    monkeypatch.setenv("DOMDOSSE_LOG_STDOUT", "sometimes")
    with pytest.raises(ValueError):
        load_logging_settings("api")


@pytest.mark.parametrize("service", ("api", "scoring", "legacy"))
def test_default_path_is_service_execution_log(service, monkeypatch):
    monkeypatch.delenv("DOMDOSSE_LOG_FILE_PATH")

    settings = load_logging_settings(service)

    assert settings.file_path == REPO_ROOT / "logs" / service / "execution.log"


def test_unwritable_log_parent_is_not_silently_replaced_by_stdout(tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    with pytest.raises(OSError):
        configure("api", blocker / "execution.log", stdout=True)

    assert capsys.readouterr().out == ""


def test_lazy_auto_setup_repeats_invalid_level_failure(monkeypatch):
    monkeypatch.setenv("DOMDOSSE_LOG_LEVEL", "INVALID")
    logger = get_logger("api.main", service="api")

    for _ in range(2):
        with pytest.raises((ValueError, RuntimeError)):
            logger.info("API_APP_CREATED", "created")


def test_lazy_auto_setup_repeats_unwritable_path_failure(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    monkeypatch.setenv("DOMDOSSE_LOG_FILE_PATH", str(blocker / "execution.log"))
    logger = get_logger("api.main", service="api")

    for _ in range(2):
        with pytest.raises((OSError, RuntimeError)):
            logger.info("API_APP_CREATED", "created")


def test_create_app_fails_fast_on_startup_with_invalid_logging_config(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DOMDOSSE_LOG_LEVEL", "INVALID")
    application = api_cases.create_app(api_settings(tmp_path))

    with pytest.raises((ValueError, RuntimeError)):
        with TestClient(application):
            pass


def test_api_main_import_and_reimport_do_not_write_before_lifespan_startup(
    tmp_path, monkeypatch
):
    log_path = tmp_path / "logs" / "api" / "execution.log"
    monkeypatch.setenv("DOMDOSSE_LOG_FILE_PATH", str(log_path))
    monkeypatch.setenv("DOMDOSSE_LOG_LEVEL", "INFO")
    monkeypatch.delitem(sys.modules, "api.main")

    module = importlib.import_module("api.main")
    assert not log_path.exists(), "api.main import wrote execution.log"
    module = importlib.reload(module)
    assert not log_path.exists(), "api.main reload wrote execution.log"

    application = module.create_app(api_settings(tmp_path))
    assert not log_path.exists(), "create_app wrote execution.log before startup"
    with TestClient(application):
        assert log_path.is_file(), "lifespan startup did not create execution.log"
        assert event(log_path, "API_APP_CREATED")["service"] == "api"


def test_legacy_main_fails_fast_on_invalid_logging_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DOMDOSSE_LOG_LEVEL", "INVALID")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "legacy_dataset.py",
            "--legacy", str(tmp_path / "missing-legacy.json"),
            "--current", str(tmp_path / "missing-current.json"),
            "--output", str(tmp_path / "output.json"),
        ],
    )

    with pytest.raises(ValueError):
        legacy_cases.main()


def test_autouse_fixture_drives_real_auto_setup_to_unique_tmp_file(
    isolated_execution_log,
):
    settings = load_logging_settings("api")
    assert settings.file_path == isolated_execution_log
    assert settings.stdout is False

    get_logger("api.routes", service="api").info("API_READY", "ready", house_count=20)

    assert isolated_execution_log.is_file()
    assert event(isolated_execution_log, "API_READY")["house_count"] == 20


def test_metadata_is_json_unicode_single_line_and_validated(tmp_path):
    path = tmp_path / "execution.log"
    logger = get_logger("sources.utility_rating_json", service="api")
    configure("api", path)

    logger.info(
        "JSON_FILE_LOADED",
        "loaded\nnow",
        file_kind="dataset",
        file_name="датасет.json",
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "датасет.json" in lines[0]
    data = event(path, "JSON_FILE_LOADED")
    assert data["file_name"] == "датасет.json"
    assert LINE_RE.fullmatch(lines[0])["message"] == "loaded now"
    for value in (math.nan, math.inf, object()):
        with pytest.raises((TypeError, ValueError)):
            logger.info("JSON_FILE_LOADED", "invalid", value=value)
    with pytest.raises((TypeError, ValueError)):
        logger.info("JSON_FILE_LOADED", "invalid", service="scoring")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_api_503_has_boundary_markers_without_raw_path(tmp_path):
    path = tmp_path / "execution.log"
    configure("api", path)
    missing = tmp_path / "private-missing-name.json"
    settings = api_cases.Settings(dataset_path=missing, schema_path=missing)

    with TestClient(api_cases.create_app(settings)) as client:
        response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dataset_unavailable"
    assert event(path, "JSON_FILE_LOAD_FAILED")["reason"] == "file_not_found"
    assert event(path, "SNAPSHOT_LOAD_FAILED")["reason"] == "source_read_failed"
    assert event(path, "HTTP_ERROR_RETURNED")["reason"] == "dataset_unavailable"
    assert str(missing) not in path.read_text(encoding="utf-8")


def test_snapshot_ready_and_cache_hit_are_machine_readable(tmp_path):
    path = tmp_path / "execution.log"
    configure("api", path)

    with TestClient(api_cases.create_app(api_settings(tmp_path))) as client:
        assert client.get("/api/houses").status_code == 200
        assert client.get("/api/houses").status_code == 200

    ready = event(path, "SNAPSHOT_READY")
    assert ready["service"] == "api"
    assert ready["house_count"] == 20
    assert ready["event_count"] == 2
    assert event(path, "SNAPSHOT_CACHE_HIT")["cache_state"] == "hit"


def test_legacy_skip_counters_and_no_plain_print(tmp_path, monkeypatch, capsys):
    legacy = tmp_path / "legacy.json"
    current = tmp_path / "current.json"
    schema = tmp_path / "schema.json"
    output = tmp_path / "output.json"
    records = [
        legacy_cases.make_record(1, "2026-10-13T23:00:00", "2026-10-14T01:00:00"),
        legacy_cases.make_record(2, "2026-11-12T23:00:00", "2026-11-13T01:00:00"),
        legacy_cases.make_record(3, "2026-10-13T20:00:00", "2026-10-13T21:00:00"),
        legacy_cases.make_record(4, "2026-11-13T00:00:00", "2026-11-13T01:00:00"),
        legacy_cases.make_record(5, "2026-10-20T10:00:00", None),
        legacy_cases.make_record(6, "2026-10-13T23:00:00", "2026-10-14T00:00:00"),
    ]
    legacy.write_text(json.dumps(records), encoding="utf-8")
    current.write_text(
        json.dumps(legacy_cases.make_draft(legacy_cases.ADDRESSES)), encoding="utf-8"
    )
    schema.write_text(json.dumps(legacy_cases.SCHEMA), encoding="utf-8")
    log_path = tmp_path / "execution.log"
    monkeypatch.setenv("DOMDOSSE_LOG_FILE_PATH", str(log_path))
    monkeypatch.setenv("DOMDOSSE_LOG_STDOUT", "false")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "legacy_dataset.py",
            "--legacy", str(legacy),
            "--current", str(current),
            "--output", str(output),
            "--schema", str(schema),
        ],
    )
    configure("legacy", log_path)

    legacy_cases.main()

    assert capsys.readouterr().out == ""
    built = event(log_path, "LEGACY_DATASET_BUILT")
    assert built["input_record_count"] == 6
    assert built["output_event_count"] == 2
    skipped = event(log_path, "LEGACY_RECORDS_SKIPPED")
    assert skipped["skipped_count"] == 4
    assert skipped["outside_window_count"] == 3
    assert skipped["missing_end_count"] == 1
    assert skipped["unmatched_address_count"] == 0
    summary = event(log_path, "LEGACY_RATING_SUMMARY")
    assert summary["hot_water_count"] == 0
    assert summary["cold_water_count"] == 0
    assert summary["electricity_count"] == 2
    assert summary["heating_count"] == 0


def test_run_directory_uses_utc_name_and_rejects_collision(tmp_path):
    root = tmp_path / "runs"
    now = datetime(2026, 11, 14, 12, 34, 56, tzinfo=timezone.utc)

    run_dir = create_run_directory(root=root, now=now)

    assert run_dir == root / "20261114_123456"
    assert run_dir.is_dir()
    with pytest.raises(FileExistsError):
        create_run_directory(root=root, now=now)
    with pytest.raises(ValueError):
        create_run_directory(root=root, now=datetime(2026, 11, 14, 12, 34, 57))


def test_artifacts_allowlist_results_not_run_and_service_paths(tmp_path):
    run_dir = create_run_directory(
        root=tmp_path, now=datetime(2026, 11, 14, tzinfo=timezone.utc)
    )
    secret = "SECRET_VALUE_DO_NOT_LOG"
    snapshot = write_env_snapshot(
        run_dir,
        {
            "DOMDOSSE_LOG_LEVEL": "INFO",
            "DOMDOSSE_UTILITY_RATING_DATASET_PATH": "dataset/synthetic.json",
            "SECRET_KEY": secret,
            "UNRELATED": "excluded",
        },
    )

    assert json.loads(snapshot.read_text(encoding="utf-8")) == {
        "DOMDOSSE_LOG_LEVEL": "INFO",
        "DOMDOSSE_UTILITY_RATING_DATASET_PATH": "dataset/synthetic.json",
    }
    assert secret not in snapshot.read_text(encoding="utf-8")
    results = append_test_result(run_dir, "pytest -q", "2 passed\n", 0)
    append_test_result(run_dir, "ruff check .", "All checks passed!\n", 0)
    mark_not_run(run_dir, "docker compose ps", "Compose is not implemented")
    text = results.read_text(encoding="utf-8")
    assert "pytest -q" in text and "2 passed" in text and "exit_code=0" in text
    assert "ruff check ." in text and "All checks passed!" in text
    assert "NOT_RUN" in text and "Compose is not implemented" in text
    for service in ("api", "scoring", "frontend"):
        path = service_execution_log(run_dir, service)
        assert path == run_dir / service / "execution.log"
    with pytest.raises(ValueError):
        service_execution_log(run_dir, "legacy")


def test_utility_rating_has_no_logging_or_print():
    for path in (REPO_ROOT / "utility_rating").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    alias.name != "logging" and alias.name != "core.logging"
                    for alias in node.names
                ), path
            elif isinstance(node, ast.ImportFrom):
                assert node.module not in {"logging", "core.logging"}, path
            elif isinstance(node, ast.Call):
                assert not (isinstance(node.func, ast.Name) and node.func.id == "print"), path
