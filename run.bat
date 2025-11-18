@echo on
setlocal enabledelayedexpansion

rem Move to the directory of this script
cd /d "%~dp0"

set EXITCODE=0

echo [INFO] Working directory: %CD%

rem 1) Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not available on PATH. Please install Python 3.x and try again.
    set EXITCODE=1
    goto :end
)

rem 2) Create venv if needed
if not exist ".venv" (
    echo [INFO] Creating virtual environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        set EXITCODE=1
        goto :end
    )
)

rem 3) Activate venv
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    set EXITCODE=1
    goto :end
)

rem 4) Install dependencies
echo [INFO] Installing/updating Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install -r requirements.txt failed.
    set EXITCODE=1
    goto :end
)

rem 5) Ensure TELEGRAM_BOT_TOKEN is present
if "%TELEGRAM_BOT_TOKEN%"=="" (
    echo.
    set /p TELEGRAM_BOT_TOKEN=Enter your Telegram bot token (from BotFather): 
)

if "%TELEGRAM_BOT_TOKEN%"=="" (
    echo [ERROR] TELEGRAM_BOT_TOKEN is empty. Cannot start the bot.
    set EXITCODE=1
    goto :end
)

echo [INFO] Using TELEGRAM_BOT_TOKEN starting with: %TELEGRAM_BOT_TOKEN:~0,6%*****

rem 6) Start the bot
echo [INFO] Starting Telegram Media Archiver Bot...
python main.py
set EXITCODE=%ERRORLEVEL%

:end
echo.
echo [INFO] Bot exited with code %EXITCODE%.
echo.
echo Press any key to close this window...
pause >nul

endlocal
