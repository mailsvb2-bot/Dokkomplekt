@echo off
REM Startup script name: MedicalDiaryAutofill Intake Agent.vbs
chcp 65001 > nul
setlocal EnableExtensions
set "APPDIR=%~dp0"
set "AGENT=%APPDIR%desktop_intake_agent.py"
set "EXE=%APPDIR%MedicalDiaryAutofill.exe"
if not exist "%EXE%" if exist "%APPDIR%dist\MedicalDiaryAutofill.exe" set "EXE=%APPDIR%dist\MedicalDiaryAutofill.exe"

if exist "%EXE%" goto :install_exe
if exist "%AGENT%" goto :install_source

echo Не найден ни MedicalDiaryAutofill.exe, ни desktop_intake_agent.py рядом с этим BAT.
pause
exit /b 1

:install_exe
"%EXE%" --install-intake-agent
if errorlevel 1 goto :fail
goto :ok

:install_source
where python.exe >nul 2>nul
if errorlevel 1 (
  echo Python не найден в PATH. Для обычного врача используйте EXE-сборку MedicalDiaryAutofill.exe.
  pause
  exit /b 1
)
python.exe "%AGENT%" --install-autostart
if errorlevel 1 goto :fail
goto :ok

:fail
echo Не удалось включить фоновый watcher автозагрузки.
pause
exit /b 1

:ok
echo Фоновый watcher включён скрытым VBS-скриптом автозагрузки.
echo Startup VBS переписан в безопасной Unicode-кодировке для Windows Script Host.
echo Теперь первичный DOCX в папке "Выписанные пациенты" запустит программу автоматически.
pause
