# Strict regression contour — MedicalDiaryAutofill v1.4.89

This contour is the first hard gate after the v1.4.85 baseline foundation.
It turns the user behavior contract into executable checks and now includes a 75-case production interaction matrix.  A future build is
not release-ready unless this contour stays green.

## Purpose

The contour protects the real doctor workflow, not only isolated functions:

1. doctor-owned DOCX/DOCM templates remain the source of block-03 buttons;
2. created buttons can be renamed without changing identity, role, template or required fields;
3. created buttons can be removed from the active profile without deleting the doctor's template file;
4. popup/UI values, especially numeric requisites, have final priority over scanner/profile values;
5. generated custom DOCX documents receive the values entered or corrected in popups;
6. patient subfolders follow the naming principle confirmed by the doctor;
7. role-aware placeholders stay correct for VK/MSE, sick-leave VK, RVK and joint commission documents;
8. no bundled medical DOCX/DOCM templates or narrow-profile defaults are reintroduced;
9. the 75-case production interaction matrix stays green for aliases, roles, popups, folders and intake handshakes.

## Mandatory local command

Run this before creating a release archive or pushing a release branch:

```bash
python tools/run_regression_contour.py
```

The runner executes a focused behavior suite and selected smoke checks.  It does
not replace `release_check.py`; it is an earlier regression gate that should fail
fast when a user-facing behavior is broken.

## Mandatory release commands

A release candidate must pass:

```bash
python -m compileall -q .
python -m pytest -q
python tools/run_regression_contour.py
python prod_audit.py
python release_check.py
python project_auditor.py . --ci --quiet
```

## CI/build wiring

The contour must remain wired in both places:

- `.github/workflows/windows-build.yml` must run `python tools/run_regression_contour.py`;
- `build_exe_windows.bat` must run `python tools/run_regression_contour.py` before `release_check.py` and before PyInstaller.

## Non-negotiable rule

A higher version number is not a better version.  A future version is better
only if it preserves `USER_BEHAVIOR_CONTRACT.md` and passes this contour.
