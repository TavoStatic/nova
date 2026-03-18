@echo off
setlocal

set "NOVA_ROOT=%~dp0"
if "%NOVA_ROOT:~-1%"=="\" set "NOVA_ROOT=%NOVA_ROOT:~0,-1%"

set "NOVA_PS1=%NOVA_ROOT%\nova.ps1"
set "NOVA_RAW_ARGS=%*"

if not exist "%NOVA_PS1%" (
    echo [FAIL] Missing launcher script: %NOVA_PS1%
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%NOVA_PS1%" %*
exit /b %ERRORLEVEL%