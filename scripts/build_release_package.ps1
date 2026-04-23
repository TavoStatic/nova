param(
  [string]$Output = "",
  [string]$Label = "",
  [string]$Version = "",
  [string]$Channel = "rc",
  [switch]$KeepStage
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

function Get-SafeArtifactFragment([string]$value) {
  $text = if ($null -eq $value) { "" } else { [string]$value }
  $trimmed = $text.Trim()
  if ([string]::IsNullOrWhiteSpace($trimmed)) {
    return ""
  }
  return ([regex]::Replace($trimmed, "[^A-Za-z0-9._-]+", "-")).Trim('-')
}

$channelToken = Get-SafeArtifactFragment $(if ([string]::IsNullOrWhiteSpace($Channel)) { "rc" } else { $Channel })
$labelToken = Get-SafeArtifactFragment $Label

$outputRoot = if ([string]::IsNullOrWhiteSpace($Output)) {
  Join-Path $repoRoot "runtime\exports\release_packages"
} elseif ([System.IO.Path]::IsPathRooted($Output)) {
  $Output
} else {
  Join-Path $repoRoot $Output
}

$ledgerPath = Join-Path $outputRoot "release_ledger.jsonl"

function Get-AutoReleaseVersion([string]$ledgerFilePath, [string]$releaseChannel) {
  $baseVersion = Get-Date -Format "yyyy.MM.dd"
  if (-not (Test-Path $ledgerFilePath)) {
    return [ordered]@{
      token = $baseVersion
      source = "auto-date-sequence"
      sequence = 0
    }
  }

  $maxSequence = -1
  $prefixPattern = '^' + [regex]::Escape($baseVersion) + '(?:\.(\d+))?$'

  foreach ($line in Get-Content $ledgerFilePath) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }

    try {
      $entry = $line | ConvertFrom-Json
    } catch {
      continue
    }

    if ([string]$entry.event -ne "build") { continue }
    if ([string]$entry.release_channel -ne $releaseChannel) { continue }

    $entryVersion = [string]$entry.artifact_version
    if ([string]::IsNullOrWhiteSpace($entryVersion)) { continue }

    $match = [regex]::Match($entryVersion, $prefixPattern)
    if (-not $match.Success) { continue }

    $sequenceValue = if ($match.Groups[1].Success) { [int]$match.Groups[1].Value } else { 0 }
    if ($sequenceValue -gt $maxSequence) {
      $maxSequence = $sequenceValue
    }
  }

  $nextSequence = $maxSequence + 1
  $nextToken = if ($nextSequence -le 0) { $baseVersion } else { $baseVersion + "." + $nextSequence }
  return [ordered]@{
    token = $nextToken
    source = "auto-date-sequence"
    sequence = $nextSequence
  }
}

$versionInfo = if ([string]::IsNullOrWhiteSpace($Version)) {
  Get-AutoReleaseVersion -ledgerFilePath $ledgerPath -releaseChannel $channelToken
} else {
  [ordered]@{
    token = $Version
    source = "explicit"
    sequence = $null
  }
}

$versionToken = Get-SafeArtifactFragment $versionInfo.token

