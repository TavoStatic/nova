$ErrorActionPreference = 'SilentlyContinue'
Set-Location 'C:\NOVA'

$serverSideDockerEnabled = $false
$policyPath = '.\policy.json'
if (Test-Path $policyPath) {
    try {
        $policy = Get-Content $policyPath -Raw | ConvertFrom-Json
        if ($null -ne $policy.server_side -and $null -ne $policy.server_side.docker_enabled) {
            $serverSideDockerEnabled = [bool]$policy.server_side.docker_enabled
        }
    } catch {
        $serverSideDockerEnabled = $false
    }
}

# Start nova-searxng container only when server-side policy enables Docker support.
if ($serverSideDockerEnabled) {
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($dockerCmd) {
        $containerName = 'nova-searxng'
        $containerExists = & docker ps -a --filter "name=^${containerName}$" --format "{{.Names}}" 2>$null
        if ($containerExists -contains $containerName) {
            & docker start $containerName | Out-Null
        }
    }
}

Start-Process -FilePath 'C:\Users\hotst\AppData\Local\Programs\Ollama\ollama.exe' -ArgumentList @('serve') -WindowStyle Hidden
Start-Sleep -Seconds 2
if (Test-Path '.\\runtime\\guard.stop') { Remove-Item '.\\runtime\\guard.stop' -Force -ErrorAction SilentlyContinue }
Start-Process -FilePath 'C:\NOVA\.venv\Scripts\python.exe' -ArgumentList @('nova_guard.py') -WindowStyle Hidden
Start-Sleep -Seconds 3
Start-Process -FilePath 'C:\NOVA\nova.cmd' -ArgumentList @('webui-start','--host','127.0.0.1','--port','8080') -WindowStyle Hidden
