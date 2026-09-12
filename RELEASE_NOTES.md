# Release notes — v1.4.98_document_generation_hotfix

## Fixed

- Исправлена генерация результатов обследований: `ОАК`, `ОАМ`, `ЭКГ`, `ЭЭГ` больше не получают текст анамнеза/ЭПИ из-за ошибочной semantic-разметки коротких медицинских меток.
- `ЭПИ` распознаётся только как отдельная медицинская метка и больше не совпадает с фрагментами слов `эпикриз` / `эпидемиологический`; соседние блоки `За время лечения` и `Рекомендовано` не прилипают к ЭПИ.
- В popup-полях дат подтверждён и явно показан ввод без точек: например, `090926` нормализуется в `09.09.2026`.
- Расширено согласование дневников по полу пациента: женские ФИО получают формы `явилась`, `пришла`, `вялой`, `подавленной`, `спокойна` и другие клинические формы вместо мужских окончаний.
- Автоматический выбор файла текстов дневников теперь выполняется по окончательному диагнозу/МКБ в имени файла, включая диагноз, исправленный врачом в popup; ранее автоматически выбранный файл для старого диагноза переоценивается перед генерацией.
- Последний дневник отделён от диагностических шаблонов: для любого диагноза он всегда формируется единым жёстко заданным текстом `Состояние улучшилось…`.
- Добавлен regression-набор `test_user_reported_generation_fixes_v1498.py`, закрывающий реальные ошибки из пользовательских выходных DOCX.
- Дневниковые подписи теперь берут реальные ФИО врача/заведующего из текущего случая, выводят `Лечащий врач …` и `Зав.отделением …` после каждой записи и выравнивают обе строки вправо.
- Строка `Находилась/Находился на лечении в ГБУЗ НО «НКЦПЗ» диспансер №2 …` в выписном эпикризе принудительно сохраняется чёрной даже при красном стиле исходного DOCX.
- Для выписного эпикриза и Акта РВК введён обязательный выбор `первично` / `повторно`; результат формируется как `В 3 отделение КДП поступает первично|повторно`, без угадывания значения.
- Добавлен DOCX regression-набор `test_user_reported_formatting_and_rvk_v1498.py` для подписей, выравнивания, цвета и РВК/выписного режима поступления.

# Release notes — v1.4.97_unified_patient_case_architecture

## Fixed

- Разделены медицинская идентичность пациента и `output_fio`: имя для папки/файла больше не может незаметно стать ФИО внутри медицинского документа.
- Введён единый canonical `PatientCase`; scanner дополняет только отсутствующие данные и не перезаписывает уже подтверждённые поля.
- Автоматические значения UI больше не получают приоритет врачебного override без явного действия врача.
- Предзаполненные значения в DOCX врача считаются данными шаблона и заменяются canonical semantic fields, включая обычные абзацы, секции и табличные формы.
- Добавлена post-render проверка согласованности; несогласуемый медицинский DOCX удаляется до публикации результата.
- Новый архитектурный regression contour `test_unified_patient_case_architecture_v1531.py` включён в обязательный strict runner.

# Release notes — v1.4.96_live_fio_real_path_fix

## Fixed

- Реальный путь первичного DOCX теперь восстанавливает ФИО из Word/XML content controls и скрытой табличной разметки, а не только из обычных `python-docx` paragraphs/tables.
- ФИО врача отсекается как недопустимая пациентская идентичность даже рядом с демографическими полями.
- Имя файла вида `Фамилия И.О.` используется только как output fallback для имени папки/файлов; оно не подменяет ФИО внутри медицинских документов без ручного подтверждения.
- UI показывает безопасный output fallback, если полное ФИО временно не распознано, поэтому строгий folder-naming больше не падает до preflight.
- Видимая версия поднята до 1.4.96, чтобы врач мог отличить исправленный EXE от прежнего 1.4.95.

# Release notes — v1.4.95_diary_dates_picker_ux_fix

## Fixed

- Кнопка «Даты» теперь явно предлагает выбрать один конкретный DOCX/DOCM или папку с шаблонами `01.docx … 31.docx`.
- «Отмена» действительно отменяет действие: второй системный диалог больше не открывается, текущий выбор источника дат не меняется.
- Оба способа выбора дат сохранены; дневники по-прежнему формируются как текстовые DOCX, а не таблицы.

