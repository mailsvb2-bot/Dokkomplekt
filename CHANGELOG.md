## v1.4.89_release_gate_runtime_isolation_SOURCE — 2026-06-27

- Disabled desktop-intake autostart/logging during CI and release gates so tests never spawn a persistent watcher or leave `.medical_diary_autofill_data` artifacts in the source tree.
- Updated the strict regression contour and release gate to set `MEDICAL_AUTOFILL_DISABLE_AUTOSTART=1` for subprocesses.
- Kept real doctor-facing autostart behavior unchanged outside CI/release checks.

# Changelog

## v1.4.88_windows_release_gate_determinism_SOURCE — 2026-06-27

Windows release-gate determinism and primary-DOCX cache hardening release.

- Fixed Windows-only `smoke_desktop_diary_workflow.py` nondeterminism by isolating the OneDrive/Desktop fallback test from the real Explorer registry Desktop path.
- Hardened primary document parse cache invalidation with a content-aware SHA-256 signature so same-size rewrites on coarse Windows/cloud-synced filesystems cannot reuse stale parsed patient data.
- Preserved doctor-owned DOCX/DOCM constructor behavior, popup/UI priority, custom button management, folder naming and strict regression contour wiring.
- No user-facing functionality was intentionally removed.
- No bundled medical DOCX/DOCM templates were reintroduced.

## v1.4.87_production_regression_hardening_SOURCE — 2026-06-26

Production regression-hardening release after the strict contour baseline.

- Fixed the desktop intake pending-handshake regression where legacy pathful pending state could not be confirmed after the doctor moved/processed the DOCX.
- Added a 75-case production interaction matrix covering human/Russian/camelCase placeholders, context roles, popup overlays, folder naming and legacy pending state.
- Closed contextual placeholder drift for combined VK/MSE work-position fields.
- Prevented context-only visual aliases from leaking into global placeholder normalization while keeping explicit safe role aliases.
- Wired the new production interaction matrix and follow-up smoke into the strict regression contour.
- Preserved doctor-owned DOCX/DOCM constructor behavior and did not reintroduce bundled medical templates.

## v1.4.86_strict_regression_contour_SOURCE — 2026-06-26

Strict regression contour release.

- Added REGRESSION_CONTOUR.md.
- Added REGRESSION_MATRIX.md.
- Added tools/run_regression_contour.py.
- Added tests/test_regression_contour_baseline_v1486.py.
- Wired the contour into GitHub Actions and Windows build before release packaging.
- Updated prod_audit.py and release_check.py so the contour is required for production readiness.
- Preserved all baseline user-facing behavior; no bundled medical templates were reintroduced.

## v1.4.85_baseline_foundation_SOURCE — 2026-06-26

Baseline foundation release.

- Fixed the current best version as the behavior baseline before introducing the strict regression contour.
- Added BASELINE_VERSION.txt.
- Added USER_BEHAVIOR_CONTRACT.md.
- Added CHANGELOG.md as the single ordered project history.
- Added BASELINE_MANIFEST.json with deterministic file hashes for the baseline source tree.
- Updated release gates so baseline documents are required.
- No user-facing functionality was intentionally removed.
- No bundled medical DOCX/DOCM templates were reintroduced.

## v1.4.84_button_management_popup_folder_regression_closure_SOURCE

- Added safe rename for created block-03 buttons.
- Added safe delete/removal for created block-03 buttons without destroying the doctor's DOCX/DOCM template on disk.
- Strengthened popup-entered numeric values flowing into custom DOCX generation.
- Strengthened patient subfolder naming according to the selected naming principle.

## v1.4.83_docx_placeholder_role_regression_closure_SOURCE

- Closed DOCX camelCase/export-style placeholder normalization regressions.
- Passed explicit document role into placeholder extraction before saving required_fields.

## v1.4.82_live_context_ui_overlay_regression_closure_SOURCE

- Closed contextual placeholder regressions for VK/MSЭ/RVK/commission scenarios.
- Ensured doctor-confirmed UI/popup state overlays scanner data before custom medpack generation.
