"""Public rating evaluation entry point.

Dataset DTOs are revalidated through the single contract door; malformed
requests and unknown targets become safe typed refusals.
"""

from __future__ import annotations

from collections.abc import Mapping

from contract.dataset import Dataset, read_dataset
from contract.errors import ContractIssue, ContractRefused
from rating.engine import build_report
from rating.models import CalculationReport, CalculationRequest
from rating.requests import normalize_request


def _revalidated_dataset(dataset: Dataset) -> Dataset:
    """Dump a DTO and revalidate it; a forged DTO must not leak raw values or raise.

    ``model_construct`` bypasses validation, so serialization itself may warn with
    the raw input value or raise. Both are converted into a safe typed refusal
    outside the exception block, keeping ``__context__`` empty.
    """
    failed = False
    mapping = None
    try:
        mapping = dataset.model_dump(mode="json", by_alias=True, warnings="error")
    except Exception:
        failed = True
    if failed or mapping is None:
        raise ContractRefused((ContractIssue("INVALID-INPUT", ()),))
    return read_dataset(mapping)


def evaluate(
    dataset: Dataset | Mapping | str | bytes,
    request: CalculationRequest | Mapping,
) -> CalculationReport:
    """Compute the observed, approximate rating report for the explicit request."""
    valid, issues = normalize_request(request)
    if issues:
        raise ContractRefused(issues)
    if valid is None:
        raise ContractRefused((ContractIssue("INVALID_REQUEST", ()),))

    if isinstance(dataset, Dataset):
        data = _revalidated_dataset(dataset)
    else:
        data = read_dataset(dataset)

    known = {house.id for house in data.houses}
    unknown = tuple(
        ContractIssue("UNKNOWN_HOUSE", ("target_house_ids", index))
        for index, target in enumerate(valid.target_house_ids)
        if target not in known
    )
    if unknown:
        raise ContractRefused(unknown)
    return build_report(data, valid)
