# Production license-key provisioning

Before building a distributable production EXE, set
`DOKKOMPLEKT_LICENSE_PUBLIC_KEY_B64` to the Ed25519 **public** verification key
that corresponds to the private issuer key used by the license server.
`build_exe_windows.bat` embeds only this public key into
`resources/license_public_key.b64`. A non-CI production build fails if no key is
provided, rather than shipping an EXE that cannot validate paid licenses.

Never place `DOKKOMPLEKT_LICENSE_ISSUER_KEY_B64` or any payment-provider secret
inside the desktop repository or EXE.

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
