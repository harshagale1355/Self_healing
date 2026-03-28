@echo off
setlocal
echo 📦 Packaging AI Log Analyzer for Windows...

:: Check for flet in venv
if not exist "venv\Scripts\flet.exe" (
    echo ❌ Error: flet not found in venv\Scripts. Make sure you have created the venv and installed dependencies.
    exit /b 1
)

:: Package as native desktop executable
:: --onefile: produce a single executable
:: --noconsole: don't show terminal window when running (GUI only)
venv\Scripts\flet.exe pack ui\app_flet.py ^
  --name "AI Log Analyzer" ^
  --icon assets\icon.png ^
  --add-data "agents;agents" ^
  --add-data "rag;rag" ^
  --add-data "workflows;workflows" ^
  --add-data "utils;utils" ^
  --add-data "prompts;prompts" ^
  --add-data "config.py;." ^
  --add-data "requirements.txt;."

echo ✅ Windows build complete! Executable is in the 'dist' folder.
pause
