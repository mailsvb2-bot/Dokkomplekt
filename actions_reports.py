from __future__ import annotations

import os
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Sequence


from diagnostic_logging import record_soft_exception
from medical_formatting import redact_technical_text, technical_ref


class ActionsReportsMixin:
    def _diagnostic_reports_enabled(self) -> bool:
        """Писать служебные TXT-отчёты только в явном debug-режиме.

        По умолчанию папка результата должна содержать только документы,
        которые пользователь выбрал в UI. Для диагностики можно запустить
        программу с переменной окружения MEDICAL_AUTOFILL_WRITE_REPORTS=1.
        """
        value = os.environ.get("MEDICAL_AUTOFILL_WRITE_REPORTS", "").strip().lower()
        return value in {"1", "true", "yes", "y", "да", "on"}

    def _write_creation_report(
        self,
        *,
        selected_medical: List[str],
        selected_diaries: bool,
        created_medical: List[Path],
        diary_result=None,
        created_custom: List[Path] | None = None,
        errors: List[str] | None = None,
    ) -> Path | None:
        """Implement the _write_creation_report workflow with validation, UI state updates and diagnostics."""
        if not self._diagnostic_reports_enabled():
            return None
        try:
            out_dir = self._result_output_dir()
            report_dir = history_dir(out_dir)
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "ОТЧЁТ_создание_документов.txt"
            lines: List[str] = []
            lines.append("ОТЧЁТ: создание выбранных документов")
            lines.append(f"Дата запуска: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
            lines.append("")
            created_custom = created_custom or []
            names = self._selected_output_names(selected_medical, selected_diaries)
            lines.append("Выбрано в UI: " + (", ".join(names) if names else "ничего"))
            lines.append(f"Медицинских документов выбрано: {len(selected_medical)}")
            lines.append(f"Дневники выбраны: {'да' if selected_diaries else 'нет'}")
            review = getattr(self, "_last_patient_case_review", None)
            if review is not None:
                lines.append("")
                lines.append("Карточка пациента перед созданием: обезличена")
                lines.append("Технический идентификатор: " + technical_ref(review.value("output_fio"), review.value("case_number"), review.value("admission_date")))
                lines.append(f"Предупреждений проверки: {len(review.warnings)}")
            lines.append("")
            lines.append(f"Медицинских документов создано: {len(created_medical)}")
            lines.append(f"Custom-документов профиля создано: {len(created_custom)}")
            if diary_result is not None:
                lines.append("")
                lines.append(f"Дневниковых файлов создано: {len(list(diary_result.created_files))}")
            if errors:
                lines.append("")
                lines.append("Ошибки:")
                lines.extend(f"- {redact_technical_text(item)}" for item in errors)
            report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._log(f"Отчёт создания: {report_path}\n")
            return report_path
        except Exception as exc:
            record_soft_exception("actions_reports.write_creation_report", exc)
            self._log(f"\n⚠️ Не удалось записать отчёт создания документов: {exc}\n")
            return None


# --- Persistent generation ledger ---
_HISTORY_CSV = "generation_log.csv"
_HISTORY_JSONL = "generation_log.jsonl"

from medical_formatting import history_dir as _privacy_history_dir, technical_history_root, technical_report_path


def _technical_history_root() -> Path:
    return technical_history_root()


def history_dir(base_dir: str | Path) -> Path:
    return _privacy_history_dir(base_dir)


def _safe_ledger_text(value: str, *, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text



def append_generation_history(
    *,
    output_dir: str | Path,
    review: PatientCaseReview | None,
    selected_outputs: Sequence[str],
    created_files: Sequence[Path],
    errors: Sequence[str] | None = None,
) -> Path | None:
    """Append a privacy-safe technical ledger outside output folders.

    The ledger stores only metadata needed for support: a pseudonymous patient
    reference, selected output labels and counts. Raw FIO, case numbers, dates,
    diagnoses, paths and generated file names are intentionally not copied.
    """
    try:
        folder = history_dir(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        errors = list(errors or [])
        now = datetime.now().isoformat(timespec="seconds")
        patient_ref = ""
        if review is not None:
            patient_ref = technical_ref(review.value("output_fio"), review.value("case_number"), review.value("admission_date"))
        row = {
            "created_at": now,
            "patient_ref": patient_ref,
            "selected_outputs": "; ".join(_safe_ledger_text(item, limit=80) for item in selected_outputs),
            "created_file_count": str(len(created_files)),
            "error_count": str(len(errors)),
            "errors_redacted": "; ".join(redact_technical_text(item, limit=120) for item in errors),
            "warning_count": str(len(review.warnings) if review else 0),
        }
        csv_path = folder / _HISTORY_CSV
        write_header = not csv_path.exists()
        with csv_path.open("a", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(row.keys()), delimiter=";")
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        jsonl_path = folder / _HISTORY_JSONL
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return csv_path
    except Exception as exc:
        record_soft_exception("generation_history.append", exc, detail=str(output_dir))
        return None

