param(
  # Subcommand: look | lookfull | chat | camera | ls | read | find | run | webui | webui-start | webui-stop | webui-status | hub | smoke | test | health | guard | install | update | diag | logs | mem | config
  [Parameter(Position=0)]
  [string]$cmd = "help",

  # Everything else after the subcommand
  [Parameter(ValueFromRemainingArguments=$true)]
  [string[]]$remainingTokens
)

# =========================
# Nova PowerShell Front Door
# =========================
# Goal:
# - One "nova <command>" interface for everything
# - Stable argument passing (spaces/quotes)
# - Room to grow (guard, health, memory, logs, config)
# - NO breaking changes (features can be commented until ready)

$ROOT      = if ($PSScriptRoot) { $PSScriptRoot } else { "C:\Nova" }
$venvPython = Join-Path $ROOT ".venv\Scripts\python.exe"

# --- Core scripts (adjust these only if you rename files) ---
$LOOK_CROP = Join-Path $ROOT "look_crop.py"
$LOOK_FULL = Join-Path $ROOT "look.py"
$CAMERA    = Join-Path $ROOT "camera.py"
$AGENT     = Join-Path $ROOT "agent.py"
$CORE      = Join-Path $ROOT "nova_core.py"
$SMOKEPY   = Join-Path $ROOT "smoke_test.py"
$REGRESSION = Join-Path $ROOT "run_regression.py"
$RUN_TOOLS = Join-Path $ROOT "run_tools.py"   # optional
$CHATPY    = Join-Path $ROOT "chat_client.py" # unified text chat client
$WEBUIPY   = Join-Path $ROOT "nova_http.py"   # network UI/API
$HEALTHPY  = Join-Path $ROOT "health.py"      # optional
$MEMORYPY  = Join-Path $ROOT "memory.py"      # optional
$DOCTORPY  = Join-Path $ROOT "doctor.py"      # preflight validator
$POLICY    = Join-Path $ROOT "policy.json"    # optional
$LOG_DIR   = Join-Path $ROOT "logs"

# --- Optional future scripts (commented until you create them) ---
$GUARDPY   = Join-Path $ROOT "nova_guard.py"  # FUTURE: supervisor/auto-restart
$DIAGPY    = Join-Path $ROOT "diag.py"        # FUTURE: full diagnostics report
$CONFIG    = Join-Path $ROOT "config\nova.json" # FUTURE: unified config
$MEM_DIR   = Join-Path $ROOT "memory"         # FUTURE: hardened memory folder
$STOPPY = Join-Path $ROOT "stop_guard.py"

# ======================
# Helpers (do not remove)
# ======================
function Join-Args([string[]]$tokenList) {
  if ($null -eq $tokenList) { return "" }
  return ($tokenList -join " ").Trim()
}

function Ensure-Python {
  if (-not (Test-Path $venvPython)) {
    Write-Host ""
    Write-Host "[FAIL] venv python not found at: $venvPython"
    Write-Host "       Make sure your venv exists at C:\Nova\.venv"
    Write-Host ""
    exit 1
  }
}

function Ensure-Logs {
  if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null }
}

function Run-Py([string]$script, [string[]]$scriptTokens=@()) {
  Ensure-Python
  if (-not (Test-Path $script)) {
    Write-Host ""
    Write-Host "[FAIL] Missing script: $script"
    Write-Host ""
    exit 1
  }
  & $venvPython $script @scriptTokens
  exit $LASTEXITCODE
}

function Run-Ollama([string[]]$ollamaTokens=@()) {
  # "ollama" should be on PATH if installed
  & ollama @ollamaTokens
  exit $LASTEXITCODE
}

function Run-DoctorPreflight([bool]$useFix=$false) {
  Ensure-Python
  if (-not (Test-Path $DOCTORPY)) {
    Write-Host "[FAIL] Missing preflight validator: $DOCTORPY"
    return $false
  }
  if ($useFix) {
    & $venvPython $DOCTORPY --fix --quiet
  } else {
    & $venvPython $DOCTORPY --quiet
  }
  if ($LASTEXITCODE -ne 0) {
    if ($useFix) {
      Write-Host "[FAIL] Preflight failed after --fix. Run: nova doctor"
    } else {
      Write-Host "[FAIL] Preflight failed. Run: nova doctor or nova doctor --fix"
    }
    return $false
  }
  return $true
}

