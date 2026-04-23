param(
  [string]$Path = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$defaultOutputRoot = Join-Path $repoRoot "runtime\exports\release_packages"
$ledgerPath = Join-Path $defaultOutputRoot "release_ledger.jsonl"

function Resolve-VerificationTarget([string]$targetPath) {
  if ([string]::IsNullOrWhiteSpace($targetPath)) {
    if (-not (Test-Path $defaultOutputRoot)) {
      throw "No release artifact path was provided and the default release output folder does not exist: $defaultOutputRoot"
    }

    $latestZip = Get-ChildItem -Path $defaultOutputRoot -File -Filter "*.zip" |
      Sort-Object LastWriteTimeUtc -Descending |
      Select-Object -First 1

    if ($null -eq $latestZip) {
      throw "No release zip was found under: $defaultOutputRoot"
    }

    return $latestZip.FullName
  }

  if ([System.IO.Path]::IsPathRooted($targetPath)) {
    return (Resolve-Path $targetPath).Path
  }

  return (Resolve-Path (Join-Path $repoRoot $targetPath)).Path
}

function Normalize-RelativePath([string]$value) {
  if ([string]::IsNullOrWhiteSpace($value)) { return "" }

  $normalized = [regex]::Replace($value.Trim(), '[\\/]+', '/')
  while ($normalized.StartsWith('./')) {
    $normalized = $normalized.Substring(2)
  }
  while ($normalized.StartsWith('/')) {
    $normalized = $normalized.Substring(1)
  }
  return $normalized
}

function Add-CheckResult([System.Collections.ArrayList]$failures, [bool]$condition, [string]$successMessage, [string]$failureMessage) {
  if ($condition) {
    Write-Host ("[OK]   " + $successMessage)
    return
  }

  [void]$failures.Add($failureMessage)
  Write-Host ("[FAIL] " + $failureMessage)
}

function Get-ZipPayload([string]$zipPath) {
  Add-Type -AssemblyName System.IO.Compression
  Add-Type -AssemblyName System.IO.Compression.FileSystem

  $archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
  try {
    $entryPaths = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    $manifestEntry = $archive.Entries |
      Where-Object { $_.FullName.Replace('\', '/') -match '(^|/)package_manifest.json$' } |
      Select-Object -First 1

    if ($null -eq $manifestEntry) {
      throw "package_manifest.json was not found in zip: $zipPath"
    }

    $reader = New-Object System.IO.StreamReader($manifestEntry.Open())
    try {
      $manifestText = $reader.ReadToEnd()
    } finally {
      $reader.Dispose()
    }

    $manifestEntryPath = $manifestEntry.FullName.Replace('\', '/')
    $rootPrefix = ""
    if ($manifestEntryPath -match '^([^/]+)/package_manifest\.json$') {
      $rootPrefix = [string]$Matches[1]
    }

    $relativeEntryPaths = @()
    foreach ($entryPath in $entryPaths) {
      $candidate = [string]$entryPath.TrimStart('/')
      if (-not [string]::IsNullOrWhiteSpace($rootPrefix) -and $candidate.StartsWith($rootPrefix + '/')) {
        $candidate = $candidate.Substring($rootPrefix.Length + 1)
      }
      if (-not [string]::IsNullOrWhiteSpace($candidate)) {
        $relativeEntryPaths += $candidate
      }
    }

    return [ordered]@{
      root_type = "zip"
      root_path = $zipPath
      manifest = ($manifestText | ConvertFrom-Json)
      entry_paths = $entryPaths
      relative_entry_paths = $relativeEntryPaths
    }
  } finally {
    $archive.Dispose()
  }
}

function Get-DirectoryPayload([string]$directoryPath) {
  $manifestPath = Join-Path $directoryPath "package_manifest.json"
  if (-not (Test-Path $manifestPath)) {
    throw "package_manifest.json was not found under: $directoryPath"
  }

  $relativeEntryPaths = @()
  foreach ($entry in Get-ChildItem -Path $directoryPath -Recurse -Force -ErrorAction SilentlyContinue) {
    $candidate = $entry.FullName.Substring($directoryPath.Length).TrimStart([char[]]@('\', '/'))
    if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
    $candidate = $candidate.Replace('\', '/')
    if ($entry.PSIsContainer) {
      $candidate += "/"
    }
    $relativeEntryPaths += $candidate
  }

  return [ordered]@{
    root_type = "directory"
    root_path = $directoryPath
    manifest = (Get-Content -Raw $manifestPath | ConvertFrom-Json)
    entry_paths = @()
    relative_entry_paths = $relativeEntryPaths
  }
}

function Test-PayloadHasRelativePath([hashtable]$payload, [string]$relativePath) {
  $normalized = Normalize-RelativePath $relativePath
  if ([string]::IsNullOrWhiteSpace($normalized)) { return $false }

  foreach ($entryPath in @($payload.relative_entry_paths)) {
    $candidate = [string]$entryPath.TrimEnd('/')
    if ($candidate -eq $normalized) { return $true }
  }
  return $false
}

function Test-PayloadContainsRelativePrefix([hashtable]$payload, [string]$relativePrefix) {
  $normalized = Normalize-RelativePath $relativePrefix
  if ([string]::IsNullOrWhiteSpace($normalized)) { return $false }

  foreach ($entryPath in @($payload.relative_entry_paths)) {
    $candidate = [string]$entryPath.TrimEnd('/')
    if ($candidate -eq $normalized) { return $true }
    if ($candidate.StartsWith($normalized + '/')) { return $true }
  }
  return $false
}

function Test-PayloadContainsPathSegment([hashtable]$payload, [string]$segmentName) {
  $normalized = [string]$segmentName.Trim()
  if ([string]::IsNullOrWhiteSpace($normalized)) { return $false }

  foreach ($entryPath in @($payload.relative_entry_paths)) {
    foreach ($segment in ([string]$entryPath.Trim('/')).Split('/')) {
      if ($segment -eq $normalized) {
        return $true
      }
    }
  }
  return $false
}

function Test-PayloadContainsLeafPattern([hashtable]$payload, [string]$pattern) {
  if ([string]::IsNullOrWhiteSpace($pattern)) { return $false }

  foreach ($entryPath in @($payload.relative_entry_paths)) {
    $candidate = [string]$entryPath.TrimEnd('/')
    if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
    $leaf = Split-Path -Path $candidate -Leaf
    if ($leaf -like $pattern) {
      return $true
    }
  }
  return $false
}

$targetPath = Resolve-VerificationTarget $Path
$targetItem = Get-Item $targetPath
$payload = if ($targetItem.PSIsContainer) {
  Get-DirectoryPayload $targetItem.FullName
} else {
  Get-ZipPayload $targetItem.FullName
}

$manifest = $payload.manifest
$failures = New-Object System.Collections.ArrayList
$manifestPropertyNames = @($manifest.PSObject.Properties.Name)
$requiredManifestProperties = @(
  "schema_version",
  "package_name",
  "artifact_type",
  "artifact_version",
  "release_channel",
  "built_at",
  "bootstrap_entrypoint",
  "validation_commands",
  "validation_profiles",
  "includes",
  "excludes"
)
$requiredValidationCommands = @(
  ".\\nova.cmd doctor",
  ".\\nova.cmd runtime-status",
  ".\\nova.cmd smoke-base --fix",
  ".\\nova.cmd smoke --fix",
  ".\\nova.cmd test"
)
$requiredProfileKeys = @(
  "base_package",
  "runtime_model",
  "fresh_machine_checklist",
  "validation_record_template"
)
$requiredPackageFiles = @(
  "nova.cmd",
  "nova.ps1",
  "requirements.txt",
  "docs/FRESH_MACHINE_VALIDATION.md",
  "docs/RC_VALIDATION_TEMPLATE.md"
)
$forbiddenPathPrefixes = @(
  ".ci_venv",
  ".venv",
  "knowledge/packs",
  "knowledge/peims",
  "knowledge/web",
  "logs",
  "memory",
  "runtime",
  "updates"
)
$forbiddenExactPaths = @(
  "LAST_SESSION.json",
  "RESUME_HERE.txt",
  "nova_memory.sqlite"
)
$forbiddenLeafPatterns = @(
  "*.log",
  "*.pyc",
  "*.pyo"
)

Write-Host ""
Write-Host "NYO System Package Verification"
Write-Host "-------------------------------"
Write-Host ("[INFO] Target         : " + $targetItem.FullName)
Write-Host ("[INFO] Target type    : " + $payload.root_type)

foreach ($propertyName in $requiredManifestProperties) {
  Add-CheckResult $failures ($manifestPropertyNames -contains $propertyName) ("manifest field present: " + $propertyName) ("manifest field missing: " + $propertyName)
}

Add-CheckResult $failures ($manifest.schema_version -eq 1) "schema_version == 1" ("unexpected schema_version: " + $manifest.schema_version)
Add-CheckResult $failures ($manifest.artifact_type -eq "source-bootstrap-zip") "artifact_type is source-bootstrap-zip" ("unexpected artifact_type: " + $manifest.artifact_type)
Add-CheckResult $failures (-not [string]::IsNullOrWhiteSpace([string]$manifest.artifact_version)) "artifact_version is populated" "artifact_version is blank"
Add-CheckResult $failures (-not [string]::IsNullOrWhiteSpace([string]$manifest.release_channel)) "release_channel is populated" "release_channel is blank"
Add-CheckResult $failures (-not [string]::IsNullOrWhiteSpace([string]$manifest.bootstrap_entrypoint)) "bootstrap_entrypoint is populated" "bootstrap_entrypoint is blank"

$manifestValidationCommands = @($manifest.validation_commands)
foreach ($requiredCommand in $requiredValidationCommands) {
  Add-CheckResult $failures ($manifestValidationCommands -contains $requiredCommand) ("validation command present: " + $requiredCommand) ("validation command missing: " + $requiredCommand)
}

$profileNames = @($manifest.validation_profiles.PSObject.Properties.Name)
foreach ($profileKey in $requiredProfileKeys) {
  Add-CheckResult $failures ($profileNames -contains $profileKey) ("validation profile present: " + $profileKey) ("validation profile missing: " + $profileKey)
}

foreach ($packageFile in $requiredPackageFiles) {
  Add-CheckResult $failures (Test-PayloadHasRelativePath $payload $packageFile) ("artifact file present: " + $packageFile) ("artifact file missing: " + $packageFile)
}

$profileDocs = @(
  [string]$manifest.validation_profiles.fresh_machine_checklist,
  [string]$manifest.validation_profiles.validation_record_template
)
foreach ($profileDoc in $profileDocs) {
  Add-CheckResult $failures (Test-PayloadHasRelativePath $payload $profileDoc) ("profile reference resolves: " + $profileDoc) ("profile reference missing from artifact: " + $profileDoc)
}

foreach ($forbiddenPrefix in $forbiddenPathPrefixes) {
  Add-CheckResult $failures (-not (Test-PayloadContainsRelativePrefix $payload $forbiddenPrefix)) ("forbidden path absent: " + $forbiddenPrefix) ("forbidden path present: " + $forbiddenPrefix)
}

foreach ($forbiddenPath in $forbiddenExactPaths) {
  Add-CheckResult $failures (-not (Test-PayloadHasRelativePath $payload $forbiddenPath)) ("forbidden path absent: " + $forbiddenPath) ("forbidden path present: " + $forbiddenPath)
}

Add-CheckResult $failures (-not (Test-PayloadContainsPathSegment $payload "__pycache__")) "forbidden cache path absent: __pycache__" "forbidden cache path present: __pycache__"

foreach ($forbiddenPattern in $forbiddenLeafPatterns) {
  Add-CheckResult $failures (-not (Test-PayloadContainsLeafPattern $payload $forbiddenPattern)) ("forbidden file pattern absent: " + $forbiddenPattern) ("forbidden file pattern present: " + $forbiddenPattern)
}

Write-Host ("[INFO] Version        : " + [string]$manifest.artifact_version)
Write-Host ("[INFO] Channel        : " + [string]$manifest.release_channel)
if (-not [string]::IsNullOrWhiteSpace([string]$manifest.release_label)) {
  Write-Host ("[INFO] Label          : " + [string]$manifest.release_label)
}

if ($failures.Count -gt 0) {
  Write-Host ""
  Write-Host ("[FAIL] Package verification failed with " + $failures.Count + " issue(s).")
  exit 1
}

if (Test-Path $ledgerPath) {
  $verificationEntry = [ordered]@{
    recorded_at = (Get-Date).ToString("o")
    event = "verify"
    artifact_kind = "package-zip"
    artifact_name = if ($payload.root_type -eq "zip") { [string]$targetItem.Name } else { [string]$manifest.package_name }
    artifact_path = [string]$targetItem.FullName
    artifact_version = [string]$manifest.artifact_version
    release_channel = [string]$manifest.release_channel
    release_label = [string]$manifest.release_label
    verification_result = "pass"
    verification_target_type = [string]$payload.root_type
    verification_target_path = [string]$targetItem.FullName
    verification_note = "manifest_and_content_ok"
    validation_record_seed_path = ""
  }
  Add-Content -Path $ledgerPath -Value (($verificationEntry | ConvertTo-Json -Compress))
}

Write-Host ""
Write-Host "[OK]   Package verification passed."
exit 0