param(
    [string]$RepoUrl = 'https://github.com/TavoStatic/nova.git',
    [string]$Dest = 'C:\\Nova',
    [switch]$Force
)

function Timestamp() { return (Get-Date).ToString('yyyyMMdd_HHmmss') }

if (Test-Path $Dest) {
    if (-not $Force) {
        Write-Host "Destination '$Dest' already exists. Re-run with -Force to back up and replace." -ForegroundColor Yellow
        exit 1
    }
    $bak = "$Dest-backup-$(Timestamp())"
    Write-Host "Backing up existing folder to: $bak"
    Rename-Item -Path $Dest -NewName $bak -ErrorAction Stop
}

Write-Host "Cloning $RepoUrl -> $Dest"
git clone $RepoUrl $Dest
if ($LASTEXITCODE -ne 0) { Write-Host 'git clone failed' -ForegroundColor Red; exit 2 }

# Create venv
Write-Host 'Creating virtual environment...'
python -m venv "$Dest\\.venv"
if ($LASTEXITCODE -ne 0) { Write-Host 'venv creation failed' -ForegroundColor Red; exit 3 }

$py = "$Dest\\.venv\\Scripts\\python.exe"
Write-Host 'Upgrading pip and installing requirements (if present)...'
& $py -m pip install --upgrade pip | Out-Null
if (Test-Path "$Dest\\requirements.txt") {
    & $py -m pip install -r "$Dest\\requirements.txt"
}

# Run smoke e2e
Write-Host 'Running smoke e2e runner (this may take a few seconds)...'
& $py "$Dest\\scripts\\smoke_e2e.py"
$smokeCode = $LASTEXITCODE

# Run unit tests as a fallback verification
Write-Host 'Running unit tests...'
& $py -m unittest discover -v -s "$Dest\\tests"
$testCode = $LASTEXITCODE

# Compute repo size
Write-Host 'Calculating repository size...'
$size = (Get-ChildItem -Path $Dest -Recurse -File | Measure-Object -Property Length -Sum).Sum
$sizeMb = '{0:N2}' -f ($size/1MB)
Write-Host "Repo size: $sizeMb MB"

if ($smokeCode -eq 0 -and $testCode -eq 0) {
    Write-Host 'Verification complete: smoke runner and tests passed.' -ForegroundColor Green
    exit 0
} else {
    Write-Host 'Verification completed with non-zero exit code(s).' -ForegroundColor Yellow
    exit 4
}