$artifactParts = @("nyo-system-base", $channelToken, $versionToken)
if (-not [string]::IsNullOrWhiteSpace($labelToken)) {
  $artifactParts += $labelToken
}
$artifactParts += $timestamp
$artifactStem = ($artifactParts | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "-"

$stageRoot = Join-Path $outputRoot "_stage"
$stageDir = Join-Path $stageRoot $artifactStem
$zipPath = Join-Path $outputRoot ($artifactStem + ".zip")
$validationRecordRoot = Join-Path $outputRoot "validation_records"
$validationRecordPath = Join-Path $validationRecordRoot ($artifactStem + ".md")

function Remove-StageRelativePath([string]$rootPath, [string]$relativePath) {
  if ([string]::IsNullOrWhiteSpace($relativePath)) { return }
  $targetPath = Join-Path $rootPath $relativePath
  if (Test-Path $targetPath) {
    Remove-Item -Recurse -Force $targetPath
  }
}

$excludeDirs = @(
  ".git",
  ".ci_venv",
  ".venv",
  "__pycache__",
  "knowledge\packs",
  "knowledge\peims",
  "knowledge\web",
  "logs",
  "memory",
  "runtime",
  "updates",
  "tests\__pycache__",
  "scripts\__pycache__",
  "tools\__pycache__"
)

$excludeFiles = @(
  "LAST_SESSION.json",
  "RESUME_HERE.txt",
  "full_suite_out.txt",
  "runtime_full_suite_out.txt",
  "discovery_results_phase_i.txt",
  "nova_memory.sqlite"
)

$forbiddenStagePaths = @(
  ".ci_venv",
  ".venv",
  "knowledge\packs",
  "knowledge\peims",
  "knowledge\web",
  "updates",
  "nova_memory.sqlite"
)

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null
New-Item -ItemType Directory -Force -Path $validationRecordRoot | Out-Null

if (Test-Path $stageDir) {
  Remove-Item -Recurse -Force $stageDir
}
if (Test-Path $zipPath) {
  Remove-Item -Force $zipPath
}
if (Test-Path $validationRecordPath) {
  Remove-Item -Force $validationRecordPath
}

New-Item -ItemType Directory -Force -Path $stageDir | Out-Null

$robocopyArgs = @(
  $repoRoot,
  $stageDir,
  "/E",
  "/R:1",
  "/W:1",
  "/NFL",
  "/NDL",
  "/NJH",
  "/NJS",
  "/NP"
)

if ($excludeDirs.Count -gt 0) {
  $robocopyArgs += "/XD"
  foreach ($dir in $excludeDirs) {
    $robocopyArgs += (Join-Path $repoRoot $dir)
  }
}

if ($excludeFiles.Count -gt 0) {
  $robocopyArgs += "/XF"
  foreach ($file in $excludeFiles) {
    $robocopyArgs += (Join-Path $repoRoot $file)
  }
}

& robocopy @robocopyArgs | Out-Null
$robocopyCode = $LASTEXITCODE
if ($robocopyCode -ge 8) {
  throw "robocopy failed with exit code $robocopyCode"
}

foreach ($relativePath in $forbiddenStagePaths) {
  Remove-StageRelativePath $stageDir $relativePath
}

Get-ChildItem -Path $stageDir -Recurse -Directory -Force -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -eq "__pycache__" } |
  ForEach-Object { Remove-Item -Recurse -Force $_.FullName }

Get-ChildItem -Path $stageDir -Recurse -File -Force -Include *.pyc,*.pyo -ErrorAction SilentlyContinue |
  ForEach-Object { Remove-Item -Force $_.FullName }

Get-ChildItem -Path $stageDir -Recurse -File -Force -Include *.log -ErrorAction SilentlyContinue |
  ForEach-Object { Remove-Item -Force $_.FullName }

