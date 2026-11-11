@echo off
REM Double-click installer for Track Tamer (Windows, Anaconda).
REM Builds the conda environment from environment.yml, or updates it to match
REM if it's already installed, so it's safe to run again after an update.
REM (Mac equivalent: "Install Track Tamer.command")

REM Move to the program's "app" folder beside this script (handles spaces in the path).
cd /d "%~dp0app"

call find_conda.bat
if errorlevel 1 (
    echo Anaconda wasn't found on this computer.
    echo Install Anaconda or Miniconda ^(https://www.anaconda.com/download^),
    echo then double-click this installer again.
    goto failed
)
echo Using conda at %CONDA_BASE%
echo.

call "%CONDA_BAT%" env list | findstr /b /c:"%ENV_NAME% " >nul
if errorlevel 1 goto create

echo Updating the "%ENV_NAME%" environment (this can take a few minutes)...
call "%CONDA_BAT%" env update -n %ENV_NAME% -f environment.yml --prune
if errorlevel 1 goto install_failed
goto check

:create
echo Creating the "%ENV_NAME%" environment (this can take a few minutes)...
call "%CONDA_BAT%" env create -f environment.yml
if errorlevel 1 goto install_failed

:check
call "%CONDA_BAT%" activate %ENV_NAME%
if errorlevel 1 (
    echo Couldn't activate "%ENV_NAME%".
    goto failed
)
python -c "import pandas, numpy, matplotlib, openpyxl, tkinter, tkinterdnd2, cv2, PIL"
if errorlevel 1 (
    echo.
    echo The environment was built but a package won't load. See the messages above.
    goto failed
)
REM Remember which environment.yml this was built from (see the Open launcher).
copy /y environment.yml "%CONDA_PREFIX%\%STAMP_NAME%" >nul

echo.
echo Done. Double-click "Open Track Tamer.bat" to start the app.
echo.
pause
exit /b 0

:install_failed
echo.
echo Install failed. See the messages above.

:failed
echo.
pause
exit /b 1
