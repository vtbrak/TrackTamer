@echo off
REM Double-click uninstaller for Track Tamer (Windows, Anaconda).
REM Removes only the conda environment; the program folder and your data,
REM results and settings are left untouched.
REM (Mac equivalent: "Uninstall Track Tamer.command")

REM Move to the program's "app" folder beside this script (handles spaces in the path).
cd /d "%~dp0app"

call find_conda.bat
if errorlevel 1 (
    echo Anaconda wasn't found, so there's no environment to remove.
    goto done
)
call "%CONDA_BAT%" env list | findstr /b /c:"%ENV_NAME% " >nul
if errorlevel 1 (
    echo The "%ENV_NAME%" environment isn't installed. Nothing to remove.
    goto done
)

set "ANSWER="
set /p "ANSWER=Remove the "%ENV_NAME%" environment? Your files are kept. [y/N] "
if /i not "%ANSWER:~0,1%"=="y" (
    echo Nothing removed.
    goto done
)

call "%CONDA_BAT%" remove -n %ENV_NAME% --all -y
if errorlevel 1 (
    echo.
    echo Removal failed. See the messages above.
    goto done
)
echo.
echo Removed. Run "Install Track Tamer.bat" to install it again.

:done
echo.
pause
