# Fix report v1.4.85 baseline foundation

## Fixed

1. Safe rename path for doctor created block 03 buttons.
2. Safe delete path for doctor created block 03 buttons.
3. Setup center UI actions for rename and delete.
4. First run and normal setup flows preserved.
5. Regression coverage for popup values in custom document generation.
6. Regression coverage for patient subfolder naming.
7. Existing doctor owned profile behavior preserved.

## Latest CI rebuild note

- Restored the full analyses popup modal contract.
- Documented large dialog field modal functions for release quality gate.
- Improved release quality gate diagnostics for remaining large functions.
- Fresh Windows EXE rebuild requested after release gate hardening.

## Verification

- python -m compileall -q .
- python -m pytest -q
- python prod_audit.py
- python release_check.py
- smoke and project audit checks