$manifestPath = Join-Path $stageDir "package_manifest.json"
$manifest = [ordered]@{
  schema_version = 1
  package_name = "NYO System Base"
  artifact_type = "source-bootstrap-zip"
  artifact_version = $versionToken
  version_source = $versionInfo.source
  version_sequence = $versionInfo.sequence
  release_channel = $channelToken
  release_label = $labelToken
  built_at = (Get-Date).ToString("o")
  built_on_host = $env:COMPUTERNAME
  source_root = $repoRoot
  bootstrap_entrypoint = ".\\nova.cmd install"
  validation_commands = @(
    ".\\nova.cmd doctor",
    ".\\nova.cmd runtime-status",
    ".\\nova.cmd smoke-base --fix",
    ".\\nova.cmd smoke --fix",
    ".\\nova.cmd test"
  )
  validation_profiles = [ordered]@{
    base_package = ".\\nova.cmd smoke-base --fix"
    runtime_model = ".\\nova.cmd smoke --fix"
    fresh_machine_checklist = "docs\\FRESH_MACHINE_VALIDATION.md"
    validation_record_template = "docs\\RC_VALIDATION_TEMPLATE.md"
  }
  includes = @(
    "tracked source files",
    "docs",
    "tests",
    "templates and static assets",
    "requirements.txt",
    "policy.json",
    "piper runtime assets"
  )
  excludes = @(
    ".ci_venv",
    ".venv",
    "knowledge/packs",
    "knowledge/peims",
    "knowledge/web",
    "nova_memory.sqlite",
    "runtime",
    "logs",
    "memory",
    "updates",
    "interpreter caches",
    "ad hoc local status files"
  )
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $manifestPath

Compress-Archive -Path $stageDir -DestinationPath $zipPath -CompressionLevel Optimal

$validationRecord = @(
  "# NYO System RC Validation Record",
  "",
  "Date: " + (Get-Date -Format "yyyy-MM-dd"),
  "",
  "Use this prefilled record for the fresh-machine or VM validation pass.",
  "",
  "## Candidate",
  "",
  "- Artifact path: " + $zipPath,
  "- Artifact version: " + $versionToken,
  "- Version source: " + $versionInfo.source,
  "- Release channel: " + $channelToken,
  "- Release label: " + $(if ([string]::IsNullOrWhiteSpace($labelToken)) { "" } else { $labelToken }),
  "- Manifest reviewed: yes/no",
  "- Release ledger path: " + $ledgerPath,
  "",
  "## Environment",
  "",
  "- Machine or VM name:",
  "- Windows version:",
  "- Python source used during install:",
  "- Ollama expected for this target: yes/no",
  "",
  "## Results",
  "",
  "### Bootstrap",
  "",
  "- nova package-verify .:",
  "- nova install:",
  "- Notes:",
  "",
  "### Base Validation",
  "",
  "- nova doctor:",
  "- nova runtime-status:",
  "- nova smoke-base --fix:",
  "- nova test:",
  "- Notes:",
  "",
  "### Operator Surface",
  "",
  "- nova run:",
  "- nova webui-start --host 127.0.0.1 --port 8080:",
  "- /control load result:",
  "- Notes:",
  "",
  "### Extended Runtime Validation",
  "",
  "- nova smoke --fix:",
  "- Notes:",
  "",
  "## Final Decision",
  "",
  "- Result: pass / pass-with-notes / fail",
  "- Blocking issues:",
  "- Non-blocking issues:",
  "- Follow-up owner:"
)
$validationRecord | Set-Content -Encoding UTF8 $validationRecordPath

$ledgerEntry = [ordered]@{
  recorded_at = (Get-Date).ToString("o")
  event = "build"
  artifact_kind = "package-zip"
  artifact_name = (Split-Path $zipPath -Leaf)
  artifact_path = $zipPath
  stage_dir = $stageDir
  manifest_path = $manifestPath
  artifact_version = $versionToken
  version_source = $versionInfo.source
  version_sequence = $versionInfo.sequence
  release_channel = $channelToken
  release_label = $labelToken
  built_on_host = $env:COMPUTERNAME
  validation_record_seed_path = $validationRecordPath
}
Add-Content -Path $ledgerPath -Value (($ledgerEntry | ConvertTo-Json -Compress))

Write-Host ""
Write-Host "NYO System Release Package"
Write-Host "--------------------------"
Write-Host ("[OK]   Version        : " + $versionToken)
Write-Host ("[OK]   Version source : " + $versionInfo.source)
Write-Host ("[OK]   Channel        : " + $channelToken)
if (-not [string]::IsNullOrWhiteSpace($labelToken)) {
  Write-Host ("[OK]   Label          : " + $labelToken)
}
Write-Host ("[OK]   Stage directory: " + $stageDir)
Write-Host ("[OK]   Zip artifact   : " + $zipPath)
Write-Host ("[OK]   Release ledger : " + $ledgerPath)
Write-Host ("[OK]   Validation seed: " + $validationRecordPath)
Write-Host "[INFO] Bootstrap after extract: .\\nova.cmd install"

if (-not $KeepStage) {
  Write-Host "[INFO] Stage directory retained for inspection. Remove it manually when no longer needed."
}