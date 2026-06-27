@echo off
chcp 65001 > nul
setlocal EnableExtensions
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%STARTUP%\MedicalDiaryAutofill Intake Agent.vbs"
set "LNK=%STARTUP%\MedicalDiaryAutofill Intake Agent.lnk"
if exist "%VBS%" del /f /q "%VBS%" >nul 2>nul
if exist "%LNK%" del /f /q "%LNK%" >nul 2>nul
echo Фоновый watcher удалён из автозагрузки.
echo Если он уже был запущен, он остановится после перезагрузки Windows.
echo Внешняя командная оболочка не используется.
pause
