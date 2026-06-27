# Release notes — v1.4.89_release_gate_runtime_isolation_SOURCE

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
