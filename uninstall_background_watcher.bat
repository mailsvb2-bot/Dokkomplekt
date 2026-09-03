@echo off
chcp 65001 > nul
setlocal EnableExtensions
set "APPDIR=%~dp0"
set "EXE=%APPDIR%MedicalDiaryAutofill.exe"
set "AGENT=%APPDIR%desktop_intake_agent.py"

if exist "%EXE%" (
  "%EXE%" --uninstall-intake-agent
  if errorlevel 1 exit /b 1
  exit /b 0
)

if exist "%AGENT%" (
  where python.exe >nul 2>nul
  if errorlevel 1 exit /b 1
  python.exe "%AGENT%" --uninstall-autostart
  if errorlevel 1 exit /b 1
  exit /b 0
)

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
del /f /q "%STARTUP%\MedicalDiaryAutofill Intake Agent.vbs" >nul 2>nul
del /f /q "%STARTUP%\MedicalDiaryAutofill Intake Agent.lnk" >nul 2>nul
exit /b 0
