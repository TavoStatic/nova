param(
  [switch]$Json
)

$ErrorActionPreference = "Stop"

function Get-CommandPathOrEmpty([string]$name) {
  try {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
      return [string]$cmd.Source
    }
  } catch {
  }
  return ""
}

function Get-PortListenerInfo([int[]]$Ports) {
  $rows = @()
  foreach ($port in @($Ports)) {
    $listeners = @()
    try {
      $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
    } catch {
      $listeners = @()
    }

    $owning = @($listeners | ForEach-Object { [int]$_.OwningProcess } | Select-Object -Unique)
    $rows += [pscustomobject]@{
      port = [int]$port
      in_use = ($owning.Count -gt 0)
      owning_pids = @($owning)
    }
  }
  return @($rows)
}

$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$cpu = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
$computer = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
$gpus = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue)

$systemDrive = [System.Environment]::GetFolderPath("System")
$systemRoot = if ([string]::IsNullOrWhiteSpace($systemDrive)) { $env:SystemDrive } else { [System.IO.Path]::GetPathRoot($systemDrive) }
if ([string]::IsNullOrWhiteSpace($systemRoot)) {
  $systemRoot = $env:SystemDrive
}
$disk = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='" + $systemRoot.TrimEnd('\\') + "'") -ErrorAction SilentlyContinue

$pythonCmd = Get-CommandPathOrEmpty "python"
$pyLauncher = Get-CommandPathOrEmpty "py"
$ollamaCmd = Get-CommandPathOrEmpty "ollama"
$ports = @(Get-PortListenerInfo @(8080, 11434))

$totalRamGb = if ($computer -and $computer.TotalPhysicalMemory) { [math]::Round(([double]$computer.TotalPhysicalMemory / 1GB), 2) } else { $null }
$freeRamGb = if ($os -and $os.FreePhysicalMemory) { [math]::Round((([double]$os.FreePhysicalMemory * 1KB) / 1GB), 2) } else { $null }
$freeDiskGb = if ($disk -and $disk.FreeSpace) { [math]::Round(([double]$disk.FreeSpace / 1GB), 2) } else { $null }

$issues = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

if ($cpu -and [int]$cpu.AddressWidth -lt 64) {
  [void]$issues.Add("64-bit Windows is required for the recommended NYO System install path.")
}

if ($null -ne $totalRamGb -and $totalRamGb -lt 8) {
  [void]$warnings.Add("Less than 8 GB RAM detected; base install may work, but runtime headroom will be limited.")
}

if ($null -ne $freeDiskGb -and $freeDiskGb -lt 5) {
  [void]$issues.Add("Less than 5 GB free disk space detected on the system drive.")
}

if ([string]::IsNullOrWhiteSpace($pythonCmd) -and [string]::IsNullOrWhiteSpace($pyLauncher)) {
  [void]$warnings.Add("Python was not found on PATH. Phase-1 bootstrap installer would need the user to install Python first.")
}

if ([string]::IsNullOrWhiteSpace($ollamaCmd)) {
  [void]$warnings.Add("Ollama was not found on PATH. Base package can still install, but model-backed runtime will be limited.")
}

foreach ($portInfo in $ports) {
  if ($portInfo.in_use) {
    if ([int]$portInfo.port -eq 8080) {
      [void]$warnings.Add("Port 8080 is already in use; NYO System Control may need a different bind port.")
    }
    if ([int]$portInfo.port -eq 11434) {
      [void]$warnings.Add("Port 11434 is already in use; verify it belongs to Ollama before runtime validation.")
    }
  }
}

$baseReady = ($issues.Count -eq 0)
$runtimeReady = $baseReady -and (-not [string]::IsNullOrWhiteSpace($ollamaCmd))

$summary = if (-not $baseReady) {
  "Blocked"
} elseif ($runtimeReady) {
  "Runtime OK"
} elseif ($baseReady) {
  "Runtime limited: Ollama missing"
} else {
  "Base package limited"
}

$payload = [ordered]@{
  summary = $summary
  base_ready = $baseReady
  runtime_ready = $runtimeReady
  os = [ordered]@{
    caption = if ($os) { [string]$os.Caption } else { "" }
    version = if ($os) { [string]$os.Version } else { "" }
    build = if ($os) { [string]$os.BuildNumber } else { "" }
  }
  cpu = [ordered]@{
    name = if ($cpu) { [string]$cpu.Name } else { "" }
    logical_cores = if ($cpu) { [int]$cpu.NumberOfLogicalProcessors } else { $null }
    address_width = if ($cpu) { [int]$cpu.AddressWidth } else { $null }
  }
  memory = [ordered]@{
    total_gb = $totalRamGb
    free_gb = $freeRamGb
  }
  disk = [ordered]@{
    system_drive = $systemRoot
    free_gb = $freeDiskGb
  }
  gpu = @(
    $gpus | ForEach-Object {
      [ordered]@{
        name = [string]$_.Name
        adapter_ram_gb = if ($_.AdapterRAM) { [math]::Round(([double]$_.AdapterRAM / 1GB), 2) } else { $null }
      }
    }
  )
  dependencies = [ordered]@{
    python = [ordered]@{
      python_cmd = $pythonCmd
      py_launcher = $pyLauncher
      found = (-not [string]::IsNullOrWhiteSpace($pythonCmd) -or -not [string]::IsNullOrWhiteSpace($pyLauncher))
    }
    ollama = [ordered]@{
      command = $ollamaCmd
      found = (-not [string]::IsNullOrWhiteSpace($ollamaCmd))
    }
  }
  ports = $ports
  issues = @($issues)
  warnings = @($warnings)
}

if ($Json) {
  $payload | ConvertTo-Json -Depth 6
  exit 0
}

Write-Host ""
Write-Host "NYO System Installer Readiness"
Write-Host "------------------------------"
Write-Host ("Summary             : " + $payload.summary)
Write-Host ("Windows             : " + $payload.os.caption + " " + $payload.os.version + " (build " + $payload.os.build + ")")
Write-Host ("CPU                 : " + $payload.cpu.name)
Write-Host ("Logical cores       : " + $(if ($null -ne $payload.cpu.logical_cores) { $payload.cpu.logical_cores } else { "-" }))
Write-Host ("RAM total/free GB   : " + $(if ($null -ne $payload.memory.total_gb) { $payload.memory.total_gb } else { "-" }) + " / " + $(if ($null -ne $payload.memory.free_gb) { $payload.memory.free_gb } else { "-" }))
Write-Host ("Disk free GB        : " + $(if ($null -ne $payload.disk.free_gb) { $payload.disk.free_gb } else { "-" }))
Write-Host ("Python found        : " + $(if ($payload.dependencies.python.found) { "yes" } else { "no" }))
Write-Host ("Ollama found        : " + $(if ($payload.dependencies.ollama.found) { "yes" } else { "no" }))

foreach ($portInfo in $payload.ports) {
  Write-Host ("Port " + $portInfo.port + " in use     : " + $(if ($portInfo.in_use) { "yes" } else { "no" }))
}

if ($payload.issues.Count -gt 0) {
  Write-Host ""
  Write-Host "Blocking issues:"
  foreach ($item in $payload.issues) {
    Write-Host ("- " + $item)
  }
}

if ($payload.warnings.Count -gt 0) {
  Write-Host ""
  Write-Host "Warnings:"
  foreach ($item in $payload.warnings) {
    Write-Host ("- " + $item)
  }
}

exit 0