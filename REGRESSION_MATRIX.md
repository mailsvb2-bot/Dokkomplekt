# Regression matrix — MedicalDiaryAutofill v1.4.89

| Contract area | Protected behavior | Executable checks |
| --- | --- | --- |
| Product model | Doctor-owned constructor, no bundled medical DOCX/DOCM templates, no narrow-profile defaults | `prod_audit.py`, `release_check.py`, `tests/test_regression_contour_baseline_v1486.py::test_no_bundled_templates_or_builtin_documents_returned` |
| Block 03 buttons | Created buttons can be renamed and removed without changing document identity or deleting template files | `tests/test_regression_contour_baseline_v1486.py::test_full_doctor_regression_replay_from_template_to_output` |
| Template placeholders | Human-readable, Russian and camelCase placeholders resolve through semantic/context-aware registry | `tests/test_docx_placeholder_camelcase_regression_v1483.py`, `tests/test_contextual_role_disambiguation_v1482.py`, `tests/test_regression_contour_baseline_v1486.py` |
| Popup values | Numeric/requisite popup values reach generated DOCX documents and outrank scanner data | `tests/test_button_management_popup_values_folder_v1484.py`, `tests/test_regression_contour_baseline_v1486.py::test_full_doctor_regression_replay_from_template_to_output` |
| UI/data priority | Doctor-confirmed UI/popup state is the final overlay over parser/scanner/profile values | `tests/test_contextual_role_disambiguation_v1482.py::test_doctor_confirmed_ui_values_are_final_overlay_for_custom_case`, `tests/test_regression_contour_baseline_v1486.py` |
| Folder naming | Patient subfolders follow the confirmed naming principle and do not silently fall back to old defaults | `tests/test_button_management_popup_values_folder_v1484.py`, `tests/test_regression_contour_baseline_v1486.py::test_folder_naming_contract_is_part_of_regression_contour` |
| Diary behavior | Diary date templates and diary texts remain separate choices; diagnosis matching stays neutral | `smoke_full_patient_replay.py`, `smoke_desktop_diary_workflow.py`, `release_check.py` |
| Privacy/safety | No telemetry, no upload behavior, technical reports stay depersonalized | `prod_audit.py`, `release_check.py`, `project_auditor.py` |
| Archive/CI hygiene | Regression contour is wired into local build and GitHub Actions | `tests/test_regression_contour_baseline_v1486.py::test_regression_contour_is_wired_into_docs_build_and_ci`, `release_check.py` |

| Production interaction matrix | 75+ executable interaction checks for aliases, roles, popup overlays, folder naming and intake handshake | `tests/test_production_interaction_matrix_v1487.py`, `tools/run_regression_contour.py` |
