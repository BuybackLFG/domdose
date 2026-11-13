"""Централизованное маркированное логирование и run-артефакты (только stdlib).

Единственная точка сборки логгеров: прикладные модули импортируют этот
модуль и не создают собственных file handlers и не используют print.
Иерархия stdlib logging (root, uvicorn) не изменяется: события идут
напрямую в handlers сервиса, попадание в root исключено.
"""

import json
import logging
import os
import re
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]

_FILE_ENV = "DOMDOSSE_LOG_FILE_PATH"
_LEVEL_ENV = "DOMDOSSE_LOG_LEVEL"
_STDOUT_ENV = "DOMDOSSE_LOG_STDOUT"

_DEFAULT_LEVEL = "INFO"
_DEFAULT_STDOUT = True

_LINE_TEMPLATE = (
    "[{timestamp}] [{level}] [{module}] [{marker}] {message} | data={data}"
)
_MESSAGE_FORMAT = "%(message)s"
_MARKER_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_WHITESPACE_RE = re.compile(r"\s+")
_TRUE_WORDS = frozenset({"true", "1", "yes", "on"})
_FALSE_WORDS = frozenset({"false", "0", "no", "off"})

_SNAPSHOT_ALLOWLIST = (
    "DOMDOSSE_UTILITY_RATING_DATASET_PATH",
    "DOMDOSSE_UTILITY_RATING_SCHEMA_PATH",
    "DOMDOSSE_SCORING_URL",
    _FILE_ENV,
    _LEVEL_ENV,
    _STDOUT_ENV,
)
_RUN_SERVICES = frozenset({"api", "scoring", "frontend"})

_FORMATTER = logging.Formatter(_MESSAGE_FORMAT)
_lock = threading.RLock()


class ServiceName(StrEnum):
    """Сервис с отдельным файловым журналом execution.log."""

    API = "api"
    SCORING = "scoring"
    LEGACY = "legacy"


@dataclass(frozen=True)
class LoggingSettings:
    """Настройки журнала сервиса: файл, уровень и опциональный stdout."""

    service: ServiceName
    file_path: Path
    level: str = _DEFAULT_LEVEL
    stdout: bool = _DEFAULT_STDOUT

    def __post_init__(self) -> None:
        object.__setattr__(self, "service", ServiceName(self.service))
        object.__setattr__(self, "file_path", Path(self.file_path))
        object.__setattr__(self, "level", str(self.level).upper())
        _level_number(self.level)


@dataclass
class _ServiceState:
    """Живые handlers и порог уровня одного настроенного сервиса."""

    settings: LoggingSettings
    handlers: list[logging.Handler]
    level_number: int


_states: dict[ServiceName, _ServiceState] = {}


def _level_number(name: str) -> int:
    """Числовой уровень по имени; ValueError на неизвестном имени."""
    number = logging.getLevelName(str(name).upper())
    if not isinstance(number, int):
        raise ValueError(f"unknown log level: {name!r}")
    return number


def _parse_stdout(raw: str | None) -> bool:
    """Разобрать булево DOMDOSSE_LOG_STDOUT; ValueError на прочем значении."""
    if raw is None:
        return _DEFAULT_STDOUT
    word = raw.strip().casefold()
    if word in _TRUE_WORDS:
        return True
    if word in _FALSE_WORDS:
        return False
    raise ValueError(f"invalid log stdout value: {raw!r}")


def load_logging_settings(service: ServiceName | str) -> LoggingSettings:
    """Собрать настройки журнала сервиса из DOMDOSSE_LOG_* переменных.

    Относительный DOMDOSSE_LOG_FILE_PATH трактуется от корня репозитория.
    """
    name = ServiceName(service)
    raw_path = os.environ.get(_FILE_ENV)
    if raw_path:
        candidate = Path(raw_path)
        file_path = candidate if candidate.is_absolute() else _REPO_ROOT / candidate
    else:
        file_path = _REPO_ROOT / "logs" / name.value / "execution.log"
    level = os.environ.get(_LEVEL_ENV, _DEFAULT_LEVEL)
    stdout = _parse_stdout(os.environ.get(_STDOUT_ENV))
    return LoggingSettings(
        service=name, file_path=file_path, level=str(level).upper(), stdout=stdout
    )


def setup_logging(settings: LoggingSettings) -> None:
    """Идемпотентно настроить журнал сервиса; конфликт — RuntimeError.

    Файл создаётся сразу (OSError при недоступном каталоге не подменяется
    stdout-режимом); два сервиса не делят один файл.
    """
    with _lock:
        existing = _states.get(settings.service)
        if existing is not None:
            if existing.settings == settings:
                return
            raise RuntimeError(
                f"logging for service {settings.service.value!r} is already configured"
            )
        for service, state in _states.items():
            if state.settings.file_path == settings.file_path:
                raise RuntimeError(
                    f"log file is already used by service {service.value!r}"
                )
        handlers: list[logging.Handler] = []
        try:
            settings.file_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(settings.file_path, encoding="utf-8")
            file_handler.setFormatter(_FORMATTER)
            handlers.append(file_handler)
            if settings.stdout:
                stream_handler = logging.StreamHandler(sys.stdout)
                stream_handler.setFormatter(_FORMATTER)
                handlers.append(stream_handler)
        except BaseException:
            for handler in handlers:
                handler.close()
            raise
        _states[settings.service] = _ServiceState(
            settings=settings,
            handlers=handlers,
            level_number=_level_number(settings.level),
        )


