# Standalone Python library

This additive package is separate from the existing backend/frontend application. It implements process settings, explicit logging, dataset 1.0 contracts and the approved observed-exposure rating method `rating_observed_exposure_proxy_v1`.

## Local environment on Windows

Python 3.12+ is required. All development dependencies, caches and temporary files stay in the checkout. Do not point the application backend at this virtual environment: its own dependency management remains unchanged.

```powershell
$workspace = (Get-Location).Path
New-Item -ItemType Directory -Force .local/tmp, .local/pip-cache | Out-Null
$env:TEMP = Join-Path $workspace '.local/tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $workspace '.local/pip-cache'
$env:PYTHONNOUSERSITE = '1'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements-dev.lock -e '.[dev]'
```

`requirements-dev.lock` pins the verified dependency versions; it is a constraints snapshot, not a hash-locked supply-chain manifest. `scripts/env.ps1` applies the local paths to a shell that dot-sources it. Under an execution policy requiring signatures, do not change the machine policy; run the environment assignments above directly.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_dataset.py tests/test_config_logging.py tests/test_architecture.py tests/test_instrument.py
.\.venv\Scripts\python.exe -m pytest tests/test_rating_instrument.py
.\.venv\Scripts\python.exe -m pytest tests/test_rating_rules.py tests/test_rating_contract.py tests/test_rating_guards.py
.\.venv\Scripts\python.exe -m ruff check core contract rating tests scripts/inspect_dataset.py
```

`scripts/check-library.ps1` runs the whole library suite and lint from one command. It requires a Python interpreter: pass `-Python <path>` or have `.venv` in the working directory. The script reports the library state only. It is NOT a substitute for the existing application's `scripts/check.sh`, and a green library run does not make the application checks green.

## Public interfaces

- `core.config.Settings`, `get_settings`, `SettingsRefused`: frozen settings; explicit arguments > environment > UTF-8 dotenv > declared defaults. Only log level and optional log file are configured.
- `core.logging.setup_logging`, `get_logger`: explicit named-logger setup; no handlers/files on import and no global root logger modification.
- `contract.dataset.Dataset`, `read_dataset`, `dataset_schema`: immutable typed dataset; schema and semantic validation without reading dataset files or environment. Nullable facts remain nullable; empty datasets are permitted.
- `contract.errors.ContractRefused`, `ContractIssue`: sanitized machine-readable code/path errors.
- `rating.CalculationRequest`, `rating.CalculationReport`, `rating.evaluate`: pure rating of a dataset 1.0 input for the explicit request. The request carries target house IDs, an explicit +10:00 end timestamp and the policy version; there is no implicit clock. Reports hold the window, per-house category metrics, city baselines, ratios, penalties, scores, effective weights, source spans, original limitations and deterministic diagnostics. Malformed requests and unknown houses/policies raise `ContractRefused` with `INVALID_REQUEST`, `UNKNOWN_HOUSE` or `UNKNOWN_POLICY`; insufficient facts produce a partial report instead of an exception. `rating` imports only the public dataset/error contracts and never `core`, settings, files, logs or network.

For JSON input use `read_dataset(mapping_or_json_or_bytes)`. Validation refuses malformed structure, duplicate IDs/keys, invalid references, inconsistent dates/times/durations and nonfinite/negative relevant numbers. It does not infer missing facts, normalize addresses or judge source truth. Direct model construction is not a replacement for whole-dataset semantic validation.

`contract/dataset.schema.json` is the unchanged supplied schema. The library validates Draft 2020-12 format and adds semantic invariants documented in `SPEC.md`. A stored duration must agree with its actual/planned endpoints within 0.005 hours, half of the 0.01 hour rounding step of the published source; calculations use the stored `duration_hours`. Other numeric comparisons keep the 1e-9 tolerance. Do not change this rounding tolerance without a separately approved contract change.

## Dataset inspection

```powershell
.\.venv\Scripts\python.exe scripts/inspect_dataset.py --dataset '<local dataset path>' --schema contract/dataset.schema.json --out .local/dataset-inspection.json
```

The inspector reads local data and writes the requested report; it does not repair records, access sources, infer city population or produce reliability scores. Its candidate duplicate groups and missing card numbers are indicators, not independently confirmed duplicate/lost source events. Local inspection reports are excluded from publication. The supplied candidate dataset is published explicitly at `data/datasets/communal-outages-2026.json`; contract acceptance does not mean it is suitable for a complete rating. Heating season start is 2026-10-12, supplied by the dataset owner for the main part of the city without an accompanying source URL.

## Rating status and next boundary

The rating implementation is covered by frozen synthetic rules, contract and guard tests. The approved 0.005 hour tolerance (owner decision A) lets the published dataset pass `read_dataset`: 20 houses, 2682 events, no contract issues. The source rounds durations to two decimals, so the stored value is authoritative within that tolerance; the engine uses `duration_hours`, not a recomputation from endpoints. A complete score is still unavailable because `city_houses.total` is null, 1083 events have unknown kind and 16 of 20 houses have unknown services; `evaluate` returns a partial report with `BASELINE_UNAVAILABLE`, `UNKNOWN_KIND` and `SERVICE_UNKNOWN` diagnostics instead of a score.

FastAPI remains a future thin adapter: formulas, validation and null handling belong to this library, not routes. Do not mark the associated rating task Done until the real-data decision, the real-data integration and the required application checks are complete. A green synthetic library run is not a certified reliability claim, not a continuous-coverage claim, and not application readiness.
