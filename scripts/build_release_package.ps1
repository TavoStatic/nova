param(
  [string]$Output = "",
  [string]$Label = "",
  [string]$Version = "",
  [string]$Channel = "rc",
  [switch]$KeepStage,
  [int]$RetainZipCount = 12
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

$artifactParts = @("nova-platform", $channelToken, $versionToken)
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
  ".github",
  ".ci_venv",
  ".venv",
  ".pytest_cache",
  "__pycache__",
  "knowledge\packs",
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
  "This_is_nova",
  "tests_to_review.txt",
  "full_suite_out.txt",
  "runtime_full_suite_out.txt",
  "discovery_results_phase_i.txt",
  "nova_memory.sqlite"
)

$forbiddenStagePaths = @(
  ".github",
  ".ci_venv",
  ".venv",
  ".pytest_cache",
  "knowledge\internal",
  "knowledge\packs",
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

function Test-ExcludedRelativePath([string]$relativePath) {
  $normalized = ($relativePath -replace '\\', '/').TrimStart('/')
  if ([string]::IsNullOrWhiteSpace($normalized)) { return $true }
  foreach ($dir in $excludeDirs) {
    $dirToken = ($dir -replace '\\', '/').Trim('/')
    if ($normalized -eq $dirToken -or $normalized.StartsWith("$dirToken/")) {
      return $true
    }
  }
  foreach ($fileName in $excludeFiles) {
    if ($normalized -eq $fileName) {
      return $true
    }
  }
  return $false
}

function Get-StageSourceFiles([string]$rootPath) {
  $files = New-Object System.Collections.Generic.List[string]
  Get-ChildItem -Path $rootPath -Recurse -File -Force | ForEach-Object {
    $relative = $_.FullName.Substring($rootPath.Length).TrimStart('\', '/')
    if (Test-ExcludedRelativePath $relative) { return }
    $files.Add(($relative -replace '\\', '/'))
  }
  return ,$files.ToArray()
}

$trackedFiles = @()
$gitDir = Join-Path $repoRoot ".git"
if (Test-Path $gitDir) {
  $trackedRaw = & git -C $repoRoot ls-files -z
  if ($LASTEXITCODE -ne 0) {
    throw "git ls-files failed with exit code $LASTEXITCODE"
  }
  foreach ($entry in ($trackedRaw -split "`0")) {
    if (-not [string]::IsNullOrWhiteSpace($entry)) {
      $trackedFiles += $entry
    }
  }
} else {
  $trackedFiles = Get-StageSourceFiles $repoRoot
}
if ($trackedFiles.Count -eq 0) {
  throw "No source files found for release packaging"
}

foreach ($relPath in $trackedFiles) {
  $normalized = $relPath -replace '/', '\'
  $src = Join-Path $repoRoot $normalized
  if (-not (Test-Path $src)) { continue }
  $dest = Join-Path $stageDir $normalized
  $destParent = Split-Path $dest -Parent
  if (-not (Test-Path $destParent)) {
    New-Item -ItemType Directory -Force -Path $destParent | Out-Null
  }
  Copy-Item -Path $src -Destination $dest -Force
}

# Root packaging honesty: staged imports under services/ must exist in the package.
# git-ls-files packaging silently drops untracked modules and then nova test fails
# with ModuleNotFoundError (observed: services.decision_proposal_judge).
$importPattern = "from\s+services\.([A-Za-z0-9_]+)\s+import|import\s+services\.([A-Za-z0-9_]+)"
$stagedPy = Get-ChildItem -Path $stageDir -Recurse -File -Filter "*.py" -ErrorAction SilentlyContinue
$missingModules = New-Object System.Collections.Generic.List[string]
foreach ($py in $stagedPy) {
  $text = Get-Content -LiteralPath $py.FullName -Raw -ErrorAction SilentlyContinue
  if ([string]::IsNullOrWhiteSpace($text)) { continue }
  foreach ($match in [regex]::Matches($text, $importPattern)) {
    $mod = $match.Groups[1].Value
    if ([string]::IsNullOrWhiteSpace($mod)) { $mod = $match.Groups[2].Value }
    if ([string]::IsNullOrWhiteSpace($mod)) { continue }
    $modPath = Join-Path $stageDir ("services\" + $mod + ".py")
    $modPkg = Join-Path $stageDir ("services\" + $mod + "\__init__.py")
    if (-not (Test-Path $modPath) -and -not (Test-Path $modPkg)) {
      $relativePyPath = $py.FullName.Substring($stageDir.Length).TrimStart([char[]]@('\\', '/'))
      $missingModules.Add("$relativePyPath imports services.$mod (missing from package)")
    }
  }
}
if ($missingModules.Count -gt 0) {
  Write-Host "[FAIL] Package stage is incomplete - imported services modules missing:"
  $missingModules | Select-Object -Unique | ForEach-Object { Write-Host ("  - " + $_) }
  throw "Release package incomplete: missing services modules."
}

foreach ($relativePath in $forbiddenStagePaths) {
  Remove-StageRelativePath $stageDir $relativePath
}

$validationActionsScaffold = Join-Path $stageDir "runtime\validation\actions"
New-Item -ItemType Directory -Force -Path $validationActionsScaffold | Out-Null
Set-Content -Encoding UTF8 -Path (Join-Path $validationActionsScaffold ".keep") -Value "release package validation action scaffold"

# Remove pipeline-local lane artifacts that can contain credentials or sensitive operator data.
Get-ChildItem -Path (Join-Path $stageDir "data_sources") -Recurse -File -Force -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -eq "local_config.json" -or
    $_.Name -eq "operator_intake.jsonl" -or
    $_.Name -eq "lane_control.json"
  } |
  ForEach-Object { Remove-Item -Force $_.FullName }

Get-ChildItem -Path $stageDir -Recurse -Directory -Force -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -eq "__pycache__" } |
  ForEach-Object { Remove-Item -Recurse -Force $_.FullName }

Get-ChildItem -Path $stageDir -Recurse -File -Force -Include *.pyc,*.pyo -ErrorAction SilentlyContinue |
  ForEach-Object { Remove-Item -Force $_.FullName }

Get-ChildItem -Path $stageDir -Recurse -File -Force -Include *.log -ErrorAction SilentlyContinue |
  ForEach-Object { Remove-Item -Force $_.FullName }

Get-ChildItem -Path $stageDir -Recurse -Directory -Force -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like "codex_pulse_test_*" -or $_.Name -like "codex_reflect_*" } |
  ForEach-Object { Remove-Item -Recurse -Force $_.FullName }

Get-ChildItem -Path $stageDir -Recurse -File -Force -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -eq "This_is_nova" -or
    $_.Name -eq "tests_to_review.txt" -or
    $_.Name -like "codex_health_*.jsonl" -or
    $_.Name -like "codex_reflection_*.jsonl"
  } |
  ForEach-Object { Remove-Item -Force $_.FullName }

