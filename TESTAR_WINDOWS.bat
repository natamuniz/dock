@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Execute INSTALAR.bat primeiro.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -s tests -v
set "ntdock_test_exit=%ERRORLEVEL%"
pause
exit /b %ntdock_test_exit%
