param(
    [string]$ArgsJson = "{}"
)

$ErrorActionPreference = "Stop"

function Write-JsonResult {
    param([hashtable]$Payload)
    $Payload | ConvertTo-Json -Depth 8 -Compress
}

try {
    $parsedArgs = $ArgsJson | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-JsonResult @{
        ok     = $false
        error  = "invalid_args_json"
        detail = $_.Exception.Message
    }
    exit 2
}

$guardLogLines = 60
if ($null -ne $parsedArgs -and $null -ne $parsedArgs.guard_log_lines) {
    $guardLogLines = [int]$parsedArgs.guard_log_lines
}
$staleAfterSeconds = 120
if ($null -ne $parsedArgs -and $null -ne $parsedArgs.stale_after_seconds) {
    $staleAfterSeconds = [int]$parsedArgs.stale_after_seconds
}

$errors = @()
$healthFindings = @()
$root = (Get-Location).Path

function Read-RuntimeJson {
    param([string]$RelPath)
    $full = Join-Path $root $RelPath
    if (-not (Test-Path -LiteralPath $full)) { return $null }
    try {
        return (Get-Content -LiteralPath $full -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop)
    } catch {
        $script:errors += "read_failed:${RelPath}:$($_.Exception.Message)"
        return $null
    }
}

function Test-PidAlive {
    param($ProcId)
    if ($null -eq $ProcId) { return $false }
    try {
        $null = Get-Process -Id ([int]$ProcId) -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# --- core process ---
$corePid = $null
$coreState = Read-RuntimeJson "runtime/core_state.json"
if ($null -ne $coreState -and $null -ne $coreState.pid) { $corePid = [int]$coreState.pid }
$coreAlive = Test-PidAlive $corePid

# --- guard process ---
$guardPid = $null
$guardState = Read-RuntimeJson "runtime/guard_pid.json"
if ($null -ne $guardState -and $null -ne $guardState.pid) { $guardPid = [int]$guardState.pid }
$guardAlive = Test-PidAlive $guardPid

# --- heartbeat age ---
$heartbeatAge = $null
$heartbeatPath = Join-Path $root "runtime/core.heartbeat"
if (Test-Path -LiteralPath $heartbeatPath) {
    try {
        $hbItem = Get-Item -LiteralPath $heartbeatPath -ErrorAction Stop
        $heartbeatAge = [math]::Round(((Get-Date) - $hbItem.LastWriteTime).TotalSeconds, 1)
    } catch {
        $errors += "heartbeat_read_failed:$($_.Exception.Message)"
    }
} else {
    $healthFindings += "heartbeat_file_missing"
}
$heartbeatStale = $false
if ($null -ne $heartbeatAge -and $heartbeatAge -gt $staleAfterSeconds) { $heartbeatStale = $true }

# --- recent guard restart causes ---
$restartCauses = @{}
$restartCount = 0
$guardLogPath = Join-Path $root "logs/guard.log"
if (Test-Path -LiteralPath $guardLogPath) {
    try {
        $tail = @(Get-Content -LiteralPath $guardLogPath -Tail $guardLogLines -ErrorAction Stop)
        foreach ($line in $tail) {
            if ($line -match "Core attempt failed:\s*(.+?)\s*$") {
                $cause = $Matches[1].Trim()
                $restartCount += 1
                if ($restartCauses.ContainsKey($cause)) {
                    $restartCauses[$cause] = $restartCauses[$cause] + 1
                } else {
                    $restartCauses[$cause] = 1
                }
            }
        }
    } catch {
        $errors += "guard_log_read_failed:$($_.Exception.Message)"
    }
} else {
    $healthFindings += "guard_log_unavailable"
}

# --- health verdict ---
if (-not $coreAlive)     { $healthFindings += "core_process_not_alive" }
if ($heartbeatStale)     { $healthFindings += "heartbeat_stale" }
if (-not $guardAlive)    { $healthFindings += "guard_process_not_alive" }
if ($restartCount -ge 3) { $healthFindings += "frequent_guard_restarts" }
$healthStatus = if ($healthFindings.Count -eq 0) { "ok" } else { "degraded" }

Write-JsonResult @{
    ok                          = ($errors.Count -eq 0)
    health_status               = $healthStatus
    health_findings             = $healthFindings
    core_pid                    = $corePid
    core_alive                  = $coreAlive
    guard_pid                   = $guardPid
    guard_alive                 = $guardAlive
    heartbeat_age_sec           = $heartbeatAge
    heartbeat_stale             = $heartbeatStale
    stale_after_seconds         = $staleAfterSeconds
    recent_guard_restart_count  = $restartCount
    recent_guard_restart_causes = $restartCauses
    guard_log_lines_scanned     = $guardLogLines
    errors                      = $errors
}
exit 0
