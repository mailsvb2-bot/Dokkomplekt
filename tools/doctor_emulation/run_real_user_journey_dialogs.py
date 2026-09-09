"""Live Tk proof for creation dialogs that ordinary doctor scenarios stub."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import tkinter as tk

from doctor_sim import DoctorSim, make_docx
from medical_docx_reader import extract_docx_text
from universal_main_documents import custom_kind
from universal_profiles import save_document_pack
from universal_template_engine import attach_template_to_pack


def check(condition, message: object) -> None:
    if not condition:
        raise AssertionError(str(message))


def main() -> None:
    from app import CombinedMedicalDiaryApp

    real_folder_dialog = CombinedMedicalDiaryApp.configure_patient_folder_naming_dialog
    real_creation_guard = CombinedMedicalDiaryApp._confirm_patient_case_before_creation
    sim = DoctorSim(answers={("askyesno", "Формат результата"): False})
    CombinedMedicalDiaryApp.configure_patient_folder_naming_dialog = real_folder_dialog
    CombinedMedicalDiaryApp._confirm_patient_case_before_creation = real_creation_guard
    try:
        primary = sim.root_dir / "Первичный осмотр.docx"
        make_docx(
            primary,
            [
                "История болезни № 314/26. Пациентка: Орлова Мария Ивановна, 1985 г.р.",
                "Дата поступления: 05.05.2026. Дата выписки: 19.05.2026.",
                "Диагноз: F32.1 Депрессивный эпизод средней степени.",
                "Лечение: сертралин 100 мг утром.",
            ],
        )
        sim.drop(primary)

        template = sim.root_dir / "Документ с анализами.docx"
        make_docx(
            template,
            [
                "ФИО: {{patient.fio}}",
                "Диагноз: {{diagnosis.main}}",
                "Анализы: {{labs.results}}",
            ],
        )
        pack = sim.app._load_or_create_universal_pack()
        spec, _copy = attach_template_to_pack(
            pack,
            template,
            sim.app._universal_profile_path().parent,
            button_label="Документ с анализами",
            role_id="primary_exam",
        )
        save_document_pack(pack, sim.app._universal_profile_path())
        kind = custom_kind(spec.id)
        var = tk.BooleanVar(master=sim.tk_root, value=True)
        sim.app.output_vars[kind] = var
        sim.app.custom_output_vars[kind] = var

        seen: set[str] = set()

        def drive(attempt: int = 0) -> None:
            for top in sim.toplevels():
                title = str(top.title())
                if title == "Как называть сохранённую папку?" and title not in seen:
                    seen.add(title)
                    sim.popups.append(("REAL", title))
                    sim.click_button("Сохранить", top)
                elif title.startswith("Не заполнено обязательное поле") and title not in seen:
                    seen.add(title)
                    sim.popups.append(("REAL", title))
                    check(
                        sim.click_button("Нет анализов", top),
                        "В required-fields окне нет кнопки «Нет анализов»",
                    )
                    check(
                        sim.click_button("Сохранить и продолжить", top),
                        "В required-fields окне нет кнопки сохранения",
                    )
            if len(seen) < 2 and attempt < 320:
                sim.tk_root.after(25, lambda: drive(attempt + 1))

        sim.tk_root.after(25, drive)
        created_ok = sim.app.create_selected_outputs(print_after=False)
        sim.pump(0.4)
        check(
            created_ok,
            f"create_selected_outputs=False; popups={sim.popups}; errors={sim.errors}",
        )
        check(
            "Как называть сохранённую папку?" in seen,
            f"реальная настройка папки не открылась: {sim.popups}",
        )
        check(
            any(title.startswith("Не заполнено обязательное поле") for title in seen),
            f"реальное окно обязательных полей не открылось: {sim.popups}",
        )

        expected_parent = "Орлова М.И. май 2026"
        outputs = [
            path
            for path in sim.outputs()
            if "Документ с анализами" in path.name
        ]
        check(outputs, [str(path) for path in sim.outputs()])
        check(outputs[0].parent.name == expected_parent, outputs[0])
        text = extract_docx_text(outputs[0])
        check("Орлова Мария Ивановна" in text, text)
        check("F32.1" in text, text)
        check("Нет анализов" in text, text)
        check("{{" not in text and "}}" not in text, text)

        reopened: list[bool] = []
        sim.app.configure_patient_folder_naming_dialog = (
            lambda: reopened.append(True) or False
        )
        check(
            sim.app._ensure_patient_folder_naming_configured(force=True),
            "сохранённое правило папки не принято",
        )
        check(not reopened, "сохранённое правило имени папки было запрошено повторно")
        check(not sim.errors, sim.errors)
        print("REAL USER JOURNEY DIALOGS OK")
    finally:
        sim.close()


if __name__ == "__main__":
    main()
