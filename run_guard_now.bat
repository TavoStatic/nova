@echo off
cd /d C:\NOVA
if exist runtime\guard.stop del /f runtime\guard.stop
start "" /B "C:\NOVA\.venv\Scripts\python.exe" nova_guard.py
start "" /B "C:\NOVA\.venv\Scripts\python.exe" scripts\start_webui_detached.py
echo Guard and WebUI started.