$manifestPath = Join-Path $stageDir "package_manifest.json"
$manifest = [ordered]@{
  schema_version = 1
  package_name = "Nova Base"
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
    ".\\nova.cmd wiring-check --offline",
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
    "git-tracked source files only",
    "docs",
    "tests",
    "templates and static assets",
    "requirements.txt",
    "policy.json",
    "piper runtime assets",
    "runtime/validation/actions/.keep scaffold"
  )
  excludes = @(
    ".github",
    ".ci_venv",
    ".venv",
    ".pytest_cache",
    "knowledge/packs",
    "knowledge/web",
    "data_sources/*/local_config.json",
    "data_sources/*/operator_intake.jsonl",
    "data_sources/*/lane_control.json",
    "nova_memory.sqlite",
    "runtime state except runtime/validation/actions/.keep scaffold",
    "logs",
    "memory",
    "updates",
    "interpreter caches",
    "ad hoc local status files",
    "operator-only notes",
    "codex scratch telemetry"
  )
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $manifestPath

Compress-Archive -Path $stageDir -DestinationPath $zipPath -CompressionLevel Optimal

$releaseLabelText = if ([string]::IsNullOrWhiteSpace($labelToken)) { "" } else { $labelToken }
$validationRecord = @(
  "# Nova RC Validation Record",
  "",
  ("Date: {0}" -f (Get-Date -Format "yyyy-MM-dd")),
  "",
  "Use this prefilled record for the fresh-machine or VM validation pass.",
  "",
  "## Candidate",
  "",
  ("- Artifact path: {0}" -f $zipPath),
  ("- Artifact version: {0}" -f $versionToken),
  ("- Version source: {0}" -f $versionInfo.source),
  ("- Release channel: {0}" -f $channelToken),
  ("- Release label: {0}" -f $releaseLabelText),
  "- Manifest reviewed: yes/no",
  ("- Release ledger path: {0}" -f $ledgerPath),
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

$removedZipCount = 0
if ($RetainZipCount -gt 0) {
  $oldZipArtifacts = Get-ChildItem -Path $outputRoot -File -Filter "*.zip" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -Skip $RetainZipCount
  foreach ($oldZip in @($oldZipArtifacts)) {
    Remove-Item -LiteralPath $oldZip.FullName -Force
    $removedZipCount += 1
  }
}

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
  stage_retained = [bool]$KeepStage
  retained_zip_count = $RetainZipCount
  removed_old_zip_count = $removedZipCount
}
Add-Content -Path $ledgerPath -Value (($ledgerEntry | ConvertTo-Json -Compress))

Write-Host ""
Write-Host "Nova Release Package"
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
Write-Host ("[OK]   Zip retention  : kept latest " + $RetainZipCount + ", removed " + $removedZipCount)
Write-Host "[INFO] Bootstrap after extract: .\\nova.cmd install"

if ($KeepStage) {
  Write-Host "[INFO] Stage directory retained for inspection because -KeepStage was provided."
} else {
  Remove-Item -Recurse -Force $stageDir
  Write-Host "[INFO] Stage directory removed after zip creation. Use -KeepStage to retain it."
}
