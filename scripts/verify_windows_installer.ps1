param(
  [string]$Path = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$installerRoot = Join-Path $repoRoot "runtime\exports\installers"
$ledgerPath = Join-Path $repoRoot "runtime\exports\release_packages\release_ledger.jsonl"

function Get-EntryArtifactKind($entry) {
  $kind = [string]$entry.artifact_kind
  if ([string]::IsNullOrWhiteSpace($kind)) {
    return "package-zip"
  }
  return $kind
}

function Resolve-VerificationTarget([string]$targetPath) {
  if ([string]::IsNullOrWhiteSpace($targetPath)) {
    if (-not (Test-Path $installerRoot)) {
      throw "No installer artifact path was provided and the default installer output folder does not exist: $installerRoot"
    }

    $latestInstaller = Get-ChildItem -Path $installerRoot -File -Filter "nyo-system-installer-*.exe" |
      Sort-Object LastWriteTimeUtc -Descending |
      Select-Object -First 1

    if ($null -eq $latestInstaller) {
      throw "No installer executable was found under: $installerRoot"
    }

    return $latestInstaller.FullName
  }

  if ([System.IO.Path]::IsPathRooted($targetPath)) {
    return (Resolve-Path $targetPath).Path
  }

  return (Resolve-Path (Join-Path $repoRoot $targetPath)).Path
}

function Add-CheckResult([System.Collections.ArrayList]$failures, [bool]$condition, [string]$successMessage, [string]$failureMessage) {
  if ($condition) {
    Write-Host ("[OK]   " + $successMessage)
    return
  }

  [void]$failures.Add($failureMessage)
  Write-Host ("[FAIL] " + $failureMessage)
}

if (-not (Test-Path $ledgerPath)) {
  Write-Host ("[FAIL] Release ledger not found: " + $ledgerPath)
  exit 1
}

try {
  $targetPath = Resolve-VerificationTarget $Path
} catch {
  Write-Host ("[FAIL] " + $_.Exception.Message)
  exit 1
}

$targetItem = Get-Item $targetPath
$entries = @()
foreach ($line in Get-Content $ledgerPath) {
  if ([string]::IsNullOrWhiteSpace($line)) { continue }
  try {
    $entry = $line | ConvertFrom-Json
  } catch {
    continue
  }
  $entries += $entry
}

$buildEntry = $entries |
  Where-Object {
    [string]$_.event -eq "build" -and
    (Get-EntryArtifactKind $_) -eq "windows-installer" -and
    [string]$_.artifact_path -eq $targetItem.FullName
  } |
  Sort-Object { [datetime]$_.recorded_at } -Descending |
  Select-Object -First 1

$packageBuildEntry = $null
$packageVerifyEntry = $null
if ($null -ne $buildEntry) {
  $packageBuildEntry = $entries |
    Where-Object {
      [string]$_.event -eq "build" -and
      (Get-EntryArtifactKind $_) -eq "package-zip" -and
      [string]$_.artifact_path -eq [string]$buildEntry.source_package_artifact_path
    } |
    Sort-Object { [datetime]$_.recorded_at } -Descending |
    Select-Object -First 1

  if ($null -ne $packageBuildEntry) {
    $packageVerifyEntry = $entries |
      Where-Object {
        [string]$_.event -eq "verify" -and
        (Get-EntryArtifactKind $_) -eq "package-zip" -and
        [string]$_.artifact_path -eq [string]$packageBuildEntry.artifact_path
      } |
      Sort-Object { [datetime]$_.recorded_at } -Descending |
      Select-Object -First 1
  }
}

$failures = New-Object System.Collections.ArrayList

Write-Host ""
Write-Host "NYO System Installer Verification"
Write-Host "---------------------------------"
Write-Host ("[INFO] Target         : " + $targetItem.FullName)

Add-CheckResult $failures ($targetItem.Extension.ToLowerInvariant() -eq ".exe") "artifact has .exe extension" ("artifact is not an .exe file: " + $targetItem.FullName)
Add-CheckResult $failures ($targetItem.Length -gt 0) "artifact file is non-empty" "artifact file is empty"
Add-CheckResult $failures ($null -ne $buildEntry) "installer build entry exists in release ledger" "installer build entry missing from release ledger"

if ($null -ne $buildEntry) {
  Add-CheckResult $failures (-not [string]::IsNullOrWhiteSpace([string]$buildEntry.artifact_version)) "artifact_version is populated" "artifact_version is blank"
  Add-CheckResult $failures (-not [string]::IsNullOrWhiteSpace([string]$buildEntry.release_channel)) "release_channel is populated" "release_channel is blank"
  Add-CheckResult $failures (-not [string]::IsNullOrWhiteSpace([string]$buildEntry.source_package_artifact_path)) "source package path is recorded" "source package path is blank"

  if (-not [string]::IsNullOrWhiteSpace([string]$buildEntry.source_package_artifact_path)) {
    Add-CheckResult $failures (Test-Path ([string]$buildEntry.source_package_artifact_path)) "source package artifact still exists" ("source package artifact missing: " + [string]$buildEntry.source_package_artifact_path)
  }
}

Add-CheckResult $failures ($null -ne $packageBuildEntry) "source package build entry exists in release ledger" "source package build entry missing from release ledger"
Add-CheckResult $failures ($null -ne $packageVerifyEntry) "source package verify entry exists in release ledger" "source package verify entry missing from release ledger"

if ($failures.Count -gt 0) {
  Write-Host ""
  Write-Host ("[FAIL] Installer verification failed with " + $failures.Count + " issue(s).")
  exit 1
}

$verificationEntry = [ordered]@{
  recorded_at = (Get-Date).ToString("o")
  event = "verify"
  artifact_kind = "windows-installer"
  artifact_name = [string]$buildEntry.artifact_name
  artifact_path = [string]$buildEntry.artifact_path
  artifact_version = [string]$buildEntry.artifact_version
  release_channel = [string]$buildEntry.release_channel
  release_label = [string]$buildEntry.release_label
  verification_result = "pass"
  verification_target_type = "file"
  verification_target_path = [string]$targetItem.FullName
  verification_note = "installer_file_and_package_provenance_ok"
  validation_record_seed_path = [string]$buildEntry.validation_record_seed_path
}
Add-Content -Path $ledgerPath -Value (($verificationEntry | ConvertTo-Json -Compress))

Write-Host ""
Write-Host "[OK]   Installer verification passed."
exit 0