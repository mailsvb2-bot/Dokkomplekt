# MedicalDiaryAutofill v1.4.58 — labs/preflight safety fix report

## Fixed

1. `labs.results` no longer falls back to `epi_text` in universal case mapping.
2. Explicit “Нет анализов” now becomes a real `labs.results` value and passes strict required-field preflight.
3. Legacy lab placeholders are no longer filled with synthetic “normal” values.
4. Lab date normalization now uses strict medical date parsing and rejects invalid dates.
5. Short lab markers such as `вич`, `оак`, `оам`, `алт`, `аст`, `rw` are matched as standalone tokens, not as substrings inside names.
6. Unrelated text files are rejected as lab sources instead of being inserted wholesale.
7. Lab placeholder aliases are aligned between renderer and universal field registry.
8. Switching lab modes in preflight resets stale lab date policy safely.
9. Added regression tests for labs safety, aliases, date parsing, no-labs behavior, and unrelated-file rejection.

## Verification

- `python3 -m compileall -q .` — OK
- `python3 -m pytest -q` — 26 passed
- `python3 prod_audit.py` — PROD AUDIT OK
- `python3 release_check.py` — RELEASE CHECK OK
- `python3 project_auditor.py .` — Status OK, score 100/100
