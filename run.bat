@echo off
REM One-click setup and run script for Windows
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not found in PATH. Please install Python 3 and try again.
    pause
    goto :eof
)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

if "%TELEGRAM_BOT_TOKEN%"=="" (
    set /p TELEGRAM_BOT_TOKEN=Enter your Telegram bot token (from BotFather): 
)

echo Starting bot...
python main.py

echo.
echo Bot stopped. Press any key to close.
pause
