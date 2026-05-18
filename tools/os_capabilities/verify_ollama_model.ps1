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

$baseUrl = [string]($argsObject.base_url)
if (-not $baseUrl) {
    $baseUrl = "http://127.0.0.1:11434"
}
$model = [string]($argsObject.model)
if (-not $model) {
    $model = "llama3.2:3b"
}
$probeChat = [bool]($argsObject.probe_chat)
$timeoutSec = 5

$result = @{
    ok = $false
    base_url = $baseUrl
    model = $model
    api_up = $false
    model_present = $false
    chat_ready = $false
    version = ""
    errors = @()
}

try {
    $versionResponse = Invoke-RestMethod -Method Get -Uri "$baseUrl/api/version" -TimeoutSec $timeoutSec
    $result.api_up = $true
    if ($versionResponse.version) {
        $result.version = [string]$versionResponse.version
    }
} catch {
    $result.errors += "version_probe_failed:$($_.Exception.Message)"
}

try {
    $tagsResponse = Invoke-RestMethod -Method Get -Uri "$baseUrl/api/tags" -TimeoutSec $timeoutSec
    $models = @($tagsResponse.models)
    foreach ($item in $models) {
        if ([string]$item.name -eq $model) {
            $result.model_present = $true
            break
        }
    }
} catch {
    $result.errors += "tags_probe_failed:$($_.Exception.Message)"
}

if ($probeChat -and $result.model_present) {
    try {
        $body = @{
            model = $model
            messages = @(@{ role = "user"; content = "respond with ok" })
            stream = $false
            options = @{ num_predict = 8 }
        } | ConvertTo-Json -Depth 8
        $chatResponse = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/chat" -Body $body -ContentType "application/json" -TimeoutSec $timeoutSec
        if ($chatResponse.message.content) {
            $result.chat_ready = $true
        }
    } catch {
        $result.errors += "chat_probe_failed:$($_.Exception.Message)"
    }
} elseif ($result.model_present) {
    $result.chat_ready = $true
}

$result.ok = [bool]($result.api_up -and $result.model_present -and $result.chat_ready)
Write-JsonResult $result
exit 0
