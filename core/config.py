"""Project settings: the single place that reads environment configuration.

Environment names are the uppercase field names. An explicit argument overrides
the environment, which overrides a UTF-8 ``.env`` in the working directory,
which overrides the declared defaults. Unknown constructor and dotenv fields
are refused; unrelated environment variables are ignored.

A refused construction is reported as :class:`SettingsRefused` without input
values, unknown field names or the original exception chain.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsRefused(Exception):
    """Refused settings construction with only safe, machine-readable facts.

    ``error`` names the originating exception class. ``problems`` maps a
    declared field to its first validation error code. ``undeclared`` counts
    errors outside declared fields. Input values and original exception chains
    are never carried.
    """

    def __init__(self, error: str, problems: dict[str, str], undeclared: int) -> None:
        super().__init__(f"settings refused: {error}")
        self.error = error
        self.problems = problems
        self.undeclared = undeclared


def _is_blank(value: str) -> bool:
    """Whether a string has no character outside whitespace."""
    return not any(not character.isspace() for character in value)


def _census(error: ValidationError) -> tuple[dict[str, str], int]:
    """Declared field/code pairs and the count of errors outside fields."""
    problems: dict[str, str] = {}
    undeclared = 0
    for found in error.errors(
        include_url=False, include_input=False, include_context=False
    ):
        location = found.get("loc", ())
        name = location[0] if location else None
        if isinstance(name, str) and name in Settings.model_fields:
            problems.setdefault(name, str(found.get("type", "validation")))
        else:
            undeclared += 1
    return problems, undeclared


class Settings(BaseSettings):
    """Frozen process settings: log level and optional log file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    log_file: Path | None = None

    @field_validator("log_file", mode="before")
    @classmethod
    def _blank_file_is_none(cls, value: object) -> object:
        """An empty or whitespace-only log file means no file output."""
        if isinstance(value, str) and _is_blank(value):
            return None
        return value

    def __init__(self, **values: Any) -> None:
        try:
            super().__init__(**values)
        except Exception as exc:
            error = type(exc).__name__
            problems, undeclared = (
                _census(exc) if isinstance(exc, ValidationError) else ({}, 0)
            )
        else:
            return
        # Raised outside the handler: the original exception chain is dropped.
        raise SettingsRefused(error, problems, undeclared)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings cached after the first successful build."""
    return Settings()
