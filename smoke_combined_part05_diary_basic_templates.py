from pathlib import Path as _SmokePath
if "_SMOKE_COMBINED_RUNNER_ACTIVE" not in globals() and "OUT" not in globals():
    from smoke_combined_runner import build_namespace_before as _build_smoke_namespace_before
    globals().update(_build_smoke_namespace_before(_SmokePath(__file__).name))

# --- Diary filler smoke ---
source = OUT / "texts.docx"
doc = Document()
doc.add_paragraph("01.06.2026 Пациент был спокоен, жалоб активно не предъявлял, в беседе доступен, инструкции выполнял.")
doc.add_paragraph("02.06.2026 Пациент сообщил об улучшении сна, фон настроения ровный, поведение упорядоченное.")
doc.save(source)
assert len(extract_statuses_from_docx(source)) == 2

merged_status = OUT / "merged_status.docx"
merged_doc = Document()
merged_table = merged_doc.add_table(rows=1, cols=2)
merged_cell = merged_table.cell(0, 0).merge(merged_table.cell(0, 1))
merged_cell.text = "Пациент был спокоен, жалоб активно не предъявлял, в беседе доступен, инструкции выполнял."
merged_doc.save(merged_status)
assert len(extract_statuses_from_docx(merged_status)) == 1
assert extract_docx_text(merged_status).count("Пациент был спокоен") == 1

table_file = OUT / "diary_table.docx"
doc = Document()
table = doc.add_table(rows=1, cols=4)
headers = ["№", "Число", "Месяц/год", "Дневник наблюдения"]
for i, h in enumerate(headers):
    table.rows[0].cells[i].text = h
for day in [10, 11, 12, 13, 14, 15]:
    row = table.add_row()
    row.cells[0].text = str(day)
    row.cells[1].text = str(day)
    row.cells[2].text = ""
    row.cells[3].text = "Лечащий врач Балаганин С.В."
doc.save(table_file)

result = fill_diary_batch(
    status_files=[source],
    diary_files=[table_file],
    output_dir=OUT / "diaries",
    patient_name="Иванова И.И.",
    admission_value="10.06.2026",
    discharge_value="12.06.2026",
    repeat_statuses=True,
    reset_each_file=True,
    keep_signature=True,
    fill_months=True,
    force_final_diary=True,
    remove_holiday_rows=True,
)
assert result.processed_files == 1
assert result.created_files[0].exists()
assert result.report_path is None
assert not any(path.name.startswith("ОТЧЁТ_") for path in (OUT / "diaries").glob("*.txt"))
assert result.filled_rows >= 1
assert result.final_rows_filled == 1
# The production diary route is text-only. Calendar table rows are not mutated
# or counted; discharge bounds are enforced while the text-date plan is built.
assert result.removed_after_discharge_rows == 0
result_doc = Document(result.created_files[0])
assert not result_doc.tables, "Text diary output must not resurrect legacy table rendering"
diary_text = "\n".join(paragraph.text for paragraph in result_doc.paragraphs)
assert "11.06.26 Пациентка была спокойна" in diary_text
assert "12.06.26 Состояние улучшилось" in diary_text
assert "13.06.26" not in diary_text
assert "не предъявляла" in diary_text

# --- Diary gender source smoke: UI filename may be male, source document is female ---
result_filename_male = fill_diary_batch(
    status_files=[source],
    diary_files=[table_file],
    output_dir=OUT / "diaries_gender_source",
    patient_name="Иванов Иван Иванович",
    gender_source_name="Иванова Ирина Ивановна",
    admission_value="10.06.2026",
    discharge_value="12.06.2026",
    repeat_statuses=True,
    reset_each_file=True,
    keep_signature=True,
    fill_months=True,
    force_final_diary=True,
    remove_holiday_rows=True,
)
result_filename_male_doc = Document(result_filename_male.created_files[0])
assert not result_filename_male_doc.tables
diary_text2 = "\n".join(paragraph.text for paragraph in result_filename_male_doc.paragraphs)
assert "Пациентка была спокойна" in diary_text2
assert "не предъявляла" in diary_text2
assert "13.06.26" not in diary_text2
assert result_filename_male.created_files[0].name.startswith("Иванов Иван Иванович")


# --- Admission date regression: title date is admission, FIO-near date is birth ---
title_date_doc = OUT / "title_date_primary.docx"
title_doc = Document()
title_doc.add_paragraph("12.01.2026 Первичный осмотр")
title_doc.add_paragraph("Ф.И.О.: Сидоров Иван Михайлович, Дата рождения: 09.01.1980")
title_doc.add_paragraph("Жалобы: тест")
title_doc.add_paragraph("Профильный статус: тест")
title_doc.add_paragraph("Диагноз: K35.8 тест")
title_doc.save(title_date_doc)
title_data = MedicalDocumentService().parse_primary_document(title_date_doc)
assert title_data.admission_date == "12.01.2026", title_data.admission_date
assert title_data.birth == "09.01.1980", title_data.birth

# --- Production diary dates are calendar-driven, not 01-31 DOCX-driven ---
from main import CombinedMedicalDiaryApp

class _Var:
    def __init__(self, value=""):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value

