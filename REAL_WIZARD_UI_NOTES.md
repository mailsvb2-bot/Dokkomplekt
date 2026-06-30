# Real wizard UI notes

This branch replaces the old visual surface with a standalone doctor-facing wizard.

Main contract:

1. The screen is not a shell around old 01/02/03/04 cards.
2. Old document logic remains the backend: selecting primary DOCX/DOCM, parsing, doctor-owned buttons, popups, preflight, duplicate handling, folder naming, printing, batch processing and licensing still call existing methods.
3. The visible path is: Document -> Data -> Create -> Done.
4. First-run setup is explicit: create buttons from Word templates, configure discharged-patients folder, configure patient subfolder naming.
5. The branch is intentionally not merged until the produced EXE is visually reviewed.
