param(
  # Subcommand: look | lookfull | chat | camera | ls | read | find | run | webui | webui-start | webui-stop | webui-status | operator | hub | smoke | test | health | guard | install | update | diag | logs | mem | config
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
$SUBCONSCIOUSRUNNER = Join-Path $ROOT "subconscious_runner.py"
$OPERATORCLI = Join-Path $ROOT "scripts\operator_cli.py"
$PACKAGEBUILDPS1 = Join-Path $ROOT "scripts\build_release_package.ps1"
$PACKAGEVERIFYPS1 = Join-Path $ROOT "scripts\verify_release_package.ps1"
$INSTALLERBUILDPS1 = Join-Path $ROOT "scripts\build_windows_installer.ps1"
$INSTALLERVERIFYPS1 = Join-Path $ROOT "scripts\verify_windows_installer.ps1"
$PACKAGELEDGERPS1 = Join-Path $ROOT "scripts\show_release_ledger.ps1"
$PACKAGEPROMOTEPS1 = Join-Path $ROOT "scripts\promote_release_package.ps1"
$PACKAGESTATUSPS1 = Join-Path $ROOT "scripts\show_release_status.ps1"
$PACKAGEREADINESSPS1 = Join-Path $ROOT "scripts\show_release_readiness.ps1"
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
    Write-Host "       Make sure your venv exists under: $ROOT"
    Write-Host ""
    exit 1
  }
}

