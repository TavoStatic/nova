param(
  [string]$Zip = "",
  [string]$SandboxRoot = "C:\NovaSandbox",
  [string]$PythonLauncher = "py",
  [string]$PythonVersion = "3.12",
  [int]$WebuiPort = 18088,
  [switch]$SkipWebui,
  [switch]$KeepSandbox
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$message) {
  Write-Host ""
  Write-Host ("==> " + $message)
}

function Invoke-Checked([string]$label, [scriptblock]$action) {
  Write-Step $label
  & $action
  $code = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
  if ($code -ne 0) {
    throw ("STEP_FAILED:" + $label + " exit=" + $code)
  }
}

$repoRoot = (Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..")).Path
if ([string]::IsNullOrWhiteSpace($Zip)) {
  $packageRoot = Join-Path $repoRoot "runtime\exports\release_packages"
  $latest = Get-ChildItem -Path $packageRoot -File -Filter "nova-platform-rc-*.zip" |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
  if ($null -eq $latest) {
    throw "No release zip found under $packageRoot"
  }
  $Zip = $latest.FullName
}

$Zip = (Resolve-Path $Zip).Path
$reportPath = Join-Path $SandboxRoot "clean_install_report.json"
$extractRoot = Join-Path $SandboxRoot "extract"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Host "Nova Clean-Install Sandbox"
Write-Host "--------------------------"
Write-Host ("Zip           : " + $Zip)
Write-Host ("Sandbox root  : " + $SandboxRoot)
Write-Host ("Python        : " + $PythonLauncher + " -" + $PythonVersion)
Write-Host ("WebUI port    : " + $WebuiPort)

if (Test-Path $SandboxRoot) {
  Write-Step "Removing previous sandbox"
  # Stop any leftover webui on the sandbox port first
  try {
    Get-NetTCPConnection -LocalPort $WebuiPort -State Listen -ErrorAction SilentlyContinue |
      ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  } catch {}
  Remove-Item -LiteralPath $SandboxRoot -Recurse -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
}

New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null

Write-Step "Extracting package"
Expand-Archive -Path $Zip -DestinationPath $extractRoot -Force

$novaCmd = Get-ChildItem -Path $extractRoot -Recurse -Filter "nova.cmd" | Select-Object -First 1
if ($null -eq $novaCmd) {
  throw "Extracted package does not contain nova.cmd"
}
$pkg = $novaCmd.Directory.FullName
Write-Host ("Package root  : " + $pkg)

$results = [ordered]@{
  started_at = (Get-Date).ToString("o")
  zip = $Zip
  sandbox_root = $SandboxRoot
  package_root = $pkg
  python_version_requested = $PythonVersion
  steps = @()
}

function Add-Result([string]$name, [int]$code, [string]$detail = "") {
  $script:results.steps += [ordered]@{
    name = $name
    exit_code = $code
    ok = ($code -eq 0)
    detail = $detail
  }
}

Push-Location $pkg
try {
  # package-verify is a payload integrity check — must run BEFORE creating .venv
  Write-Step "package-verify (clean extract, no .venv yet)"
  & .\nova.cmd package-verify .
  Add-Result "package-verify" ([int]$LASTEXITCODE)

  # Force supported Python for this sandbox (do not inherit default 3.13/3.14).
  Write-Step ("Creating venv with Python " + $PythonVersion)
  $venvPython = Join-Path $pkg ".venv\Scripts\python.exe"
  & $PythonLauncher ("-" + $PythonVersion) -m venv (Join-Path $pkg ".venv")
  if (-not (Test-Path $venvPython)) {
    throw ("Failed to create venv with " + $PythonLauncher + " -" + $PythonVersion)
  }
  Add-Result "venv create" 0 ("python=" + $PythonVersion)

  Write-Step "Upgrading pip"
  & $venvPython -m pip install --upgrade pip setuptools wheel
  Add-Result "pip upgrade" ([int]$LASTEXITCODE)
  if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

  Write-Step "Installing requirements (this can take several minutes)"
  & $venvPython -m pip install -r (Join-Path $pkg "requirements.txt")
  Add-Result "pip install requirements" ([int]$LASTEXITCODE)
  if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt failed" }

  Write-Step "doctor --fix"
  & $venvPython doctor.py --fix
  Add-Result "doctor --fix" ([int]$LASTEXITCODE)

  Write-Step "doctor"
  & $venvPython doctor.py
  Add-Result "doctor" ([int]$LASTEXITCODE)

  Write-Step "wiring-check --offline"
  & .\nova.cmd wiring-check --offline
  Add-Result "wiring-check --offline" ([int]$LASTEXITCODE)

  Write-Step "smoke-base --fix"
  & .\nova.cmd smoke-base --fix
  Add-Result "smoke-base --fix" ([int]$LASTEXITCODE)

  if (-not $SkipWebui) {
    Write-Step ("webui-start port " + $WebuiPort)
    & .\nova.cmd webui-start --host 127.0.0.1 --port $WebuiPort
    $webuiStart = [int]$LASTEXITCODE
    Add-Result "webui-start" $webuiStart

    $healthOk = $false
    if ($webuiStart -eq 0) {
      try {
        $r = Invoke-WebRequest -UseBasicParsing ("http://127.0.0.1:" + $WebuiPort + "/api/health") -TimeoutSec 8
        $healthOk = ($r.StatusCode -eq 200)
        Add-Result "webui /api/health" ($(if ($healthOk) { 0 } else { 1 })) ("status=" + $r.StatusCode)
      } catch {
        Add-Result "webui /api/health" 1 ([string]$_.Exception.Message)
      }
    }

    Write-Step "webui-stop"
    & .\nova.cmd webui-stop --port $WebuiPort
    Add-Result "webui-stop" ([int]$LASTEXITCODE)
  }
} finally {
  Pop-Location
}

$results.finished_at = (Get-Date).ToString("o")
$failed = @($results.steps | Where-Object { -not $_.ok })
$results.ok = ($failed.Count -eq 0)
$results.failed_steps = @($failed | ForEach-Object { $_.name })
$results.python_report = (& $venvPython --version 2>&1 | Out-String).Trim()

$results | ConvertTo-Json -Depth 6 | Set-Content -Path $reportPath -Encoding UTF8

Write-Host ""
Write-Host "Sandbox report: $reportPath"
Write-Host ("Overall OK   : " + $results.ok)
if (-not $results.ok) {
  Write-Host ("Failed steps : " + ($results.failed_steps -join ", "))
  exit 1
}

Write-Host "[OK] Clean-install sandbox passed T1/T2 checks on this host."
exit 0
