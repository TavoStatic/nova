param(
  # Subcommand: look | lookfull | chat | camera | ls | read | find | run | hub | smoke | health | guard | install | update | diag | logs | mem | config
  [Parameter(Position=0)]
  [string]$cmd = "help",

  # Everything else after the subcommand
  [Parameter(ValueFromRemainingArguments=$true)]
  [string[]]$remainingArgs
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
$RUN_TOOLS = Join-Path $ROOT "run_tools.py"   # optional
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
function Join-Args([string[]]$args) {
  if ($null -eq $args) { return "" }
  return ($args -join " ").Trim()
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

function Run-Py([string]$script, [string[]]$args=@()) {
  Ensure-Python
  if (-not (Test-Path $script)) {
    Write-Host ""
    Write-Host "[FAIL] Missing script: $script"
    Write-Host ""
    exit 1
  }
  & $venvPython $script @args
  exit $LASTEXITCODE
}

function Run-Ollama([string[]]$args=@()) {
  # "ollama" should be on PATH if installed
  & ollama @args
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

function Show-Help {
  Write-Host ""
  Write-Host "Nova commands:"
  Write-Host "  nova help"
  Write-Host "  nova look                      # center-crop screenshot -> vision"
  Write-Host "  nova lookfull                  # full screenshot -> vision"
  Write-Host "  nova chat                      # ollama run llama3.1:8b"
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
  Write-Host "  nova smoke [--fix]             # doctor -> guard -> smoke_test -> stop"
  Write-Host "  nova runtools                  # (optional) run_tools.py if you use it"
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
    $prompt = Join-Args $remainingArgs
    if ([string]::IsNullOrWhiteSpace($prompt)) { $prompt = "what do you see" }
    Run-Py $CAMERA @($prompt)
    break
  }

  # ----------
  # Chat
  # ----------
  "chat" {
    # If you later build chat.py, you can swap this to Run-Py
    Run-Ollama @("run","llama3.1:8b")
    break
  }

  # ----------
  # File tools (agent.py)
  # ----------
  "ls" {
    $arg = Join-Args $remainingArgs
    if ([string]::IsNullOrWhiteSpace($arg)) {
      Run-Py $AGENT @("ls")
    } else {
      Run-Py $AGENT @("ls",$arg)
    }
    break
  }

  "read" {
    $arg = Join-Args $remainingArgs
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
    $arg = Join-Args $remainingArgs
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
    if ($remainingArgs -and $remainingArgs.Count -gt 0) {
      Run-Py $DOCTORPY $remainingArgs
    } else {
      Run-Py $DOCTORPY
    }
    break
  }

  "run" {
    $useFix = $false
    if ($remainingArgs -contains "--fix") { $useFix = $true }
    if (-not (Run-DoctorPreflight $useFix)) { exit 1 }
    Run-Py $CORE
    break
  }

  "smoke" {
    $useFix = $false
    if ($remainingArgs -contains "--fix") { $useFix = $true }
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

  "runtools" {
    # Optional script you already used earlier
    Run-Py $RUN_TOOLS
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
      $arg = Join-Args $remainingArgs
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
      if ($remainingArgs -contains "--fix") { $useFix = $true }
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