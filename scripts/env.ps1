# Apply only to the shell that dot-sources this script.
$workspace = Split-Path -Parent $PSScriptRoot
$env:VIRTUAL_ENV = Join-Path $workspace '.venv'
$env:PATH = (Join-Path $env:VIRTUAL_ENV 'Scripts') + [IO.Path]::PathSeparator + $env:PATH
$env:TEMP = Join-Path $workspace '.local\tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $workspace '.local\pip-cache'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:PIP_CACHE_DIR | Out-Null
