@echo on
setlocal EnableExtensions EnableDelayedExpansion

rem Move to the repository root (same directory as this script)
cd /d "%~dp0"
set "APP_BASE_DIR=%CD%"
set EXITCODE=0

echo [INFO] Working directory: %APP_BASE_DIR%

rem Load environment variables from .env if present (ignoring comment/blank lines)
if exist ".env" (
    echo [INFO] Loading environment variables from .env
    for /f "usebackq tokens=* delims=" %%i in (".env") do (
        set "LINE=%%i"
        if not "!LINE!"=="" if not "!LINE:~0,1!"=="#" set "!LINE!"
    )
)

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

set "APP_BASE_DIR=%APP_BASE_DIR%"
set "PYTHONUNBUFFERED=1"

rem 4) Install dependencies if needed
if exist requirements.txt (
    echo [INFO] Installing/updating Python dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] pip install -r requirements.txt failed.
        set EXITCODE=1
        goto :end
    )
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

echo [INFO] Starting Telegram Media Archiver Bot...
python main.py
set EXITCODE=%ERRORLEVEL%

:end
echo.
if %EXITCODE% EQU 0 (
    echo [INFO] Bot exited normally with code %EXITCODE%.
) else (
    echo [ERROR] Bot terminated with code %EXITCODE%. Review the logs above for details.
)
echo.
echo Press any key to close this window...
pause >nul

endlocal