function Get-NovaNormalizedPath([string]$pathValue) {
  if ([string]::IsNullOrWhiteSpace($pathValue)) { return "" }

  try {
    return [System.IO.Path]::GetFullPath($pathValue).Replace('/', '\').ToLowerInvariant()
  } catch {
    return [string]$pathValue.Replace('/', '\').ToLowerInvariant()
  }
}

function Test-NovaCommandLineHasPath([object]$process, [string]$expectedPath) {
  if ($null -eq $process -or [string]::IsNullOrWhiteSpace($expectedPath)) { return $false }
  $commandLine = [string]$process.CommandLine
  if ([string]::IsNullOrWhiteSpace($commandLine)) { return $false }

  $normalizedExpected = Get-NovaNormalizedPath $expectedPath
  $normalizedCommand = $commandLine.Replace('/', '\').ToLowerInvariant()
  return $normalizedCommand.Contains($normalizedExpected)
}

function Get-BootstrapPythonDescription {
  if (Test-Path $venvPython) {
    return $venvPython
  }

  $pyCmd = Get-Command py -ErrorAction SilentlyContinue
  if ($pyCmd) {
    return ($pyCmd.Source + " -3")
  }

  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCmd) {
    return $pythonCmd.Source
  }

  $python3Cmd = Get-Command python3 -ErrorAction SilentlyContinue
  if ($python3Cmd) {
    return $python3Cmd.Source
  }

  return ""
}

function Invoke-BootstrapPython([string[]]$pythonTokens=@()) {
  if (Test-Path $venvPython) {
    & $venvPython @pythonTokens
    return $LASTEXITCODE
  }

  $pyCmd = Get-Command py -ErrorAction SilentlyContinue
  if ($pyCmd) {
    & $pyCmd.Source -3 @pythonTokens
    return $LASTEXITCODE
  }

  $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCmd) {
    & $pythonCmd.Source @pythonTokens
    return $LASTEXITCODE
  }

  $python3Cmd = Get-Command python3 -ErrorAction SilentlyContinue
  if ($python3Cmd) {
    & $python3Cmd.Source @pythonTokens
    return $LASTEXITCODE
  }

  Write-Host "[FAIL] No bootstrap Python was found on PATH."
  Write-Host "       Install Python 3 with venv support, then run: nova install"
  return 1
}

function Invoke-NovaInstall {
  $requirementsPath = Join-Path $ROOT "requirements.txt"
  $venvDir = Join-Path $ROOT ".venv"
  $doctorArgs = @("--fix")

  Write-Host ""
  Write-Host "Nova Install"
  Write-Host "------------"

  if (-not (Test-Path $requirementsPath)) {
    Write-Host ("[FAIL] Missing dependency manifest: " + $requirementsPath)
    return 1
  }

  if (-not (Test-Path $venvPython)) {
    $bootstrapSource = Get-BootstrapPythonDescription
    if ([string]::IsNullOrWhiteSpace($bootstrapSource)) {
      Write-Host "[FAIL] No bootstrap Python was found on PATH."
      Write-Host "       Install Python 3 with venv support, then run: nova install"
      return 1
    }

    Write-Host ("[INFO] Creating virtual environment with " + $bootstrapSource)
    $createCode = Invoke-BootstrapPython @("-m", "venv", $venvDir)
    if ($createCode -ne 0 -or -not (Test-Path $venvPython)) {
      Write-Host "[FAIL] Virtual environment creation failed."
      return 1
    }
  } else {
    Write-Host ("[INFO] Using existing virtual environment at " + $venvDir)
  }

  Write-Host "[INFO] Upgrading pip ..."
  & $venvPython -m pip install --upgrade pip
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] pip upgrade failed."
    return $LASTEXITCODE
  }

  Write-Host ("[INFO] Installing dependencies from " + $requirementsPath)
  & $venvPython -m pip install -r $requirementsPath
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Dependency installation failed."
    return $LASTEXITCODE
  }

  if (Test-Path $DOCTORPY) {
    Write-Host "[INFO] Running doctor --fix ..."
    & $venvPython $DOCTORPY @doctorArgs
    if ($LASTEXITCODE -ne 0) {
      Write-Host "[FAIL] Doctor validation failed after install."
      return $LASTEXITCODE
    }
  } else {
    Write-Host ("[WARN] doctor.py not found at " + $DOCTORPY)
  }

  $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
  if (-not $ollamaCmd) {
    Write-Host "[WARN] Optional dependency missing: ollama is not on PATH."
    Write-Host "       Chat/runtime paths that need a local model backend will stay limited until Ollama is installed."
  }

  $piperExe = Join-Path $ROOT "piper\piper.exe"
  $piperModel = Join-Path $ROOT "piper\models\en_US-lessac-medium.onnx"
  if (-not (Test-Path $piperExe) -or -not (Test-Path $piperModel)) {
    Write-Host "[WARN] Optional TTS assets are incomplete. Voice output may remain unavailable."
  }

  Write-Host ""
  Write-Host "[OK] Install bootstrap completed."
  Write-Host "[INFO] Next steps:"
  Write-Host "       1. nova doctor"
  Write-Host "       2. nova run"
  Write-Host "       3. nova webui-start --host 127.0.0.1 --port 8080"
  Write-Host "       4. nova smoke --fix"
  Write-Host ""
  return 0
}

function Invoke-NovaPackageBuild([string[]]$buildTokens=@()) {
  if (-not (Test-Path $PACKAGEBUILDPS1)) {
    Write-Host ("[FAIL] Missing package builder: " + $PACKAGEBUILDPS1)
    return 1
  }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PACKAGEBUILDPS1 @buildTokens
  return $LASTEXITCODE
}

function Invoke-NovaPackageVerify([string[]]$verifyTokens=@()) {
  if (-not (Test-Path $PACKAGEVERIFYPS1)) {
    Write-Host ("[FAIL] Missing package verifier: " + $PACKAGEVERIFYPS1)
    return 1
  }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PACKAGEVERIFYPS1 @verifyTokens
  return $LASTEXITCODE
}

function Invoke-NovaInstallerBuild([string[]]$installerTokens=@()) {
  if (-not (Test-Path $INSTALLERBUILDPS1)) {
    Write-Host ("[FAIL] Missing installer builder: " + $INSTALLERBUILDPS1)
    return 1
  }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $INSTALLERBUILDPS1 @installerTokens
  return $LASTEXITCODE
}

