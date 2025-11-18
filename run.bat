@echo on
setlocal enabledelayedexpansion

rem Move to this script's directory
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not available on PATH. Please install Python 3.x and reopen this script.
    echo.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [INFO] Creating virtual environment (.venv)...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    echo.
    pause
    exit /b 1
)

echo [INFO] Installing/updating Python dependencies...
pip install -r requirements.txt

if "%TELEGRAM_BOT_TOKEN%"=="" (
    echo.
    set /p TELEGRAM_BOT_TOKEN=Enter your Telegram bot token (from BotFather): 
)

if "%TELEGRAM_BOT_TOKEN%"=="" (
    echo [ERROR] TELEGRAM_BOT_TOKEN is still empty. Cannot start the bot.
    echo.
    pause
    exit /b 1
)

echo [INFO] Using TELEGRAM_BOT_TOKEN starting with: %TELEGRAM_BOT_TOKEN:~0,6%*****

echo [INFO] Starting Telegram Media Archiver Bot...
python main.py
set EXITCODE=%ERRORLEVEL%
echo.
echo [INFO] Bot exited with code %EXITCODE%.

echo.
echo Press any key to close this window...
pause >nul

endlocal
