# Standalone Python library

This additive package is separate from the existing backend/frontend application. It currently implements process settings, explicit logging and dataset 1.0 contracts. Rating rules are specified and tested against test-only instruments, but the `rating` implementation is not present yet.

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
.\.venv\Scripts\python.exe -m ruff check core contract tests scripts/inspect_dataset.py
```

`scripts/check-library.ps1` runs the implemented foundation checks and rating instrument calibration only. It is NOT a substitute for the existing application's `scripts/check.sh`. Running the entire root test directory currently fails collection because `rating` is not implemented. Keep that pending suite; do not suppress it or report the full suite green.

## Public interfaces

- `core.config.Settings`, `get_settings`, `SettingsRefused`: frozen settings; explicit arguments > environment > UTF-8 dotenv > declared defaults. Only log level and optional log file are configured.
- `core.logging.setup_logging`, `get_logger`: explicit named-logger setup; no handlers/files on import and no global root logger modification.
- `contract.dataset.Dataset`, `read_dataset`, `dataset_schema`: immutable typed dataset; schema and semantic validation without reading dataset files or environment. Nullable facts remain nullable; empty datasets are permitted.
- `contract.errors.ContractRefused`, `ContractIssue`: sanitized machine-readable code/path errors.

For JSON input use `read_dataset(mapping_or_json_or_bytes)`. Validation refuses malformed structure, duplicate IDs/keys, invalid references, inconsistent dates/times/durations and nonfinite/negative relevant numbers. It does not infer missing facts, normalize addresses or judge source truth. Direct model construction is not a replacement for whole-dataset semantic validation.

`contract/dataset.schema.json` is the unchanged supplied schema. The library validates Draft 2020-12 format and adds semantic invariants documented in `SPEC.md`. Duration agreement currently requires tolerance 1e-9 hours; two-decimal rounded durations may be refused. Do not widen this tolerance without a separately approved contract change.

## Dataset inspection

```powershell
.\.venv\Scripts\python.exe scripts/inspect_dataset.py --dataset '<local dataset path>' --schema contract/dataset.schema.json --out .local/dataset-inspection.json
```

The inspector reads local data and writes the requested report; it does not repair records, access sources, infer city population or produce reliability scores. Its candidate duplicate groups and missing card numbers are indicators, not independently confirmed duplicate/lost source events. Local inspection reports are excluded from publication. The supplied candidate dataset is published explicitly at `data/datasets/communal-outages-2026.json`; its inclusion does not mean that it passes the semantic gate or is suitable for a complete rating. Heating season start is 2026-10-12, supplied by the dataset owner for the main part of the city without an accompanying source URL.

## Next boundary

Implement `rating.evaluate` and the public request/report DTOs against the frozen synthetic tests and `SPEC.md`. FastAPI remains a future thin adapter; formulas, validation and null handling belong to the library, not routes. Do not mark the associated rating task Done until the computation, real-data integration and required application checks are complete.