function Invoke-NovaInstallerVerify([string[]]$verifyTokens=@()) {
  if (-not (Test-Path $INSTALLERVERIFYPS1)) {
    Write-Host ("[FAIL] Missing installer verifier: " + $INSTALLERVERIFYPS1)
    return 1
  }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $INSTALLERVERIFYPS1 @verifyTokens
  return $LASTEXITCODE
}

function Invoke-NovaPackageLedger([string[]]$ledgerTokens=@()) {
  if (-not (Test-Path $PACKAGELEDGERPS1)) {
    Write-Host ("[FAIL] Missing package ledger tool: " + $PACKAGELEDGERPS1)
    return 1
  }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PACKAGELEDGERPS1 @ledgerTokens
  return $LASTEXITCODE
}

function Invoke-NovaInstallerLedger([string[]]$ledgerTokens=@()) {
  if (-not (Test-Path $PACKAGELEDGERPS1)) {
    Write-Host ("[FAIL] Missing package ledger tool: " + $PACKAGELEDGERPS1)
    return 1
  }

  $args = @("-ArtifactKind", "windows-installer") + $ledgerTokens
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PACKAGELEDGERPS1 @args
  return $LASTEXITCODE
}

function Invoke-NovaPackagePromote([string[]]$promoteTokens=@()) {
  if (-not (Test-Path $PACKAGEPROMOTEPS1)) {
    Write-Host ("[FAIL] Missing package promote tool: " + $PACKAGEPROMOTEPS1)
    return 1
  }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PACKAGEPROMOTEPS1 @promoteTokens
  return $LASTEXITCODE
}

function Invoke-NovaInstallerPromote([string[]]$promoteTokens=@()) {
  if (-not (Test-Path $PACKAGEPROMOTEPS1)) {
    Write-Host ("[FAIL] Missing package promote tool: " + $PACKAGEPROMOTEPS1)
    return 1
  }

  $args = @("-ArtifactKind", "windows-installer") + $promoteTokens
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PACKAGEPROMOTEPS1 @args
  return $LASTEXITCODE
}

function Invoke-NovaPackageStatus([string[]]$statusTokens=@()) {
  if (-not (Test-Path $PACKAGESTATUSPS1)) {
    Write-Host ("[FAIL] Missing package status tool: " + $PACKAGESTATUSPS1)
    return 1
  }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PACKAGESTATUSPS1 @statusTokens
  return $LASTEXITCODE
}

function Invoke-NovaInstallerStatus([string[]]$statusTokens=@()) {
  if (-not (Test-Path $PACKAGESTATUSPS1)) {
    Write-Host ("[FAIL] Missing package status tool: " + $PACKAGESTATUSPS1)
    return 1
  }

  $args = @("-ArtifactKind", "windows-installer") + $statusTokens
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PACKAGESTATUSPS1 @args
  return $LASTEXITCODE
}

function Invoke-NovaPackageReadiness([string[]]$readinessTokens=@()) {
  if (-not (Test-Path $PACKAGEREADINESSPS1)) {
    Write-Host ("[FAIL] Missing package readiness tool: " + $PACKAGEREADINESSPS1)
    return 1
  }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PACKAGEREADINESSPS1 @readinessTokens
  return $LASTEXITCODE
}

function Invoke-NovaInstallerReadiness([string[]]$readinessTokens=@()) {
  if (-not (Test-Path $PACKAGEREADINESSPS1)) {
    Write-Host ("[FAIL] Missing package readiness tool: " + $PACKAGEREADINESSPS1)
    return 1
  }

  $args = @("-ArtifactKind", "windows-installer") + $readinessTokens
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PACKAGEREADINESSPS1 @args
  return $LASTEXITCODE
}