def shutdown_logging() -> None:
    """Закрыть все журналы и забыть настройки; root и uvicorn не трогает."""
    with _lock:
        states = list(_states.values())
        _states.clear()
    for state in states:
        for handler in state.handlers:
            handler.close()


def _state_for(service: ServiceName) -> _ServiceState:
    """Найти состояние сервиса; при отсутствии выполнить auto setup.

    Ошибка настройки пробрасывается первому событию (fail-fast) и не
    кэшируется: повторная попытка setup выполняется на следующем событии.
    """
    state = _states.get(service)
    if state is not None:
        return state
    with _lock:
        state = _states.get(service)
        if state is None:
            setup_logging(load_logging_settings(service))
            state = _states.get(service)
    if state is None:
        raise RuntimeError(f"auto setup did not configure {service.value!r}")
    return state


class EventLogger:
    """Ленивый логгер маркированных событий модуля одного сервиса.

    Файл не требуется до первого события: при необходимости выполняется
    auto setup из переменных окружения.
    """

    def __init__(self, module: str, service: ServiceName | str) -> None:
        self._module = str(module)
        self._service = ServiceName(service)

    def debug(self, marker: str, message: str, **data: Any) -> None:
        """Событие уровня DEBUG."""
        self._emit(logging.DEBUG, "DEBUG", marker, message, data)

    def info(self, marker: str, message: str, **data: Any) -> None:
        """Событие уровня INFO."""
        self._emit(logging.INFO, "INFO", marker, message, data)

    def warning(self, marker: str, message: str, **data: Any) -> None:
        """Событие уровня WARNING."""
        self._emit(logging.WARNING, "WARNING", marker, message, data)

    def error(self, marker: str, message: str, **data: Any) -> None:
        """Событие уровня ERROR (отказы и потери)."""
        self._emit(logging.ERROR, "ERROR", marker, message, data)

    def _emit(
        self,
        level_number: int,
        level_name: str,
        marker: str,
        message: str,
        data: dict[str, Any],
    ) -> None:
        if not _MARKER_RE.fullmatch(marker):
            raise ValueError(f"invalid log marker: {marker!r}")
        if "service" in data:
            raise ValueError("key 'service' is reserved in log metadata")
        state = _state_for(self._service)
        if level_number < state.level_number:
            return
        payload = {"service": self._service.value}
        payload.update(data)
        data_json = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        clean_message = _WHITESPACE_RE.sub(" ", str(message)).strip()
        line = _LINE_TEMPLATE.format(
            timestamp=f"{timestamp}Z",
            level=level_name,
            module=self._module,
            marker=marker,
            message=clean_message,
            data=data_json,
        )
        record = logging.LogRecord(
            name=self._module,
            level=level_number,
            pathname="",
            lineno=0,
            msg=line,
            args=(),
            exc_info=None,
        )
        for handler in state.handlers:
            handler.handle(record)


def get_logger(module: str, service: ServiceName | str) -> EventLogger:
    """Создать ленивый логгер модуля; файла до первого события не требует."""
    return EventLogger(module, service)


def create_run_directory(root: Path, now: datetime | None = None) -> Path:
    """Создать каталог прогона YYYYMMDD_HHMMSS в UTC.

    now обязано быть timezone-aware (ValueError иначе); коллизия имени —
    FileExistsError.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(root) / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_env_snapshot(run_dir: Path, env: Mapping[str, str]) -> Path:
    """Записать env_snapshot.json: только allowlist-имена, секреты исключены."""
    snapshot = {name: env[name] for name in _SNAPSHOT_ALLOWLIST if name in env}
    path = Path(run_dir) / "env_snapshot.json"
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def append_test_result(
    run_dir: Path, command: str, output: str, exit_code: int
) -> Path:
    """Дописать в test_results.log команду, фактический вывод и exit_code."""
    path = Path(run_dir) / "test_results.log"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"$ {command}\n{output.rstrip()}\nexit_code={exit_code}\n\n")
    return path


def mark_not_run(run_dir: Path, command: str, reason: str) -> Path:
    """Зафиксировать в test_results.log сознательно незапущенную проверку."""
    path = Path(run_dir) / "test_results.log"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"$ {command}\nNOT_RUN: {reason}\n\n")
    return path


def service_execution_log(run_dir: Path, service: str) -> Path:
    """Путь отдельного execution.log сервиса внутри каталога прогона."""
    if service not in _RUN_SERVICES:
        raise ValueError(f"unknown run service: {service!r}")
    return Path(run_dir) / service / "execution.log"
