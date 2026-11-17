@echo off
rem SPDX-License-Identifier: AGPL-3.0-only
rem AudioHub LOCAL OFFLINE music preparation: user starts this explicitly.
rem No codec installer, network request, Pi access, media write or auto-export.
setlocal DisableDelayedExpansion
set "AUDIOHUB_DIR=%~dp0"
if "%AUDIOHUB_DIR:~0,2%"=="\\" goto refuse_network
pushd "%AUDIOHUB_DIR%" || goto error
set "MODE=--gui"
if /I "%~1"=="--check" set "MODE=--check-local"
if not "%~2"=="" goto error_pushed
if not "%~1"=="" if /I not "%~1"=="--check" goto error_pushed
where py.exe >nul 2>&1
if not errorlevel 1 goto use_py
where python.exe >nul 2>&1
if errorlevel 1 goto python_missing
python.exe "START-OFFLINE-WAV-PREP.py" %MODE%
set "RC=%errorlevel%"
goto finish
:use_py
py.exe -3 "START-OFFLINE-WAV-PREP.py" %MODE%
set "RC=%errorlevel%"
goto finish
:python_missing
echo AudioHub: Python 3.11+ is required and not found on PATH.
echo Install Python separately from a trusted source; this file does not download it.
set "RC=2"
goto finish
:error_pushed
echo AudioHub: double-click for GUI, or use --check for a no-write dependency check.
set "RC=2"
:finish
popd
if not "%RC%"=="0" if /I not "%~1"=="--check" pause
exit /b %RC%
:refuse_network
echo AudioHub: run from an extracted LOCAL drive folder, not a network share.
if /I not "%~1"=="--check" pause
exit /b 2
:error
echo AudioHub: local portable folder could not be opened.
if /I not "%~1"=="--check" pause
exit /b 2