function Wait-NovaCoreSignal([int]$timeoutSeconds=25) {
  $heartbeatPath = Join-Path $ROOT "runtime\core.heartbeat"
  $statePath = Join-Path $ROOT "runtime\core_state.json"
  $deadline = (Get-Date).ToUniversalTime().AddSeconds($timeoutSeconds)

  while ((Get-Date).ToUniversalTime() -lt $deadline) {
    if ((Test-Path $heartbeatPath) -and (Test-Path $statePath)) {
      return $true
    }
    Start-Sleep -Seconds 1
  }

  return $false
}

function Invoke-NovaSmoke([string]$tier="runtime", [bool]$useFix=$false) {
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

  Write-Host ("[INFO] Starting guard in background for smoke tier '" + $tier + "' ...")
  try {
    Remove-Item (Join-Path $ROOT "runtime\guard.stop") -Force -ErrorAction SilentlyContinue
  } catch {}
  $guardProc = Start-Process -FilePath $venvPython -ArgumentList @($GUARDPY) -PassThru -WindowStyle Hidden
  if (-not (Wait-NovaCoreSignal 25)) {
    Write-Host "[WARN] Core heartbeat/state did not appear before smoke execution. Continuing with smoke probe."
  }

  try {
    Write-Host ("[INFO] Running smoke_test.py --tier " + $tier + " ...")
    & $venvPython $SMOKEPY "--tier" $tier
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
  $expectedWebuiPath = Get-NovaNormalizedPath $WEBUIPY
  return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Name -match '^python(\.exe)?$' -and
      (Test-NovaCommandLineHasPath $_ $expectedWebuiPath)
    })
}

function Get-NovaProcessFamilyIds([int]$rootPid) {
  if ($rootPid -le 0) { return @() }

  $familyIds = New-Object System.Collections.Generic.HashSet[int]
  $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
  if (-not $allProcesses -or $allProcesses.Count -eq 0) {
    [void]$familyIds.Add($rootPid)
    return @($familyIds)
  }

  $childrenByParent = @{}
  foreach ($proc in $allProcesses) {
    $parentId = [int]$proc.ParentProcessId
    if (-not $childrenByParent.ContainsKey($parentId)) {
      $childrenByParent[$parentId] = New-Object System.Collections.Generic.List[int]
    }
    [void]$childrenByParent[$parentId].Add([int]$proc.ProcessId)
  }

  $queue = New-Object System.Collections.Generic.Queue[int]
  $queue.Enqueue($rootPid)
  while ($queue.Count -gt 0) {
    $currentPid = $queue.Dequeue()
    if ($familyIds.Contains($currentPid)) { continue }
    [void]$familyIds.Add($currentPid)
    if ($childrenByParent.ContainsKey($currentPid)) {
      foreach ($childPid in $childrenByParent[$currentPid]) {
        if (-not $familyIds.Contains([int]$childPid)) {
          $queue.Enqueue([int]$childPid)
        }
      }
    }
  }

  return @($familyIds)
}

function Get-NovaScriptProcesses([string]$scriptName) {
  if ([string]::IsNullOrWhiteSpace($scriptName)) { return @() }
  $scriptPath = $scriptName
  if (-not [System.IO.Path]::IsPathRooted($scriptPath)) {
    $scriptPath = Join-Path $ROOT $scriptName
  }
  $expectedScriptPath = Get-NovaNormalizedPath $scriptPath
  return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.Name -match '^python(\.exe)?$' -and
      (Test-NovaCommandLineHasPath $_ $expectedScriptPath)
    })
}

function Get-NovaLogicalProcesses([string]$scriptName) {
  $all = @(Get-NovaScriptProcesses $scriptName)
  if (-not $all -or $all.Count -eq 0) { return @() }

  $parentIds = @{}
  foreach ($p in $all) {
    $parentIds[[int]$p.ParentProcessId] = $true
  }

  $leaf = @($all | Where-Object { -not $parentIds.ContainsKey([int]$_.ProcessId) })
  if ($leaf.Count -gt 0) { return $leaf }
  return $all
}

