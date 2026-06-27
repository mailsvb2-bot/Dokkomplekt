# MedicalDiaryAutofill

Version: `v1.4.89_release_gate_runtime_isolation_SOURCE`

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
with `v1.4.89_release_gate_runtime_isolation_SOURCE`, a future version is allowed to
be considered better only if it preserves `USER_BEHAVIOR_CONTRACT.md` and
passes `REGRESSION_CONTOUR.md` / `REGRESSION_MATRIX.md` checks.
