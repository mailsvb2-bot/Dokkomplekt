@echo off
chcp 65001 > nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  Сборка медицинского автозаполнителя в один .EXE
echo  Пользователю Python и зависимости ставить не нужно.
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ОШИБКА] Python не найден. Для сборки нужен Python на компьютере разработчика.
  if "%CI%"=="" pause
  exit /b 1
)

if not exist .venv_build (
  echo [1/6] Создаю виртуальное окружение сборки...
  python -m venv .venv_build
  if errorlevel 1 (
    echo [ОШИБКА] Не удалось создать виртуальное окружение.
    if "%CI%"=="" pause
    exit /b 1
  )
)

call .venv_build\Scripts\activate.bat
if errorlevel 1 (
  echo [ОШИБКА] Не удалось активировать виртуальное окружение.
  if "%CI%"=="" pause
  exit /b 1
)

echo [2/6] Обновляю pip...
python -m pip install --upgrade pip
if errorlevel 1 (
  echo [ОШИБКА] Не удалось обновить pip.
  if "%CI%"=="" pause
  exit /b 1
)

echo [3/6] Устанавливаю сборочные зависимости...
python -m pip install -r requirements_build.txt
if errorlevel 1 (
  echo [ОШИБКА] Не удалось установить зависимости сборки.
  if "%CI%"=="" pause
  exit /b 1
)

echo [4/6] Запускаю полную smoke-проверку...
for %%S in (smoke_test.py smoke_test_combined.py smoke_desktop_diary_workflow.py smoke_universal_hardening.py smoke_stress_hardening.py smoke_auditor_layer.py smoke_project_auditor.py smoke_technical_debt_cleanup.py smoke_split_entrypoints.py smoke_followup_regressions.py smoke_quality_modernization.py smoke_points_5_11.py smoke_user_reported_regressions.py smoke_full_patient_replay.py) do (
  echo [SMOKE] %%S
  python %%S
  if errorlevel 1 (
    echo [ОШИБКА] Smoke-проверка не прошла: %%S
    if "%CI%"=="" pause
    exit /b 1
  )
)

echo [5/6] Запускаю железный regression-контур...
python tools/run_regression_contour.py
if errorlevel 1 (
  echo [ОШИБКА] Regression-контур не прошёл. EXE не собираю.
  if "%CI%"=="" pause
  exit /b 1
)

echo [5/6] Проверяю release-gate...
python release_check.py
if errorlevel 1 (
  echo [ОШИБКА] Release-gate не прошёл. EXE не собираю.
  if "%CI%"=="" pause
  exit /b 1
)

echo [6/6] Собираю один EXE через PyInstaller...
set ADD_TEMPLATES=
if exist templates (
  set ADD_TEMPLATES=--add-data "templates;templates"
) else (
  echo [INFO] Папка templates не найдена. Сборка остаётся doctor-owned: врач загружает свои Word-шаблоны в программе.
)

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name MedicalDiaryAutofill ^
  --version-file version_info.txt ^
  --noupx ^
  %ADD_TEMPLATES% ^
  --collect-all docx ^
  --collect-all lxml ^
  --collect-all tkinterdnd2 ^
  --hidden-import win32api ^
  --hidden-import win32print ^
  main.py

if exist dist\MedicalDiaryAutofill.exe (
  echo.
  echo ГОТОВО: dist\MedicalDiaryAutofill.exe
  echo Этот файл можно отдавать пользователям. Он запускается без Python/pip.
  if "%CI%"=="" pause
  exit /b 0
) else (
  echo.
  echo [ОШИБКА] EXE не найден. Смотри вывод выше.
  if "%CI%"=="" pause
  exit /b 1
)
