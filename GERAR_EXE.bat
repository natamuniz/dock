@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Execute INSTALAR.bat primeiro.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6,<7"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir --name Dock --collect-submodules comtypes --collect-data tzdata --hidden-import PySide6.QtPdf --hidden-import PySide6.QtPdfWidgets --add-data "example-widgets;example-widgets" app.py
if errorlevel 1 goto failed
echo.
echo Pronto: dist\Dock\Dock.exe
echo Para levar a outro PC, copie toda a pasta dist\Dock.
pause
exit /b 0
:failed
echo.
echo A geracao nao terminou. Consulte o erro acima.
pause
exit /b 1
