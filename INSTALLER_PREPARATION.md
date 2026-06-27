# Installer preparation — MedicalDiaryAutofill

Эта версия остаётся source/EXE-ready. Для продажи врачу нужен отдельный установщик.

## Минимальный установщик должен делать

1. Ставить программу в `%LocalAppData%\\MedicalDiaryAutofill` или `Program Files`.
2. Создавать ярлык на рабочем столе.
3. Создавать/проверять папку `Выписанные пациенты`.
4. Ставить watcher в Startup без админ-прав.
5. Давать пункт удаления, который удаляет Startup-shortcut и watcher lock.
6. Запускать post-install self-check: та же логика, что кнопка `Диагн.` в UI.
7. Не просить врача устанавливать Python/зависимости вручную.

## Рекомендованный путь

- Build EXE: `build_exe_windows.bat`.
- Установщик: Inno Setup или NSIS.
- Подпись: code signing certificate для EXE и setup.
- Smoke перед релизом: `python release_check.py` + ручной `WINDOWS_ACCEPTANCE_CHECKLIST.md`.

## Важно

Фоновый watcher не должен быть Windows service и не должен использовать keyboard/mouse hooks. Безопасный путь — обычный Startup shortcut + скрытый `--intake-agent` процесс.
