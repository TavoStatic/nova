Param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

if (Test-Path $venvPy) {
    & $venvPy (Join-Path $root "run_regression.py")
} else {
    python (Join-Path $root "run_regression.py")
}

exit $LASTEXITCODE
