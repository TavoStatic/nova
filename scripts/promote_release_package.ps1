param(
  [string]$Artifact = "",
  [string]$Version = "",
  [string]$Channel = "",
  [string]$ArtifactKind = "package-zip",
  [string]$Result = "",
  [string]$Note = "",
  [string]$Owner = "",
  [string]$Machine = "",
  [string]$Record = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$ledgerPath = Join-Path $repoRoot "runtime\exports\release_packages\release_ledger.jsonl"

function Get-RecordField([string[]]$lines, [string]$label) {
  foreach ($line in $lines) {
    $trimmed = [string]$line
    if ($trimmed -match ('^\s*-\s*' + [regex]::Escape($label) + '\s*:\s*(.*)$')) {
      return [string]$Matches[1]
    }
  }
  return ""
}

function Get-EntryArtifactKind($entry) {
  $kind = [string]$entry.artifact_kind
  if ([string]::IsNullOrWhiteSpace($kind)) {
    return "package-zip"
  }
  return $kind
}

if (-not [string]::IsNullOrWhiteSpace($Record)) {
  $recordPath = if ([System.IO.Path]::IsPathRooted($Record)) {
    (Resolve-Path $Record).Path
  } else {
    (Resolve-Path (Join-Path $repoRoot $Record)).Path
  }

  $recordLines = Get-Content $recordPath
  if ([string]::IsNullOrWhiteSpace($Artifact)) { $Artifact = Get-RecordField $recordLines "Artifact path" }
  if ([string]::IsNullOrWhiteSpace($Version)) { $Version = Get-RecordField $recordLines "Artifact version" }
  if ([string]::IsNullOrWhiteSpace($Channel)) { $Channel = Get-RecordField $recordLines "Release channel" }
  if ([string]::IsNullOrWhiteSpace($Machine)) { $Machine = Get-RecordField $recordLines "Machine or VM name" }
  if ([string]::IsNullOrWhiteSpace($Owner)) { $Owner = Get-RecordField $recordLines "Follow-up owner" }
  if ([string]::IsNullOrWhiteSpace($Result)) { $Result = Get-RecordField $recordLines "Result" }

  $blockingIssues = Get-RecordField $recordLines "Blocking issues"
  $nonBlockingIssues = Get-RecordField $recordLines "Non-blocking issues"
  if ([string]::IsNullOrWhiteSpace($Note)) {
    $noteParts = @()
    if (-not [string]::IsNullOrWhiteSpace($blockingIssues)) { $noteParts += ("blocking=" + $blockingIssues) }
    if (-not [string]::IsNullOrWhiteSpace($nonBlockingIssues)) { $noteParts += ("non_blocking=" + $nonBlockingIssues) }
    $Note = ($noteParts -join "; ")
  }
}

if (-not (Test-Path $ledgerPath)) {
  Write-Host ("[FAIL] Release ledger not found: " + $ledgerPath)
  exit 1
}

$validResults = @("pass", "pass-with-notes", "fail")
if ([string]::IsNullOrWhiteSpace($Result) -or ($validResults -notcontains $Result)) {
  Write-Host "[FAIL] --result is required and must be one of: pass, pass-with-notes, fail"
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

$candidateEntries = @($entries | Where-Object { [string]$_.event -eq "build" })
$candidateEntries = @($candidateEntries | Where-Object { (Get-EntryArtifactKind $_) -eq $ArtifactKind })
if (-not [string]::IsNullOrWhiteSpace($Artifact)) {
  $artifactLeaf = Split-Path $Artifact -Leaf
  $candidateEntries = @($candidateEntries | Where-Object {
    ([string]$_.artifact_path -eq $Artifact) -or ([string]$_.artifact_name -eq $artifactLeaf)
  })
}
if (-not [string]::IsNullOrWhiteSpace($Version)) {
  $candidateEntries = @($candidateEntries | Where-Object { [string]$_.artifact_version -eq $Version })
}
if (-not [string]::IsNullOrWhiteSpace($Channel)) {
  $candidateEntries = @($candidateEntries | Where-Object { [string]$_.release_channel -eq $Channel })
}

$targetEntry = $candidateEntries | Sort-Object { [datetime]$_.recorded_at } -Descending | Select-Object -First 1
if ($null -eq $targetEntry) {
  Write-Host "[FAIL] No matching build entry was found to promote."
  exit 1
}

$machineName = if ([string]::IsNullOrWhiteSpace($Machine)) { $env:COMPUTERNAME } else { $Machine }
$promotionEntry = [ordered]@{
  recorded_at = (Get-Date).ToString("o")
  event = "promotion"
  artifact_kind = Get-EntryArtifactKind $targetEntry
  artifact_name = [string]$targetEntry.artifact_name
  artifact_path = [string]$targetEntry.artifact_path
  stage_dir = [string]$targetEntry.stage_dir
  manifest_path = [string]$targetEntry.manifest_path
  artifact_version = [string]$targetEntry.artifact_version
  version_source = [string]$targetEntry.version_source
  version_sequence = $targetEntry.version_sequence
  release_channel = [string]$targetEntry.release_channel
  release_label = [string]$targetEntry.release_label
  validation_result = $Result
  validation_note = $Note
  follow_up_owner = $Owner
  validation_machine = $machineName
  validation_record_seed_path = [string]$targetEntry.validation_record_seed_path
  validation_record_path = if ([string]::IsNullOrWhiteSpace($Record)) { "" } else { $recordPath }
}

Add-Content -Path $ledgerPath -Value (($promotionEntry | ConvertTo-Json -Compress))

Write-Host ""
Write-Host "NYO System Release Artifact Promotion"
Write-Host "------------------------------------"
Write-Host ("[OK]   Artifact kind : " + [string]$promotionEntry.artifact_kind)
Write-Host ("[OK]   Result         : " + $Result)
Write-Host ("[OK]   Version        : " + [string]$targetEntry.artifact_version)
Write-Host ("[OK]   Channel        : " + [string]$targetEntry.release_channel)
if (-not [string]::IsNullOrWhiteSpace([string]$targetEntry.release_label)) {
  Write-Host ("[OK]   Label          : " + [string]$targetEntry.release_label)
}
Write-Host ("[OK]   Artifact       : " + [string]$targetEntry.artifact_path)
Write-Host ("[OK]   Ledger         : " + $ledgerPath)
if (-not [string]::IsNullOrWhiteSpace($Note)) {
  Write-Host ("[INFO] Note           : " + $Note)
}
if (-not [string]::IsNullOrWhiteSpace($Owner)) {
  Write-Host ("[INFO] Follow-up owner: " + $Owner)
}

exit 0