@echo off
echo ===================================================
echo   Installing AgentLens CLI (Pure Standalone)
echo ===================================================

python -m pip install -e .

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Installation failed. Ensure Python 3.9+ and pip are installed.
    exit /b 1
)

echo.
echo ===================================================
echo   Verifying Installation...
echo ===================================================
agentlens --help

echo.
echo ===================================================
echo   SUCCESS! AgentLens CLI is installed and ready.
echo   Try:
echo     agentlens run
echo     agentlens scan ..
echo ===================================================
