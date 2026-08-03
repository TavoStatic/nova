param(
  [string]$Zip = "",
  [string]$SandboxRoot = "C:\NovaSandbox",
  [int]$WebuiPort = 18088,
  [switch]$UseExe,
  [switch]$HeadlessExe
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path

if ([string]::IsNullOrWhiteSpace($Zip)) {
  $packageRoot = Join-Path $repoRoot "runtime\exports\release_packages"
  $latest = Get-ChildItem -Path $packageRoot -File -Filter "nyo-system-base-rc-*.zip" |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
  if ($null -eq $latest) { throw "No release zip under $packageRoot" }
  $Zip = $latest.FullName
}
$Zip = (Resolve-Path $Zip).Path

Write-Host "Nova Setup Wizard Sandbox"
Write-Host "-------------------------"
Write-Host ("Zip          : " + $Zip)
Write-Host ("Sandbox root : " + $SandboxRoot)

if (Test-Path $SandboxRoot) {
  try {
    Get-NetTCPConnection -LocalPort $WebuiPort -State Listen -ErrorAction SilentlyContinue |
      ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  } catch {}
  Remove-Item -LiteralPath $SandboxRoot -Recurse -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
}

$extractRoot = Join-Path $SandboxRoot "extract"
New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
Expand-Archive -Path $Zip -DestinationPath $extractRoot -Force
$novaCmd = Get-ChildItem -Path $extractRoot -Recurse -Filter "nova.cmd" | Select-Object -First 1
if ($null -eq $novaCmd) { throw "Extract missing nova.cmd" }
$pkg = $novaCmd.Directory.FullName
Write-Host ("Package root : " + $pkg)

# Overlay current setup wizard sources so sandbox tests the latest wizard against a clean package tree.
# (RC zip may predate the wizard.)
$overlay = @(
  "services\nova_setup_wizard.py",
  "services\sock_service.py",
  "scripts\run_setup_wizard.py",
  "scripts\nova_setup_gui.py",
  "nova.ps1"
)
foreach ($rel in $overlay) {
  $src = Join-Path $repoRoot $rel
  $dst = Join-Path $pkg $rel
  if (Test-Path $src) {
    $dstDir = Split-Path -Parent $dst
    New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
    Copy-Item -Path $src -Destination $dst -Force
  }
}

# Ensure package nova.ps1 can find setup script after overlay
$report = Join-Path $SandboxRoot "setup_wizard_sandbox_report.json"
$env:PYTHONUNBUFFERED = "1"
$env:NOVA_ROOT = $pkg

Push-Location $pkg
try {
  Write-Host "==> package-verify"
  & .\nova.cmd package-verify .
  if ($LASTEXITCODE -ne 0) { throw "package-verify failed" }

  if ($UseExe -or $HeadlessExe) {
    $exe = Join-Path $repoRoot "NovaSetup.exe"
    if (-not (Test-Path $exe)) {
      $exe = Join-Path $repoRoot "runtime\exports\setup_exe\NovaSetup.exe"
    }
    if (-not (Test-Path $exe)) {
      throw "NovaSetup.exe not found. Build with scripts\build_nova_setup_exe.ps1 first."
    }
    $localExe = Join-Path $pkg "NovaSetup.exe"
    Copy-Item $exe $localExe -Force
    Write-Host "==> Running REAL NovaSetup.exe against sandbox package"
    Write-Host ("    exe  = " + $localExe)
    Write-Host ("    root = " + $pkg)
    $exeArgs = @(
      "--headless",
      "--root", $pkg,
      "--webui-port", "$WebuiPort",
      "--report", $report
    )
    $p = Start-Process -FilePath $localExe -ArgumentList $exeArgs -WorkingDirectory $pkg -Wait -PassThru -NoNewWindow
    $code = [int]$p.ExitCode
    Write-Host ("NovaSetup.exe exit: " + $code)
    if (Test-Path $report) {
      Write-Host ("Report: " + $report)
      Get-Content $report -TotalCount 100
    }
    exit $code
  }

  Write-Host "==> setup wizard (CLI fallback, package root)"
  $py = Join-Path $repoRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path $py)) {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) { $py = $pyCmd.Source } else { throw "No python to run setup wizard" }
    & $py -3.12 (Join-Path $pkg "scripts\run_setup_wizard.py") --root $pkg --webui-port $WebuiPort --report $report
  } else {
    & $py -u (Join-Path $pkg "scripts\run_setup_wizard.py") --root $pkg --webui-port $WebuiPort --report $report
  }
  $code = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
  Write-Host ("Wizard exit: " + $code)
  if (Test-Path $report) {
    Write-Host ("Report: " + $report)
    Get-Content $report -TotalCount 80
  }
  exit $code
} finally {
  Pop-Location
}
