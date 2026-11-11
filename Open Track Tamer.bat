@echo off
REM Double-click launcher for Track Tamer GUI (Windows).
REM Uses the Anaconda environment from "Install Track Tamer.bat" when
REM it's installed. On computers without Anaconda it falls back to the
REM program's own virtual environment (app\.venv), creating it on first run.
REM (Mac equivalent: "Open Track Tamer.command")

REM Move to the program's "app" folder beside this script (handles spaces in the path).
cd /d "%~dp0app"

call find_conda.bat
if errorlevel 1 goto venv

call "%CONDA_BAT%" env list | findstr /b /c:"%ENV_NAME% " >nul
if errorlevel 1 goto no_conda_env
REM Activating (not just running its python.exe) sets the PATH that numpy
REM and the other packages need to load on Windows.
call "%CONDA_BAT%" activate %ENV_NAME%
if errorlevel 1 goto no_conda_env

fc /b environment.yml "%CONDA_PREFIX%\%STAMP_NAME%" >nul 2>nul
if errorlevel 1 (
    echo Note: the program's package list has changed since it was installed.
    echo Double-click "Install Track Tamer.bat" to update.
    echo.
)
set "PY=%CONDA_PREFIX%\python.exe"
goto launch

:no_conda_env
if exist ".venv\Scripts\python.exe" goto venv
echo Track Tamer isn't installed yet.
echo Double-click "Install Track Tamer.bat" first.
echo.
pause
exit /b 1

:venv
REM No Anaconda environment: use the virtual environment instead.
set "PY=.venv\Scripts\python.exe"

if exist "%PY%" goto launch

echo First run - setting up the environment (this can take a few minutes)...

REM Prefer the "py" launcher that the python.org installer adds; fall back to python.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if not exist "%PY%" (
    echo.
    echo Could not create the virtual environment.
    echo Install Anaconda and run "Install Track Tamer.bat", or install
    echo Python 3 from https://www.python.org/downloads/ and tick
    echo "Add python.exe to PATH" during setup, then run this again.
    pause
    exit /b 1
)

"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Dependency install failed. See the messages above.
    pause
    exit /b 1
)

:launch
REM Runs in this console window so any error messages stay visible.
"%PY%" gui.py
if errorlevel 1 (
    echo.
    echo The app closed with an error. See the messages above.
    pause
)
