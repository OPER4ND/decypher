@echo off
setlocal
echo ================================
echo  decypher setup
echo ================================
echo.

:: Get current directory
set "SCRIPT_DIR=%~dp0"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "EXE_PATH=%SCRIPT_DIR%decypher.exe"

if not exist "%EXE_PATH%" (
    echo decypher.exe not found in this folder.
    echo run this script from the extracted release zip folder that contains decypher.exe
    pause
    exit /b 1
)

:: Options menu
echo select an option:
echo   1. install on startup and run now
echo   2. install on startup only
echo   3. run now only
echo.
choice /c 123 /n /m "enter choice (1-3): "

if errorlevel 3 goto run_only
if errorlevel 2 goto startup_only
if errorlevel 1 goto startup_and_run

:startup_and_run
echo.
echo setting up auto-start...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$startup = '%STARTUP_DIR%'; foreach ($name in 'run_decypher.vbs','Decypher.lnk') { $path = Join-Path $startup $name; if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }; $ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut((Join-Path $startup 'Decypher.lnk')); $s.TargetPath = '%EXE_PATH%'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()"
echo starting decypher...
start "" "%EXE_PATH%"
goto done

:startup_only
echo.
echo setting up auto-start...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$startup = '%STARTUP_DIR%'; foreach ($name in 'run_decypher.vbs','Decypher.lnk') { $path = Join-Path $startup $name; if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }; $ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut((Join-Path $startup 'Decypher.lnk')); $s.TargetPath = '%EXE_PATH%'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()"
goto done

:run_only
echo.
echo starting decypher...
start "" "%EXE_PATH%"
goto done

:done
echo.
echo ================================
echo  done
echo ================================
echo.
endlocal
pause
