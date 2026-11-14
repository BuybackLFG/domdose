"""Explicit, idempotent logging setup for the ``domdose`` logger namespace.

Importing this module creates no handlers, files or settings. A caller opts in
by calling :func:`setup_logging`. The root logger and the global log record
factory are never modified.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from core.config import Settings, get_settings

_LOGGER_NAME = "domdose"
_OWNED = "_domdose_owned"
_TARGET = "_domdose_target"


def get_logger(name: str) -> logging.Logger:
    """Return a logger inside the ``domdose`` namespace."""
    if not name:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def _target(settings: Settings) -> tuple[str, str]:
    """An owned handler target description: standard output or a resolved file."""
    if settings.log_file is None:
        return ("stream", "stdout")
    return ("file", str(Path(settings.log_file).resolve()))


def _remove_owned(logger: logging.Logger, keep: logging.Handler | None = None) -> None:
    """Detach and close owned handlers other than ``keep``."""
    for handler in list(logger.handlers):
        if not getattr(handler, _OWNED, False) or handler is keep:
            continue
        logger.removeHandler(handler)
        handler.close()


def setup_logging(settings: Settings | None = None) -> logging.Logger:
    """Initialize the ``domdose`` logger exactly once for the given settings.

    ``None`` settings are loaded through :func:`core.config.get_settings`.
    ``log_file=None`` selects standard output; a path selects UTF-8 file output
    with its parent directory created. Repeated calls with the same target keep
    the existing handler. The root logger and record factory stay untouched.
    """
    if settings is None:
        settings = get_settings()

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(settings.log_level)
    logger.propagate = False
    logger.disabled = False

    target = _target(settings)
    for handler in list(logger.handlers):
        if getattr(handler, _OWNED, False) and getattr(handler, _TARGET, None) == target:
            _remove_owned(logger, keep=handler)
            return logger

    _remove_owned(logger)
    if settings.log_file is None:
        handler: logging.Handler = logging.StreamHandler(sys.stdout)
    else:
        path = Path(settings.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
    setattr(handler, _OWNED, True)
    setattr(handler, _TARGET, target)
    logger.addHandler(handler)
    return logger
