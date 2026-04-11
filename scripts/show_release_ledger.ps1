param(
  [int]$Count = 10,
  [string]$Channel = "",
  [string]$Version = "",
  [string]$ArtifactKind = "package-zip",
  [string]$Event = "",
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

$filteredEntries = $entries
$filteredEntries = @($filteredEntries | Where-Object { (Get-EntryArtifactKind $_) -eq $ArtifactKind })
if (-not [string]::IsNullOrWhiteSpace($Channel)) {
  $filteredEntries = @($filteredEntries | Where-Object { [string]$_.release_channel -eq $Channel })
}
if (-not [string]::IsNullOrWhiteSpace($Version)) {
  $filteredEntries = @($filteredEntries | Where-Object { [string]$_.artifact_version -eq $Version })
}
if (-not [string]::IsNullOrWhiteSpace($Event)) {
  $filteredEntries = @($filteredEntries | Where-Object { [string]$_.event -eq $Event })
}

$filteredEntries = @($filteredEntries | Sort-Object { [datetime]$_.recorded_at } -Descending | Select-Object -First $Count)

if ($Json) {
  $filteredEntries | ConvertTo-Json -Depth 5
  exit 0
}

Write-Host ""
Write-Host "NYO System Release Ledger"
Write-Host "-------------------------"
Write-Host ("[INFO] Ledger path    : " + $ledgerPath)
Write-Host ("[INFO] Returned rows : " + $filteredEntries.Count)
Write-Host ("[INFO] Artifact kind : " + $ArtifactKind)
if (-not [string]::IsNullOrWhiteSpace($Channel)) {
  Write-Host ("[INFO] Channel filter : " + $Channel)
}
if (-not [string]::IsNullOrWhiteSpace($Version)) {
  Write-Host ("[INFO] Version filter : " + $Version)
}
if (-not [string]::IsNullOrWhiteSpace($Event)) {
  Write-Host ("[INFO] Event filter   : " + $Event)
}
Write-Host ""

if ($filteredEntries.Count -eq 0) {
  Write-Host "[INFO] No matching release ledger entries."
  exit 0
}

$table = $filteredEntries | ForEach-Object {
  [pscustomobject]@{
    recorded_at = [string]$_.recorded_at
    kind = Get-EntryArtifactKind $_
    event = [string]$_.event
    version = [string]$_.artifact_version
    channel = [string]$_.release_channel
    label = [string]$_.release_label
    result = [string]$_.validation_result
    source = [string]$_.version_source
    artifact = [string]$_.artifact_name
  }
}

$table | Format-Table -AutoSize | Out-String | Write-Host

Write-Host "Latest artifact path:"
Write-Host ([string]$filteredEntries[0].artifact_path)

if ($filteredEntries[0].validation_record_seed_path) {
  Write-Host "Validation seed path:"
  Write-Host ([string]$filteredEntries[0].validation_record_seed_path)
}

if ($filteredEntries[0].validation_note) {
  Write-Host "Latest validation note:"
  Write-Host ([string]$filteredEntries[0].validation_note)
}

exit 0