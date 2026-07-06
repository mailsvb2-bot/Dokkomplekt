from __future__ import annotations

from pathlib import Path
from typing import List


class ActionsDocumentIntelligenceFlowMixin:
    def _missing_custom_completion_inputs(self, current_pack, case, selected_custom_ids: List[str]):
        missing: list[str] = []
        inferred_missing = []
        selected = {str(item).strip() for item in selected_custom_ids if str(item).strip()}
        try:
            base_dir = self._universal_profile_path().parent
        except Exception as exc:
            from diagnostic_logging import record_soft_exception

            record_soft_exception("actions_document_intelligence.profile_base", exc)
            base_dir = None
        for document in current_pack.documents:
            if selected and document.id not in selected:
                continue
            from universal_template_engine import missing_required_fields
            from universal_document_principles import missing_fields_from_principles

            missing.extend(missing_required_fields(case, document))
            inferred_missing.extend(missing_fields_from_principles(case, document, base_dir=base_dir))
        from regulatory_completion_blocks import completion_inputs_for_missing_fields
        from universal_document_principles import completion_inputs_from_inferred_fields

        inputs = list(
            completion_inputs_for_missing_fields(
                tuple(dict.fromkeys(missing)),
                registry=current_pack.registry(),
                existing_case=case,
                reason_prefix="Не заполнено обязательное поле",
            )
        )
        inputs.extend(
            completion_inputs_from_inferred_fields(
                tuple(inferred_missing),
                existing_case=case,
                reason_prefix="Шаблон документа требует поле",
            )
        )
        dedup = {}
        for item in inputs:
            dedup.setdefault(item.field_id, item)
        return tuple(dedup.values())

    def _create_regular_custom_documents(self, current_pack, case, regular_ids: List[str], out_dir) -> List[Path]:
        created = super()._create_regular_custom_documents(current_pack, case, regular_ids, out_dir)
        if not created:
            return created
        try:
            from document_intelligence.form_fill import fill_docx_visible_fields

            values = {field_id: value.value for field_id, value in case.values.items()}
            for path in created:
                fill_docx_visible_fields(path, values)
        except Exception as exc:
            from diagnostic_logging import record_soft_exception

            record_soft_exception("actions_document_intelligence.post_render_fill", exc)
        return created