function Read-NovaIdentityFile([string]$path) {
  if (-not (Test-Path $path)) {
    return [pscustomobject]@{ pid = $null; create_time = $null; exists = $false }
  }
  try {
    $raw = Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json
    $storedPid = $null
    if ($raw.pid -is [int] -and $raw.pid -gt 0) {
      $storedPid = [int]$raw.pid
    } elseif ($raw.pid) {
      $candidatePid = 0
      if ([int]::TryParse([string]$raw.pid, [ref]$candidatePid) -and $candidatePid -gt 0) {
        $storedPid = $candidatePid
      }
    }

    $createTime = $null
    if ($raw.create_time -is [double] -or $raw.create_time -is [single] -or $raw.create_time -is [decimal] -or $raw.create_time -is [int] -or $raw.create_time -is [long]) {
      $createTime = [double]$raw.create_time
    }

    return [pscustomobject]@{
      pid = $storedPid
      create_time = $createTime
      exists = $true
    }
  } catch {
    return [pscustomobject]@{ pid = $null; create_time = $null; exists = $true }
  }
}

function Convert-NovaCreationDateToUnixSeconds([object]$creationDate) {
  if ($null -eq $creationDate -or [string]::IsNullOrWhiteSpace([string]$creationDate)) {
    return $null
  }

  try {
    $parsedDate = [Management.ManagementDateTimeConverter]::ToDateTime([string]$creationDate).ToUniversalTime()
    return [double][DateTimeOffset]$parsedDate.ToUnixTimeSeconds()
  } catch {
    return $null
  }
}

function Select-NovaLogicalProcess($logicalProcesses, $identityPid, $identityCreateTime) {
  $logical = @($logicalProcesses)
  if (-not $logical -or $logical.Count -eq 0) {
    return $null
  }

  $selected = $null
  $expectedPid = 0
  if ([int]::TryParse([string]$identityPid, [ref]$expectedPid) -and $expectedPid -gt 0) {
    $selected = @($logical | Where-Object { [int]$_.ProcessId -eq $expectedPid } | Select-Object -First 1)
    if ($selected -and $null -ne $identityCreateTime) {
      $actualCreateTime = Convert-NovaCreationDateToUnixSeconds $selected.CreationDate
      if ($null -ne $actualCreateTime) {
        $timeDelta = [math]::Abs([double]$actualCreateTime - [double]$identityCreateTime)
        if ($timeDelta -gt 2.0) {
          $selected = $null
        }
      }
    }
  }

  if ($selected) {
    return $selected
  }

  if ($logical.Count -eq 1) {
    return $logical[0]
  }

  return @(
    $logical |
      Sort-Object -Property @(
        @{ Expression = { Convert-NovaCreationDateToUnixSeconds $_.CreationDate }; Descending = $true },
        @{ Expression = { [int]$_.ProcessId }; Descending = $true }
      ) |
      Select-Object -First 1
  ) | Select-Object -First 1
}

function Get-NovaHeartbeatAgeSeconds {
  $heartbeatPath = Join-Path $ROOT "runtime\core.heartbeat"
  if (-not (Test-Path $heartbeatPath)) { return $null }
  try {
    $age = ((Get-Date).ToUniversalTime() - (Get-Item $heartbeatPath).LastWriteTimeUtc).TotalSeconds
    return [int][math]::Max([math]::Floor($age), 0)
  } catch {
    return $null
  }
}

