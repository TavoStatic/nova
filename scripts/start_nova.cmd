@echo off
setlocal
cd /d C:\nova

echo [1/3] Ollama...
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" (
  start "" /MIN "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
)
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
  start "" /MIN "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
)
timeout /t 5 /nobreak >nul

echo [2/3] Guard...
start "nova-guard" /MIN "C:\nova\.venv\Scripts\python.exe" C:\nova\nova_guard.py
timeout /t 4 /nobreak >nul

echo [3/3] Web UI...
start "nova-http" /MIN "C:\nova\.venv\Scripts\python.exe" C:\nova\nova_http.py --host 127.0.0.1 --port 8080
timeout /t 6 /nobreak >nul

echo.
echo Control Room: http://127.0.0.1:8080/control
echo If the page fails, run this script again.
echo.
endlocal
