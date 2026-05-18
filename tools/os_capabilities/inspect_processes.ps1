param(
    [string]$ArgsJson = "{}"
)

$ErrorActionPreference = "Stop"

function Write-JsonResult {
    param([hashtable]$Payload)
    $Payload | ConvertTo-Json -Depth 8 -Compress
}

function Get-ProcessPath {
    param($Process)
    try {
        return [string]$Process.Path
    } catch {
        return ""
    }
}

try {
    $null = $ArgsJson | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-JsonResult @{
        ok = $false
        error = "invalid_args_json"
        detail = $_.Exception.Message
    }
    exit 2
}

$errors = @()
$processRows = @()

try {
    $processes = @(Get-Process -ErrorAction Stop)
    foreach ($process in $processes) {
        $processRows += [pscustomobject]@{
            id = [int]$process.Id
            name = [string]$process.ProcessName
            cpu_seconds = if ($null -ne $process.CPU) { [math]::Round([double]$process.CPU, 2) } else { $null }
            working_set_mb = [math]::Round(([double]$process.WorkingSet64 / 1MB), 2)
            path = Get-ProcessPath $process
        }
    }
} catch {
    $errors += "process_probe_failed:$($_.Exception.Message)"
}

$topMemory = @(
    $processRows |
        Sort-Object -Property working_set_mb -Descending |
        Select-Object -First 30
)

$novaRelated = @(
    $processRows |
        Where-Object {
            $_.name -match "nova|python|ollama|searx|node|pwsh|powershell" -or
            $_.path -match "NOVA|Ollama|searx"
        } |
        Sort-Object -Property name, id
)

Write-JsonResult @{
    ok = ($errors.Count -eq 0)
    process_count = $processRows.Count
    nova_related_count = $novaRelated.Count
    nova_related = $novaRelated
    top_memory = $topMemory
    errors = $errors
}
exit 0