calendar_app = CombinedMedicalDiaryApp.__new__(CombinedMedicalDiaryApp)
calendar_app.diary_files = []
calendar_app.diary_template_dir = ""
assert calendar_app._auto_select_numbered_diary_template(ask_folder=False) is False
assert calendar_app.diary_files == []
assert calendar_app.diary_template_dir == ""

# No active primary-load path may silently revive numbered diary templates.
desktop_source = Path("desktop_intake_mixin.py").read_text(encoding="utf-8")
actions_source = Path("actions_navigation.py").read_text(encoding="utf-8")
files_source = Path("files_mixin.py").read_text(encoding="utf-8")
primary_start = files_source.index("    def _apply_primary_document_path")
primary_end = files_source.index("    def choose_navigation", primary_start)
assert "self._auto_select_numbered_diary_template(ask_folder=False)" not in desktop_source
assert "self._auto_select_numbered_diary_template(ask_folder=False)" not in actions_source
assert "self._auto_select_numbered_diary_template(ask_folder=False)" not in files_source[primary_start:primary_end]

# The visible Dates control and legacy drops converge on one calendar activation method.
app_source = Path("app.py").read_text(encoding="utf-8")
choose_start = app_source.index("    def choose_diary_files")
choose_end = app_source.index("    def _diary_template_label_text", choose_start)
choose_source = app_source[choose_start:choose_end]
assert "prompt_diary_calendar_principle" in choose_source
assert "self._activate_diary_calendar_mode()" in choose_source
assert "filedialog.askopenfilename" not in choose_source
assert "filedialog.askdirectory" not in choose_source
assert 'source="старый набор 01–31"' in app_source
assert 'source="старый файл дат"' in app_source

# --- Diary text auto-selection by diagnosis filename ---
from diary_text_selection import (
    normalize_diary_diagnosis_name,
    diary_diagnosis_match_score,
    find_diary_text_file_for_diagnosis,
)

texts_by_diagnosis = OUT / "тексты по диагнозам"
texts_by_diagnosis.mkdir(parents=True, exist_ok=True)
Document().save(texts_by_diagnosis / "Острый аппендицит.docx")
Document().save(texts_by_diagnosis / "Артериальная гипертензия.docx")
assert normalize_diary_diagnosis_name("K35 Острый аппендицит.") == "острый аппендицит"
assert diary_diagnosis_match_score(
    "K35 Острый аппендицит.",
    "Острый аппендицит.docx",
) >= 90
matched_text = find_diary_text_file_for_diagnosis(
    texts_by_diagnosis,
    "K35 Острый аппендицит.",
)
assert matched_text is not None
assert matched_text.name == "Острый аппендицит.docx"

app3 = CombinedMedicalDiaryApp.__new__(CombinedMedicalDiaryApp)
app3.diagnosis_var = _Var("K35 Острый аппендицит.")
app3.navigation_path_var = _Var("")
app3.output_dir_var = _Var("")
app3.status_files = []
app3.diary_texts_dir = str(texts_by_diagnosis)
app3._diary_text_files_auto_selected = False
app3._settings = {"folders": {}}
app3._settings_folders = lambda: app3._settings.setdefault("folders", {})
app3._save_settings = lambda: None
app3._get_saved_directory = lambda _key: ""
app3._update_diary_text_label = lambda success=None: None
app3._redraw_selection_controls = lambda: None
app3._log = lambda _text: None
app3.data = None
assert app3._auto_select_diary_text_by_diagnosis(ask_folder=False) is True
assert Path(app3.status_files[0]).name == "Острый аппендицит.docx"
assert app3._diary_text_files_auto_selected is True


# --- Neutral real-world diary-text filenames from physician folders ---
real_names = {
    "дневники ВЭ острый аппендицит.docx": "K35 Острый аппендицит",
    "дневники ВЭ аппендицит после операции.docx": "K35 Острый аппендицит после операции",
    "дневники ВЭ артериальная гипертензия.docx": "I10 Артериальная гипертензия",
    "дневники ВЭ пневмония с датами.docx": "J18 Пневмония",
    "дневники ВЭ сахарный диабет.docx": "E11 Сахарный диабет 2 типа",
}
real_text_dir = OUT / "реальные имена текстов"
real_text_dir.mkdir(parents=True, exist_ok=True)
for filename in real_names:
    Document().save(real_text_dir / filename)
for expected_name, diagnosis in real_names.items():
    matched = find_diary_text_file_for_diagnosis(real_text_dir, diagnosis)
    assert matched is not None, diagnosis
    assert matched.name == expected_name, (diagnosis, matched.name)
assert normalize_diary_diagnosis_name("дневники ВЭ пневмония с датами.docx") == "пневмония"
assert normalize_diary_diagnosis_name("K35 Острый аппендицит") == "острый аппендицит"

# --- UI defaults and service-line regression ---
source_all = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted(ROOT.glob("*.py"))
    if not path.name.startswith(("smoke_test", "smoke_combined_"))
)
assert 'kind: tk.BooleanVar(value=False) for kind in DOCUMENT_ORDER' in source_all
assert 'self.output_vars[DIARY_KIND] = tk.BooleanVar(value=False)' in source_all
assert 'Служебный отчёт создания документов не сохранён' not in source_all
assert 'Служебный отчёт дневников не сохранён' not in source_all
assert 'font=self._font(10 if self._compact_ui else 12, "bold" if checked else None)' in source_all
assert 'Автоматически выбран текст дневников по диагнозу' in source_all