function Show-NovaRuntimeStatus {
  $runtimeDir = Join-Path $ROOT "runtime"
  $guardIdentity = Read-NovaIdentityFile (Join-Path $runtimeDir "guard_pid.json")
  $coreIdentity = Read-NovaIdentityFile (Join-Path $runtimeDir "core_state.json")
  $guardLogical = @(Get-NovaLogicalProcesses "nova_guard.py")
  $coreLogical = @(Get-NovaLogicalProcesses "nova_core.py")
  $webLogical = @(Get-NovaHttpLogicalProcesses)
  $guardSelected = Select-NovaLogicalProcess $guardLogical $guardIdentity.pid $guardIdentity.create_time
  $coreSelected = Select-NovaLogicalProcess $coreLogical $coreIdentity.pid $coreIdentity.create_time
  $heartbeatAge = Get-NovaHeartbeatAgeSeconds

  $guardStatus = "stopped"
  if ($guardSelected) {
    $guardStatus = "running"
  } elseif ($guardIdentity.pid) {
    $guardStatus = if (Get-Process -Id $guardIdentity.pid -ErrorAction SilentlyContinue) { "stale_identity" } else { "not_running" }
  }

  $coreStatus = "stopped"
  if ($coreSelected) {
    $coreStatus = "running"
  } elseif ($coreIdentity.pid) {
    $coreStatus = if (Get-Process -Id $coreIdentity.pid -ErrorAction SilentlyContinue) { "stale_identity" } else { "not_running" }
  } elseif ($null -ne $heartbeatAge -and $heartbeatAge -le 5) {
    $coreStatus = "heartbeat_only"
  }

  $stopFlag = Test-Path (Join-Path $runtimeDir "guard.stop")
  $guardLock = Test-Path (Join-Path $runtimeDir "guard.lock")

  Write-Host ""
  Write-Host "Nova Runtime Status"
  Write-Host "-------------------"
  Write-Host ("guard status      : " + $guardStatus)
  Write-Host ("guard pid         : " + ($(if ($guardSelected) { $guardSelected.ProcessId } elseif ($guardIdentity.pid) { $guardIdentity.pid } else { "-" })))
  Write-Host ("guard count       : " + $guardLogical.Count)
  Write-Host ("guard lock        : " + ($(if ($guardLock) { "present" } else { "missing" })))
  Write-Host ("guard stop flag   : " + ($(if ($stopFlag) { "present" } else { "missing" })))
  Write-Host ""
  Write-Host ("core status       : " + $coreStatus)
  Write-Host ("core pid          : " + ($(if ($coreSelected) { $coreSelected.ProcessId } elseif ($coreIdentity.pid) { $coreIdentity.pid } else { "-" })))
  Write-Host ("core count        : " + $coreLogical.Count)
  Write-Host ("heartbeat age sec : " + ($(if ($null -ne $heartbeatAge) { $heartbeatAge } else { "-" })))
  Write-Host ""
  Write-Host ("webui status      : " + ($(if ($webLogical.Count -gt 0) { "running" } else { "stopped" })))
  Write-Host ("webui pid(s)      : " + ($(if ($webLogical.Count -gt 0) { (($webLogical | ForEach-Object { $_.ProcessId }) -join ", ") } else { "-" })))
  Write-Host ("webui count       : " + $webLogical.Count)
  Write-Host ""
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
  $keepFamilyIds = @(Get-NovaProcessFamilyIds $keepPid)
  $procs = Get-NovaHttpProcesses | Where-Object { $keepFamilyIds -notcontains [int]$_.ProcessId }
  foreach ($p in $procs) {
    try {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
      Write-Host ("[OK]   Stopped extra nova_http pid=" + $p.ProcessId)
    } catch {}
  }
}

function Wait-NovaHttpStopped([int]$bindPort=0, [int]$timeoutSeconds=8) {
  $deadline = (Get-Date).ToUniversalTime().AddSeconds($timeoutSeconds)

  while ((Get-Date).ToUniversalTime() -lt $deadline) {
    $procs = @(Get-NovaHttpProcesses)
    $listeners = @()
    if ($bindPort -gt 0) {
      try {
        $listeners = @(Get-NetTCPConnection -LocalPort $bindPort -State Listen -ErrorAction SilentlyContinue)
      } catch {
        $listeners = @()
      }
    }

    if ($procs.Count -eq 0 -and $listeners.Count -eq 0) {
      return $true
    }

    Start-Sleep -Milliseconds 500
  }

  return $false
}

