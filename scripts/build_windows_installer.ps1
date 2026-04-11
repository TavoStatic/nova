param(
  [string]$Artifact = "",
  [string]$Output = "",
  [string]$Compiler = "",
  [switch]$SkipPackageVerify,
  [switch]$KeepPayload
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$verifyScript = Join-Path $scriptRoot "verify_release_package.ps1"
$installerScript = Join-Path $repoRoot "installer\NYO_System.iss"
$defaultPackageRoot = Join-Path $repoRoot "runtime\exports\release_packages"
$releaseLedgerPath = Join-Path $defaultPackageRoot "release_ledger.jsonl"

function Resolve-WorkingPath([string]$value, [string]$defaultPath) {
  if ([string]::IsNullOrWhiteSpace($value)) {
    return $defaultPath
  }
  if ([System.IO.Path]::IsPathRooted($value)) {
    return [System.IO.Path]::GetFullPath($value)
  }
  return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $value))
}

function Resolve-InstallerArtifact([string]$targetPath) {
  if ([string]::IsNullOrWhiteSpace($targetPath)) {
    if (-not (Test-Path $defaultPackageRoot)) {
      throw "Default package output folder not found: $defaultPackageRoot"
    }
    $latestZip = Get-ChildItem -Path $defaultPackageRoot -File -Filter "*.zip" |
      Sort-Object LastWriteTimeUtc -Descending |
      Select-Object -First 1
    if ($null -eq $latestZip) {
      throw "No package artifact was found under: $defaultPackageRoot"
    }
    return $latestZip.FullName
  }

  return (Resolve-WorkingPath $targetPath $targetPath)
}

function Resolve-InnoCompiler([string]$providedPath) {
  if (-not [string]::IsNullOrWhiteSpace($providedPath)) {
    $candidate = Resolve-WorkingPath $providedPath $providedPath
    if (Test-Path $candidate) {
      return $candidate
    }
    throw "Requested Inno Setup compiler was not found: $candidate"
  }

  foreach ($name in @("ISCC.exe", "iscc.exe", "iscc")) {
    try {
      $cmd = Get-Command $name -ErrorAction SilentlyContinue
      if ($cmd -and -not [string]::IsNullOrWhiteSpace([string]$cmd.Source)) {
        return [string]$cmd.Source
      }
    } catch {
    }
  }

  $programFilesX86 = [Environment]::GetFolderPath("ProgramFilesX86")
  $programFiles = [Environment]::GetFolderPath("ProgramFiles")
  $commonCandidates = @(
    (Join-Path $programFilesX86 "Inno Setup 6\ISCC.exe"),
    (Join-Path $programFilesX86 "Inno Setup 5\ISCC.exe"),
    (Join-Path $programFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path $programFiles "Inno Setup 5\ISCC.exe")
  ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

  foreach ($candidate in $commonCandidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }

  throw "Inno Setup compiler not found. Install Inno Setup 6 or pass -Compiler <path-to-ISCC.exe>."
}

function Invoke-InnoCompiler([string]$compilerPath, [string]$issPath) {
  $extension = [System.IO.Path]::GetExtension($compilerPath).ToLowerInvariant()
  if ($extension -eq ".ps1") {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $compilerPath $issPath | ForEach-Object { Write-Host $_ }
    return [int]$LASTEXITCODE
  }

  & $compilerPath $issPath | ForEach-Object { Write-Host $_ }
  return [int]$LASTEXITCODE
}

function Expand-InstallerPayloadZip([string]$zipPath, [string]$destinationPath) {
  Add-Type -AssemblyName System.IO.Compression
  Add-Type -AssemblyName System.IO.Compression.FileSystem

  if (Test-Path $destinationPath) {
    Remove-Item -Recurse -Force $destinationPath
  }

  [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $destinationPath)
}

if (-not (Test-Path $installerScript)) {
  Write-Host ("[FAIL] Missing installer definition: " + $installerScript)
  exit 1
}

$artifactPath = Resolve-InstallerArtifact $Artifact
if (-not (Test-Path $artifactPath)) {
  Write-Host ("[FAIL] Package artifact not found: " + $artifactPath)
  exit 1
}

if ([System.IO.Path]::GetExtension($artifactPath).ToLowerInvariant() -ne ".zip") {
  Write-Host ("[FAIL] Installer build currently expects a package zip artifact: " + $artifactPath)
  exit 1
}

if (-not $SkipPackageVerify) {
  if (-not (Test-Path $verifyScript)) {
    Write-Host ("[FAIL] Missing package verifier: " + $verifyScript)
    exit 1
  }
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyScript $artifactPath
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Package verification failed; installer build aborted."
    exit $LASTEXITCODE
  }
}

try {
  $compilerPath = Resolve-InnoCompiler $Compiler
} catch {
  Write-Host ("[FAIL] " + $_.Exception.Message)
  exit 1
}

$outputRoot = Resolve-WorkingPath $Output (Join-Path $repoRoot "runtime\exports\installers")
$payloadStageRoot = Join-Path $outputRoot "_payload"
$artifactStem = [System.IO.Path]::GetFileNameWithoutExtension($artifactPath)
$extractRoot = Join-Path $payloadStageRoot "pkg"
$validationRecordRoot = Join-Path $outputRoot "validation_records"

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
New-Item -ItemType Directory -Force -Path $payloadStageRoot | Out-Null
New-Item -ItemType Directory -Force -Path $validationRecordRoot | Out-Null

