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

$latestPromotion = $entries |
  Where-Object {
    [string]$_.event -eq "promotion" -and
    (Get-EntryArtifactKind $_) -eq $ArtifactKind -and
    [string]$_.artifact_path -eq [string]$latestBuild.artifact_path
  } |
  Sort-Object { [datetime]$_.recorded_at } -Descending |
  Select-Object -First 1

$state = if ($null -eq $latestPromotion) {
  "built-only"
} else {
  $result = [string]$latestPromotion.validation_result
  if ([string]::IsNullOrWhiteSpace($result)) { "promoted" } else { "promoted-" + $result }
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
  latest_validation_seed_path = [string]$latestBuild.validation_record_seed_path
  latest_state = $state
  promoted = ($null -ne $latestPromotion)
  latest_validation_result = if ($null -eq $latestPromotion) { "" } else { [string]$latestPromotion.validation_result }
  latest_validation_note = if ($null -eq $latestPromotion) { "" } else { [string]$latestPromotion.validation_note }
  latest_follow_up_owner = if ($null -eq $latestPromotion) { "" } else { [string]$latestPromotion.follow_up_owner }
  latest_validation_machine = if ($null -eq $latestPromotion) { "" } else { [string]$latestPromotion.validation_machine }
  latest_promoted_at = if ($null -eq $latestPromotion) { "" } else { [string]$latestPromotion.recorded_at }
}

if ($Json) {
  $payload | ConvertTo-Json -Depth 5
  exit 0
}

Write-Host ""
Write-Host "NYO System Release Status"
Write-Host "-------------------------"
Write-Host ("[OK]   Artifact kind  : " + $payload.artifact_kind)
Write-Host ("[OK]   State          : " + $payload.latest_state)
Write-Host ("[OK]   Version        : " + $payload.latest_version)
Write-Host ("[OK]   Channel        : " + $payload.latest_channel)
if (-not [string]::IsNullOrWhiteSpace($payload.latest_label)) {
  Write-Host ("[OK]   Label          : " + $payload.latest_label)
}
Write-Host ("[OK]   Artifact       : " + $payload.latest_artifact_path)
Write-Host ("[OK]   Built at       : " + $payload.latest_build_recorded_at)
if (-not [string]::IsNullOrWhiteSpace($payload.latest_promoted_at)) {
  Write-Host ("[OK]   Promoted at    : " + $payload.latest_promoted_at)
}
if (-not [string]::IsNullOrWhiteSpace($payload.latest_validation_result)) {
  Write-Host ("[OK]   Result         : " + $payload.latest_validation_result)
}
if (-not [string]::IsNullOrWhiteSpace($payload.latest_validation_note)) {
  Write-Host ("[INFO] Note           : " + $payload.latest_validation_note)
}
if (-not [string]::IsNullOrWhiteSpace($payload.latest_follow_up_owner)) {
  Write-Host ("[INFO] Follow-up owner: " + $payload.latest_follow_up_owner)
}
if (-not [string]::IsNullOrWhiteSpace($payload.latest_validation_seed_path)) {
  Write-Host ("[INFO] Validation seed: " + $payload.latest_validation_seed_path)
}

exit 0