@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Modo console/depuracao opcional se invocado explicitamente com flag --console
if "%~1"=="--console" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    if exist "%PYTHON_EXE%" (
        "%PYTHON_EXE%" main.py --console
    ) else (
        python main.py --console
    )
    exit /b %errorlevel%
)

REM Inicializacao de producao desacoplada (sem janela CMD persistente)
if exist "%~dp0iniciar.vbs" (
    start "" wscript.exe "%~dp0iniciar.vbs"
    exit /b 0
)

REM Fallback direto para pythonw caso iniciar.vbs nao esteja presente
set "PYTHONW_EXE=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"

if exist "%PYTHONW_EXE%" (
    start "" "%PYTHONW_EXE%" "%~dp0main.py" %*
) else (
    start "" pythonw "%~dp0main.py" %*
)

exit /b 0
