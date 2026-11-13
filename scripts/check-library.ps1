$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace '.venv\Scripts\python.exe'
$env:TEMP = Join-Path $workspace '.local\tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $workspace '.local\pip-cache'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:PIP_CACHE_DIR | Out-Null
Push-Location $workspace
try {
    & $python -m pytest tests/test_dataset.py tests/test_config_logging.py tests/test_architecture.py tests/test_instrument.py
    if ($LASTEXITCODE -ne 0) { throw 'Foundation tests failed.' }
    & $python -m pytest tests/test_rating_instrument.py
    if ($LASTEXITCODE -ne 0) { throw 'Rating instrument checks failed.' }
    & $python -m ruff check core contract
    if ($LASTEXITCODE -ne 0) { throw 'Library lint failed.' }
    Write-Output 'Foundation checks passed. Rating implementation and application integration are not checked by this command.'
} finally {
    Pop-Location
}
