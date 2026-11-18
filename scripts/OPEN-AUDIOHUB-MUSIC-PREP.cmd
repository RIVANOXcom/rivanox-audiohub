@echo off
rem SPDX-License-Identifier: AGPL-3.0-only
rem AudioHub LOCAL OFFLINE music preparation, explicitly started by operator.
rem Not a signed installer: does not install codecs, change media, use Pi/network.
rem The bundled self-check is NOT an authenticity/signature verification.
setlocal DisableDelayedExpansion
set "AUDIOHUB_DIR=%~dp0"
if "%AUDIOHUB_DIR:~0,2%"=="\\" goto refuse_network
pushd "%AUDIOHUB_DIR%" || goto error
if not "%~2"=="" goto error_pushed
if not "%~1"=="" if /I not "%~1"=="--check" if /I not "%~1"=="--package-check" if /I not "%~1"=="--smoke" goto error_pushed
rem Windows py.exe can exist but target an incompatible Python 3.x.
rem Validate py -3 first; if unsuitable, fall back to an independently
rem available python.exe (e.g. 3.12 alongside py launcher on 3.10).
rem The package-only diagnostic works without Tk or a desktop session.
set "AUDIOHUB_PROBE=import sys,tkinter;sys.exit(0 if sys.version_info >= (3,11) else 2)"
if /I "%~1"=="--package-check" set "AUDIOHUB_PROBE=import sys;sys.exit(0 if sys.version_info >= (3,11) else 2)"
where py.exe >nul 2>&1
if errorlevel 1 goto try_python
py.exe -3 -c "%AUDIOHUB_PROBE%" >nul 2>&1
if errorlevel 1 goto try_python
set "AUDIOHUB_PY=py.exe -3"
goto dispatch
:try_python
where python.exe >nul 2>&1
if errorlevel 1 goto python_missing
python.exe -c "%AUDIOHUB_PROBE%" >nul 2>&1
if errorlevel 1 goto dependency_failed
set "AUDIOHUB_PY=python.exe"
:dispatch
if /I "%~1"=="--package-check" goto package_only
rem Normal double-click, --smoke and --check use selected Python/Tk.
call :dependency_gate
if errorlevel 1 goto dependency_failed
if /I "%~1"=="--check" goto dependency_only
rem Auto-check the actual current extracted folder BEFORE displaying the GUI.
rem Prevents accidental partial/wrong unpacking, not deliberate tampering.
call :package_gate
if errorlevel 1 goto package_failed
if /I "%~1"=="--smoke" goto smoke
echo AudioHub: dependencies and local package contents MATCH.
echo AudioHub: launching offline GUI (no automatic conversion or music scan).
%AUDIOHUB_PY% "START-OFFLINE-WAV-PREP.py" --gui
set "RC=%errorlevel%"
goto finish
:smoke
echo AudioHub: running generated synthetic WAV demo only.
%AUDIOHUB_PY% "START-OFFLINE-WAV-PREP.py" --demo
set "RC=%errorlevel%"
if not "%RC%"=="0" goto smoke_failed
echo AudioHub FIRST-RUN SMOKE PASS: dependencies, package and synthetic demo.
goto finish
:dependency_only
echo AudioHub LOCAL PC readiness PASS: compatible Python and Tk selected.
set "RC=0"
goto finish
:package_only
call :package_gate
set "RC=%errorlevel%"
goto finish
:dependency_gate
%AUDIOHUB_PY% "START-OFFLINE-WAV-PREP.py" --check-local
exit /b %errorlevel%
:package_gate
%AUDIOHUB_PY% "START-OFFLINE-WAV-PREP.py" --package-check
exit /b %errorlevel%
:dependency_failed
echo AudioHub START REFUSED: installed Python could not pass 3.11+/Tk readiness.
echo This launcher installs NOTHING; resolve the dependency on a trusted PC.
set "RC=2"
goto finish
:package_failed
echo AudioHub START REFUSED: extracted package is incomplete or changed.
echo Re-extract an independently SHA256-verified ZIP to a NEW local folder.
echo Keep the prior portable folder and all original music.
set "RC=2"
goto finish
:smoke_failed
echo AudioHub FIRST-RUN SMOKE FAILED: synthetic demo did not pass.
set "RC=2"
goto finish
:python_missing
echo AudioHub: no working Python 3.11+ with Tk found via py.exe -3 or python.exe.
echo Install Python separately from a trusted source; this file downloads nothing.
set "RC=2"
goto finish
:error_pushed
echo AudioHub: double-click starts checked GUI. Use --check, --package-check or --smoke.
set "RC=2"
:finish
popd
if not "%RC%"=="0" if "%~1"=="" pause
exit /b %RC%
:refuse_network
echo AudioHub: run from an extracted LOCAL drive folder, not a network share.
if "%~1"=="" pause
exit /b 2
:error
echo AudioHub: local portable folder could not be opened.
if "%~1"=="" pause
exit /b 2
