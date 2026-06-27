# Fix report — v1.4.85_baseline_foundation_SOURCE

## Fixed

1. Added a safe rename path for doctor-created block-03 buttons. The rename updates only profile-owned `button_label` metadata and preserves internal document id, template, role, required fields and generation behavior.
2. Added a safe delete path for doctor-created block-03 buttons. The delete removes the button from the active profile while intentionally keeping the copied DOCX template file available for re-adding.
3. Added setup-center UI actions: `Переименовать созданную кнопку` and `Удалить созданную кнопку`.
4. Kept first-run and normal setup flows intact: doctors can still create buttons in batch, add one template manually, configure folder naming, train source-document reading, import/export profiles and check templates.
5. Added regression tests that prove popup-entered numeric requisites are overlaid into custom DOCX generation and rendered into created documents.
6. Added regression tests that prove patient subfolder names follow the doctor-confirmed naming principle, including discharge-date based names, instead of falling back to the legacy default.
7. Kept all existing user workflows: no bundled medical templates were restored, no doctor-owned profile behavior was removed, and previous semantic/role/placeholder fixes remain intact.

## Verification

- `python -m compileall -q .`
- `python -m pytest -q`
- `python prod_audit.py`
- `python release_check.py`
- smoke/project audit checks
