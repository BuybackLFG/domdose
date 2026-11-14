"""Safe normalization of public calculation requests.

Only a validated ``CalculationRequest`` or a plain mapping is accepted.  JSON
text and bytes are malformed request input, not a serialized shortcut.  All
refusals carry stable codes and field/index paths only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from contract.errors import ContractIssue
from rating.models import POLICY_VERSION, CalculationRequest

_OFFSET = timedelta(hours=10)
_ALLOWED_KEYS = frozenset({"target_house_ids", "end_exclusive", "policy_version"})
_MISSING = object()


@dataclass(frozen=True)
class ValidRequest:
    """Normalized request values used by the calculation engine."""

    target_house_ids: tuple[str, ...]
    end_exclusive: datetime
    policy_version: str


def _check_ids(value: object, issues: list[ContractIssue]) -> tuple[str, ...] | None:
    """Validate target identifiers; JSON arrays are accepted, other types are not."""
    if not isinstance(value, (list, tuple)):
        issues.append(ContractIssue("INVALID_REQUEST", ("target_house_ids",)))
        return None
    items: tuple[object, ...] = tuple(value)
    if not items:
        issues.append(ContractIssue("INVALID_REQUEST", ("target_house_ids",)))
        return None
    seen: set[str] = set()
    normalized: list[str] = []
    valid = True
    for index, item in enumerate(items):
        if not isinstance(item, str) or not item:
            issues.append(ContractIssue("INVALID_REQUEST", ("target_house_ids", index)))
            valid = False
            continue
        if item in seen:
            issues.append(ContractIssue("INVALID_REQUEST", ("target_house_ids", index)))
            valid = False
            continue
        seen.add(item)
        normalized.append(item)
    if not valid:
        return None
    return tuple(normalized)


def _check_dto_end(value: object, issues: list[ContractIssue]) -> datetime | None:
    """A direct DTO must already hold a +10:00 aware datetime."""
    if not isinstance(value, datetime) or value.utcoffset() != _OFFSET:
        issues.append(ContractIssue("INVALID_REQUEST", ("end_exclusive",)))
        return None
    return value


def _parse_mapping_end(value: object, issues: list[ContractIssue]) -> datetime | None:
    """A JSON request accepts a +10:00 aware datetime or ISO timestamp string."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            issues.append(ContractIssue("INVALID_REQUEST", ("end_exclusive",)))
            return None
    else:
        issues.append(ContractIssue("INVALID_REQUEST", ("end_exclusive",)))
        return None
    if parsed.utcoffset() != _OFFSET:
        issues.append(ContractIssue("INVALID_REQUEST", ("end_exclusive",)))
        return None
    return parsed


def _normalize_dto(request: CalculationRequest, issues: list[ContractIssue]) -> ValidRequest | None:
    ids = _check_ids(getattr(request, "target_house_ids", None), issues)
    end = _check_dto_end(getattr(request, "end_exclusive", None), issues)
    policy = getattr(request, "policy_version", None)
    if not isinstance(policy, str):
        issues.append(ContractIssue("INVALID_REQUEST", ("policy_version",)))
        policy_ok = False
    elif policy != POLICY_VERSION:
        issues.append(ContractIssue("UNKNOWN_POLICY", ("policy_version",)))
        policy_ok = False
    else:
        policy_ok = True
    if ids is None or end is None or not policy_ok:
        return None
    return ValidRequest(target_house_ids=ids, end_exclusive=end, policy_version=policy)


def _normalize_mapping(request: Mapping, issues: list[ContractIssue]) -> ValidRequest | None:
    for key in request.keys():
        if key not in _ALLOWED_KEYS:
            issues.append(ContractIssue("INVALID_REQUEST", ("$extra",)))
            break

    ids_value = request["target_house_ids"] if "target_house_ids" in request else _MISSING
    ids = None if ids_value is _MISSING else _check_ids(ids_value, issues)
    if ids_value is _MISSING:
        issues.append(ContractIssue("INVALID_REQUEST", ("target_house_ids",)))

    end_value = request["end_exclusive"] if "end_exclusive" in request else _MISSING
    end = None if end_value is _MISSING else _parse_mapping_end(end_value, issues)
    if end_value is _MISSING:
        issues.append(ContractIssue("INVALID_REQUEST", ("end_exclusive",)))

    policy = POLICY_VERSION
    if "policy_version" in request:
        raw_policy = request["policy_version"]
        if not isinstance(raw_policy, str):
            issues.append(ContractIssue("INVALID_REQUEST", ("policy_version",)))
            policy = ""
        elif raw_policy != POLICY_VERSION:
            issues.append(ContractIssue("UNKNOWN_POLICY", ("policy_version",)))
            policy = ""
        else:
            policy = raw_policy

    if ids is None or end is None or policy == "":
        return None
    return ValidRequest(target_house_ids=ids, end_exclusive=end, policy_version=policy)


def normalize_request(request: object) -> tuple[ValidRequest | None, tuple[ContractIssue, ...]]:
    """Return normalized values plus safe issues; never raises for request data."""
    issues: list[ContractIssue] = []
    if isinstance(request, CalculationRequest):
        normalized = _normalize_dto(request, issues)
    elif isinstance(request, Mapping):
        normalized = _normalize_mapping(request, issues)
    else:
        issues.append(ContractIssue("INVALID_REQUEST", ()))
        normalized = None
    return normalized, tuple(issues)
