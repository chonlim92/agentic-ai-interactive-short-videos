@echo off
REM start-site.bat — Start the StorySmith AI dev server (cmd.exe version)
REM Appends system paths so npm is found, WITHOUT replacing existing PATH (preserves venv).

REM Check if npm is already available
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo npm not found, appending system paths...
    for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
    for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
    set "PATH=%PATH%;%SYS_PATH%;%USR_PATH%"
)

REM Verify npm
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: npm still not found. Install Node.js and add to system PATH.
    exit /b 1
)

REM Start the dev server
cd /d "%~dp0site"
echo Starting Next.js dev server on port 3000...
npm run dev -- --port 3000
