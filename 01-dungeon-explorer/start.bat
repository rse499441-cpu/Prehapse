
@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Config created: .env
  echo Fill in DISCORD_TOKEN, TEST_GUILD_ID and DUNGEON_CHANNEL_ID, then run start.bat again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First launch: creating Python environment...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -m venv .venv
  ) else (
    where python >nul 2>nul
    if errorlevel 1 goto :python_error
    python -m venv .venv
  )
  if errorlevel 1 goto :python_error

  echo Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :install_error
)

echo Starting Dungeon Explorer Bot...
".venv\Scripts\python.exe" -u bot.py
if errorlevel 1 echo Bot stopped because of the error shown above.
pause
exit /b

:python_error
echo Python was not found. Install Python 3.11 or newer and enable Add Python to PATH.
pause
exit /b 1

:install_error
echo Dependency installation failed. Check your network and run start.bat again.
pause
exit /b 1
