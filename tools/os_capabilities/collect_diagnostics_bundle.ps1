param(
    [string]$ArgsJson = "{}"
)

$ErrorActionPreference = "Stop"

function Write-JsonResult {
    param([hashtable]$Payload)
    $Payload | ConvertTo-Json -Depth 8 -Compress
}

function Read-Tail {
    param(
        [string]$Path,
        [int]$Lines = 80
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return @()
    }
    try {
        return @(Get-Content -LiteralPath $Path -Tail $Lines -ErrorAction Stop)
    } catch {
        return @("tail_failed:$($_.Exception.Message)")
    }
}

try {
    $argsObject = $ArgsJson | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-JsonResult @{
        ok = $false
        error = "invalid_args_json"
        detail = $_.Exception.Message
    }
    exit 2
}

$label = [string]($argsObject.label)
if (-not $label) {
    $label = "diagnostics"
}
$safeLabel = ($label -replace "[^A-Za-z0-9_.-]", "_").Trim("_")
if (-not $safeLabel) {
    $safeLabel = "diagnostics"
}
$includeRuntimeTail = [bool]($argsObject.include_runtime_tail)

$base = (Get-Location).Path
$outDir = Join-Path $base "runtime\os_capability_evidence"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$bundlePath = Join-Path $outDir "$timestamp`_$safeLabel.json"
$runtimeDir = Join-Path $base "runtime"

$runtimeFiles = @(
    "core.heartbeat",
    "autonomy_maintenance_state.json",
    "operator_outbox.jsonl",
    "os_capability_ledger.jsonl",
    "health.log"
)

$fileSummaries = @()
foreach ($name in $runtimeFiles) {
    $path = Join-Path $runtimeDir $name
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $item = Get-Item -LiteralPath $path
        $fileSummaries += [pscustomobject]@{
            path = "runtime\$name"
            size_bytes = [int64]$item.Length
            last_write_utc = $item.LastWriteTimeUtc.ToString("o")
        }
    }
}

$tails = @{}
if ($includeRuntimeTail) {
    foreach ($name in $runtimeFiles) {
        $path = Join-Path $runtimeDir $name
        $tails[$name] = Read-Tail $path 80
    }
}

$bundle = [ordered]@{
    schema = "nova.os_capability_diagnostics_bundle.v1"
    created_utc = (Get-Date).ToUniversalTime().ToString("o")
    label = $label
    base_dir = $base
    runtime_files = $fileSummaries
    runtime_tails = $tails
}

$bundle | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $bundlePath -Encoding UTF8
$item = Get-Item -LiteralPath $bundlePath

Write-JsonResult @{
    ok = $true
    bundle_path = $bundlePath
    output_path = $bundlePath
    writes = @($bundlePath)
    size_bytes = [int64]$item.Length
    runtime_file_count = $fileSummaries.Count
    include_runtime_tail = $includeRuntimeTail
    errors = @()
}
exit 0
