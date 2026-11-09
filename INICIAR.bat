@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Execute INSTALAR.bat primeiro.
    pause
    exit /b 1
)
start "NT Dock" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
