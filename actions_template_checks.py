from __future__ import annotations

from diagnostic_logging import record_soft_exception


class ActionsTemplateChecksMixin:
    def _check_templates(self) -> None:
        """Startup template check for the doctor-owned mode.

        The product no longer ships user-facing medical DOCX templates.  The
        only valid setup is: doctor loads their own templates into the active
        medpack profile, and block 03 shows those profile buttons.
        """

        def apply_result() -> None:
            try:
                self._log("\nℹ Встроенных медицинских шаблонов нет: добавьте свои DOCX через блок 03.\n")
            except Exception as exc:
                record_soft_exception("actions_template_checks.doctor_owned", exc)

        try:
            self.root.after(0, apply_result)
        except Exception as exc:
            record_soft_exception("actions_template_checks.after", exc)
