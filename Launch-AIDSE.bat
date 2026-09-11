@echo off
title AIDSE Desktop Launcher
cd /d "%~dp0"

set "DATA_DIR=%LOCALAPPDATA%\AIDSE-Desktop"
set "PORT_FILE=%DATA_DIR%\port.txt"
set "PROFILE_DIR=%DATA_DIR%\profile"
set "ERROR_LOG=%DATA_DIR%\startup_error.log"
set "CRASH_MARKER=%DATA_DIR%\startup_crashed.txt"
set "BACKEND_EXE=dist\aidse-backend\aidse-backend.exe"

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

set "TARGET_PORT=8010"
if exist "%PORT_FILE%" (
    set /p SAVED_PORT=<"%PORT_FILE%"
    if defined SAVED_PORT set "TARGET_PORT=%SAVED_PORT%"
)

rem 1. Check if AIDSE is already running
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%TARGET_PORT%/health' -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 goto launch_browser

rem Check if backend binary exists
if not exist "%BACKEND_EXE%" (
    echo [ERROR] Backend executable not found at %BACKEND_EXE%
    powershell -Command "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; [System.Windows.Forms.MessageBox]::Show('Could not find AIDSE engine at: %BACKEND_EXE%', 'AIDSE Startup Error', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)"
    exit /b 1
)

rem Pre-flight check for runtime directory & DLLs
set "INTERNAL_DIR=dist\aidse-backend\_internal"
if exist "%INTERNAL_DIR%" (
    if not exist "%INTERNAL_DIR%\python3.dll" (
        powershell -Command "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; [System.Windows.Forms.MessageBox]::Show('System file python3.dll is missing. Please reinstall AIDSE Desktop.', 'Missing File - AIDSE Startup Error', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)"
        exit /b 1
    )
    if not exist "%INTERNAL_DIR%\sqlite3.dll" (
        powershell -Command "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; [System.Windows.Forms.MessageBox]::Show('System file sqlite3.dll is missing. Please reinstall AIDSE Desktop.', 'Missing File - AIDSE Startup Error', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)"
        exit /b 1
    )
)


rem 2. Delete stale markers & start backend with stderr capture
if exist "%PORT_FILE%" del /f /q "%PORT_FILE%" >nul 2>&1
if exist "%ERROR_LOG%" del /f /q "%ERROR_LOG%" >nul 2>&1
if exist "%CRASH_MARKER%" del /f /q "%CRASH_MARKER%" >nul 2>&1

echo Starting AIDSE Local Backend (auto-selecting free port)...
start /b "" cmd.exe /c """%BACKEND_EXE%"" --host 127.0.0.1 2> ""%ERROR_LOG%"""

echo Waiting for AIDSE services to become healthy...
set /a attempts=0

:wait_loop
set /a attempts+=1

if exist "%PORT_FILE%" (
    set /p SAVED_PORT=<"%PORT_FILE%"
    if defined SAVED_PORT set "TARGET_PORT=%SAVED_PORT%"
)

powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%TARGET_PORT%/health' -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 goto launch_browser

rem Early crash detection: if process died prematurely
if %attempts% gtr 12 (
    tasklist /fi "imagename eq aidse-backend.exe" 2>nul | find /i "aidse-backend.exe" >nul
    if errorlevel 1 goto startup_failed
)

if %attempts% gtr 90 goto startup_failed

timeout /t 1 /nobreak >nul
goto wait_loop

:startup_failed
echo.
echo ===============================================================================
echo [ERROR] AIDSE Local Engine failed to start or did not pass healthcheck.
if exist "%ERROR_LOG%" (
    echo Startup error log excerpt:
    type "%ERROR_LOG%"
)
echo.
echo Full error log saved at: %ERROR_LOG%
echo ===============================================================================
powershell -Command "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; [System.Windows.Forms.MessageBox]::Show('An error occurred while starting the AIDSE local engine.`n`nPlease check the log file at:`n%ERROR_LOG%', 'AIDSE Startup Error', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)"
exit /b 1

:launch_browser
echo Launching AIDSE Desktop Application on port %TARGET_PORT%...
if exist "%PROFILE_DIR%\Default\Extensions" rmdir /s /q "%PROFILE_DIR%\Default\Extensions" >nul 2>&1
set "EDGE_FLAGS=--disable-extensions --disable-sync --disable-features=msEdgeSidebarSupport,msHubApps,msEdgeCopilot,msEdgeSearchCopilotProvider,msEdgeShopping --no-first-run --no-default-browser-check"
start "" msedge.exe --app="http://127.0.0.1:%TARGET_PORT%" --user-data-dir="%PROFILE_DIR%" %EDGE_FLAGS% --window-size=1280,832 || start "" "http://127.0.0.1:%TARGET_PORT%"

