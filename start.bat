@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "PYTHON=%ROOT%env\python\python311\python.exe"
set "NODE=%ROOT%env\node\node-v20\node-v20.18.3-win-x64\node.exe"
set "NPM=%ROOT%env\node\node-v20\node-v20.18.3-win-x64\npm.cmd"
set "NPX=%ROOT%env\node\node-v20\node-v20.18.3-win-x64\npx.cmd"
set "MARKER=%ROOT%data\.installed"

echo ============================================================
echo   NVIDIA API Pool Manager
echo ============================================================

REM ==================== Check Environment ====================
if not exist "%PYTHON%" (
    echo.
    echo [ERROR] Python not found. Please keep this folder structure intact:
    echo   env\python\python311\python.exe
    echo.
    pause
    exit /b 1
)

if not exist "%NODE%" (
    echo.
    echo [ERROR] Node.js not found. Please keep this folder structure intact:
    echo   env\node\node-v20\node-v20.18.3-win-x64\node.exe
    echo.
    pause
    exit /b 1
)

"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python cannot run. You may need VC++ Redistributable:
    echo https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo.
    pause
    exit /b 1
)

REM ==================== Auto Install ====================
if exist "%MARKER%" (
    echo Already installed, skipping setup...
    goto :start
)

echo.
echo First run, installing dependencies...
echo.

echo [1/3] Installing Python packages...
"%PYTHON%" -m pip install -r "%ROOT%requirements.txt" --no-warn-script-location
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)
echo Done.

echo [2/3] Installing frontend packages...
cd /d "%ROOT%frontend"
call "%NPM%" install
if errorlevel 1 (
    echo [ERROR] npm install failed
    pause
    exit /b 1
)
echo Done.

echo [3/3] Building frontend...
call "%NPX%" vite build
if errorlevel 1 (
    echo [ERROR] frontend build failed
    pause
    exit /b 1
)
echo Done.

if not exist "%ROOT%data" mkdir "%ROOT%data"
echo installed > "%MARKER%"
echo.
echo Setup complete!

REM ==================== Start Service ====================
:start
echo.
echo   Proxy: http://localhost:8080
echo   GUI:   http://localhost:8081
echo.
echo   Press Ctrl+C to stop
echo ============================================================
echo.

cd /d "%ROOT%"
"%PYTHON%" main.py --config config\config.yaml

pause