if (Test-Path $extractRoot) {
  Remove-Item -Recurse -Force $extractRoot
}

Expand-InstallerPayloadZip -zipPath $artifactPath -destinationPath $extractRoot

$manifestPath = Get-ChildItem -Path $extractRoot -Recurse -File -Filter "package_manifest.json" |
  Select-Object -First 1

if ($null -eq $manifestPath) {
  Write-Host ("[FAIL] Extracted package did not contain package_manifest.json: " + $artifactPath)
  exit 1
}

$payloadDir = $manifestPath.Directory.FullName
$manifest = Get-Content -Raw -Encoding UTF8 $manifestPath.FullName | ConvertFrom-Json
$appVersion = [string]$manifest.artifact_version
if ([string]::IsNullOrWhiteSpace($appVersion)) {
  $appVersion = $artifactStem
}

$expectedInstallerPath = Join-Path $outputRoot ("nyo-system-installer-" + $appVersion + ".exe")
$validationRecordPath = Join-Path $validationRecordRoot ("nyo-system-installer-" + $appVersion + ".md")
if (Test-Path $expectedInstallerPath) {
  Remove-Item -Force $expectedInstallerPath
}
if (Test-Path $validationRecordPath) {
  Remove-Item -Force $validationRecordPath
}

$previousPayloadDir = $env:NYO_PAYLOAD_DIR
$previousAppVersion = $env:NYO_APP_VERSION
$previousOutputDir = $env:NYO_INSTALLER_OUTPUT_DIR

$env:NYO_PAYLOAD_DIR = $payloadDir
$env:NYO_APP_VERSION = $appVersion
$env:NYO_INSTALLER_OUTPUT_DIR = $outputRoot

try {
  $compileCode = Invoke-InnoCompiler $compilerPath $installerScript
  if ($compileCode -ne 0) {
    Write-Host ("[FAIL] Inno Setup compiler exited with code " + $compileCode)
    exit $compileCode
  }
  if (-not (Test-Path $expectedInstallerPath)) {
    Write-Host ("[FAIL] Installer compile finished but expected output was not found: " + $expectedInstallerPath)
    exit 1
  }
} finally {
  $env:NYO_PAYLOAD_DIR = $previousPayloadDir
  $env:NYO_APP_VERSION = $previousAppVersion
  $env:NYO_INSTALLER_OUTPUT_DIR = $previousOutputDir
}

if (-not $KeepPayload -and (Test-Path $extractRoot)) {
  Remove-Item -Recurse -Force $extractRoot
}

$validationRecord = @(
  "# NYO System Installer Validation Record",
  "",
  "Date: " + (Get-Date -Format "yyyy-MM-dd"),
  "",
  "Use this record after building and manually validating the installer executable.",
  "",
  "## Candidate",
  "",
  "- Artifact path: " + $expectedInstallerPath,
  "- Artifact version: " + $appVersion,
  "- Release channel: " + [string]$manifest.release_channel,
  "- Release label: " + [string]$manifest.release_label,
  "- Source package artifact: " + $artifactPath,
  "- Release ledger path: " + $releaseLedgerPath,
  "",
  "## Build Provenance",
  "",
  "- Package manifest path: " + $manifestPath.FullName,
  "- Compiler path: " + $compilerPath,
  "- Payload source: " + $payloadDir,
  "",
  "## Validation",
  "",
  "- Installer launches:",
  "- Guided install flow:",
  "- Base-only install flow:",
  "- nova doctor:",
  "- nova runtime-status:",
  "- nova smoke-base --fix:",
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

if (Test-Path $releaseLedgerPath) {
  $ledgerEntry = [ordered]@{
    recorded_at = (Get-Date).ToString("o")
    event = "build"
    artifact_kind = "windows-installer"
    artifact_name = (Split-Path $expectedInstallerPath -Leaf)
    artifact_path = $expectedInstallerPath
    stage_dir = $extractRoot
    manifest_path = $manifestPath.FullName
    artifact_version = $appVersion
    version_source = [string]$manifest.version_source
    version_sequence = $manifest.version_sequence
    release_channel = [string]$manifest.release_channel
    release_label = [string]$manifest.release_label
    built_on_host = $env:COMPUTERNAME
    source_package_artifact_path = $artifactPath
    source_package_manifest_path = $manifestPath.FullName
    compiler_path = $compilerPath
    validation_record_seed_path = $validationRecordPath
  }
  Add-Content -Path $releaseLedgerPath -Value (($ledgerEntry | ConvertTo-Json -Compress))
}

Write-Host ""
Write-Host "[OK]   Windows installer build completed."
Write-Host ("[INFO] Package artifact : " + $artifactPath)
Write-Host ("[INFO] Installer output : " + $expectedInstallerPath)
Write-Host ("[INFO] Payload source   : " + $payloadDir)
Write-Host ("[INFO] Compiler        : " + $compilerPath)
Write-Host ("[INFO] Release ledger   : " + $releaseLedgerPath)
Write-Host ("[INFO] Validation seed  : " + $validationRecordPath)
Write-Host ""
exit 0