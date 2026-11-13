"""Approved observed-exposure rating method.

Public interface: ``CalculationRequest``, ``CalculationReport`` and
``evaluate``.  The package imports only the public dataset/error contracts and
never ``core``, FastAPI, settings, environment, files, network or a clock.
"""

from __future__ import annotations

from rating._evaluate import evaluate
from rating.models import CalculationReport, CalculationRequest

__all__ = ["CalculationReport", "CalculationRequest", "evaluate"]