function Wait-NovaHttpReady([string]$bindHost, [string]$bindPort, [int]$timeoutSeconds=18) {
  $deadline = (Get-Date).ToUniversalTime().AddSeconds($timeoutSeconds)
  $url = "http://" + $bindHost + ":" + $bindPort + "/api/health"

  while ((Get-Date).ToUniversalTime() -lt $deadline) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 6
      if ($response.StatusCode -eq 200) {
        return $true
      }
    } catch {
    }
    Start-Sleep -Milliseconds 500
  }

  return $false
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
  Write-Host "  nova install                   # create/refresh venv, install deps, run doctor --fix"
  Write-Host "  nova package-build [--label rc1] [--version 2026.03.30] [--channel rc] [--output path]  # stage and zip base package artifact"
  Write-Host "  nova package-verify [path]     # verify latest or selected release artifact manifest/content"
  Write-Host "  nova installer-build [--artifact path] [--compiler path-to-ISCC.exe] [--output path]  # build Windows installer from a verified package zip"
  Write-Host "  nova installer-verify [path]   # verify latest or selected Windows installer artifact/provenance"
  Write-Host "  nova package-ledger [--count 10] [--channel rc] [--version 2026.03.30.2] [--event build]  # recent release artifact history"
  Write-Host "  nova installer-ledger [--count 10] [--channel rc] [--version 2026.03.30.2] [--event build]  # recent Windows installer history"
  Write-Host "  nova package-status            # latest release artifact and promotion state"
  Write-Host "  nova installer-status          # latest Windows installer and promotion state"
  Write-Host "  nova package-readiness         # ship-gate summary from latest build, verify, and promotion records"
  Write-Host "  nova installer-readiness       # ship-gate summary for latest Windows installer"
  Write-Host "  nova package-promote --result pass [--version 2026.03.30.2] [--note text]  # record RC validation outcome"
  Write-Host "  nova installer-promote --result pass [--version 2026.03.30.2] [--note text]  # record installer validation outcome"
  Write-Host "  nova doctor [--fix]            # startup preflight validator"
  Write-Host "  nova run [--fix]               # Nova core (voice + tools)"
  Write-Host "  nova webui [--host 0.0.0.0 --port 8080]  # network web interface"
  Write-Host "  nova webui-start [--host 127.0.0.1 --port 8080] [--fix]  # start webui in background"
  Write-Host "  nova webui-stop                # stop all nova_http processes"
  Write-Host "  nova webui-status [--port 8080] # show webui pids + endpoint check"
  Write-Host "  nova runtime-status            # logical guard/core/webui summary"
  Write-Host "  nova operator [--session <id>] [--macro <id>] [message]  # local operator CLI via /api/control/action"
  Write-Host "  nova operator --list-macros      # list saved operator macros"
  Write-Host "  nova smoke-base [--fix]        # base package smoke without Ollama requirement"
  Write-Host "  nova smoke [--fix]             # doctor -> guard -> smoke_test -> stop"
  Write-Host "  nova smoke-runtime [--fix]     # explicit Ollama-backed runtime smoke"
  Write-Host "  nova test                      # compact regression checks"
  Write-Host "  nova subconscious [--family <id>] [--label overnight]  # unattended subconscious batch report"
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

    Stop-NovaHttpProcesses | Out-Null
    if (-not (Wait-NovaHttpStopped ([int]$bindPort) 8)) {
      Write-Host ("[WARN] Existing nova_http listeners did not clear from port " + $bindPort + " before restart.")
    }

    $occupied = @(Get-NetTCPConnection -LocalPort ([int]$bindPort) -State Listen -ErrorAction SilentlyContinue)
    if ($occupied.Count -gt 0) {
      if ($portSpecified) {
        $owners = (($occupied | ForEach-Object { [string]$_.OwningProcess }) | Select-Object -Unique) -join ", "
        Write-Host ("[FAIL] Requested port " + $bindPort + " is still occupied by non-Nova listener(s): " + $owners)
        exit 1
      } else {
        Write-Host ("[WARN] Port " + $bindPort + " is occupied; switching to 8090.")
        $bindPort = "8090"
      }
    }

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
    if (-not (Wait-NovaHttpReady $bindHost $bindPort 18)) {
      Write-Host ("[FAIL] webui process did not become ready on http://" + $bindHost + ":" + $bindPort + "/api/health")
      Write-Host ("[INFO] Check logs: " + $errLog)
      exit 1
    }
    Write-Host ("[OK]   Started webui pid=" + $proc.Id)
    Write-Host ("[INFO] URL: http://" + $bindHost + ":" + $bindPort + "/control")
    break
  }

  "webui-stop" {
    Stop-NovaHttpProcesses | Out-Null
    if (-not (Wait-NovaHttpStopped 0 8)) {
      Write-Host "[WARN] Some nova_http processes or listeners may still be shutting down."
    }
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
      $r = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 8
      Write-Host ("[OK]   " + $url + " => " + $r.StatusCode)
    } catch {
      Write-Host ("[WARN] " + $url + " unreachable")
    }
    break
  }

  "runtime-status" {
    Show-NovaRuntimeStatus
    break
  }

  "smoke" {
    $useFix = $false
    if ($remainingTokens -contains "--fix") { $useFix = $true }
    Invoke-NovaSmoke "runtime" $useFix
    break
  }

  "smoke-base" {
    $useFix = $false
    if ($remainingTokens -contains "--fix") { $useFix = $true }
    Invoke-NovaSmoke "base" $useFix
    break
  }

  "smoke-runtime" {
    $useFix = $false
    if ($remainingTokens -contains "--fix") { $useFix = $true }
    Invoke-NovaSmoke "runtime" $useFix
    break
  }

  "test" {
    Run-Py $REGRESSION $remainingTokens
    break
  }

  "operator" {
    if ($remainingTokens -and $remainingTokens.Count -gt 0) {
      Run-Py $OPERATORCLI $remainingTokens
    } else {
      Run-Py $OPERATORCLI
    }
    break
  }

  "subconscious" {
    if ($remainingTokens -and $remainingTokens.Count -gt 0) {
      Run-Py $SUBCONSCIOUSRUNNER $remainingTokens
    } else {
      Run-Py $SUBCONSCIOUSRUNNER
    }
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
    $installCode = Invoke-NovaInstall
    exit $installCode
  }

  "package-build" {
    $buildCode = Invoke-NovaPackageBuild $remainingTokens
    exit $buildCode
  }

  "package-verify" {
    $verifyCode = Invoke-NovaPackageVerify $remainingTokens
    exit $verifyCode
  }

  "installer-build" {
    $installerCode = Invoke-NovaInstallerBuild $remainingTokens
    exit $installerCode
  }

  "installer-verify" {
    $installerVerifyCode = Invoke-NovaInstallerVerify $remainingTokens
    exit $installerVerifyCode
  }

  "package-ledger" {
    $ledgerCode = Invoke-NovaPackageLedger $remainingTokens
    exit $ledgerCode
  }

  "installer-ledger" {
    $ledgerCode = Invoke-NovaInstallerLedger $remainingTokens
    exit $ledgerCode
  }

  "package-promote" {
    $promoteCode = Invoke-NovaPackagePromote $remainingTokens
    exit $promoteCode
  }

  "installer-promote" {
    $promoteCode = Invoke-NovaInstallerPromote $remainingTokens
    exit $promoteCode
  }

  "package-status" {
    $statusCode = Invoke-NovaPackageStatus $remainingTokens
    exit $statusCode
  }

  "installer-status" {
    $statusCode = Invoke-NovaInstallerStatus $remainingTokens
    exit $statusCode
  }

  "package-readiness" {
    $readinessCode = Invoke-NovaPackageReadiness $remainingTokens
    exit $readinessCode
  }

  "installer-readiness" {
    $readinessCode = Invoke-NovaInstallerReadiness $remainingTokens
    exit $readinessCode
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