param(
    [string]$ArgsJson = "{}"
)

$ErrorActionPreference = "Stop"

function Write-JsonResult {
    param([hashtable]$Payload)
    $Payload | ConvertTo-Json -Depth 8 -Compress
}

function Get-RelativePath {
    param(
        [string]$BasePath,
        [string]$FullPath
    )
    try {
        $baseUri = [System.Uri]((Resolve-Path $BasePath).Path.TrimEnd("\") + "\")
        $fileUri = [System.Uri]((Resolve-Path $FullPath).Path)
        return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($fileUri).ToString()).Replace("/", "\")
    } catch {
        return $FullPath
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

$rootName = [string]($argsObject.root)
$limit = [int]($argsObject.limit)
if ($limit -lt 1) {
    $limit = 25
}

$base = (Get-Location).Path
$target = Join-Path $base $rootName
$errors = @()
$files = @()

if (-not (Test-Path -LiteralPath $target -PathType Container)) {
    Write-JsonResult @{
        ok = $false
        root = $rootName
        target_path = $target
        files = @()
        errors = @("root_missing:$rootName")
    }
    exit 0
}

try {
    $items = @(
        Get-ChildItem -LiteralPath $target -Recurse -File -Force -ErrorAction SilentlyContinue |
            Sort-Object -Property Length -Descending |
            Select-Object -First $limit
    )
    foreach ($item in $items) {
        $files += [pscustomobject]@{
            relative_path = Get-RelativePath $base $item.FullName
            size_bytes = [int64]$item.Length
            size_mb = [math]::Round(([double]$item.Length / 1MB), 2)
            last_write_utc = $item.LastWriteTimeUtc.ToString("o")
        }
    }
} catch {
    $errors += "scan_failed:$($_.Exception.Message)"
}

Write-JsonResult @{
    ok = ($errors.Count -eq 0)
    root = $rootName
    target_path = $target
    limit = $limit
    file_count = $files.Count
    files = $files
    errors = $errors
}
exit 0