function Get-NovaHttpProcesses {
  return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Name -match '^python(\.exe)?$' -and
      ($_.CommandLine -match 'nova_http\.py')
    })
}

function Get-NovaHttpLogicalProcesses {
  $all = @(Get-NovaHttpProcesses)
  if (-not $all -or $all.Count -eq 0) { return @() }

  $parentIds = @{}
  foreach ($p in $all) {
    $parentIds[[int]$p.ParentProcessId] = $true
  }

  $leaf = @($all | Where-Object { -not $parentIds.ContainsKey([int]$_.ProcessId) })
  if ($leaf.Count -gt 0) { return $leaf }
  return $all
}

function Stop-NovaHttpProcesses {
  $procs = Get-NovaHttpProcesses
  if (-not $procs -or $procs.Count -eq 0) {
    Write-Host "[INFO] No nova_http.py processes running."
    return 0
  }
  foreach ($p in $procs) {
    try {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
      Write-Host ("[OK]   Stopped nova_http pid=" + $p.ProcessId)
    } catch {
      Write-Host ("[WARN] Failed to stop pid=" + $p.ProcessId)
    }
  }
  return $procs.Count
}

function Stop-NovaHttpExcept([int]$keepPid) {
  $procs = Get-NovaHttpProcesses | Where-Object { $_.ProcessId -ne $keepPid }
  foreach ($p in $procs) {
    try {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
      Write-Host ("[OK]   Stopped extra nova_http pid=" + $p.ProcessId)
    } catch {}
  }
}

function Show-Help {
  Write-Host ""
  Write-Host "Nova commands:"
  Write-Host "  nova help"
  Write-Host "  nova look                      # center-crop screenshot -> vision"
  Write-Host "  nova lookfull                  # full screenshot -> vision"
  Write-Host "  nova chat                      # unified API chat (/api/chat)"
  Write-Host "  nova camera                    # webcam snapshot -> vision"
  Write-Host "  nova camera ""your prompt""      # webcam with custom prompt"
  Write-Host "  nova hub                       # menu: chat / look / camera"
  Write-Host ""
  Write-Host "File tools (via agent.py):"
  Write-Host "  nova ls [folder]"
  Write-Host "  nova read <file>"
  Write-Host "  nova find ""keyword"" [folder]"
  Write-Host ""
  Write-Host "Runtime:"
  Write-Host "  nova doctor [--fix]            # startup preflight validator"
  Write-Host "  nova run [--fix]               # Nova core (voice + tools)"
  Write-Host "  nova webui [--host 0.0.0.0 --port 8080]  # network web interface"
  Write-Host "  nova webui-start [--host 127.0.0.1 --port 8080] [--fix]  # start webui in background"
  Write-Host "  nova webui-stop                # stop all nova_http processes"
  Write-Host "  nova webui-status [--port 8080] # show webui pids + endpoint check"
  Write-Host "  nova smoke [--fix]             # doctor -> guard -> smoke_test -> stop"
  Write-Host "  nova test                      # compact regression checks"
  Write-Host "  nova runtools                  # (optional) run_tools.py if you use it"
  Write-Host "  nova tools                     # list registered Nova tools"
  Write-Host ""
  Write-Host "Ops (optional / future):"
  Write-Host "  nova health                    # health.py (if present)"
  Write-Host "  nova logs                      # open log folder"
  Write-Host "  nova policy                    # open policy.json"
  Write-Host "  nova mem                       # open memory folder"
  Write-Host "  nova config                    # open config file (future)"
  Write-Host "  nova guard [--fix]             # supervisor (future)"
  Write-Host "  nova diag                      # full diagnostics (future)"
  Write-Host ""
}

