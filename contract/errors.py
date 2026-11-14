"""Public dataset contract errors with safe, machine-readable facts only."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ContractIssue:
    """A stable issue code and a field/index path without input values."""

    code: str
    path: tuple[str | int, ...]


class ContractRefused(Exception):
    """Dataset refusal carrying only contract issues, never raw input or chains."""

    def __init__(self, issues: Iterable[ContractIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(f"dataset contract refused: {len(self.issues)} issue(s)")
