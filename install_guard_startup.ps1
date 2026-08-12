# Nova Guard — Windows Task Scheduler registration
# Run this once as Administrator (or right-click -> Run with PowerShell)
# After this, the guard starts automatically at every login.

$taskName  = "NovaGuard"
$novaRoot  = "C:\NOVA"
$python    = "C:\NOVA\.venv\Scripts\python.exe"
$script    = "nova_guard.py"
$logFile   = "C:\NOVA\runtime\guard_startup_task.log"

# Remove any previous version of this task
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument $script `
    -WorkingDirectory $novaRoot

# Trigger: at logon of whichever user runs this script
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName  $taskName `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -Principal $principal `
    -Description "Starts Nova Guard (nova_guard.py) at login. Restarts up to 5x on crash." `
    -Force

# Verify registration
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Host "OK  Nova Guard task registered. It will start automatically at next login."
    Write-Host "    To start it NOW without rebooting, run:"
    Write-Host "    Start-ScheduledTask -TaskName NovaGuard"
} else {
    Write-Host "FAIL  Task registration failed. Check permissions."
}
