# MedicalDiaryAutofill / Dokkomplekt

Version: `v1.4.92_trial_uninstall_hotfix`

## v1.4.92 — production trial / uninstall hotfix

- первый публичный production-релиз один раз отделяет реальный 14-дневный Trial от старого pre-release/test состояния; повторная установка Trial не сбрасывает;
- «Акт для РВК» закреплён отдельным DOCX regression replay и пресетами Ленинский / Канавинский / Сормовский / Московский с возможностью ручного ввода;
- packaged watcher получает явный shutdown handshake перед удалением, поэтому скрытый `--intake-agent` больше не должен удерживать EXE;
- добавлен полноценный per-user Windows Setup/Uninstaller и CI-smoke реального сценария install → live agent → uninstall.

## v1.4.91 — audit hardening

Security/runtime hardening after an independent production audit: fail-closed
trial/license accounting, pinned packaged Ed25519 verification key, real DOCM
compatibility through a macro-free working copy, safer batch primary discovery,
extension-preserving output names, broader runtime coverage and a packaged
runtime-bundle smoke check. A production EXE build now requires
`DOKKOMPLEKT_LICENSE_PUBLIC_KEY_B64`; the issuer/private key is never bundled.

## v1.4.89 hotfix — discharge custom case propagation

This hotfix is part of the v1.4.89 release line. It fixes doctor-owned discharge epicrisis generation so parsed primary-document data and doctor-confirmed UI/popup values reach custom DOCX placeholders instead of producing empty output. The regression contour includes a doctor-owned discharge template replay that checks patient identity, case number, dates, complaints, anamnesis, status, discharge condition, diagnosis and treatment in the generated DOCX.

## v1.4.89 — release-gate runtime isolation

Production hardening over the strict contour: 75-case interaction matrix, legacy intake pending handshake fix, context-safe placeholder routing and VK/MSE combined work-position rendering.

## v1.4.86 — strict regression contour

This source release introduces the first hard regression contour on top of the
v1.4.85 behavior baseline.  The contour protects the preserved doctor workflow:
custom DOCX/DOCM templates, block-03 created buttons, popup-to-DOCX values,
patient folder naming, context-aware placeholders, diary flow, privacy and CI
wiring.

No bundled medical DOCX/DOCM templates were added. The build remains a
doctor-owned constructor: the doctor uploads their own Word templates and the
program creates the working buttons.

## Product access / licensing contour

The commercial product layer is local-only and does not upload patient documents
or telemetry.  It adds one consolidated package, `product_access`, with:

- tariff source of truth;
- trial limits: 14 days / 30 generated documents / watermark;
- paid limits by plan: Doctor Start, Doctor Pro, Department, Clinic, Enterprise;
- local offline license JSON with machine binding and signed payload support;
- runtime creation guard;
- trial/demo DOCX footer watermark;
- doctor-facing license dialog via `Ctrl+L`;
- contract tests in `tests/test_product_licensing_contract.py`.

See `PRODUCT_PRICING_AND_LICENSING.md` for the product tariff policy.

## Запуск локально

```bash
python main.py
```

Для запуска из исходников нужны Python, pip и зависимости из `requirements.txt`.

## Проверки перед релизом

```bash
python -m compileall -q .
python -m pytest -q
python tools/run_regression_contour.py
python prod_audit.py
python release_check.py
python project_auditor.py . --ci --quiet
```

## Windows EXE

После успешных проверок используйте `build_exe_windows.bat` на Windows. Результатом сборки должен быть готовый `MedicalDiaryAutofill.exe`.

## Regression policy

`v1.4.85_baseline_foundation_SOURCE` remains the behavior baseline.  Starting
with `v1.4.91_audit_hardening`, a future version is allowed to
be considered better only if it preserves `USER_BEHAVIOR_CONTRACT.md` and
passes `REGRESSION_CONTOUR.md` / `REGRESSION_MATRIX.md` checks.
