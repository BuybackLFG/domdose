param(
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $candidate = Join-Path $workspace '.venv\Scripts\python.exe'
    if (Test-Path $candidate) {
        $Python = $candidate
    } elseif ($env:PYTHON) {
        $Python = $env:PYTHON
    } else {
        throw 'Python interpreter not found. Pass -Python <path> or create .venv in the workspace.'
    }
}
if (-not (Test-Path $Python)) {
    throw "Python interpreter not found: $Python"
}

$env:TEMP = Join-Path $workspace '.local\tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $workspace '.local\pip-cache'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = $workspace
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:PIP_CACHE_DIR | Out-Null

Push-Location $workspace
try {
    $basetemp = Join-Path $env:TEMP ('check-library-' + [guid]::NewGuid().ToString('N'))
    & $Python -B -m pytest tests -q --basetemp=$basetemp
    if ($LASTEXITCODE -ne 0) { throw 'Library tests failed.' }
    & $Python -B -m ruff check core contract rating tests scripts/inspect_dataset.py scripts/rating_readiness.py
    if ($LASTEXITCODE -ne 0) { throw 'Library lint failed.' }
    & $Python -B -m ruff format --check rating scripts/rating_readiness.py
    if ($LASTEXITCODE -ne 0) { throw 'Rating formatting check failed.' }
    Write-Output 'Library checks passed: synthetic tests and lint only. Application checks (scripts/check.sh) and real-data rating are separate.'
} finally {
    Pop-Location
}
