@echo off
REM Finds Anaconda/Miniconda for the Windows launchers (use: call find_conda.bat).
REM (Mac equivalent: find_conda.sh)
REM
REM Sets, for the calling script:
REM   ENV_NAME     the environment name from environment.yml
REM   STAMP_NAME   copy of environment.yml kept inside the installed env, so
REM                the Open launcher can tell when the file has changed since
REM   CONDA_BASE   the Anaconda folder, and CONDA_BAT, its condabin\conda.bat
REM                (use: call "%CONDA_BAT%" activate ...)
REM Exits with errorlevel 1 if conda isn't found.

set "ENV_NAME="
for /f "tokens=2" %%N in ('findstr /b /c:"name:" environment.yml') do (
    if not defined ENV_NAME set "ENV_NAME=%%N"
)
set "STAMP_NAME=track-tamer-environment.yml"
set "CONDA_BASE="
set "CONDA_BAT="

REM Already known: CONDA_EXE is set by conda itself (...\Scripts\conda.exe).
if defined CONDA_EXE for %%I in ("%CONDA_EXE%\..\..") do call :try "%%~fI"
if defined CONDA_BAT exit /b 0

REM On PATH (condabin\conda.bat or Scripts\conda.exe): the base is one up.
for /f "delims=" %%I in ('where conda 2^>nul') do (
    if not defined CONDA_BAT for %%J in ("%%~dpI..") do call :try "%%~fJ"
)
if defined CONDA_BAT exit /b 0

REM Otherwise, the usual install folders ("just me" and "all users").
for %%B in (
    "%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3"
    "%USERPROFILE%\miniforge3" "%USERPROFILE%\mambaforge"
    "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3"
    "%LOCALAPPDATA%\Continuum\anaconda3" "%LOCALAPPDATA%\Continuum\miniconda3"
    "%ProgramData%\anaconda3" "%ProgramData%\miniconda3" "%ProgramData%\miniforge3"
    "C:\anaconda3" "C:\miniconda3"
) do (
    if not defined CONDA_BAT call :try "%%~B"
)
if defined CONDA_BAT exit /b 0
exit /b 1

:try
if exist "%~1\condabin\conda.bat" (
    set "CONDA_BASE=%~1"
    set "CONDA_BAT=%~1\condabin\conda.bat"
)
exit /b 0