# Release notes — v1.4.94_real_template_creation_fix

## Fixed

- Исправлено реальное создание документов из обычных Word-шаблонов врача: распознанные условные поля больше не объявляются обязательными только потому, что в шаблоне есть видимое пустое место.
- Пустой номер больничного, место работы или должность теперь не отменяют весь комплект, когда эти данные по сценарию не требуются.
- Явные технические `{{...}}` поля и обязательные поля клинической роли по-прежнему проверяются строго.
- Уже созданные профили врача автоматически и узко мигрируются с резервной копией; пересоздавать кнопки и шаблоны не нужно.

# Release notes — v1.4.93_generation_trial_hotfix

## Fixed

- Document creation can no longer be blocked by a stale pre-public trial copy after the v1.4.91 public reset. Current-epoch state wins and heals divergent redundant copies.
- Trial users can create a normal multi-document patient set; the 30-document total trial limit remains unchanged.
- The packaged user-journey check now includes the real trial watermark, usage reservation and output transaction before declaring the EXE healthy.
- Windows CI explicitly runs the full patient flow with product access enabled.

# Release notes — v1.4.92_trial_uninstall_hotfix

- Исправлен ложный «Пробный период завершён» у первого публичного production-релиза: состояние внутренних/pre-release сборок не съедает 14-дневный Trial. Сброс выполняется строго один раз и защищён integrity state/guard.
- «Акт для РВК» проверяется отдельным реальным DOCX regression replay; восстановлены быстрые варианты Ленинский / Канавинский / Сормовский / Московский, ручной ввод военкомата остаётся доступен.
- Исправлено удаление программы при активном фоне: uninstaller публикует shutdown-handoff, ждёт завершения скрытого `--intake-agent`, удаляет Startup VBS/LNK и только затем освобождает EXE.
- Добавлен Inno Setup установщик для `%LocalAppData%\Dokkomplekt` с ярлыками и штатным Windows uninstaller.
- CI теперь строит Setup и реально проверяет install → запуск фонового агента → uninstall → отсутствие удерживаемого EXE.

# Release notes — v1.4.91_audit_hardening

- Закрыт fail-open коммерческого доступа: packaged EXE больше нельзя перевести в unrestricted-режим через `CI`, legacy disable/unsigned environment flags или подмену Ed25519 public key; production-сборка требует встраиваемый публичный ключ лицензирования.
- Trial state переведён на integrity-protected primary + guard storage; на Windows добавлен независимый HKCU guard. Повреждение состояния теперь восстанавливается из целой копии или блокирует trial вместо молчаливого сброса лимита.
- Watermark и usage ledger стали fail-closed: если trial watermark или запись счётчика не подтверждены, созданные файлы удаляются и не выдаются как успешный результат.
- Настоящий `.docm` поддерживается через временную macro-free DOCX-копию; исходный DOCM не изменяется, VBA не переносится в рабочую копию.
- Исправлено обрезание длинных имён: известное расширение `.docx/.pdf/...` сохраняется в пределах лимита имени.
- Исправлены ФИО капсом и с инициалами, сохранение повторяющихся структурных строк DOCX и пакетный discovery, который ранее мог принять выписной эпикриз за новый первичный документ.
- PDF template import на Windows сначала использует Microsoft Word PDF reflow для лучшего сохранения структуры и только затем переходит к явно обозначенному text fallback.
- Техническая ошибка popup-а больше не трактуется как осознанное решение врача «создать как есть»; запрос PDF больше не маскирует ошибку конвертации успешным DOCX-результатом.
- Coverage gate теперь измеряет весь runtime (`--cov=.`) с общим порогом 35%, а packaged Windows EXE дополнительно проходит GUI-free runtime-bundle smoke с DOCX intake/discovery.

