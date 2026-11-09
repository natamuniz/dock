@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo Instalando NT Dock para este usuario...
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,15), 'Use Python 3.11 a 3.14'"
    if errorlevel 1 goto python_error
    if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
) else (
    python -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,15), 'Use Python 3.11 a 3.14'"
    if errorlevel 1 goto python_error
    if not exist ".venv\Scripts\python.exe" python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" goto install_error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto install_error
echo.
echo Instalacao concluida. Para abrir novamente use INICIAR.bat.
call INICIAR.bat
exit /b 0
:python_error
echo.
echo Instale Python 3.11 a 3.14 para Windows em https://www.python.org/downloads/windows/
echo Marque a opcao de adicionar Python ao PATH. Depois execute este arquivo novamente.
pause
exit /b 1
:install_error
echo.
echo A instalacao nao terminou. Verifique as mensagens e a conexao com a internet.
pause
exit /b 1
