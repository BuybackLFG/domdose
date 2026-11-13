import importlib
import logging
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from test_dataset import CANARY, assert_safe

from core.config import Settings, SettingsRefused, get_settings
from core.logging import get_logger, setup_logging


@pytest.fixture(autouse=True)
def reset_cache(isolated_env):
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def local_logger():
    logger = logging.getLogger("domdose")
    original = (logger.handlers[:], logger.level, logger.propagate, logger.disabled)
    logger.handlers = []
    yield logger
    for handler in logger.handlers:
        if handler not in original[0]:
            handler.close()
    logger.handlers, logger.level, logger.propagate, logger.disabled = original


def test_settings_defaults_exact_and_frozen():
    assert issubclass(Settings, BaseSettings)
    settings = Settings()
    assert set(Settings.model_fields) == {"log_level", "log_file"}
    assert settings.log_level == "INFO" and settings.log_file is None
    with pytest.raises((ValidationError, AttributeError, TypeError)):
        settings.log_level = "DEBUG"


@pytest.mark.parametrize("level", ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"])
def test_declared_levels(level):
    assert Settings(log_level=level).log_level == level


def test_precedence_utf8_and_empty_file(monkeypatch, isolated_env):
    (isolated_env / ".env").write_text("LOG_LEVEL=WARNING\nLOG_FILE=журнал.log\n", encoding="utf-8")
    assert Settings().log_level == "WARNING"
    assert Settings().log_file == Path("журнал.log")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    monkeypatch.setenv("LOG_FILE", "env.log")
    assert Settings().log_level == "ERROR" and Settings().log_file == Path("env.log")
    assert Settings(log_level="DEBUG", log_file="kw.log").log_level == "DEBUG"
    assert Settings(log_file="kw.log").log_file == Path("kw.log")
    assert Settings(log_file="").log_file is None
    monkeypatch.setenv("LOG_FILE", "")
    assert Settings().log_file is None


@pytest.mark.parametrize("origin", ["kwargs", "env", "dotenv"])
@pytest.mark.parametrize("invalid", ["", "info", CANARY])
def test_settings_refusal_safe(monkeypatch, isolated_env, origin, invalid):
    kwargs = {}
    if origin == "kwargs":
        kwargs["log_level"] = invalid
    elif origin == "env":
        monkeypatch.setenv("LOG_LEVEL", invalid)
    else:
        (isolated_env / ".env").write_text(f"LOG_LEVEL={invalid}\n", encoding="utf-8")
    with pytest.raises(SettingsRefused) as caught:
        Settings(**kwargs)
    error = caught.value
    assert isinstance(error.error, str) and error.error
    assert isinstance(error.problems, dict) and error.problems
    assert "log_level" in error.problems
    assert all(isinstance(code, str) and code for code in error.problems.values())
    assert isinstance(error.undeclared, int) and error.undeclared == 0
    assert_safe(error)


@pytest.mark.parametrize("origin", ["kwargs", "dotenv"])
def test_undeclared_values_are_safe(origin, isolated_env):
    kwargs = {}
    if origin == "kwargs":
        kwargs[CANARY] = CANARY
    else:
        (isolated_env / ".env").write_text(f"{CANARY}={CANARY}\n", encoding="utf-8")
    with pytest.raises(SettingsRefused) as caught:
        Settings(**kwargs)
    assert caught.value.undeclared == 1
    assert isinstance(caught.value.error, str) and caught.value.error
    assert_safe(caught.value)


def test_cache_only_explicit_loading(monkeypatch):
    first = get_settings()
    assert first is get_settings()
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert get_settings() is first and first.log_level == "INFO"
    get_settings.cache_clear()
    assert get_settings().log_level == "DEBUG"
    assert get_settings() is not first


def root_snapshot():
    root = logging.getLogger()
    return (
        root.handlers[:],
        root.level,
        root.propagate,
        root.disabled,
        logging.getLogRecordFactory(),
    )


def test_imports_do_not_load_settings_or_setup(monkeypatch, isolated_env, local_logger):
    monkeypatch.setenv("LOG_LEVEL", CANARY)
    monkeypatch.setenv("LOG_FILE", str(isolated_env / "must-not-exist.log"))
    before = root_snapshot()
    modules = [importlib.import_module(name) for name in ("core.config", "core.logging")]
    snapshots = [vars(module).copy() for module in modules]
    try:
        for module in modules:
            importlib.reload(module)
        assert not list(isolated_env.iterdir())
        assert local_logger.handlers == []
        assert root_snapshot() == before
        assert modules[0].get_settings.cache_info().currsize == 0
    finally:
        # Preserve exception/class identities held by other tests after reload.
        for module, snapshot in zip(modules, snapshots, strict=True):
            vars(module).clear()
            vars(module).update(snapshot)


@pytest.mark.parametrize("sink", ["stdout", "file"])
def test_logging_explicit_idempotent_local(sink, isolated_env, local_logger, capsys):
    before = root_snapshot()
    target = isolated_env / "тест.log"
    settings = Settings(log_level="DEBUG", log_file=None if sink == "stdout" else target)
    assert not target.exists() and local_logger.handlers == []
    setup_logging(settings)
    handlers = local_logger.handlers[:]
    setup_logging(settings)
    assert local_logger.handlers == handlers and len(handlers) == 1
    assert local_logger.level == logging.DEBUG
    assert local_logger.propagate is False
    assert root_snapshot() == before
    if sink == "stdout":
        assert isinstance(handlers[0], logging.StreamHandler)
        assert not isinstance(handlers[0], logging.FileHandler)
    else:
        assert isinstance(handlers[0], logging.FileHandler)
        assert handlers[0].encoding.lower().replace("-", "") == "utf8"
    child = get_logger("probe")
    assert child.name == "domdose.probe"
    child.info("synthetic-log-marker поле=значение")
    for handler in handlers:
        handler.flush()
    captured = capsys.readouterr()
    text = captured.out if sink == "stdout" else target.read_text(encoding="utf-8")
    assert text.count("synthetic-log-marker поле=значение") == 1
    assert "synthetic-log-marker" not in captured.err
    assert root_snapshot() == before


def test_setup_none_explicitly_uses_cached_settings(monkeypatch, local_logger):
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    setup_logging()
    assert local_logger.level == logging.ERROR
    assert len(local_logger.handlers) == 1
