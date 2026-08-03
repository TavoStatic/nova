param(
  [string]$Python = "",
  [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  $OutputDir = Join-Path $repoRoot "runtime\exports\setup_exe"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

function Resolve-Python {
  param([string]$Preferred)
  if ($Preferred -and (Test-Path $Preferred)) { return $Preferred }
  $venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
  if (Test-Path $venvPy) { return $venvPy }
  $cmd = Get-Command py -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  throw "No Python found to build NovaSetup.exe"
}

$py = Resolve-Python -Preferred $Python
Write-Host "Using Python: $py"
Write-Host "Installing/ensuring PyInstaller..."
if ($py -like "*py.exe") {
  & $py -3.12 -m pip install --upgrade pyinstaller
  $buildPyArgs = @("-3.12", "-m", "PyInstaller")
  $runner = $py
} else {
  & $py -m pip install --upgrade pyinstaller
  $buildPyArgs = @("-m", "PyInstaller")
  $runner = $py
}

$entry = Join-Path $repoRoot "scripts\nova_setup_gui.py"
$work = Join-Path $OutputDir "build_work"
New-Item -ItemType Directory -Path $work -Force | Out-Null

$args = $buildPyArgs + @(
  "--noconfirm",
  "--clean",
  "--windowed",
  "--onefile",
  "--name", "NovaSetup",
  "--paths", $repoRoot,
  "--distpath", $OutputDir,
  "--workpath", (Join-Path $work "work"),
  "--specpath", (Join-Path $work "spec"),
  # Collect package data used by wizard-adjacent imports if frozen later.
  "--hidden-import", "services.nova_setup_wizard",
  "--hidden-import", "services.sock_service",
  "--hidden-import", "tkinter",
  "--hidden-import", "tkinter.ttk",
  "--hidden-import", "tkinter.scrolledtext",
  "--hidden-import", "tkinter.messagebox",
  $entry
)

Write-Host "Building NovaSetup.exe..."
if ($runner -like "*py.exe") {
  & $runner @args
} else {
  & $runner @args
}
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed with exit $LASTEXITCODE"
}

$exe = Join-Path $OutputDir "NovaSetup.exe"
if (-not (Test-Path $exe)) {
  throw "NovaSetup.exe was not produced at $exe"
}

# Convenience copy to package root for double-click during development.
$rootCopy = Join-Path $repoRoot "NovaSetup.exe"
Copy-Item -Path $exe -Destination $rootCopy -Force

Write-Host ""
Write-Host "[OK] Built: $exe"
Write-Host "[OK] Copied: $rootCopy"
Write-Host "Double-click NovaSetup.exe to run the GUI setup wizard."
exit 0
