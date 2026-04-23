param(
  [string]$ArtifactKind = "package-zip",
  [switch]$Json
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$ledgerPath = Join-Path $repoRoot "runtime\exports\release_packages\release_ledger.jsonl"

function Get-EntryArtifactKind($entry) {
  $kind = [string]$entry.artifact_kind
  if ([string]::IsNullOrWhiteSpace($kind)) {
    return "package-zip"
  }
  return $kind
}

function Test-ReleaseEntryMatchesBuild($entry, $buildEntry) {
  if ($null -eq $entry -or $null -eq $buildEntry) { return $false }
  if ((Get-EntryArtifactKind $entry) -ne (Get-EntryArtifactKind $buildEntry)) { return $false }

  $entryArtifactPath = [string]$entry.artifact_path
  $buildArtifactPath = [string]$buildEntry.artifact_path
  if (-not [string]::IsNullOrWhiteSpace($entryArtifactPath) -and $entryArtifactPath -eq $buildArtifactPath) {
    return $true
  }

  $entryVersion = [string]$entry.artifact_version
  $buildVersion = [string]$buildEntry.artifact_version
  $entryChannel = [string]$entry.release_channel
  $buildChannel = [string]$buildEntry.release_channel
  $entryLabel = [string]$entry.release_label
  $buildLabel = [string]$buildEntry.release_label

  if (-not [string]::IsNullOrWhiteSpace($entryVersion) -and
      $entryVersion -eq $buildVersion -and
      $entryChannel -eq $buildChannel -and
      $entryLabel -eq $buildLabel) {
    return $true
  }

  return $false
}

if (-not (Test-Path $ledgerPath)) {
  Write-Host ("[FAIL] Release ledger not found: " + $ledgerPath)
  exit 1
}

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

$latestBuild = $entries |
  Where-Object {
    [string]$_.event -eq "build" -and
    (Get-EntryArtifactKind $_) -eq $ArtifactKind
  } |
  Sort-Object { [datetime]$_.recorded_at } -Descending |
  Select-Object -First 1
if ($null -eq $latestBuild) {
  Write-Host ("[INFO] No build entries are present in the release ledger for artifact kind: " + $ArtifactKind)
  exit 0
}

$latestVerify = $entries |
  Where-Object {
    [string]$_.event -eq "verify" -and (Test-ReleaseEntryMatchesBuild $_ $latestBuild)
  } |
  Sort-Object { [datetime]$_.recorded_at } -Descending |
  Select-Object -First 1

$latestPromotion = $entries |
  Where-Object {
    [string]$_.event -eq "promotion" -and (Test-ReleaseEntryMatchesBuild $_ $latestBuild)
  } |
  Sort-Object { [datetime]$_.recorded_at } -Descending |
  Select-Object -First 1

$readinessState = "needs-verification"
$readyToShip = $false
$readinessNote = "Latest build has not been re-verified."
if ($null -ne $latestVerify) {
  if ($null -eq $latestPromotion) {
    $readinessState = "needs-promotion"
    $readinessNote = "Latest build was verified, but no validation outcome is recorded yet."
  } else {
    $result = [string]$latestPromotion.validation_result
    switch ($result) {
      "pass" {
        $readinessState = "ready"
        $readyToShip = $true
        $readinessNote = "Latest build is verified and promoted with a pass result."
      }
      "pass-with-notes" {
        $readinessState = "ready-with-notes"
        $readyToShip = $true
        $readinessNote = "Latest build is verified and promoted with notes."
      }
      "fail" {
        $readinessState = "blocked"
        $readinessNote = "Latest build has a failing validation result."
      }
      default {
        $readinessState = "needs-promotion"
        $readinessNote = "Latest build has a promotion entry without a recognized validation result."
      }
    }
  }
}

$payload = [ordered]@{
  ok = $true
  ledger_path = $ledgerPath
  artifact_kind = $ArtifactKind
  latest_artifact_path = [string]$latestBuild.artifact_path
  latest_artifact_name = [string]$latestBuild.artifact_name
  latest_version = [string]$latestBuild.artifact_version
  latest_channel = [string]$latestBuild.release_channel
  latest_label = [string]$latestBuild.release_label
  latest_build_recorded_at = [string]$latestBuild.recorded_at
  latest_verified_at = if ($null -eq $latestVerify) { "" } else { [string]$latestVerify.recorded_at }
  latest_verification_target = if ($null -eq $latestVerify) { "" } else {
    $verificationTarget = [string]$latestVerify.verification_target_path
    if ([string]::IsNullOrWhiteSpace($verificationTarget)) {
      $verificationTarget = [string]$latestVerify.artifact_path
    }
    $verificationTarget
  }
  latest_promoted_at = if ($null -eq $latestPromotion) { "" } else { [string]$latestPromotion.recorded_at }
  latest_validation_result = if ($null -eq $latestPromotion) { "" } else { [string]$latestPromotion.validation_result }
  latest_validation_note = if ($null -eq $latestPromotion) { "" } else { [string]$latestPromotion.validation_note }
  latest_follow_up_owner = if ($null -eq $latestPromotion) { "" } else { [string]$latestPromotion.follow_up_owner }
  latest_readiness_state = $readinessState
  latest_ready_to_ship = $readyToShip
  latest_readiness_note = $readinessNote
}

if ($Json) {
  $payload | ConvertTo-Json -Depth 5
  exit 0
}

Write-Host ""
Write-Host "NYO System Release Readiness"
Write-Host "----------------------------"
Write-Host ("[OK]   Artifact kind  : " + $payload.artifact_kind)
Write-Host ("[OK]   Readiness      : " + $payload.latest_readiness_state)
Write-Host ("[OK]   Ready to ship  : " + $(if ($payload.latest_ready_to_ship) { "yes" } else { "no" }))
Write-Host ("[OK]   Version        : " + $payload.latest_version)
Write-Host ("[OK]   Channel        : " + $payload.latest_channel)
if (-not [string]::IsNullOrWhiteSpace($payload.latest_label)) {
  Write-Host ("[OK]   Label          : " + $payload.latest_label)
}
Write-Host ("[OK]   Artifact       : " + $payload.latest_artifact_path)
Write-Host ("[OK]   Built at       : " + $payload.latest_build_recorded_at)
if (-not [string]::IsNullOrWhiteSpace($payload.latest_verified_at)) {
  Write-Host ("[OK]   Verified at    : " + $payload.latest_verified_at)
}
if (-not [string]::IsNullOrWhiteSpace($payload.latest_verification_target)) {
  Write-Host ("[INFO] Verify target  : " + $payload.latest_verification_target)
}
if (-not [string]::IsNullOrWhiteSpace($payload.latest_promoted_at)) {
  Write-Host ("[OK]   Promoted at    : " + $payload.latest_promoted_at)
}
if (-not [string]::IsNullOrWhiteSpace($payload.latest_validation_result)) {
  Write-Host ("[OK]   Result         : " + $payload.latest_validation_result)
}
Write-Host ("[INFO] Note           : " + $payload.latest_readiness_note)
if (-not [string]::IsNullOrWhiteSpace($payload.latest_validation_note)) {
  Write-Host ("[INFO] Validation note: " + $payload.latest_validation_note)
}

exit 0