- Полный МКБ-10 (ВОЗ/Минздрав РФ): 721 → 14 852 кода; поиск и нормализация диагнозов работают по всем классам A–Z, приоритет выверенных психиатрических формулировок сохранён.
- Автозапуск при обновлении EXE: фоновый intake-агент получает handoff-эстафету — старый агент уступает новому без перезагрузки Windows, запуск GUI всегда идёт по актуальному пути (v1.8).
- Исправлены регрессии пользовательского потока: суффиксная дата рождения («1985 г.р.») больше не заглатывает строку дат; дата выписки не затирается пустым UI-значением; дневники, попап «Как составлять дневники», динамические эпикризы и подстановка данных работают сквозняком.
- Версия сборки видна в заголовке окна.

# Release notes — v1.4.89_release_gate_runtime_isolation_SOURCE

## Hotfix — discharge custom case propagation

This v1.4.89 source line includes a discharge custom case propagation fix for doctor-owned DOCX templates. Parsed primary-document data and doctor-confirmed UI/popup values are overlaid into custom discharge epicrisis placeholders before rendering, so patient identity, case number, dates, complaints, anamnesis, status, discharge condition, diagnosis and treatment do not silently disappear from generated output.

The hotfix is intentionally documented here and in `README.md` under the same release label. `tests/test_build_check_wiring_v1495.py` locks that synchronization so future hotfix documentation cannot drift away from the release metadata.

## v1.4.89 — release-gate runtime isolation

This release fixes the Windows source-release problem where the release gate itself could create `.medical_diary_autofill_data\desktop_intake_agent.log` after all behavioral checks had passed.

- Disabled desktop-intake autostart while running CI/release checks through `MEDICAL_AUTOFILL_DISABLE_AUTOSTART=1`.
- Disabled desktop-intake agent logging during CI/release checks so strict contour tests cannot leave `.log` artifacts in the source tree.
- Updated the strict regression contour runner and `release_check.py` to set the release-safe autostart flag for subprocesses and in-process smoke checks.
- Kept real doctor-facing first-run autostart behavior unchanged outside CI/release checks.
- No user-facing functionality was intentionally removed.
- No bundled medical DOCX/DOCM templates were reintroduced.

## v1.4.88 — Windows release-gate determinism

This release fixes two failures found during the user's local pre-GitHub CMD run on Windows.

- Fixed deterministic OneDrive/Desktop smoke coverage by isolating the fallback test from the real Windows registry Desktop location.
- Hardened the primary DOCX parse cache with a content-aware signature: mtime, size and SHA-256 digest. This prevents stale patient data after same-size rewrites on Windows/cloud-synced folders.
- Kept the strict regression contour and production interaction matrix intact.
- No user-facing functionality was intentionally removed.
- No bundled medical DOCX/DOCM templates were reintroduced.

## v1.4.87 — production regression hardening

This release hardens the v1.4.86 strict regression contour before GitHub upload.

- Fixed legacy desktop-intake pending handshake confirmation.
- Added 75 executable production interaction matrix checks.
- Added VK/MSE combined work-position semantic field and popup overlay.
- Kept context-only human placeholders from being globally misrouted.
- Added `smoke_followup_regressions.py` and `tests/test_production_interaction_matrix_v1487.py` to the strict contour.
- No user-facing functionality was intentionally removed.
- No bundled medical DOCX/DOCM templates were reintroduced.

## v1.4.86 — strict regression contour

This release introduces the first hard regression contour after the v1.4.85
baseline foundation.

- Added `REGRESSION_CONTOUR.md` with mandatory local, release and CI commands.
- Added `REGRESSION_MATRIX.md` mapping user behavior contract areas to executable checks.
- Added `tools/run_regression_contour.py` as the focused behavior-preservation runner.
- Added `tests/test_regression_contour_baseline_v1486.py` covering a full doctor replay:
  custom template attachment, button rename/delete, role-aware placeholders,
  popup numeric values into generated DOCX, UI overlay priority and folder naming.
- Wired the strict contour into GitHub Actions and `build_exe_windows.bat`.
- Updated `prod_audit.py` and `release_check.py` so a release cannot pass without the contour files and wiring.
- No user-facing functionality was intentionally removed.
- No bundled medical DOCX/DOCM templates were reintroduced.

## Baseline inherited from v1.4.85

The v1.4.85 behavior baseline remains the protected reference: doctor-owned
constructor, custom block-03 buttons, popup/UI final priority, selected patient
folder naming principle, privacy/local-only behavior and neutral medical wording.
