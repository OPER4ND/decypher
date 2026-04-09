@echo off
echo ================================
echo  decypher setup
echo ================================
echo.

:: Get current directory
set "SCRIPT_DIR=%~dp0"

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
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Decypher.lnk'); $s.TargetPath = '%SCRIPT_DIR%decypher.exe'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()"
echo starting decypher...
start "" "%SCRIPT_DIR%decypher.exe"
goto done

:startup_only
echo.
echo setting up auto-start...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Decypher.lnk'); $s.TargetPath = '%SCRIPT_DIR%decypher.exe'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()"
goto done

:run_only
echo.
echo starting decypher...
start "" "%SCRIPT_DIR%decypher.exe"
goto done

:done
echo.
echo ================================
echo  done
echo ================================
echo.
pause
