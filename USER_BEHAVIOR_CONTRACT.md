# User behavior contract — MedicalDiaryAutofill baseline v1.4.85

This document is the baseline behavior contract. Future fixes must preserve this behavior unless the change is explicitly intentional, documented in CHANGELOG.md, and covered by regression checks.

## 1. Product model

The application is a local Windows desktop utility for filling medical DOCX/DOCM documents and diary documents.

The application must remain a doctor-owned constructor:

- the doctor uploads their own Word templates;
- the application recognizes templates and creates working buttons;
- the application must not rely on bundled medical DOCX/DOCM templates;
- default built-in medical templates must not be reintroduced;
- the project must stay neutral and depersonalized, without hardcoded narrow-profile medical defaults.

## 2. Main user flow

The preserved user scenario is:

1. The doctor launches the program.
2. The doctor selects or drops a primary DOCX/DOCM document.
3. The application reads the primary document and extracts available patient/context values.
4. The doctor configures their own templates if block 03 has no created buttons yet.
5. The application creates document buttons from uploaded templates.
6. The doctor can create target documents from block 03.
7. If mandatory values are missing, the program asks in popups.
8. Values entered or corrected by the doctor in UI/popups must have final priority in generated documents.
9. Generated documents are saved into the correct patient folder/subfolder.

## 3. Block 03 custom buttons

Block 03 is controlled by doctor-owned templates.

Required behavior:

- before setup, block 03 must show the first-run create-buttons path;
- the doctor can upload DOCX/DOCM templates;
- the application recognizes document roles where possible;
- the application creates visible buttons from templates;
- a created button can be renamed;
- renaming must change the visible label only and must not break document id, role, template path, required fields, diary schedule or rendering;
- a created button can be removed from the active profile;
- deleting a button must not destroy the doctor's source DOCX/DOCM file from disk;
- existing buttons must not disappear after unrelated repairs.

## 4. Template/placeholder behavior

The application must support technical and human-readable placeholders.

Examples that must stay compatible include:

- patient.fio, patientName, patientFio, fullName, ФИО;
- case.number, caseNo, medicalRecordNo, История болезни №, Номер истории болезни;
- diagnosis, mainDiagnosis, Диагноз;
- icd_code, МКБ-10, Код МКБ-10;
- discharge.date, dischargeDate, Дата выписки;
- treatment.plan, Назначенное лечение;
- labs.results, labResults, Лабораторные исследования.

Ambiguous placeholders must be resolved using document role where role context exists. Examples: Дата комиссии, Номер протокола, Место работы / должность.

## 5. Popup behavior

Popups must preserve doctor workflow.

Required behavior:

- a popup must ask for values that cannot be confidently extracted;
- related questions should be combined into one popup where possible;
- invalid input must not silently close the popup;
- the doctor must be able to correct an invalid value;
- entered values must be remembered for later documents in the same session where appropriate;
- numeric/requisite fields entered in popups must reach generated DOCX/DOCM documents.

Numeric/requisite fields include:

- medical history number;
- sick leave number;
- protocol number;
- commission number;
- RVK act/medical conclusion number;
- dates associated with the above fields.

## 6. UI/data priority

The final data priority must be:

1. doctor-confirmed UI/popup state;
2. values explicitly selected in the current session;
3. scanner/profile values extracted from the primary document;
4. safe defaults only when allowed by the scenario.

Scanner output must not overwrite a value that the doctor has already corrected in the UI or popup.

## 7. Folder naming behavior

The program must preserve the patient folder naming principle selected by the doctor.

Required behavior:

- the setup flow must ask how to name the saved patient folder;
- the selected naming principle must be stored;
- generated documents must use the selected naming principle;
- the program must not silently fall back to an old default if a valid naming principle exists;
- folder names must be safe for Windows paths.

Examples of preserved naming principles include short surname/initials/date variants and full-FIO/month variants, where available in the UI.

## 8. Diary behavior

Diary behavior must be preserved:

- diary template dates and diary texts are separate user choices;
- diary text selection may use diagnosis-based matching;
- diary matching must stay neutral and must not hardcode narrow-profile semantics;
- existing diary controls must not be removed while repairing medical document regressions.

## 9. Privacy and safety behavior

The project must remain local and privacy-conscious:

- do not add telemetry;
- do not upload patient documents anywhere;
- do not add bundled medical templates;
- do not hardcode psychiatric/narrow-profile defaults;
- keep generated reports technical and depersonalized.

## 10. Release rule

A future release is not better just because it has a higher version number.
It is better only if it preserves this contract and passes the regression checks created on top of this baseline.
