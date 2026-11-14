"""Изоляция файловых журналов всех pytest-сцен."""

from pathlib import Path

import pytest

_ACTIVE_LOG_PATHS: set[Path] = set()


def _shutdown_project_logging() -> None:
    try:
        from core.logging import shutdown_logging
    except ModuleNotFoundError as exc:
        if exc.name != "core.logging":
            raise
        return
    shutdown_logging()


@pytest.fixture(autouse=True)
def isolated_execution_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Направить каждый тест в отдельный журнал и закрыть handlers после него."""
    log_path = tmp_path / "execution.log"
    assert log_path not in _ACTIVE_LOG_PATHS
    _ACTIVE_LOG_PATHS.add(log_path)
    monkeypatch.setenv("DOMDOSSE_LOG_FILE_PATH", str(log_path))
    monkeypatch.setenv("DOMDOSSE_LOG_STDOUT", "false")
    _shutdown_project_logging()
    yield log_path
    _shutdown_project_logging()
