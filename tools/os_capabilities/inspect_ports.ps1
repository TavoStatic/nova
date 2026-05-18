param(
    [string]$ArgsJson = "{}"
)

$ErrorActionPreference = "Stop"

function Write-JsonResult {
    param([hashtable]$Payload)
    $Payload | ConvertTo-Json -Depth 8 -Compress
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

$ports = @($argsObject.ports)
if (-not $ports -or $ports.Count -eq 0) {
    $ports = @(8080, 8081, 11434)
}

$errors = @()
$rows = @()

foreach ($portValue in $ports) {
    $port = [int]$portValue
    try {
        $connections = @(Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue)
        foreach ($connection in $connections) {
            $processName = ""
            if ($connection.OwningProcess) {
                try {
                    $processName = [string](Get-Process -Id $connection.OwningProcess -ErrorAction Stop).ProcessName
                } catch {
                    $processName = ""
                }
            }
            $rows += [pscustomobject]@{
                local_address = [string]$connection.LocalAddress
                local_port = [int]$connection.LocalPort
                remote_address = [string]$connection.RemoteAddress
                remote_port = [int]$connection.RemotePort
                state = [string]$connection.State
                owning_process = [int]$connection.OwningProcess
                process_name = $processName
            }
        }
    } catch {
        $errors += "port_probe_failed:$($port):$($_.Exception.Message)"
    }
}

Write-JsonResult @{
    ok = ($errors.Count -eq 0)
    ports = $ports
    connection_count = $rows.Count
    connections = $rows
    errors = $errors
}
exit 0