# ==========================
# Command Router (main switch)
# ==========================
switch ($cmd.ToLower()) {

  # ----------
  # Help / hub
  # ----------
  "help" {
    Show-Help
    break
  }

  "hub" {
    Write-Host ""
    Write-Host "Nova Hub:"
    Write-Host "  1) Chat"
    Write-Host "  2) Look (center crop)"
    Write-Host "  3) Camera"
    Write-Host "  4) Run (voice + tools)"
    Write-Host ""
    $choice = Read-Host "Choose 1-4"
    switch ($choice) {
      "1" { Run-Ollama @("run","llama3.1:8b") }
      "2" { Run-Py $LOOK_CROP }
      "3" { Run-Py $CAMERA @("what do you see") }
      "4" { Run-Py $CORE }
      default { Write-Host "No action." }
    }
    break
  }

  # ----------
  # Vision tools
  # ----------
  "look" {
    Run-Py $LOOK_CROP
    break
  }

  "lookfull" {
    Run-Py $LOOK_FULL
    break
  }

  "camera" {
    # Join args into ONE string so quotes/spaces behave
    $prompt = Join-Args $remainingTokens
    if ([string]::IsNullOrWhiteSpace($prompt)) { $prompt = "what do you see" }
    Run-Py $CAMERA @($prompt)
    break
  }

  # ----------
  # Chat
  # ----------
  "chat" {
    if (Test-Path $CHATPY) {
      Run-Py $CHATPY
    } else {
      Run-Ollama @("run","llama3.1:8b")
    }
    break
  }

  # ----------
  # File tools (agent.py)
  # ----------
  "ls" {
    $arg = Join-Args $remainingTokens
    if ([string]::IsNullOrWhiteSpace($arg)) {
      Run-Py $AGENT @("ls")
    } else {
      Run-Py $AGENT @("ls",$arg)
    }
    break
  }

  "read" {
    $arg = Join-Args $remainingTokens
    if ([string]::IsNullOrWhiteSpace($arg)) {
      Write-Host ""
      Write-Host "Usage: nova read <file>"
      Write-Host ""
      exit 1
    }
    Run-Py $AGENT @("read",$arg)
    break
  }

  "find" {
    # Keep it flexible: allow user to pass "keyword [folder]" in one line
    $arg = Join-Args $remainingTokens
    if ([string]::IsNullOrWhiteSpace($arg)) {
      Write-Host ""
      Write-Host "Usage: nova find ""keyword"" [folder]"
      Write-Host ""
      exit 1
    }
    Run-Py $AGENT @("find",$arg)
    break
  }

  # ----------
  # Runtime (Nova Core)
  # ----------
  "doctor" {
    if ($remainingTokens -and $remainingTokens.Count -gt 0) {
      Run-Py $DOCTORPY $remainingTokens
    } else {
      Run-Py $DOCTORPY
    }
    break
  }

  "run" {
    $useFix = $false
    if ($remainingTokens -contains "--fix") { $useFix = $true }
    if (-not (Run-DoctorPreflight $useFix)) { exit 1 }
    Run-Py $CORE
    break
  }

  "webui" {
    $useFix = $false
    if ($remainingTokens -contains "--fix") { $useFix = $true }

    # Fallback for cmd->powershell forwarding quirks with double-dash args.
    # nova.cmd stores the raw argument tail in NOVA_RAW_ARGS.
    $rawArgs = [string]($env:NOVA_RAW_ARGS)
    if (-not $useFix -and $rawArgs -match "(^|\s)--fix(\s|$)") { $useFix = $true }

    $webuiArgs = @()
    if ($remainingTokens -and $remainingTokens.Count -gt 0) {
      $webuiArgs = @($remainingTokens)
    } else {
      if ($rawArgs) {
        if ($rawArgs -match "(?i)(^|\s)--host\s+([^\s]+)") {
          $hostValue = $Matches[2].Trim().Trim('"')
          if ($hostValue) { $webuiArgs += @("--host", $hostValue) }
        }
        if ($rawArgs -match "(?i)(^|\s)--port\s+(\d+)") {
          $portValue = $Matches[2].Trim()
          if ($portValue) { $webuiArgs += @("--port", $portValue) }
        }
      }
    }

    if (-not (Run-DoctorPreflight $useFix)) { exit 1 }

    # Pass remaining args through (e.g., --host 0.0.0.0 --port 8080)
    if ($webuiArgs -and $webuiArgs.Count -gt 0) {
      Run-Py $WEBUIPY $webuiArgs
    } else {
      Run-Py $WEBUIPY
    }
    break
  }

  "webui-start" {
    $useFix = $false
    if ($remainingTokens -contains "--fix") { $useFix = $true }
    if (-not (Run-DoctorPreflight $useFix)) { exit 1 }

    $bindHost = "127.0.0.1"
    $bindPort = "8080"
    $portSpecified = $false
    for ($i = 0; $i -lt $remainingTokens.Count; $i++) {
      if ($remainingTokens[$i] -ieq "--host" -and $i + 1 -lt $remainingTokens.Count) {
        $bindHost = $remainingTokens[$i + 1]
      }
      if ($remainingTokens[$i] -ieq "--port" -and $i + 1 -lt $remainingTokens.Count) {
        $bindPort = $remainingTokens[$i + 1]
        $portSpecified = $true
      }
    }

    $occupied = @(Get-NetTCPConnection -LocalPort ([int]$bindPort) -State Listen -ErrorAction SilentlyContinue)
    if ($occupied.Count -gt 0) {
      if ($portSpecified) {
        Write-Host ("[WARN] Requested port " + $bindPort + " already has listeners. Trying anyway.")
      } else {
        Write-Host ("[WARN] Port " + $bindPort + " is occupied; switching to 8090.")
        $bindPort = "8090"
      }
    }

    Stop-NovaHttpProcesses | Out-Null
    try {
      Remove-Item (Join-Path $ROOT "runtime\guard.stop") -Force -ErrorAction SilentlyContinue
    } catch {}

    Ensure-Python
    Ensure-Logs
    $outLog = Join-Path $LOG_DIR "nova_http.out.log"
    $errLog = Join-Path $LOG_DIR "nova_http.err.log"
    $proc = Start-Process -FilePath $venvPython -ArgumentList @($WEBUIPY, "--host", $bindHost, "--port", $bindPort) -PassThru -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    Start-Sleep -Milliseconds 700
    Stop-NovaHttpExcept $proc.Id
    if ($proc.HasExited) {
      Write-Host ("[FAIL] webui process exited early (pid=" + $proc.Id + ").")
      Write-Host ("[INFO] Check logs: " + $errLog)
      exit 1
    }
    Write-Host ("[OK]   Started webui pid=" + $proc.Id)
    Write-Host ("[INFO] URL: http://" + $bindHost + ":" + $bindPort + "/control")
    break
  }

  "webui-stop" {
    Stop-NovaHttpProcesses | Out-Null
    break
  }

  "webui-status" {
    $port = "8080"
    for ($i = 0; $i -lt $remainingTokens.Count; $i++) {
      if ($remainingTokens[$i] -ieq "--port" -and $i + 1 -lt $remainingTokens.Count) {
        $port = $remainingTokens[$i + 1]
      }
    }

    $procs = Get-NovaHttpLogicalProcesses
    if ($procs.Count -eq 0) {
      Write-Host "[INFO] No nova_http.py process running."
    } else {
      foreach ($p in $procs) {
        Write-Host ("[INFO] nova_http pid=" + $p.ProcessId)
      }
    }

    $url = "http://127.0.0.1:" + $port + "/api/control/status"
    try {
      $r = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 4
      Write-Host ("[OK]   " + $url + " => " + $r.StatusCode)
    } catch {
      Write-Host ("[WARN] " + $url + " unreachable")
    }
    break
  }

  "smoke" {
    $useFix = $false
    if ($remainingTokens -contains "--fix") { $useFix = $true }
    if (-not (Run-DoctorPreflight $useFix)) { exit 1 }

    Ensure-Python
    if (-not (Test-Path $GUARDPY)) {
      Write-Host "[FAIL] Missing guard script: $GUARDPY"
      exit 1
    }
    if (-not (Test-Path $SMOKEPY)) {
      Write-Host "[FAIL] Missing smoke script: $SMOKEPY"
      exit 1
    }
    if (-not (Test-Path $STOPPY)) {
      Write-Host "[FAIL] Missing stop script: $STOPPY"
      exit 1
    }

    Write-Host "[INFO] Starting guard in background..."
    $guardProc = Start-Process -FilePath $venvPython -ArgumentList @($GUARDPY) -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2

    try {
      Write-Host "[INFO] Running smoke_test.py ..."
      & $venvPython $SMOKEPY
      $smokeCode = $LASTEXITCODE
    }
    finally {
      Write-Host "[INFO] Stopping guard/core ..."
      & $venvPython $STOPPY
      Start-Sleep -Seconds 1
      if ($guardProc -and -not $guardProc.HasExited) {
        try { Stop-Process -Id $guardProc.Id -Force -ErrorAction SilentlyContinue } catch {}
      }
    }

    exit $smokeCode
  }

  "test" {
    Run-Py $REGRESSION
    break
  }

  "runtools" {
    # Optional script you already used earlier
    Run-Py $RUN_TOOLS
    break
  }

  "tools" {
    Run-Py $RUN_TOOLS @("--list-tools")
    break
  }

  # ----------
  # Ops / Health / Logs
  # ----------
  "health" {
    if (Test-Path $HEALTHPY) {
      Run-Py $HEALTHPY
    } else {
      Write-Host "[WARN] health.py not found at $HEALTHPY"
      Write-Host "       (Create it later; this hook is ready.)"
    }
    break
  }

  "logs" {
    Ensure-Logs
    # Opens File Explorer to logs folder
    Start-Process explorer.exe $LOG_DIR
    break
  }

  "policy" {
    if (Test-Path $POLICY) {
      notepad $POLICY
    } else {
      Write-Host "[WARN] policy.json not found at $POLICY"
    }
    break
  }

  "mem" {
    # Opens memory folder (future-proof)
    if (-not (Test-Path $MEM_DIR)) {
      # If you keep memory in a single file for now, adjust here later
      New-Item -ItemType Directory -Force -Path $MEM_DIR | Out-Null
    }
    Start-Process explorer.exe $MEM_DIR
    break
  }

  "memory" {
    # If you have a memory.py tool, run it; otherwise keep this as a hook.
    if (Test-Path $MEMORYPY) {
      $arg = Join-Args $remainingTokens
      if ([string]::IsNullOrWhiteSpace($arg)) {
        Run-Py $MEMORYPY
      } else {
        Run-Py $MEMORYPY @($arg)
      }
    } else {
      Write-Host "[WARN] memory.py not found at $MEMORYPY"
      Write-Host "       (Create it later; this hook is ready.)"
    }
    break
  }

  # ----------
  # Future: unified config + diagnostics + guard (commented/guarded)
  # ----------
  "config" {
    if (Test-Path $CONFIG) {
      notepad $CONFIG
    } else {
      Write-Host "[WARN] config not found at $CONFIG"
      Write-Host "       (This is a future bridge: unified nova.json.)"
      # Uncomment later if you want auto-create:
      # New-Item -ItemType Directory -Force -Path (Split-Path $CONFIG) | Out-Null
      # '{}' | Out-File -Encoding utf8 $CONFIG
      # notepad $CONFIG
    }
    break
  }

  "diag" {
    if (Test-Path $DIAGPY) {
      Run-Py $DIAGPY
    } else {
      Write-Host "[WARN] diag.py not found at $DIAGPY"
      Write-Host "       (Future bridge: full diagnostics report.)"
    }
    break
  }

  "guard" {
    if (Test-Path $GUARDPY) {
      $useFix = $false
      if ($remainingTokens -contains "--fix") { $useFix = $true }
      if (-not (Run-DoctorPreflight $useFix)) { exit 1 }
      Run-Py $GUARDPY
    } else {
      Write-Host "[WARN] nova_guard.py not found at $GUARDPY"
      Write-Host "       (Future bridge: supervisor/auto-restart.)"
      Write-Host "       When ready, we’ll add it and this command will just work."
    }
    break
  }

  # ----------
  # Future: install/update helpers (commented hooks)
  # ----------
  "install" {
    Write-Host "[INFO] Reserved for future install helpers."
    Write-Host "       Example future actions:"
    Write-Host "       - pip install -r requirements.txt"
    Write-Host "       - ollama pull llama3.1:8b"
    Write-Host "       - ollama pull nomic-embed-text"
    # Uncomment later when you create requirements.txt:
    # Run-Py (Join-Path $ROOT "install.py")
    break
  }

  "update" {
    Write-Host "[INFO] Reserved for future update helpers."
    Write-Host "       Example future actions:"
    Write-Host "       - git pull"
    Write-Host "       - pip upgrade"
    break
  }


"stop" {
  if (Test-Path $STOPPY) {
    Run-Py $STOPPY
  } else {
    Write-Host "[WARN] stop_guard.py not found at $STOPPY"
  }
  break
}

  # ----------
  # Default
  # ----------
  default {
    Write-Host ""
    Write-Host "Unknown command: $cmd"
    Write-Host "Try: nova help"
    Write-Host ""
  }
}