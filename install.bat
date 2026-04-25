@echo off
setlocal
echo ================================
echo  decypher installer
echo ================================
echo.

set "SCRIPT_DIR=%~dp0"

if not exist "%SCRIPT_DIR%overlay.py" (
    echo overlay.py not found in this folder.
    pause
    exit /b 1
)

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo python not found. please install python 3.10+ from python.org
    pause
    exit /b 1
)

:: Install dependencies
echo installing dependencies...
python -m pip install -r "%SCRIPT_DIR%requirements.txt" -q
echo.

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
python "%SCRIPT_DIR%setup_startup.py"
echo starting decypher...
python "%SCRIPT_DIR%setup_startup.py" --launch
goto done

:startup_only
echo.
echo setting up auto-start...
python "%SCRIPT_DIR%setup_startup.py"
goto done

:run_only
echo.
echo starting decypher...
python "%SCRIPT_DIR%setup_startup.py" --launch
goto done

:done
echo.
echo ================================
echo  done
echo ================================
echo.
endlocal
pause
